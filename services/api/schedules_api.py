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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from offer_freshness import freshness_problem
from automation import (
    AutomationDenied,
    authorize as authorize_automation,
    guardrails as automation_guardrails,
    is_automation_actor,
)
from automation_api import _budget_used, load_policy
from schedules_state import (
    PLATFORMS,
    ScheduleTransitionError,
    platform_metadata,
    script_version_hash,
    validate_transition,
)
from settings_store import get_language_policy, get_value
from state import can_generate_video

router = APIRouter(tags=["schedules"])


# ---------------------------------------------------------------- schemas


class ScheduleIn(BaseModel):
    platform: str
    local_time: datetime
    timezone: str = "Asia/Karachi"
    privacy: str = "private"  # test posts default private (§18 week 9)
    caption_variant: str = "default"
    # v0.27 content packaging. Defaults keep every existing caller working.
    language: str = "en"
    content_variant_id: Optional[uuid.UUID] = None
    metadata_variant: str = "default"
    cover_path: Optional[str] = None
    pinned_comment: Optional[str] = None
    website_url: Optional[str] = None


class ScheduleTransitionIn(BaseModel):
    to: str
    reviewer: Optional[str] = None
    note: Optional[str] = None


class ScheduleResultIn(BaseModel):
    ok: bool
    remote_post_id: Optional[str] = None
    detail: Optional[str] = None
    # v0.23: hold = "a human must look at this post" — the auto-retry sweep
    # skips held posts (e.g. an interrupted upload whose outcome is unknown:
    # retrying could publish a duplicate).
    hold: bool = False


# ---------------------------------------------------------------- create


@router.post("/offers/{offer_id}/schedules", status_code=201)
async def create_schedule(offer_id: uuid.UUID, body: ScheduleIn, request: Request) -> dict:
    pool = db.get()
    offer = await pool.fetchrow(
        """
        SELECT id, title, provider, category, offer_type, state::text AS state,
               eligibility::text AS eligibility, renewal::text AS renewal,
               redemption_url, expires_at
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
    if body.language not in ("en", "ur"):
        raise HTTPException(status_code=422, detail="language must be 'en' or 'ur'")
    language_policy = await get_language_policy(pool)
    if body.language not in language_policy["narration_languages"]:
        raise HTTPException(
            status_code=409,
            detail=f"{body.language} voiceover is disabled in Settings → Language policy",
        )
    if offer["expires_at"] and offer["expires_at"] <= datetime.now(offer["expires_at"].tzinfo or None):
        raise HTTPException(status_code=409, detail="offer already expired — cannot schedule")

    # §17: each queued post must reference an approved video version + valid evidence.
    # v0.27: the render must match the language being scheduled; falling back to a
    # different-language render would put the wrong narration/captions on a post.
    render = await pool.fetchrow(
        """
        SELECT r.id, r.video_path, r.language, r.cover_path,
               r.disclosure::text AS disclosure, c.redaction_reviewed
        FROM renders r LEFT JOIN capture_sessions c ON c.id = r.capture_id
        WHERE r.offer_id = $1 AND r.language = $2
        ORDER BY r.created_at DESC LIMIT 1
        """,
        offer_id, body.language,
    )
    if not render:
        raise HTTPException(
            status_code=409,
            detail=f"no {body.language} render exists — render this language first",
        )
    if render["redaction_reviewed"] is False:
        raise HTTPException(
            status_code=409,
            detail="latest render's capture has not passed redaction review (§4)",
        )

    scripts = await pool.fetch(
        "SELECT version, markdown FROM offer_scripts "
        "WHERE offer_id = $1 AND language = $2 ORDER BY version DESC LIMIT 1",
        offer_id, body.language,
    )
    version_hash = script_version_hash(scripts[0]["markdown"]) if scripts else None

    evidence = await pool.fetch(
        "SELECT url FROM evidence WHERE offer_id = $1 AND official AND domain_ok",
        offer_id,
    )
    brand = await get_value(pool, "brand")
    brand_value = (brand or {}).get("value") or {}
    website = body.website_url or brand_value.get("website_url") or offer.get("redemption_url") or None

    # An approved metadata variant can be scheduled directly. It must belong to
    # this offer and match the platform/language, so a stale variant cannot be
    # silently posted cross-platform.
    metadata: dict
    scheduled_variant_key = body.metadata_variant
    if body.content_variant_id:
        variant = await pool.fetchrow(
            """
            SELECT id, kind, platform, language, variant_key, payload::text AS payload
            FROM content_variants
            WHERE id = $1 AND offer_id = $2
            """,
            body.content_variant_id, offer_id,
        )
        if not variant:
            raise HTTPException(status_code=404, detail="content variant not found for this offer")
        if variant["kind"] != "metadata":
            raise HTTPException(status_code=409, detail="only metadata variants can be scheduled")
        if variant["platform"] not in (None, body.platform):
            raise HTTPException(status_code=409, detail="content variant belongs to another platform")
        if variant["language"] != body.language:
            raise HTTPException(status_code=409, detail="content variant belongs to another language")
        try:
            metadata = json.loads(variant["payload"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="content variant payload is invalid") from exc
        scheduled_variant_key = variant["variant_key"]
    else:
        correction_base = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
        metadata = platform_metadata(
            body.platform, dict(offer), [r["url"] for r in evidence],
            json.loads(render["disclosure"]) if render["disclosure"] else {},
            correction_url=f"{correction_base}/offers/{offer_id}" if correction_base else None,
            website_url=website,
            # English-first: the public package stays in the configured copy
            # language even when the voiceover is Urdu.
            language=language_policy["metadata_language"],
            variant=body.metadata_variant,
        )

    cover_path = body.cover_path or render["cover_path"]
    pinned_comment = body.pinned_comment or metadata.get("pinned_comment")

    idempotency_key = (
        f"{offer_id}:{body.platform}:{body.local_time.isoformat()}:"
        f"{body.language}:{body.caption_variant}:{body.metadata_variant}:{version_hash or ''}"
    )
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO schedules (offer_id, platform, local_time, timezone, privacy,
                                   caption_variant, idempotency_key, version_hash, metadata,
                                   language, content_variant_id, cover_path, pinned_comment,
                                   metadata_variant)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, state::text AS state, idempotency_key
            """,
            offer_id, body.platform, body.local_time, body.timezone, body.privacy,
            body.caption_variant, idempotency_key, version_hash, json.dumps(metadata),
            body.language, body.content_variant_id, cover_path, pinned_comment,
            scheduled_variant_key,
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
                                              "privacy": body.privacy,
                                              "language": body.language,
                                              "metadata_variant": scheduled_variant_key})
    return {"id": row["id"], "state": row["state"], "created": True,
            "idempotency_key": idempotency_key, "language": body.language,
            "metadata_language": metadata.get("language", language_policy["metadata_language"]),
            "cover_path": cover_path, "pinned_comment": pinned_comment,
            "metadata_variant": scheduled_variant_key, "metadata": metadata}


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
               s.metadata::text AS metadata, s.language, s.content_variant_id,
               s.cover_path, s.pinned_comment, s.metadata_variant,
               s.retry_count, s.updated_at, s.description_patched_at,
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
    policy = await load_policy()

    # v0.26: automation may approve/schedule only when Settings enables that
    # stage. A human reviewer token always wins (identity binding), so this
    # path is reachable only by workers using the service token + explicit
    # automation:<stage> actor.
    if is_automation_actor(reviewer_on_record):
        stage = "approve" if body.to == "approved" else "schedule" if body.to == "scheduled" else None
        if stage is None:
            raise HTTPException(
                status_code=403,
                detail=f"automation may not perform the schedule transition to '{body.to}'",
            )
        if body.to == "scheduled" and schedule["state"] == "paused":
            raise HTTPException(
                status_code=403,
                detail="automation may not resume a paused post — a named human must decide",
            )
        try:
            # canonical actor: approved_by must stay in the 'automation:%'
            # namespace the budget/status queries count.
            reviewer_on_record = authorize_automation(policy, stage, reviewer_on_record)
        except AutomationDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        limits = automation_guardrails(policy)
        if body.to == "approved":
            used = await _budget_used(pool)
            if used >= int(limits["auto_publish_max_per_day"]):
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "automation daily approval budget exhausted "
                        f"({used}/{limits['auto_publish_max_per_day']}) — "
                        "raise auto_publish_max_per_day in Settings or approve manually"
                    ),
                )
            await _gate_automation_schedule(pool, schedule)
        elif body.to == "scheduled":
            # Re-check the live offer and the auto-schedule guardrails even when
            # approval happened earlier: a post can sit in the queue while the
            # offer expires or the platform policy changes.
            await _gate_automation_schedule(pool, schedule)
            if schedule["platform"] not in limits["auto_schedule_platforms"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"automation may not schedule '{schedule['platform']}' — "
                        "allowed: " + ", ".join(limits["auto_schedule_platforms"])
                    ),
                )
            if schedule["privacy"] != limits["auto_schedule_privacy"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"automation may only schedule {limits['auto_schedule_privacy']} "
                        f"posts (this post is {schedule['privacy']}); a human must schedule it"
                    ),
                )

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

    if body.to == "scheduled":
        # a post that was HELD (unknown upload outcome) is being re-queued by
        # a human decision — clear the hold so it may go out (v0.23)
        sets.append("outcome_detail = outcome_detail || '{\"hold\": false}'::jsonb")

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
    """Resume revalidates the version hash — modified content stays paused.

    Resuming a paused post is always a human decision: a paused post may be
    paused because the offer expired, a correction landed, or an upload's
    outcome is unknown. Automation must never put it back in the publishing
    queue on its own.
    """
    actor = effective_reviewer(request, reviewer, default="operator")
    if is_automation_actor(actor):
        raise HTTPException(
            status_code=403,
            detail="automation may not resume a paused post — a named human must decide",
        )
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
    # §11: an offer that expired or missed its recheck while the post was paused
    # must be re-verified, not quietly re-queued; the upload recheck is the last
    # line, not the only one.
    if not await _revalidate_offer(pool, schedule["offer_id"]):
        problem = await freshness_problem(pool, schedule["offer_id"]) \
            or "offer state no longer allows publishing"
        raise HTTPException(
            status_code=409,
            detail=f"resume blocked: {problem} (§11 freshness)",
        )
    row = await pool.fetchrow(
        "UPDATE schedules SET state = 'scheduled', updated_at = now() WHERE id = $1 RETURNING state::text AS state",
        schedule_id,
    )
    # a human resumed the post: clear the hold so the worker may try again
    await pool.execute(
        "UPDATE schedules SET outcome_detail = outcome_detail || '{\"hold\": false}'::jsonb, "
        "updated_at = now() WHERE id = $1",
        schedule_id,
    )
    await _audit(pool, actor=actor, action="schedule:resume",
                 entity="schedules", entity_id=schedule_id)
    return {"id": schedule_id, "state": row["state"]}


class AttemptIn(BaseModel):
    """The worker announces an upload BEFORE it starts (v0.23). If the worker
    dies mid-upload, the marker stays open: the next sweep knows the outcome
    is UNKNOWN and holds the post for a human instead of publishing a
    duplicate."""
    detail: Optional[str] = None
    worker: Optional[str] = None


@router.post("/schedules/{schedule_id}/attempt")
async def attempt(schedule_id: uuid.UUID, body: AttemptIn) -> dict:
    """Mark an upload attempt as started (idempotent per attempt)."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] != "scheduled":
        raise HTTPException(
            status_code=409,
            detail=f"attempts only apply to scheduled posts (current: {schedule['state']})",
        )
    marker = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "detail": body.detail,
        "worker": body.worker or "publishing-worker",
    }
    await pool.execute(
        "UPDATE schedules SET outcome_detail = outcome_detail || $2::jsonb, updated_at = now() "
        "WHERE id = $1",
        schedule_id, json.dumps({"attempt": marker}),
    )
    return {"id": str(schedule_id), "attempt": marker}


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
    # a definite outcome clears any open "attempt" marker (the upload either
    # succeeded or failed — retrying is safe)
    outcome = {"detail": body.detail, "reported_at": datetime.now().isoformat(),
               "attempt": None, "hold": bool(body.hold)}
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


# ------------------------------------------------- audience metrics (v0.18)


class MetricsIn(BaseModel):
    """One audience-metrics snapshot from the metrics worker (master plan §7).
    Normalized fields feed analytics; `raw` keeps the provider payload."""
    platform: str = Field(pattern="^(youtube|facebook|instagram|tiktok)$")
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    impressions: Optional[int] = None
    avg_watch_s: Optional[float] = None
    source: str = Field(min_length=3, max_length=64)
    raw: dict = Field(default_factory=dict)


@router.post("/schedules/{schedule_id}/metrics", status_code=201)
async def ingest_metrics(schedule_id: uuid.UUID, body: MetricsIn) -> dict:
    """Upsert a daily metrics snapshot: at most one row per (post, UTC day) —
    a re-pull on the same day REPLACES the row instead of drift-duplicating."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["platform"] != body.platform:
        raise HTTPException(status_code=409, detail="metrics platform must match the schedule")
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM post_metrics WHERE schedule_id = $1 AND captured_at::date = now()::date",
                schedule_id,
            )
            await conn.execute(
                """
                INSERT INTO post_metrics
                    (schedule_id, platform, views, likes, comments, impressions, avg_watch_s, source, raw)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                """,
                schedule_id, body.platform, body.views, body.likes, body.comments,
                body.impressions, body.avg_watch_s, body.source, json.dumps(body.raw),
            )
    latest = await pool.fetchrow(
        "SELECT views, likes, comments, impressions, avg_watch_s, captured_at FROM post_metrics WHERE schedule_id = $1 ORDER BY captured_at DESC LIMIT 1",
        schedule_id,
    )
    return {"schedule_id": str(schedule_id), **dict(latest)}


@router.get("/schedules/{schedule_id}/metrics")
async def list_metrics(schedule_id: uuid.UUID) -> dict:
    """All snapshots for a post, newest first (dashboard trend display)."""
    pool = db.get()
    rows = await pool.fetch(
        """SELECT views, likes, comments, impressions, avg_watch_s, source,
                  captured_at FROM post_metrics WHERE schedule_id = $1
           ORDER BY captured_at DESC LIMIT 90""",
        schedule_id,
    )
    return {"schedule_id": str(schedule_id), "metrics": [dict(r) for r in rows]}


# ------------------------------------------ correction description patching


class DescriptionPatchedIn(BaseModel):
    detail: Optional[str] = None


@router.post("/schedules/{schedule_id}/mark-description-patched")
async def mark_description_patched(schedule_id: uuid.UUID, body: DescriptionPatchedIn,
                                   request: Request) -> dict:
    """Worker confirms the §11 correction notice was pushed into an
    already-published description (idempotency marker for the sweep)."""
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] != "published":
        raise HTTPException(status_code=409, detail="only published posts get description patches")
    await pool.execute(
        "UPDATE schedules SET description_patched_at = now(), updated_at = now() WHERE id = $1",
        schedule_id,
    )
    await _audit(pool, actor=effective_reviewer(request, None, default="publishing-worker"),
                 action="schedule:description-patched", entity="schedules", entity_id=schedule_id,
                 detail={"detail": body.detail})
    return {"id": str(schedule_id), "description_patched_at": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------- helpers


async def _gate_automation_schedule(pool, schedule: dict) -> None:
    """Unattended approval/scheduling must never act on a stale offer."""
    offer = await pool.fetchrow(
        "SELECT state::text AS state, correction_note, expires_at, recheck_at "
        "FROM offers WHERE id = $1",
        schedule["offer_id"],
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    problems: list[str] = []
    if offer["state"] != "approved_for_video":
        problems.append(f"offer state is '{offer['state']}' (must be approved_for_video)")
    if (offer["correction_note"] or "").strip():
        problems.append("an open correction note requires human review")
    now = datetime.now(timezone.utc)
    if offer["expires_at"] and offer["expires_at"] <= now:
        problems.append("offer has expired")
    if offer["recheck_at"] and offer["recheck_at"] <= now:
        problems.append("offer recheck is overdue")
    if problems:
        raise HTTPException(
            status_code=409,
            detail="automation schedule approval refused: " + "; ".join(problems),
        )


async def _load(pool, schedule_id: uuid.UUID) -> dict:
    row = await pool.fetchrow(
        "SELECT id, offer_id, state::text AS state, version_hash, platform, privacy "
        "FROM schedules WHERE id = $1",
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
    """§17: offer still fresh for scheduling, resume or upload — expiry, recheck state."""
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
