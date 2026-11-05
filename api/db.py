"""Persistence: SQLite for scan records + URL cache, filesystem for screenshots,
and in-memory asyncio queues for live SSE events. Kept deliberately small.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "phishprobe.sqlite"

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None

# scan_id -> asyncio.Queue for live events (process-local; fine for one api node)
_event_queues: dict[str, asyncio.Queue] = {}


def init() -> None:
    global _conn
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "scans").mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                registered_domain TEXT,
                status TEXT NOT NULL,          -- queued|quick_done|scanning|awaiting_approval|done|error|cancelled
                deep INTEGER NOT NULL DEFAULT 0,
                quick_result TEXT,             -- json
                verdict TEXT,                  -- json (final)
                scan_data TEXT,                -- json (sandbox observations, screenshots stripped)
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        _conn.commit()


def _now() -> float:
    return time.time()


def create_scan(scan_id: str, url: str, registered_domain: str, deep: bool, quick_result: dict) -> None:
    with _lock:
        _conn.execute(
            "INSERT INTO scans (id, url, registered_domain, status, deep, quick_result, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (scan_id, url, registered_domain, "quick_done", int(deep),
             json.dumps(quick_result), _now(), _now()),
        )
        _conn.commit()


def update_scan(scan_id: str, **fields) -> None:
    if not fields:
        return
    for key in ("quick_result", "verdict", "scan_data"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _conn.execute(f"UPDATE scans SET {cols} WHERE id=?", (*fields.values(), scan_id))
        _conn.commit()


def get_scan(scan_id: str) -> Optional[dict]:
    with _lock:
        row = _conn.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("quick_result", "verdict", "scan_data"):
        d[key] = json.loads(d[key]) if d[key] else None
    d["deep"] = bool(d["deep"])
    return d


def find_cached_verdict(url: str, ttl_hours: float) -> Optional[dict]:
    """Most recent completed scan of the same URL within the TTL window."""
    if ttl_hours <= 0:
        return None
    cutoff = _now() - ttl_hours * 3600
    with _lock:
        row = _conn.execute(
            "SELECT * FROM scans WHERE url=? AND status='done' AND updated_at>=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (url, cutoff),
        ).fetchone()
    if not row:
        return None
    return get_scan(row["id"])


# --- screenshots on disk ----------------------------------------------------

def save_screenshots(scan_id: str, scan_data: dict) -> dict:
    """Write base64 screenshots to disk, replace them in scan_data with paths."""
    scan_dir = DATA_DIR / "scans" / scan_id
    scan_dir.mkdir(parents=True, exist_ok=True)
    out = dict(scan_data)
    for key, fname in (("screenshot_desktop_b64", "desktop.png"), ("screenshot_mobile_b64", "mobile.png")):
        b64 = scan_data.get(key)
        if b64:
            try:
                (scan_dir / fname).write_bytes(base64.b64decode(b64))
                out[key.replace("_b64", "_path")] = f"/api/scans/{scan_id}/screenshot/{fname.split('.')[0]}"
            except (ValueError, OSError):
                pass
        out.pop(key, None)  # don't keep heavy base64 in the DB row
    return out


def screenshot_path(scan_id: str, which: str) -> Optional[Path]:
    fname = "desktop.png" if which == "desktop" else "mobile.png"
    p = DATA_DIR / "scans" / scan_id / fname
    return p if p.exists() else None


# --- live events (SSE) ------------------------------------------------------

def event_queue(scan_id: str) -> asyncio.Queue:
    q = _event_queues.get(scan_id)
    if q is None:
        q = asyncio.Queue()
        _event_queues[scan_id] = q
    return q


async def emit(scan_id: str, event_type: str, payload: dict) -> None:
    await event_queue(scan_id).put({"type": event_type, "payload": payload, "ts": _now()})


def drop_queue(scan_id: str) -> None:
    _event_queues.pop(scan_id, None)
