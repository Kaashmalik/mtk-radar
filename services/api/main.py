"""MTK RADAR AI — API service (FastAPI).

Single source of truth backend for offers, evidence, projects, and schedules.
Workers and the extension communicate with this API only.

Run locally:
    uvicorn main:app --reload --port 8000
"""

import os

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://mtk:mtk@localhost:5432/mtk_radar"
)

app = FastAPI(title="MTK RADAR AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # dashboard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pool: asyncpg.Pool | None = None


@app.on_event("startup")
async def startup() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _pool:
        await _pool.close()


@app.get("/health")
async def health() -> dict:
    """Liveness + DB connectivity probe."""
    if _pool is None:
        raise HTTPException(status_code=503, detail="db pool not ready")
    try:
        await _pool.fetchval("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"db unavailable: {exc}") from exc
    return {"status": "ok", "service": "api", "version": app.version}


# TODO(week-2): POST /items — extension save-current-page ingest with dedup key.
# TODO(week-3): POST /offers/{id}/evidence — immutable evidence snapshots.
# TODO(week-3): POST /offers/{id}/transition — offer state machine gatekeeping.
# TODO(week-9): POST /schedules — schedule creation requires approved version hash.
