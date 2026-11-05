"""PhishProbe orchestrator API.

All routes are mounted under /api (Caddy preserves the prefix in production;
the Next.js frontend calls the same paths in dev). This process holds the
Vultr Inference key and launches/destroys sandbox containers — the sandbox
never sees a secret.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

import db
from agent import llm
from agent.loop import request_approval, run_pipeline
from quickcheck.heuristics import quick_check
from report.builder import build_report_html
from sandbox import manager

app = FastAPI(title="PhishProbe API", version="1.0")

# In dev the Next.js origin differs; in prod everything is same-origin via Caddy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    db.init()


# --- models -----------------------------------------------------------------

class ScanRequest(BaseModel):
    url: str = Field(min_length=3, max_length=2048)
    deep: bool = True


class ApprovalRequest(BaseModel):
    approved: bool


# --- health / capabilities --------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "llm_configured": llm.is_configured(),
        "sandbox_available": manager.available(),
    }


# --- quick check (stage 1, also used by the extension) ----------------------

@app.get("/api/quick")
async def api_quick(url: str) -> dict:
    return quick_check(url)


# --- scans ------------------------------------------------------------------

@app.post("/api/scans")
async def create_scan(req: ScanRequest) -> dict:
    url = req.url.strip()
    quick = quick_check(url)

    # Serve a cached verdict for an identical recent URL.
    ttl = float(os.getenv("CACHE_TTL_HOURS", "6"))
    cached = db.find_cached_verdict(url, ttl)
    if cached:
        return {
            "scan_id": cached["id"],
            "quick_result": quick,
            "cached": True,
            "verdict": cached["verdict"],
        }

    scan_id = uuid.uuid4().hex[:16]
    db.create_scan(scan_id, url, quick.get("registered_domain", ""), req.deep, quick)

    if req.deep:
        # Fire-and-forget; progress streams over /events.
        asyncio.create_task(run_pipeline(scan_id, url, quick, req.deep))

    return {"scan_id": scan_id, "quick_result": quick, "cached": False}


@app.get("/api/scans/{scan_id}")
async def get_scan(scan_id: str) -> dict:
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "scan not found")
    return scan


@app.get("/api/scans/{scan_id}/events")
async def scan_events(scan_id: str, request: Request) -> StreamingResponse:
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "scan not found")
    queue = db.event_queue(scan_id)

    async def gen():
        # Replay current state so a late subscriber isn't stuck on a blank page.
        yield _sse("status", {"status": scan["status"]})
        if scan["status"] == "done" and scan.get("verdict"):
            yield _sse("verdict", scan["verdict"])
            yield _sse("done", {"scan_id": scan_id})
            return
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # comment frame keeps the connection open
                continue
            yield _sse(event["type"], event["payload"])
            if event["type"] == "done":
                break

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/scans/{scan_id}/approve")
async def approve(scan_id: str, req: ApprovalRequest) -> dict:
    ok = request_approval(scan_id, req.approved)
    if not ok:
        raise HTTPException(409, "no approval pending for this scan")
    return {"ok": True, "approved": req.approved}


@app.post("/api/scans/{scan_id}/cancel")
async def cancel(scan_id: str) -> dict:
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "scan not found")
    # Releases any pending approval; the sandbox has its own hard timeout.
    request_approval(scan_id, False)
    db.update_scan(scan_id, status="cancelled")
    await db.emit(scan_id, "done", {"scan_id": scan_id})
    return {"ok": True}


@app.get("/api/scans/{scan_id}/screenshot/{which}")
async def screenshot(scan_id: str, which: str):
    if which not in ("desktop", "mobile"):
        raise HTTPException(404, "unknown screenshot")
    path = db.screenshot_path(scan_id, which)
    if not path:
        raise HTTPException(404, "screenshot not available")
    return FileResponse(path, media_type="image/png")


@app.get("/api/scans/{scan_id}/report.html", response_class=HTMLResponse)
async def report_html(scan_id: str) -> HTMLResponse:
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(404, "scan not found")
    return HTMLResponse(build_report_html(scan))


def _sse(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
