"""Cost API (v0.37 — enhancement plan 2026-10-24, WP-F).

The one surface for the money ledger and the shared cache:

  POST /costs/usage           workers emit metered spend (batched, fail-open)
  POST /costs/check           the fail-closed budget gate, asked BEFORE spending
  POST /costs/cache-lookup    workers read the shared cache (extract/tts/…)
  POST /costs/cache-store     workers fill the shared cache
  GET  /costs/summary         Settings → Costs card (totals, per-stage split,
                              cache-hit rate, blocked spend, cost per video)
  GET  /costs/budget          today's spend vs the guardrail budgets
  GET  /costs/providers       capability probe (Ollama model list, TTS shim)

Design mirrors the rest of the system: the ledger is deterministic and
cite-able (every estimate's pricing formula is documented env), the cache
fails open, and the ONLY fail-closed path is an explicitly exhausted budget —
which records a zero-unit `blocked` event so the operator always sees why a
stage degraded.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

import db
from costs_store import (
    budget_state,
    cache_get,
    cache_put,
    check_budget,
    probe_providers,
    record_events,
    spend_summary,
)

router = APIRouter(prefix="/costs", tags=["costs"])


class UsageEventIn(BaseModel):
    kind: str
    provider: str = ""
    model: str = ""
    units: int = 0
    unit_type: Optional[str] = None
    cost_usd_est: Optional[float] = Field(default=None, ge=0)
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class UsageIn(BaseModel):
    events: list[UsageEventIn] = Field(min_length=1, max_length=500)


@router.post("/usage")
async def post_usage(body: UsageIn) -> dict:
    """Append metered spend. Unknown kinds/malformed rows are dropped, never
    fatal — an emitter must never break the stage that fed it."""
    pool = db.get()
    return await record_events(pool, [e.model_dump(exclude_none=True)
                                      for e in body.events])


class BudgetCheckIn(BaseModel):
    kind: str
    units: int = Field(default=0, ge=0)
    est_cost: Optional[float] = Field(default=None, ge=0)
    provider: str = ""
    model: str = ""
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


@router.post("/check")
async def post_check(body: BudgetCheckIn) -> dict:
    """May this stage spend right now? Asked BEFORE the spend; a denial is
    recorded (zero units, meta.blocked) and the caller degrades."""
    pool = db.get()
    return await check_budget(
        pool, body.kind, units=body.units, est_cost=body.est_cost,
        provider=body.provider, model=body.model,
        ref_type=body.ref_type,
        ref_id=body.ref_id, meta=body.meta,
    )


class CacheLookupIn(BaseModel):
    key: str = Field(min_length=3, max_length=300)


@router.post("/cache-lookup")
async def post_cache_lookup(body: CacheLookupIn) -> dict:
    """Shared-cache read for workers (memory → Redis → Postgres inside the
    API process). Fail-open: never a 5xx, only {hit: false}."""
    pool = db.get()
    value = await cache_get(pool, body.key)
    return {"hit": value is not None, "value": value}


class CacheStoreIn(BaseModel):
    key: str = Field(min_length=3, max_length=300)
    value: Any
    ttl_s: int = Field(default=86400, ge=1, le=30 * 86400)


@router.post("/cache-store")
async def post_cache_store(body: CacheStoreIn) -> dict:
    pool = db.get()
    await cache_put(pool, body.key, body.value, body.ttl_s)
    return {"stored": True}


@router.get("/summary")
async def get_summary() -> dict:
    return await spend_summary(db.get())


@router.get("/budget")
async def get_budget() -> dict:
    return await budget_state(db.get())


@router.get("/providers")
async def get_providers() -> dict:
    """Probe the configured providers (cached 60 s)."""
    pool = db.get()
    cached = await cache_get(pool, "providers:probe")
    if cached is not None:
        return {**cached, "cached": True}
    out = await probe_providers()
    await cache_put(pool, "providers:probe", out, 60)
    return {**out, "cached": False}


__all__ = ["router"]
