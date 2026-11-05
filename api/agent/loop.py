"""The orchestrator's scan pipeline: observe (sandbox) -> analyse (vision +
text LLM) -> optional human-approved deep check -> verdict. It emits live SSE
events at every step and persists the final result. The LLM lives here, never
in the sandbox.
"""

from __future__ import annotations

import asyncio
import os

import db  # top-level module at /app/db.py
from . import verdict as verdict_engine
from .actions import Verdict

# scan_id -> (event, result-holder) for human approval of the deep check.
_approvals: dict[str, asyncio.Event] = {}
_approval_result: dict[str, bool] = {}

APPROVAL_TIMEOUT = 120  # seconds the user has to decide


def request_approval(scan_id: str, approved: bool) -> bool:
    ev = _approvals.get(scan_id)
    if ev is None:
        return False
    _approval_result[scan_id] = approved
    ev.set()
    return True


async def run_pipeline(scan_id: str, url: str, quick: dict, deep: bool) -> None:
    """Run the full scan. Imports the sandbox manager lazily so the quick-check
    path works even where Docker is absent."""
    from sandbox.manager import run_action, SandboxUnavailable  # top-level pkg

    try:
        await db.emit(scan_id, "status", {"status": "scanning", "message": "Starte Wegwerf-Sandbox …"})
        db.update_scan(scan_id, status="scanning")

        try:
            scan = await run_action(url, action="scan")
        except SandboxUnavailable as exc:
            await db.emit(scan_id, "status", {"status": "scanning", "message": f"Sandbox nicht verfügbar: {exc}. Nutze Schnell-Check."})
            scan = _scan_stub()

        # Stream what the sandbox observed.
        await db.emit(scan_id, "redirects", {"redirects": scan.get("redirects", [])})
        await db.emit(scan_id, "network", {
            "requested_domains": scan.get("requested_domains", []),
            "downloads_blocked": scan.get("downloads_blocked", []),
        })
        for ev in scan.get("containment_events", []) or []:
            await db.emit(scan_id, "containment", ev)

        # Persist screenshots to disk, announce their URLs.
        scan = db.save_screenshots(scan_id, scan)
        await db.emit(scan_id, "screenshots", {
            "desktop": scan.get("screenshot_desktop_path"),
            "mobile": scan.get("screenshot_mobile_path"),
        })

        # Vision analysis.
        await db.emit(scan_id, "status", {"status": "analyzing", "message": "KI analysiert Screenshot und Seite …"})
        vision = await verdict_engine.run_vision(scan)
        if vision:
            await db.emit(scan_id, "vision", vision.model_dump())

        # Final verdict.
        final, used_llm = await verdict_engine.decide(quick, scan, vision)
        await db.emit(scan_id, "signals", {"signals": [s.model_dump() for s in final.signals]})

        # Optional human-approved deep check (fake test-data submission).
        dom = scan.get("dom_summary", {}) or {}
        sensitive_form = dom.get("password_field_count", 0) > 0 or dom.get("has_card_field")
        if deep and sensitive_form and scan.get("ok"):
            final = await _maybe_deep_check(scan_id, url, final)

        db.update_scan(scan_id, status="done", verdict=final.model_dump(), scan_data=scan)
        await db.emit(scan_id, "verdict", {**final.model_dump(), "used_llm": used_llm})
        await db.emit(scan_id, "done", {"scan_id": scan_id})
    except Exception as exc:  # pragma: no cover - never leave a scan hanging
        db.update_scan(scan_id, status="error")
        await db.emit(scan_id, "error", {"message": str(exc)[:300]})
        await db.emit(scan_id, "done", {"scan_id": scan_id})
    finally:
        _approvals.pop(scan_id, None)
        _approval_result.pop(scan_id, None)


async def _maybe_deep_check(scan_id: str, url: str, final: Verdict) -> Verdict:
    """Ask the human before submitting clearly-fake test data to the form."""
    from sandbox.manager import run_action, SandboxUnavailable

    ev = asyncio.Event()
    _approvals[scan_id] = ev
    db.update_scan(scan_id, status="awaiting_approval")
    await db.emit(scan_id, "approval_request", {
        "message": "Darf PhishProbe klar erkennbare Fake-Testdaten in das Formular eintippen und absenden, um zu sehen, wohin die Daten gehen?",
    })
    try:
        await asyncio.wait_for(ev.wait(), timeout=APPROVAL_TIMEOUT)
    except asyncio.TimeoutError:
        await db.emit(scan_id, "approval_result", {"approved": False, "message": "Keine Antwort – übersprungen."})
        return final

    if not _approval_result.get(scan_id):
        await db.emit(scan_id, "approval_result", {"approved": False, "message": "Vom Nutzer abgelehnt."})
        return final

    await db.emit(scan_id, "approval_result", {"approved": True, "message": "Freigegeben – sende Fake-Testdaten."})
    try:
        deep = await run_action(url, action="submit_fake")
    except SandboxUnavailable:
        return final

    targets = deep.get("post_targets", [])
    if targets:
        from urllib.parse import urlparse
        page_host = urlparse(url).hostname or ""
        external = [t for t in targets if (urlparse(t).hostname or "") != page_host]
        detail = f"Formular sendet Daten an: {', '.join(targets[:4])}"
        from .actions import Signal
        final.signals.append(Signal(type="data_exfiltration", detail=detail[:400],
                                    severity="high" if external else "medium"))
        if external:
            final.verdict = "phishing"
            final.risk_score = max(final.risk_score, 85)
            final.explanation_de = ("Die Testdaten wurden an eine fremde Domain geschickt. " + final.explanation_de).strip()
    await db.emit(scan_id, "deep_result", {"post_targets": targets})
    return final


def _scan_stub() -> dict:
    return {
        "ok": False, "final_url": None, "redirects": [], "dom_summary": {},
        "network_log": [], "requested_domains": [], "downloads_blocked": [],
        "console_errors": [], "containment_events": [],
        "screenshot_desktop_b64": None, "screenshot_mobile_b64": None,
    }
