"""Platform API quota reservation ledger (Q1, 2026-10-28 plan).

YouTube Data API quota is a daily allotment per Google Cloud project that
resets at midnight Pacific time, and invalid or retried requests still
consume it. Uploading until a 403 `quotaExceeded` wastes the remaining
units of a half-finished package (video uploaded, thumbnail/captions not),
so the publishing worker reserves the WHOLE package's predicted units here
before its first request:

  POST /quota/reserve           atomic check-and-reserve (advisory lock)
  POST /quota/{id}/settle       consumed (a request may have been sent) or
                                released (provably nothing was sent)
  GET  /quota                   today's use per provider/bucket/account

Limits come from env and should be copied from the project's quota page in
the Google Cloud console; the defaults are the long-documented conservative
values so the system never plans past the real allotment. A denied
reservation tells the caller when the day resets.
"""

from __future__ import annotations

import os
import uuid
import zlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db

router = APIRouter(tags=["quota"])

def _pacific() -> ZoneInfo:
    # Loaded on use: a host without tz data fails this endpoint loudly
    # instead of breaking API start-up (tzdata is pinned in requirements).
    return ZoneInfo("America/Los_Angeles")

#: provider → bucket → (env var, default daily limit). 0 disables a bucket.
LIMITS: dict[str, dict[str, tuple[str, int]]] = {
    "youtube": {
        "units": ("YOUTUBE_QUOTA_UNITS_PER_DAY", 10_000),
        "uploads": ("YOUTUBE_QUOTA_UPLOADS_PER_DAY", 0),
    },
}


def quota_day(now: datetime, provider: str = "youtube") -> date:
    """The provider's quota day (YouTube resets at midnight Pacific)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_pacific()).date()


def resets_at(day: date) -> datetime:
    """UTC instant the given Pacific quota day ends (DST-correct)."""
    nxt = datetime.combine(day + timedelta(days=1), time(0), tzinfo=_pacific())
    return nxt.astimezone(timezone.utc)


def daily_limit(provider: str, bucket: str) -> Optional[int]:
    """Configured limit; None for an unknown provider/bucket."""
    spec = LIMITS.get(provider, {}).get(bucket)
    if spec is None:
        return None
    env, default = spec
    try:
        return max(0, int(os.environ.get(env, default)))
    except ValueError:
        return default


def decide(used: int, requested: int, limit: int) -> tuple[bool, int]:
    """(allowed, remaining after this request). A limit of 0 = unmetered."""
    if limit == 0:
        return True, 0
    remaining = limit - used
    if requested > remaining:
        return False, max(0, remaining)
    return True, remaining - requested


def _lock_key(provider: str, bucket: str, account: str, day: date) -> int:
    raw = f"quota:{provider}:{bucket}:{account}:{day.isoformat()}".encode()
    return zlib.crc32(raw) - (1 << 31)  # signed int4 range for pg_advisory


class ReserveIn(BaseModel):
    provider: str = Field(pattern="^[a-z]{2,20}$")
    account: str = Field(default="default", min_length=1, max_length=120)
    # One reservation may span buckets (e.g. units + one upload slot).
    buckets: dict[str, int] = Field(min_length=1)
    operation: Optional[str] = Field(default=None, max_length=80)
    ref_type: Optional[str] = Field(default=None, max_length=40)
    ref_id: Optional[str] = Field(default=None, max_length=120)


class SettleIn(BaseModel):
    status: str = Field(pattern="^(consumed|released)$")


@router.post("/quota/reserve")
async def reserve(body: ReserveIn) -> dict:
    now = datetime.now(timezone.utc)
    day = quota_day(now, body.provider)
    for bucket, units in body.buckets.items():
        if daily_limit(body.provider, bucket) is None:
            raise HTTPException(status_code=422,
                                detail=f"unknown quota bucket {body.provider}/{bucket}")
        if units < 0 or units > 1_000_000:
            raise HTTPException(status_code=422, detail="units out of range")
    pool = db.get()
    group = str(uuid.uuid4())
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock buckets in a stable order so two reservations never deadlock.
            for bucket in sorted(body.buckets):
                await conn.execute("SELECT pg_advisory_xact_lock($1)",
                                   _lock_key(body.provider, bucket, body.account, day))
            report: dict[str, dict] = {}
            for bucket in sorted(body.buckets):
                used = int(await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(units), 0) FROM quota_ledger
                    WHERE provider = $1 AND bucket = $2 AND account = $3
                      AND quota_day = $4 AND status <> 'released'
                    """,
                    body.provider, bucket, body.account, day) or 0)
                limit = daily_limit(body.provider, bucket) or 0
                ok, remaining = decide(used, body.buckets[bucket], limit)
                report[bucket] = {"used": used, "limit": limit,
                                  "requested": body.buckets[bucket],
                                  "remaining": remaining, "allowed": ok}
            allowed = all(r["allowed"] for r in report.values())
            if allowed:
                for bucket in sorted(body.buckets):
                    await conn.execute(
                        """
                        INSERT INTO quota_ledger (id, provider, bucket, account, quota_day,
                                                  units, operation, ref_type, ref_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        uuid.uuid5(uuid.UUID(group), bucket), body.provider, bucket,
                        body.account, day, body.buckets[bucket], body.operation,
                        body.ref_type, body.ref_id)
    reset = resets_at(day)
    return {
        "allowed": allowed,
        "reservation_id": group if allowed else None,
        "quota_day": day.isoformat(),
        "resets_at": reset.isoformat(),
        "retry_after_s": None if allowed else max(1, int((reset - now).total_seconds())),
        "buckets": report,
    }


@router.post("/quota/{reservation_id}/settle")
async def settle(reservation_id: uuid.UUID, body: SettleIn) -> dict:
    """Settle every bucket row of one reservation. Idempotent; a consumed
    reservation is never released afterwards (units spent stay spent)."""
    pool = db.get()
    ids = [uuid.uuid5(reservation_id, bucket)
           for provider in LIMITS.values() for bucket in provider]
    result = await pool.execute(
        """
        UPDATE quota_ledger SET status = $2, settled_at = now()
        WHERE id = ANY($1::uuid[]) AND status = 'reserved'
        """,
        ids, body.status,
    )
    updated = int(result.split()[-1]) if result else 0
    if updated == 0:
        exists = await pool.fetchval(
            "SELECT 1 FROM quota_ledger WHERE id = ANY($1::uuid[])", ids)
        if not exists:
            raise HTTPException(status_code=404, detail="reservation not found")
    return {"reservation_id": str(reservation_id), "settled": updated, "status": body.status}


@router.get("/quota")
async def usage(provider: str = "youtube") -> dict:
    now = datetime.now(timezone.utc)
    day = quota_day(now, provider)
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT bucket, account,
               COALESCE(SUM(units) FILTER (WHERE status = 'consumed'), 0)::bigint AS consumed,
               COALESCE(SUM(units) FILTER (WHERE status = 'reserved'), 0)::bigint AS reserved
        FROM quota_ledger
        WHERE provider = $1 AND quota_day = $2
        GROUP BY bucket, account ORDER BY account, bucket
        """,
        provider, day,
    )
    return {
        "provider": provider,
        "quota_day": day.isoformat(),
        "resets_at": resets_at(day).isoformat(),
        "limits": {bucket: daily_limit(provider, bucket)
                   for bucket in LIMITS.get(provider, {})},
        "accounts": [dict(r) for r in rows],
    }
