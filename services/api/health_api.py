"""Health router (v0.20) — liveness + readiness for deploy probes.

A probe that only answers "the process is up" is not enough: a reachable
database with a missing migration looks healthy until the first query fails.
The probe therefore reports the database state AND the applied/total
migration counts, so a rollout can gate on schema readiness.
"""

from fastapi import APIRouter, HTTPException

import db
from db_migrate import migration_files

router = APIRouter(tags=["health"])

# stamped by services/api/main.py once the app knows its version
APP_VERSION = "0.0.0"


@router.get("/health")
async def health() -> dict:
    """Liveness + DB connectivity + migration readiness."""
    pool = db.get()
    try:
        await pool.fetchval("SELECT 1")
    except Exception:
        # /health is reachable without credentials — never echo DB error text.
        raise HTTPException(status_code=503, detail="database unavailable") from None

    applied = total = None
    try:
        applied = await pool.fetchval("SELECT COUNT(*) FROM schema_migrations")
        total = len(migration_files())
    except Exception:  # noqa: BLE001 — pre-migration schema: still healthy
        applied = None

    return {
        "status": "ok",
        "service": "api",
        "version": APP_VERSION,
        "database": "ok",
        "migrations_applied": applied,
        "migrations_total": total,
    }
