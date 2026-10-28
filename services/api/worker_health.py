"""Worker heartbeats and liveness (v0.30).

The API is the source of truth for which workers are expected. Each worker
posts ``POST /workers/heartbeat`` on a cadence; the dashboard and monitor read
``GET /workers``. A stale or missing heartbeat is an alert, not a quiet
success — the exact failure mode that a laptop deployment hides best.

Heartbeats are best-effort and deliberately un-audited. Writing an audit row
every minute would bury the operator's approval trail; start/stop and policy
changes remain audited in the automation router.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db

router = APIRouter(prefix="/workers", tags=["workers"])

#: Long-running worker services. The capture session is intentionally absent:
#: it is a human-operated browser, not a daemon that must stay online.
EXPECTED_WORKERS: dict[str, dict[str, Any]] = {
    "collectors": {"label": "Collectors", "interval_s": 60},
    "verification": {"label": "Verification", "interval_s": 120},
    "batch": {"label": "Batch / scheduler", "interval_s": 900},
    "render": {"label": "Render / QC", "interval_s": 900},
    "publishing": {"label": "Publishing", "interval_s": 60},
    "monitor": {"label": "Monitor / alerts", "interval_s": 300},
    "metrics": {"label": "Metrics", "interval_s": 3600},
    # Storyboard source-page screenshots (workers/capture/page_capture.py).
    "page-capture": {"label": "Page capture", "interval_s": 60},
}

_WORKER_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_STATUSES = {"starting", "ok", "degraded", "stopped", "error"}


class HeartbeatIn(BaseModel):
    worker: str = Field(min_length=2, max_length=64)
    status: str = "ok"
    detail: Optional[str] = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    interval_s: int = Field(default=60, ge=5, le=86400)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _as_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def stale_after_s(worker: str, interval_s: Any) -> int:
    """Allow one missed beat plus startup/render slack.

    Render jobs can legitimately run for several minutes, so the threshold is
    intentionally generous. A dead worker still becomes visible within roughly
    two intervals, well before a publishing window is silently missed.
    """
    try:
        interval = int(interval_s)
    except (TypeError, ValueError):
        interval = int(EXPECTED_WORKERS.get(worker, {}).get("interval_s", 60))
    interval = max(5, min(interval, 86400))
    return max(120, int(interval * 2.5))


def _worker_state(status: str, age_s: Optional[float], stale_after: int) -> str:
    if status == "stopped":
        return "stopped"
    if status == "error":
        return "error"
    if status == "degraded":
        return "degraded"
    if age_s is None:
        return "missing"
    if age_s > stale_after:
        return "stale"
    if status == "starting":
        return "starting"
    return "online"


def _worker_payload(name: str, row: Optional[dict], now: datetime) -> dict[str, Any]:
    expected = EXPECTED_WORKERS.get(name, {})
    interval = (row or {}).get("interval_s") or expected.get("interval_s", 60)
    threshold = stale_after_s(name, interval)
    last_seen = _as_aware((row or {}).get("last_seen_at"))
    age = (now - last_seen).total_seconds() if last_seen else None
    status = (row or {}).get("status") or "missing"
    state = _worker_state(status, age, threshold)
    return {
        "name": name,
        "label": expected.get("label") or name.replace("_", " ").title(),
        "expected": name in EXPECTED_WORKERS,
        "status": status,
        "state": state,
        "online": state in ("online", "starting"),
        "last_seen_at": _iso((row or {}).get("last_seen_at")),
        "started_at": _iso((row or {}).get("started_at")),
        "age_s": round(age, 1) if age is not None else None,
        "interval_s": int(interval),
        "stale_after_s": threshold,
        "detail": (row or {}).get("detail"),
        "metadata": (row or {}).get("metadata") or {},
    }


async def snapshot(pool=None) -> dict[str, Any]:
    pool = pool or db.get()
    rows = await pool.fetch(
        """
        SELECT worker, status, detail, metadata::text AS metadata,
               interval_s, started_at, last_seen_at
        FROM worker_heartbeats
        """
    )
    from jsonb import decode_mapping

    by_name = {row["worker"]: dict(row) for row in rows}
    for row in by_name.values():
        # jsonb reaches Python as serialized text in this project's queries.
        row["metadata"] = decode_mapping(row.get("metadata"))
    names = sorted(set(EXPECTED_WORKERS) | set(by_name))
    now = datetime.now(timezone.utc)
    workers = [_worker_payload(name, by_name.get(name), now) for name in names]
    online = [w for w in workers if w["online"]]
    return {
        "generated_at": now.isoformat(),
        "expected_count": len(EXPECTED_WORKERS),
        "online_count": len(online),
        "all_online": all(w["online"] for w in workers if w["expected"]),
        "workers": workers,
        "stale": [w["name"] for w in workers if w["state"] == "stale"],
        "missing": [w["name"] for w in workers if w["state"] == "missing"],
        "offline": [w["name"] for w in workers if w["state"] in ("stopped", "error")],
    }


def attention_items(snapshot_data: dict[str, Any]) -> list[dict[str, Any]]:
    """One operator-facing item per unhealthy expected worker."""
    items: list[dict[str, Any]] = []
    for worker in snapshot_data.get("workers", []):
        state = worker.get("state")
        if state in ("online", "starting"):
            continue
        if state == "stale":
            title = f"{worker['label']} worker heartbeat is stale"
            detail = (
                f"No heartbeat for {worker.get('age_s')}s "
                f"(threshold {worker.get('stale_after_s')}s)."
            )
            severity = "error"
        elif state == "missing":
            title = f"{worker['label']} worker has never reported"
            detail = "Start the worker stack on the host, then refresh this page."
            severity = "error"
        elif state == "stopped":
            title = f"{worker['label']} worker is stopped"
            detail = worker.get("detail") or "The worker reported a graceful stop."
            severity = "warning"
        elif state == "degraded":
            title = f"{worker['label']} worker is degraded"
            detail = worker.get("detail") or "The worker is running but needs attention."
            severity = "warning"
        else:
            title = f"{worker['label']} worker reported an error"
            detail = worker.get("detail") or "Check the worker log."
            severity = "error"
        items.append({
            "id": f"worker:{worker['name']}",
            "kind": "worker",
            "severity": severity,
            "title": title,
            "detail": detail,
            "href": "/settings",
            "action": "Open settings",
            "entity_id": worker["name"],
            "at": worker.get("last_seen_at"),
        })
    return items


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn) -> dict[str, Any]:
    """Record one worker beat. Best-effort by contract; the worker never
    blocks its sweep on this endpoint."""
    worker = body.worker.strip().lower()
    if not _WORKER_RE.match(worker):
        raise HTTPException(status_code=422, detail="worker name is invalid")
    status = body.status.strip().lower()
    if status not in _STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(_STATUSES))}",
        )
    pool = db.get()
    row = await pool.fetchrow(
        """
        INSERT INTO worker_heartbeats
          (worker, status, detail, metadata, interval_s, started_at, last_seen_at)
        VALUES ($1, $2, $3, $4::jsonb, $5, now(), now())
        ON CONFLICT (worker) DO UPDATE SET
          status = EXCLUDED.status,
          detail = EXCLUDED.detail,
          metadata = EXCLUDED.metadata,
          interval_s = EXCLUDED.interval_s,
          last_seen_at = now(),
          started_at = CASE
            WHEN worker_heartbeats.status = 'stopped'
              OR worker_heartbeats.started_at IS NULL
            THEN now()
            ELSE worker_heartbeats.started_at
          END
        RETURNING worker, status, last_seen_at
        """,
        worker, status, body.detail, json.dumps(body.metadata, default=str),
        body.interval_s,
    )
    return {
        "worker": row["worker"],
        "status": row["status"],
        "last_seen_at": _iso(row["last_seen_at"]),
    }


@router.get("")
async def list_workers() -> dict[str, Any]:
    return await snapshot()


__all__ = [
    "EXPECTED_WORKERS",
    "attention_items",
    "router",
    "snapshot",
    "stale_after_s",
]
