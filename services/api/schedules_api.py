"""Schedules router — content calendar + approval/version controls (week 9,
master plan §17). Gates enforced server-side:

- Create: offer must be in an approved-for-video state WITH a rendered export
  whose capture passed redaction review; test posts default to private.
- Approve: records reviewer + the EXACT approved script version hash.
- Schedule: revalidates the current script hash against the approved hash —
  material edits force reapproval (rollback safety, §17).
- Pause: always available to the operator; resume/schedule revalidate the hash.
- Results (published/failed) come from the publishing worker with an
  idempotency key; remote post IDs are stored for tracking.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from schedules_state import (
    PLATFORMS,
    ScheduleTransitionError,
    platform_metadata,
    script_version_hash,
    validate_transition,
)
from state import can_generate_video

router = APIRouter(tags=["schedules"])


# ---------------------------------------------------------------- schemas


class ScheduleIn(BaseModel):
    platform: str
    local_time: datetime
    timezone: str = "Asia/Karachi"
    privacy: str = "private"  # test posts default private (§18 week 9)
    caption_variant: str = "default"


class ScheduleTransitionIn(BaseModel):
    to: str
    reviewer: Optional[str] = None
    note: Optional[str] = None


class ScheduleResultIn(BaseModel):
    ok: bool
    remote_post_id: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------- create


@router.post("/offers/{offer_id}/schedules", status_code=201)
async def create_schedule(offer_id: uuid.UUID, body: ScheduleIn, request: Request) -> dict:
    pool = db.get()
    offer = await pool.fetchrow(
        """
        SELECT id, title, provider, state::text AS state, eligibility::text AS eligibility,
               renewal::text AS renewal, expires_at
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    if not can_generate_video(offer["state"]):
        raise HTTPException(
            status_code=409,
            detail=f"scheduling blocked: offer state is '{offer['state']}' (§3)",
        )
    if offer["state"] != "approved_for_video":
        raise HTTPException(
            status_code=409,
            detail="schedule creation requires the offer to be approved for video (§17)",
        )
    if body.platform not in PLATFORMS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported platform — known: {', '.join(PLATFORMS)}",
        )
    if offer["expires_at"] and offer["expires_at"] <= datetime.now(offer["expires_at"].tzinfo or None):
        raise HTTPException(status_code=409, detail="offer already expired — cannot schedule")

    # §17: each queued post must reference an approved video version + valid evidence.
    render = await pool.fetchrow(
        """
        SELECT r.id, r.video_path, r.disclosure::text AS disclosure, c.redaction_reviewed
        FROM renders r LEFT JOIN capture_sessions c ON c.id = r.capture_id
        WHERE r.offer_id = $1
        ORDER BY r.created_at DESC LIMIT 1
        """,
        offer_id,
    )
    if not render:
        raise HTTPException(status_code=409, detail="no render exists — render the video first")
    if render["redaction_reviewed"] is False:
        raise HTTPException(
            status_code=409,
            detail="latest render's capture has not passed redaction review (§4)",
        )

    scripts = await pool.fetch(
        "SELECT version, markdown FROM offer_scripts WHERE offer_id = $1 ORDER BY version DESC LIMIT 1",
        offer_id,
    )
    version_hash = script_version_hash(scripts[0]["markdown"]) if scripts else None

    evidence = await pool.fetch(
        "SELECT url FROM evidence WHERE offer_id = $1 AND official AND domain_ok",
        offer_id,
    )
    correction_base = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    metadata = platform_metadata(
        body.platform, dict(offer), [r["url"] for r in evidence],
        json.loads(render["disclosure"]) if render["disclosure"] else {},
        correction_url=f"{correction_base}/offers/{offer_id}" if correction_base else None,
    )

    idempotency_key = f"{offer_id}:{body.platform}:{body.local_time.isoformat()}:{version_hash or ''}"
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO schedules (offer_id, platform, local_time, timezone, privacy,
                                   caption_variant, idempotency_key, version_hash, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, state::text AS state, idempotency_key
            """,
            offer_id, body.platform, body.local_time, body.timezone, body.privacy,
            body.caption_variant, idempotency_key, version_hash, json.dumps(metadata),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"schedule insert failed: {exc}") from exc

    if not row:  # identical schedule already exists — idempotent re-submit
        existing = await pool.fetchrow(
            "SELECT id, state::text AS state FROM schedules WHERE idempotency_key = $1",
            idempotency_key,
        )
        return {"id": existing["id"], "state": existing["state"], "created": False,
                "idempotency_key": idempotency_key}

    await _audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                 action="create_schedule", entity="schedules",
                 entity_id=row["id"], detail={"platform": body.platform,
                                              "privacy": body.privacy})
    return {"id": row["id"], "state": row["state"], "created": True,
            "idempotency_key": idempotency_key, "metadata": metadata}


# ---------------------------------------------------------------- calendar


@router.get("/schedules")
async def list_schedules(
    state: Optional[str] = None,
    limit: int = Query(default=100, le=500),
) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT s.id, s.offer_id, o.title AS offer_title, o.provider AS offer_provider,
               s.platform, s.state::text AS state, s.local_time, s.timezone,
               s.privacy, s.caption_variant, s.version_hash, s.approved_by,
               s.metadata::text AS metadata, s.retry_count, s.updated_at,
               s.remote_post_id, s.outcome_detail::text AS outcome_detail, s.created_at
        FROM schedules s JOIN offers o ON o.id = s.offer_id
        WHERE ($1::text IS NULL OR s.state::text = $1)
        ORDER BY s.local_time
        LIMIT $2
        """,
        state if state in ("draft", "needs_approval", "approved", "scheduled",
                           "published", "failed", "paused") else None,
        limit,
    )
    return [dict(r) for r in rows]


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: uuid.UUID) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        """
        SELECT s.*, o.title AS offer_title,
               (SELECT COUNT(*) FROM renders r WHERE r.offer_id = s.offer_id) AS render_count
        FROM schedules s JOIN offers o ON o.id = s.offer_id
        WHERE s.id = $1
        """,
        schedule_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="schedule not found")
    return dict(row)


# ---------------------------------------------------------------- transitions


@router.post("/schedules/{schedule_id}/transition")
async def transition(schedule_id: uuid.UUID, body: ScheduleTransitionIn, request: Request) -> dict:
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    reviewer_on_record = effective_reviewer(request, body.reviewer)
    try:
        validate_transition(schedule["state"], body.to,
                            reviewer=reviewer_on_record, version_hash=schedule["version_hash"])
    except ScheduleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    params: list = []
    sets = ["state = $2::schedule_state"]
    params.extend([schedule_id, body.to])

    if body.to in ("approved", "needs_approval"):
        current_hash = await _current_script_hash(pool, schedule["offer_id"])
        if not current_hash:
            raise HTTPException(status_code=409, detail="no script exists to approve")
        params.append(current_hash)
        sets.append(f"version_hash = ${len(params)}")
        if reviewer_on_record:
            params.append(reviewer_on_record)
            sets.append(f"approved_by = ${len(params)}")

    if body.to == "scheduled":
        expected = await _current_script_hash(pool, schedule["offer_id"])
        if schedule["version_hash"] != expected:
            raise HTTPException(
                status_code=409,
                detail="script changed since approval — reapproval required (§17)",
            )
        # revalidate the offer snapshot at scheduling time (§17)
        offer_ok = await _revalidate_offer(pool, schedule["offer_id"])
        params.append(offer_ok)
        sets.append(f"offer_evidence_ok = ${len(params)}")

    row = await pool.fetchrow(
        f"UPDATE schedules SET {', '.join(sets)}, updated_at = now() "
        f"WHERE id = $1 RETURNING state::text AS state, version_hash",
        *params,
    )
    await _audit(pool, actor=reviewer_on_record or "operator",
                 action=f"schedule:{schedule['state']}->{body.to}",
                 entity="schedules", entity_id=schedule_id, detail={"note": body.note})
    return {"id": schedule_id, "state": row["state"], "version_hash": row["version_hash"]}


@router.post("/schedules/{schedule_id}/pause")
async def pause(schedule_id: uuid.UUID, note: Optional[str] = None,
                request: Request = None) -> dict:
    """Operator-visible pause — available from approved or scheduled states."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] not in ("approved", "scheduled"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot pause from state '{schedule['state']}' (already paused/published?)",
        )
    row = await pool.fetchrow(
        "UPDATE schedules SET state = 'paused', updated_at = now() WHERE id = $1 RETURNING state::text AS state",
        schedule_id,
    )
    await _audit(pool, actor=effective_reviewer(request, None, default="operator"),
                 action="schedule:pause", entity="schedules",
                 entity_id=schedule_id, detail={"note": note})
    return {"id": schedule_id, "state": row["state"]}


@router.post("/schedules/{schedule_id}/resume")
async def resume(schedule_id: uuid.UUID, reviewer: str = Query(default="operator"),
                 request: Request = None) -> dict:
    """Resume revalidates the version hash — modified content stays paused."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] != "paused":
        raise HTTPException(status_code=409, detail=f"cannot resume from '{schedule['state']}'")
    expected = await _current_script_hash(pool, schedule["offer_id"])
    if schedule["version_hash"] != expected:
        raise HTTPException(
            status_code=409,
            detail="script changed since approval — reapproval required before resume (§17)",
        )
    row = await pool.fetchrow(
        "UPDATE schedules SET state = 'scheduled', updated_at = now() WHERE id = $1 RETURNING state::text AS state",
        schedule_id,
    )
    await _audit(pool, actor=effective_reviewer(request, reviewer, default="operator"),
                 action="schedule:resume", entity="schedules", entity_id=schedule_id)
    return {"id": schedule_id, "state": row["state"]}


@router.post("/schedules/{schedule_id}/result")
async def result(schedule_id: uuid.UUID, body: ScheduleResultIn) -> dict:
    """Publishing worker reports outcomes (idempotent by remote post id)."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] != "scheduled" and schedule["state"] != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"results only accepted for scheduled/failed posts (current: {schedule['state']})",
        )
    if body.ok and not body.remote_post_id:
        raise HTTPException(status_code=400, detail="successful publish requires remote_post_id")

    new_state = "published" if body.ok else "failed"
    outcome = {"detail": body.detail, "reported_at": datetime.now().isoformat()}
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(schedule_id))
            if body.remote_post_id:
                post_id = body.remote_post_id
                await conn.execute(
                    """
                    UPDATE schedules
                    SET state = $2::schedule_state,
                        remote_post_id = COALESCE(NULLIF($3, ''), remote_post_id),
                        retry_count = CASE WHEN $2 = 'failed' THEN retry_count + 1 ELSE retry_count END,
                        outcome_detail = outcome_detail || $4::jsonb,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    schedule_id, new_state, body.remote_post_id or "", json.dumps(outcome),
                )
            else:
                await conn.execute(
                    """
                    UPDATE schedules
                    SET state = $2::schedule_state,
                        retry_count = CASE WHEN $2 = 'failed' THEN retry_count + 1 ELSE retry_count END,
                        outcome_detail = outcome_detail || $3::jsonb,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    schedule_id, new_state, json.dumps(outcome),
                )
    await _audit(pool, actor="publishing-worker", action=f"result:{new_state}",
                 entity="schedules", entity_id=schedule_id, detail={"remote_post_id": body.remote_post_id})
    return {"id": schedule_id, "state": new_state}


# ---------------------------------------------------------------- helpers


async def _load(pool, schedule_id: uuid.UUID) -> dict:
    row = await pool.fetchrow(
        "SELECT id, offer_id, state::text AS state, version_hash, platform FROM schedules WHERE id = $1",
        schedule_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="schedule not found")
    return dict(row)


async def _current_script_hash(pool, offer_id: uuid.UUID) -> Optional[str]:
    row = await pool.fetchrow(
        "SELECT markdown FROM offer_scripts WHERE offer_id = $1 ORDER BY version DESC LIMIT 1",
        offer_id,
    )
    return script_version_hash(row["markdown"]) if row else None


async def _revalidate_offer(pool, offer_id: uuid.UUID) -> bool:
    """§17: revalidate offer validity before upload — expiry + recheck state."""
    row = await pool.fetchrow(
        """
        SELECT (expires_at IS NULL OR expires_at > now())
           AND recheck_at > now()
           AND state IN ('approved_for_video', 'verified') AS ok
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    return bool(row and row["ok"])


async def _audit(pool, *, actor: str, action: str, entity: str,
                 entity_id: Optional[uuid.UUID] = None, detail: Optional[dict] = None) -> None:
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        actor, action, entity, entity_id, json.dumps(detail or {}, default=str),
    )
