"""Durable job/outbox API (§8.A) — v0.32.

Orchestration used to be polling + row state only: a restart lost in-flight
intent, and nothing recorded "this work is owed". Schedules now also write a
durable record here when work is created, and anything wedged (expired lease,
dead-lettered after retries) surfaces in /attention.

Claim/lease semantics mirror the upload-attempt pattern that already exists
for schedules:
- `claim` takes the job with `FOR UPDATE SKIP LOCKED` and stamps
  `lease_expires_at` + holder, so exactly one worker holds it;
- `result` records the outcome and increments attempts; a job past its
  `max_attempts` is dead-lettered, never silently retried forever;
- an expired lease is visible in attention but is NEVER auto-reclaimed while
  its outcome is unknown — the holder may have side-effected the world (that
  is a human decision, same duplicate protection as held uploads).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import db
from api_hardening import CREDENTIAL_DISABLED, CREDENTIAL_REVIEWER, credential_class
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)

DEFAULT_RETRY_AFTER_S = 60  # seconds — default failure backoff

router = APIRouter(tags=["jobs"])

DEFAULT_LEASE_S = 900
JOB_KINDS = ("publish_schedule", "render_package", "collect", "recheck", "notify",
             "trend_scan", "script")


class JobIn(BaseModel):
    kind: str
    entity_id: Optional[uuid.UUID] = None
    payload: dict = Field(default_factory=dict)
    run_after: Optional[datetime] = None
    max_attempts: int = Field(default=5, ge=1, le=20)
    # Idempotency: a retry of the enqueue itself returns the existing job.
    dedupe_key: Optional[str] = Field(default=None, max_length=300)


class ClaimIn(BaseModel):
    worker: str = Field(min_length=3, max_length=120)
    lease_s: int = Field(default=DEFAULT_LEASE_S, ge=30, le=86400)
    kinds: list[str] = Field(default_factory=list)


class JobResultIn(BaseModel):
    ok: bool
    detail: Optional[str] = Field(default=None, max_length=2000)
    retry_after_s: Optional[int] = Field(default=None, ge=1, le=86400)


@router.post("/jobs", status_code=201)
async def enqueue(body: JobIn) -> dict:
    if body.kind not in JOB_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown job kind '{body.kind}' — known: {', '.join(JOB_KINDS)}",
        )
    pool = db.get()
    dedupe = body.dedupe_key or f"{body.kind}:{body.entity_id}"
    row = await pool.fetchrow(
        """
        INSERT INTO jobs (kind, entity_id, payload, run_after, max_attempts, dedupe_key)
        VALUES ($1, $2, $3::jsonb, COALESCE($4::timestamptz, now()), $5, $6)
        ON CONFLICT (dedupe_key) DO NOTHING
        RETURNING id, status, created_at
        """,
        body.kind, body.entity_id, json.dumps(body.payload),
        body.run_after, body.max_attempts, dedupe,
    )
    if not row:  # idempotent enqueue
        existing = await pool.fetchrow(
            "SELECT id, status::text AS status, created_at FROM jobs WHERE dedupe_key = $1",
            dedupe,
        )
        return {"id": str(existing["id"]), "status": existing["status"],
                "created": False, "dedupe_key": dedupe}
    return {"id": str(row["id"]), "status": row["status"], "created": True,
            "dedupe_key": dedupe}


@router.get("/jobs")
async def list_jobs(
    response: Response,
    status: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_updated = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT id, kind, entity_id, payload::text AS payload, status,
               run_after, lease_expires_at, lease_holder, attempts, max_attempts,
               last_error, dedupe_key, created_at, updated_at
        FROM jobs
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR kind = $2)
          AND ($3::timestamptz IS NULL
               OR (updated_at, id) < ($3::timestamptz, $4::uuid))
        ORDER BY updated_at DESC, id DESC
        LIMIT $5
        """,
        status, kind, before_updated, before_id, limit,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["updated_at"], row["id"]),
    )
    return out


@router.post("/jobs/claim")
async def claim(body: ClaimIn) -> dict:
    """Atomically lease the oldest due job for this worker (SKIP LOCKED)."""
    if body.kinds and any(k not in JOB_KINDS for k in body.kinds):
        raise HTTPException(status_code=422, detail="unknown job kind in kinds")
    now = datetime.now(timezone.utc)
    pool = db.get()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, kind, entity_id, payload::text AS payload, attempts
                FROM jobs
                WHERE status IN ('pending', 'failed')
                  AND run_after <= now()
                  AND ($1::text[] IS NULL OR kind = ANY($1::text[]))
                ORDER BY run_after ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                body.kinds or None,
            )
            if not row:
                return {"claimed": False}
            await conn.execute(
                """
                UPDATE jobs SET status = 'leased', lease_holder = $2,
                       lease_expires_at = $3, attempts = attempts + 1,
                       updated_at = now()
                WHERE id = $1
                """,
                row["id"], body.worker, now + timedelta(seconds=body.lease_s),
            )
    return {
        "claimed": True,
        "id": str(row["id"]),
        "kind": row["kind"],
        "entity_id": str(row["entity_id"]) if row["entity_id"] else None,
        "payload": json.loads(row["payload"] or "{}"),
        "attempt": row["attempts"] + 1,
        "lease_expires_at": (now + timedelta(seconds=body.lease_s)).isoformat(),
    }


@router.post("/jobs/{job_id}/result")
async def result(job_id: uuid.UUID, body: JobResultIn) -> dict:
    """Record a job outcome. Failure respects max_attempts (dead-lettered)."""
    now = datetime.now(timezone.utc)
    pool = db.get()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT status, attempts, max_attempts FROM jobs "
                "WHERE id = $1 FOR UPDATE",
                job_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="job not found")
            if row["status"] in ("done", "cancelled"):
                raise HTTPException(
                    status_code=409, detail="job already finished")
            if body.ok:
                await conn.execute(
                    "UPDATE jobs SET status = 'done', last_error = NULL, "
                    "lease_expires_at = NULL, lease_holder = NULL, updated_at = now() "
                    "WHERE id = $1",
                    job_id,
                )
                return {"id": str(job_id), "status": "done"}
            if row["attempts"] >= row["max_attempts"] or body.retry_after_s is None:
                dead = row["attempts"] >= row["max_attempts"]
                # A failure without an explicit delay gets the default backoff,
                # never 0 — run_after = now() would re-claim instantly and
                # tight-loop a failing job until it dead-letters.
                backoff = body.retry_after_s if body.retry_after_s else DEFAULT_RETRY_AFTER_S
                await conn.execute(
                    "UPDATE jobs SET status = CASE WHEN $2 THEN 'dead' ELSE 'failed' END, "
                    "last_error = $3, lease_expires_at = NULL, lease_holder = NULL, "
                    "run_after = CASE WHEN $2 THEN run_after ELSE now() + "
                    "make_interval(secs => $4::int) END, updated_at = now() WHERE id = $1",
                    job_id, dead, body.detail, backoff,
                )
                return {"id": str(job_id), "status": "dead" if dead else "failed"}
            await conn.execute(
                "UPDATE jobs SET status = 'pending', last_error = $2, "
                "lease_expires_at = NULL, lease_holder = NULL, "
                "run_after = now() + make_interval(secs => $3::int), updated_at = now() "
                "WHERE id = $1",
                job_id, body.detail, body.retry_after_s,
            )
            return {"id": str(job_id), "status": "pending"}


@router.post("/jobs/{job_id}/retry")
async def retry(job_id: uuid.UUID, request: Request) -> dict:
    """Revive a dead or stuck job: fresh attempt budget, due immediately.

    Dead jobs surface in /attention (kind `job`); this is the operator's
    un-wedge action. Available to humans and service identities (recurring
    collect jobs also self-revive via a healthy poll-result re-arm)."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE jobs SET status = 'pending', attempts = 0, last_error = NULL,
               lease_holder = NULL, lease_expires_at = NULL,
               run_after = now(), updated_at = now()
        WHERE id = $1 AND status IN ('dead', 'failed')
        RETURNING id, status::text AS status
        """,
        job_id,
    )
    if not row:
        existing = await pool.fetchval("SELECT status::text FROM jobs WHERE id = $1", job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="job not found")
        raise HTTPException(
            status_code=409,
            detail=f"job is '{existing}' — only dead or failed jobs can be retried")
    return {"id": str(row["id"]), "status": row["status"]}


class BulkRetryIn(BaseModel):
    """Filter-checked bulk un-wedge (WP-G §5.6.5)."""
    ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=200)
    all: bool = False
    kinds: list[str] = Field(default_factory=list)


@router.post("/jobs/bulk-retry")
async def bulk_retry(body: BulkRetryIn, request: Request) -> dict:
    """Revive MANY dead/failed jobs at once — the "50 jobs dead-lettered in
    an outage" morning, one click instead of fifty (WP-G §5.6.5).

    HUMAN-ONLY: mass requeuing is exactly the action automation must never
    take on its own (same rule as batch transitions). Filter-checked: kinds
    must be known job kinds, at most 200 ids, and only `dead`/`failed` rows
    are touched — leased/done/pending jobs are never re-armed. Per-id results
    (207-style multi-status) so a partially-wrong selection is visible.
    """
    if credential_class(request) not in (CREDENTIAL_REVIEWER, CREDENTIAL_DISABLED):
        raise HTTPException(
            status_code=403,
            detail="bulk retries are a human action — use a reviewer credential",
        )
    unknown = sorted(set(body.kinds) - set(JOB_KINDS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown job kind(s): {', '.join(unknown)} — known: "
                   f"{', '.join(JOB_KINDS)}")
    if not body.all and not body.ids:
        raise HTTPException(
            status_code=422, detail="provide ids or all=true (with optional kinds filter)")
    if len(body.kinds) > len(set(body.kinds)):
        kinds = list(dict.fromkeys(body.kinds))
    else:
        kinds = body.kinds
    # hard cap for the all=true path too
    MAX_BULK = 200
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, kind, status::text AS status, attempts, last_error
        FROM jobs
        WHERE status IN ('dead', 'failed')
          AND (($1::uuid[] IS NULL) OR (id = ANY($1::uuid[])))
          AND (($2::text[] IS NULL) OR (kind = ANY($2::text[])))
        ORDER BY updated_at DESC
        LIMIT $3
        """,
        [str(i) for i in body.ids] if body.ids else None,
        kinds if kinds else None,
        MAX_BULK + 1,
    )
    truncated = len(rows) > MAX_BULK
    rows = rows[:MAX_BULK]
    updated = await pool.fetch(
        """
        UPDATE jobs SET status = 'pending', attempts = 0, last_error = NULL,
               lease_holder = NULL, lease_expires_at = NULL,
               run_after = now(), updated_at = now()
        WHERE id = ANY($1::uuid[]) AND status IN ('dead', 'failed')
        RETURNING id, kind
        """,
        [str(r["id"]) for r in rows],
    ) if rows else []
    retried = len(updated)
    done: dict[str, dict] = {str(r["id"]): {"kind": r["kind"]} for r in updated}
    results: list[dict] = []
    for row in rows:
        rid = str(row["id"])
        if rid in done:
            results.append({"id": rid, "kind": row["kind"], "ok": True,
                            "status": "pending"})
        else:
            results.append({"id": rid, "kind": row["kind"], "ok": False,
                            "status": row["status"],
                            "detail": "state changed; only dead/failed jobs retry"})
    # Explicitly-requested ids that matched nothing must still be visible.
    if body.ids:
        seen = {r["id"] for r in results}
        for requested in body.ids:
            rid = str(requested)
            if rid not in seen:
                current = await pool.fetchval(
                    "SELECT status::text FROM jobs WHERE id = $1", requested)
                results.append({
                    "id": rid, "ok": False,
                    "status": current or "missing",
                    "detail": (f"job is '{current}' — only dead or failed jobs "
                               "can be retried") if current else "job not found",
                })
    await db.get().execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, NULL, $4::jsonb)",
        credential_class(request), "jobs:bulk_retry", "jobs",
        json.dumps({"requested": len(results), "retried": retried,
                    "kinds": kinds, "all": body.all}, default=str),
    )
    return {"ok": all(r["ok"] for r in results), "retried": retried,
            "requested": len(results), "truncated": truncated, "results": results}


class JobTouchIn(BaseModel):
    worker: str = Field(min_length=3, max_length=120)
    lease_s: int = Field(default=DEFAULT_LEASE_S, ge=30, le=86400)


@router.post("/jobs/{job_id}/touch")
async def touch(job_id: uuid.UUID, body: JobTouchIn) -> dict:
    """Extend a held lease (WP-G §5.6.6): renders beyond the lease window
    (long encodes) must NOT be treated as wedged mid-flight by the attention
    view, and must not lose the job to a reclaim decision on expiry. Only the
    current holder can extend it — a stolen lease would break the exactly-one-
    worker guarantee."""
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE jobs SET lease_expires_at = now() + make_interval(secs => $2),
               updated_at = now()
        WHERE id = $1 AND status = 'leased' AND lease_holder = $3
        RETURNING id, lease_expires_at
        """,
        job_id, body.lease_s, body.worker,
    )
    if not row:
        current = await pool.fetchrow(
            "SELECT status::text AS status, lease_holder FROM jobs WHERE id = $1",
            job_id,
        )
        if not current:
            raise HTTPException(status_code=404, detail="job not found")
        raise HTTPException(
            status_code=409,
            detail=f"job is '{current['status']}'"
                   + (f" held by another worker ({current['lease_holder']})"
                      if current["status"] == "leased" else
                      " — only a leased job can be touched"),
        )
    return {"id": str(row["id"]),
            "lease_expires_at": row["lease_expires_at"].isoformat()}


@router.get("/jobs/stuck")
async def stuck_jobs() -> dict:
    """Leased jobs whose lease expired without an outcome, and dead jobs.

    An expired lease is NOT auto-reclaimed: the worker may have side-effected
    the world before dying (a published upload cannot be un-published from
    here). They surface for a human, like held uploads.
    """
    pool = db.get()
    expired = await pool.fetch(
        """
        SELECT id, kind, entity_id, lease_holder, lease_expires_at, attempts
        FROM jobs WHERE status = 'leased' AND lease_expires_at <= now()
        ORDER BY lease_expires_at ASC LIMIT 100
        """,
    )
    dead = await pool.fetch(
        """
        SELECT id, kind, entity_id, attempts, max_attempts, last_error, updated_at
        FROM jobs WHERE status = 'dead' ORDER BY updated_at DESC LIMIT 100
        """,
    )
    return {
        "expired_leases": [dict(r) for r in expired],
        "dead": [dict(r) for r in dead],
    }
