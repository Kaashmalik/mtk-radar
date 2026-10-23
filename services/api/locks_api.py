"""Worker locks (v0.22) — one active sweep per worker role.

Why this exists: a deploy overlap (the old container still draining while
the new one starts) or an operator running a second worker by hand used to
mean two publishers could pick up the SAME due post and upload it twice.
The lock is a row with an expiry: if a worker dies mid-sweep, the lock ages
out and the next sweep takes over — no manual cleanup, no stuck queue.

The lock is advisory for the workers, but the API's own state transitions
stay the real gate (a post can only be published from `scheduled`).
"""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db

router = APIRouter(prefix="/locks", tags=["locks"])

MAX_TTL_S = 3600
DEFAULT_TTL_S = 300


class LockIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    holder: Optional[str] = None
    ttl_s: int = Field(default=DEFAULT_TTL_S, ge=5, le=MAX_TTL_S)


class ReleaseIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    holder: Optional[str] = None


@router.post("/acquire")
async def acquire_lock(body: LockIn) -> dict:
    """Take the lock if it is free or expired. Returns whether we got it."""
    pool = db.get()
    holder = body.holder or f"worker-{uuid.uuid4().hex[:8]}"
    row = await pool.fetchrow(
        """
        INSERT INTO worker_locks (name, holder, acquired_at, expires_at)
        VALUES ($1, $2, now(), now() + ($3 || ' seconds')::interval)
        ON CONFLICT (name) DO UPDATE
           SET holder = EXCLUDED.holder,
               acquired_at = now(),
               expires_at = EXCLUDED.expires_at
         WHERE worker_locks.expires_at < now()
        RETURNING name, holder, expires_at
        """,
        body.name, holder, str(body.ttl_s),
    )
    if row is None:
        current = await pool.fetchrow(
            "SELECT holder, expires_at FROM worker_locks WHERE name = $1", body.name
        )
        return {
            "acquired": False,
            "name": body.name,
            "holder": current["holder"] if current else None,
            "expires_at": current["expires_at"] if current else None,
        }
    return {
        "acquired": True,
        "name": row["name"],
        "holder": row["holder"],
        "expires_at": row["expires_at"],
    }


@router.post("/release")
async def release_lock(body: ReleaseIn) -> dict:
    """Release a lock we hold (best effort — an expired lock needs no release).

    The holder is mandatory: releasing by name alone would let any caller free
    another worker's lock and break sweep exclusivity. Expired locks need no
    release at all — re-acquire replaces them.
    """
    pool = db.get()
    if not body.holder:
        raise HTTPException(
            status_code=422,
            detail="lock release requires the holder that acquired it",
        )
    deleted = await pool.fetchval(
        "DELETE FROM worker_locks WHERE name = $1 AND holder = $2 RETURNING name",
        body.name, body.holder,
    )
    return {"released": bool(deleted), "name": body.name, "holder": body.holder}


@router.get("")
async def list_locks() -> list[dict]:
    """Current locks (operator view: who is holding what)."""
    pool = db.get()
    rows = await pool.fetch(
        "SELECT name, holder, acquired_at, expires_at FROM worker_locks ORDER BY name"
    )
    return [dict(r) for r in rows]
