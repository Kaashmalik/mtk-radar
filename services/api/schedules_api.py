"""Schedules router — content calendar + approval/version controls (week 9,
master plan §17). Gates enforced server-side:

- Create: offer must be in an approved-for-video state WITH a rendered export
  whose measured QC passed and whose capture passed redaction review; test
  posts default to private.
- Approve: records reviewer + the EXACT approved script version hash.
- Schedule: revalidates the current script hash against the approved hash —
  material edits force reapproval (rollback safety, §17).
- Pause: always available to the operator; resume/schedule revalidate the hash.
- Results (published/failed) come from the publishing worker with an
  idempotency key; remote post IDs are stored for tracking.
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import db
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from api_hardening import (
    CREDENTIAL_DISABLED,
    CREDENTIAL_REVIEWER,
    credential_class,
    effective_reviewer,
)
from offer_freshness import freshness_problem

_logger = logging.getLogger("mtk.schedules")
from release_gate import describe as describe_problems
from release_gate import offer_problems, release_problems
from automation import (
    AutomationDenied,
    authorize as authorize_automation,
    guardrails as automation_guardrails,
    is_automation_actor,
)
from automation_api import _budget_used, load_policy
from schedules_state import (
    PLATFORM_LIMITS,
    PLATFORMS,
    ScheduleTransitionError,
    platform_metadata,
    script_version_hash,
    validate_transition,
)
from settings_store import get_language_policy, get_value
from state import can_generate_video

router = APIRouter(tags=["schedules"])

# Native aspect for each platform's flagship surface. YouTube long-form and
# Facebook feed video are 16:9; Instagram Reels and TikTok are 9:16. An
# operator can override this by pinning an explicit render_id (e.g. a YouTube
# Short uses a vertical render).
_PREFERRED_RENDER_PRESET = {
    "youtube": "landscape",
    "facebook": "landscape",
    "instagram": "vertical",
    "tiktok": "vertical",
}


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
    # YouTube-first: pin the exact upload target. When omitted the API picks
    # the first active account for the platform (if one exists).
    platform_account_id: Optional[uuid.UUID] = None
    youtube_playlist_id: Optional[str] = None
    # Pin the exact rendered file. When omitted the API chooses the newest
    # render for the language, preferring the platform's native aspect (16:9
    # for YouTube/Facebook, 9:16 for Instagram/TikTok). YouTube Shorts can pin
    # a vertical render explicitly.
    render_id: Optional[uuid.UUID] = None


class ScheduleTransitionIn(BaseModel):
    to: str
    reviewer: Optional[str] = None
    note: Optional[str] = None
    # An open upload-attempt marker means the post may already be live. A
    # human must explicitly acknowledge the platform check before requeueing.
    acknowledge_unknown_attempt: bool = False


class ScheduleResultIn(BaseModel):
    ok: bool
    remote_post_id: Optional[str] = None
    detail: Optional[str] = None
    # v0.23: hold = "a human must look at this post" — the auto-retry sweep
    # skips held posts (e.g. an interrupted upload whose outcome is unknown:
    # retrying could publish a duplicate).
    hold: bool = False
    # v0.28: tie the outcome to the exact attempt claim. An outcome without
    # the matching token is refused rather than accidentally clearing another
    # worker's in-flight upload marker.
    attempt_token: Optional[str] = None
    # Remote confirmation is required before a post becomes `published`.
    confirmed: bool = False
    remote_url: Optional[str] = None
    remote_processing_state: Optional[str] = None
    remote_privacy: Optional[str] = None
    remote_metadata: dict = Field(default_factory=dict)


# ---------------------------------------------------------------- create


async def _trend_keywords_for_offer(pool, offer_id: uuid.UUID) -> list[str]:
    """Trend-bridged hashtag keywords (WP-E): from the production-queue row's
    trend, only when the trend is still RISING (velocity > 0) — a cooled story
    must not keep shipping its hype tags. Every keyword cites the trend row;
    nothing is invented here."""
    try:
        rows = await pool.fetch(
            """
            SELECT kv.value AS keyword
            FROM production_queue q
            JOIN trend_candidates t ON t.id = q.trend_id
            CROSS JOIN LATERAL (
                SELECT jsonb_array_elements_text(
                           COALESCE(t.score_reason->'keywords', '[]'::jsonb)) AS value
                UNION ALL
                SELECT jsonb_array_elements_text(
                           COALESCE(t.signals->'keywords', '[]'::jsonb))
            ) kv
            WHERE q.offer_id = $1 AND t.velocity > 0
            LIMIT 6
            """,
            offer_id,
        )
    except Exception:  # noqa: BLE001 — packaging must never fail on cosmetics
        return []
    return [str(r["keyword"]) for r in rows if r["keyword"]][:6]


async def _hashtag_performance(pool, platform: str) -> dict[str, dict[str, Any]]:
    """The `hashtag_performance` feedback rollup (WP-E): tags that
    consistently underperform drop down the generation pool."""
    try:
        rows = await pool.fetch(
            """
            SELECT tag, posts, impressions_total::float8
            FROM hashtag_performance WHERE platform = $1
            """,
            platform,
        )
    except Exception:  # noqa: BLE001 — table may predate migration 034
        return {}
    return {
        r["tag"]: {"posts": int(r["posts"]),
                   "avg_impressions": (float(r["impressions_total"]) / int(r["posts"]))
                   if int(r["posts"]) else 0.0}
        for r in rows
    }


async def _create_one_schedule(pool, offer_id: uuid.UUID, body: ScheduleIn,
                               actor: str) -> dict:
    """Create ONE platform schedule. Every release gate lives here and is
    identical for single and batch creation (WP-D): the batch path is this
    function called once per platform — never a copy of the checks."""
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
    if body.privacy not in ("private", "unlisted", "public"):
        raise HTTPException(
            status_code=400,
            detail="privacy must be 'private', 'unlisted' or 'public'",
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
    preferred_preset = _PREFERRED_RENDER_PRESET.get(body.platform) or ""
    render = await pool.fetchrow(        """
        SELECT r.id, r.preset, r.video_path, r.language, r.cover_path, r.captions_path,
               r.duration_s, r.video_sha256, r.cover_sha256, r.captions_sha256,
               r.script_version_hash, r.status, r.qc_status,
               r.metadata::text AS render_metadata,
               r.disclosure::text AS disclosure, c.redaction_reviewed
        FROM renders r LEFT JOIN capture_sessions c ON c.id = r.capture_id
        WHERE r.offer_id = $1 AND r.language = $2
          AND ($3::uuid IS NULL OR r.id = $3)
        ORDER BY (r.status = 'rendered' AND r.qc_status = 'passed'
                  AND r.preset = $4) DESC,
                 (r.status = 'rendered' AND r.qc_status = 'passed') DESC,
                 (r.preset = $4) DESC, r.created_at DESC LIMIT 1
        """,
        offer_id, body.language, body.render_id, preferred_preset,
    )
    if not render:
        if body.render_id:
            raise HTTPException(
                status_code=409,
                detail="the selected render does not exist for this offer and language",
            )
        raise HTTPException(
            status_code=409,
            detail=f"no {body.language} render exists — render this language first",
        )
    # v0.29: only a measured, passed render can enter the publishing package.
    # Failed attempts remain in the dead-letter view for diagnosis, never here.
    if render.get("status") != "rendered" or render.get("qc_status") != "passed":
        raise HTTPException(
            status_code=409,
            detail=(
                "the selected render did not pass measured QC — inspect the "
                "render dead-letter, fix the cause and re-render before scheduling"
            ),
        )
    # v0.28: NULL means the render was registered without a capture. An
    # unreviewed capture is not evidence of redaction; fail closed.
    if render["redaction_reviewed"] is not True:
        raise HTTPException(
            status_code=409,
            detail="latest render has no capture that passed redaction review (§4)",
        )

    scripts = await pool.fetch(
        "SELECT version, markdown FROM offer_scripts "
        "WHERE offer_id = $1 AND language = $2 ORDER BY version DESC LIMIT 1",
        offer_id, body.language,
    )
    version_hash = script_version_hash(scripts[0]["markdown"]) if scripts else None
    # Fail at scheduling time, not hours later in the publisher: the pinned
    # render must have been produced from the exact script a reviewer approved.
    if not render.get("script_version_hash"):
        raise HTTPException(
            status_code=409,
            detail="the selected render has no approved script hash — re-render it",
        )
    if not version_hash or render["script_version_hash"] != version_hash:
        raise HTTPException(
            status_code=409,
            detail="the selected render was made from a different script version — "
                   "re-render the current approved script before scheduling",
        )

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
            SELECT id, kind, platform, language, variant_key, status, payload::text AS payload
            FROM content_variants
            WHERE id = $1 AND offer_id = $2
            """,
            body.content_variant_id, offer_id,
        )
        if not variant:
            raise HTTPException(status_code=404, detail="content variant not found for this offer")
        if variant["kind"] != "metadata":
            raise HTTPException(status_code=409, detail="only metadata variants can be scheduled")
        if variant["status"] != "approved":
            raise HTTPException(
                status_code=409,
                detail="metadata variant is not approved — approve it in Content Studio first",
            )
        if variant["platform"] not in (None, body.platform):
            raise HTTPException(status_code=409, detail="content variant belongs to another platform")
        if variant["language"] != body.language:
            raise HTTPException(status_code=409, detail="content variant belongs to another language")
        try:
            metadata = json.loads(variant["payload"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="content variant payload is invalid") from exc
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=409, detail="content variant payload is invalid")
        # Instagram/TikTok have no separate title field; the caption first line
        # is the hook. Every platform still needs a non-empty approved caption.
        missing_title = (PLATFORM_LIMITS[body.platform]["title"] > 0
                         and not str(metadata.get("title") or "").strip())
        if missing_title or not str(metadata.get("caption") or "").strip():
            raise HTTPException(
                status_code=409,
                detail="content variant payload is missing an approved title or caption",
            )
        scheduled_variant_key = variant["variant_key"]
    else:
        correction_base = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
        # Trend-bridged hashtags (WP-E): keywords from the trend row that
        # produced this topic — cited, never invented — plus the measured
        # hashtag performance rollup so underperforming tags sink.
        trend_keywords, hashtag_perf = await asyncio.gather(
            _trend_keywords_for_offer(pool, offer_id),
            _hashtag_performance(pool, body.platform),
        )
        metadata = platform_metadata(
            body.platform, dict(offer), [r["url"] for r in evidence],
            json.loads(render["disclosure"]) if render["disclosure"] else {},
            correction_url=f"{correction_base}/offers/{offer_id}" if correction_base else None,
            website_url=website,
            # English-first: the public package stays in the configured copy
            # language even when the voiceover is Urdu.
            language=language_policy["metadata_language"],
            variant=body.metadata_variant,
            trend_keywords=trend_keywords,
            hashtag_performance=hashtag_perf,
        )

    # Captions can legitimately differ from the voiceover language: the
    # default policy keeps English on-screen captions for an Urdu voiceover.
    # Pin the language of the actual SRT so YouTube labels the track correctly.
    metadata.setdefault("captions_language", language_policy["captions_language"])

    cover_path = body.cover_path or render["cover_path"]
    pinned_comment = body.pinned_comment or metadata.get("pinned_comment")

    # YouTube chapters are part of the reviewable package, not a post-upload
    # edit. Build them from the render's deterministic beat sheet so the
    # metadata hash the reviewer approves is exactly what gets uploaded.
    render_metadata = _json_value(render.get("render_metadata"), {})
    if body.platform == "youtube":
        metadata = _attach_youtube_chapters(
            metadata,
            render_metadata.get("beats") or [],
            render.get("duration_s"),
            language_policy["metadata_language"],
        )
        pinned_comment = body.pinned_comment or metadata.get("pinned_comment")

    account_id = await _pin_platform_account(pool, body.platform, body.platform_account_id)

    # Hashing can read large media files — keep it off the event loop.
    render_sha256 = render.get("video_sha256") or await asyncio.to_thread(
        _hash_local, render.get("video_path"))
    cover_sha256 = render.get("cover_sha256") or await asyncio.to_thread(
        _hash_local, cover_path)
    captions_sha256 = render.get("captions_sha256") or await asyncio.to_thread(
        _hash_local, render.get("captions_path"))
    metadata_hash = _canonical_hash(metadata)
    package_hash = _canonical_hash({
        "offer_id": str(offer_id),
        "platform": body.platform,
        "account_id": str(account_id) if account_id else None,
        "render_id": str(render["id"]),
        "render_sha256": render_sha256,
        "metadata_hash": metadata_hash,
        "cover_sha256": cover_sha256,
        "captions_sha256": captions_sha256,
        "script_version_hash": version_hash,
        "language": body.language,
        "privacy": body.privacy,
        "caption_variant": body.caption_variant,
        "metadata_variant": scheduled_variant_key,
        "pinned_comment": pinned_comment,
        "youtube_playlist_id": body.youtube_playlist_id,
    })

    idempotency_key = (
        f"{offer_id}:{body.platform}:{body.local_time.isoformat()}:"
        f"{body.language}:{body.caption_variant}:{body.metadata_variant}:"
        f"{body.content_variant_id or ''}:{version_hash or ''}:"
        f"{render['id']}:{account_id or ''}"
    )
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO schedules (offer_id, platform, local_time, timezone, privacy,
                                   caption_variant, idempotency_key, version_hash, metadata,
                                   language, content_variant_id, cover_path, pinned_comment,
                                   metadata_variant, render_id, platform_account_id,
                                   package_hash, render_sha256, metadata_hash, cover_sha256,
                                   captions_sha256, youtube_playlist_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20, $21, $22)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, state::text AS state, idempotency_key
            """,
            offer_id, body.platform, body.local_time, body.timezone, body.privacy,
            body.caption_variant, idempotency_key, version_hash, json.dumps(metadata),
            body.language, body.content_variant_id, cover_path, pinned_comment,
            scheduled_variant_key, render["id"], account_id, package_hash, render_sha256,
            metadata_hash, cover_sha256, captions_sha256, body.youtube_playlist_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Never echo database error text to the caller; log it server-side.
        _logger.exception("schedule insert failed for offer %s", offer_id)
        raise HTTPException(
            status_code=500,
            detail="schedule could not be created — check server logs",
        ) from exc

    if not row:  # identical schedule already exists — idempotent re-submit
        existing = await pool.fetchrow(
            "SELECT id, state::text AS state FROM schedules WHERE idempotency_key = $1",
            idempotency_key,
        )
        return {"id": existing["id"], "state": existing["state"], "created": False,
                "idempotency_key": idempotency_key}

    await _audit(pool, actor=actor or "reviewer",
                 action="create_schedule", entity="schedules",
                 entity_id=row["id"], detail={"platform": body.platform,
                                              "privacy": body.privacy,
                                              "language": body.language,
                                              "metadata_variant": scheduled_variant_key})

    # Durable owed-work record (§8.A): the queue gains a row when the post
    # actually enters the queue (the 'scheduled' transition, see
    # _enqueue_publish_job). A draft is not owed publishing work — a
    # create-time job would be claimed against a draft, fail its gates, retry
    # and dead-letter into attention as noise.
    return {"id": row["id"], "state": row["state"], "created": True,
            "idempotency_key": idempotency_key, "language": body.language,
            "metadata_language": metadata.get("language", language_policy["metadata_language"]),
            "cover_path": cover_path, "pinned_comment": pinned_comment,
            "metadata_variant": scheduled_variant_key, "metadata": metadata,
            "render_id": str(render["id"]), "render_preset": render["preset"],
            "package_hash": package_hash,
            "render_sha256": render_sha256, "metadata_hash": metadata_hash,
            "cover_sha256": cover_sha256, "captions_sha256": captions_sha256,
            "platform_account_id": str(account_id) if account_id else None}


@router.post("/offers/{offer_id}/schedules", status_code=201)
async def create_schedule(offer_id: uuid.UUID, body: ScheduleIn, request: Request) -> dict:
    pool = db.get()
    actor = effective_reviewer(request, None, default="reviewer")
    return await _create_one_schedule(pool, offer_id, body, actor)


# ---------------------------------------------------------------- batch (WP-D)


class PlatformOverrideIn(BaseModel):
    """Per-platform overrides on top of the shared batch body. Anything set
    here wins for that platform only — pins (render/account/playlist) stay
    per-platform by nature; the release gates stay shared."""

    local_time: Optional[datetime] = None
    privacy: Optional[str] = None
    caption_variant: Optional[str] = None
    language: Optional[str] = None
    content_variant_id: Optional[uuid.UUID] = None
    metadata_variant: Optional[str] = None
    cover_path: Optional[str] = None
    pinned_comment: Optional[str] = None
    website_url: Optional[str] = None
    platform_account_id: Optional[uuid.UUID] = None
    youtube_playlist_id: Optional[str] = None
    render_id: Optional[uuid.UUID] = None


class BatchScheduleIn(BaseModel):
    """One click → the same verified package on several platforms (WP-D).

    `platforms` is the target list; every row goes through the exact single-
    schedule gates (approved offer, QC-passed render, redaction-reviewed
    capture, script-hash match, metadata validation). Repeats are idempotent
    per row via the existing idempotency key.
    """

    platforms: list[str] = Field(min_length=1, max_length=8)
    local_time: datetime
    timezone: str = "Asia/Karachi"
    language: str = "en"
    privacy: str = "private"
    caption_variant: str = "default"
    metadata_variant: str = "default"
    content_variant_id: Optional[uuid.UUID] = None
    cover_path: Optional[str] = None
    pinned_comment: Optional[str] = None
    website_url: Optional[str] = None
    render_id: Optional[uuid.UUID] = None
    platform_account_id: Optional[uuid.UUID] = None
    youtube_playlist_id: Optional[str] = None
    # Per-platform overrides, keyed by platform name.
    per_platform: dict[str, PlatformOverrideIn] = Field(default_factory=dict)


@router.post("/offers/{offer_id}/schedules/batch", status_code=207)
async def create_schedules_batch(offer_id: uuid.UUID, body: BatchScheduleIn,
                                 request: Request) -> dict:
    """Schedule the same render on several platforms in one action.

    207 multi-status: `results` carries one entry per platform with ok/id or
    the exact gate refusal — a TikTok-specific failure never blocks YouTube.
    """
    pool = db.get()
    actor = effective_reviewer(request, None, default="reviewer")
    results: list[dict] = []
    created = 0
    for platform in dict.fromkeys(body.platforms):  # dedupe, keep order
        override = body.per_platform.get(platform)
        single = ScheduleIn(
            platform=platform,
            local_time=(override.local_time if override and override.local_time
                        else body.local_time),
            timezone=body.timezone,
            language=(override.language if override and override.language
                      else body.language),
            privacy=(override.privacy if override and override.privacy
                     else body.privacy),
            caption_variant=(override.caption_variant if override and override.caption_variant
                             else body.caption_variant),
            metadata_variant=(override.metadata_variant if override and override.metadata_variant
                              else body.metadata_variant),
            content_variant_id=(override.content_variant_id if override
                                and override.content_variant_id is not None
                                else body.content_variant_id),
            cover_path=(override.cover_path if override and override.cover_path
                        else body.cover_path),
            pinned_comment=(override.pinned_comment if override and override.pinned_comment
                            else body.pinned_comment),
            website_url=(override.website_url if override and override.website_url
                         else body.website_url),
            render_id=(override.render_id if override and override.render_id is not None
                       else body.render_id),
            platform_account_id=(override.platform_account_id if override
                                 and override.platform_account_id is not None
                                 else body.platform_account_id),
            youtube_playlist_id=(override.youtube_playlist_id if override
                                 and override.youtube_playlist_id is not None
                                 else body.youtube_playlist_id),
        )
        try:
            row = await _create_one_schedule(pool, offer_id, single, actor)
        except HTTPException as exc:
            results.append({"platform": platform, "ok": False,
                            "detail": exc.detail, "status": exc.status_code})
            continue
        created += 1 if row.get("created") else 0
        results.append({"platform": platform, "ok": True, **row})
    return {
        "created": created,
        "requested": len(body.platforms),
        "ok": all(r["ok"] for r in results),
        "results": results,
    }


class BatchTransitionIn(BaseModel):
    """Approve / queue several posts at once — a HUMAN batch action.

    The per-schedule transition rules, attempt acknowledgment and audit stay
    exactly the single-transition ones (`_transition`); this endpoint only
    decides WHEN, one transaction per id, per-id results. Service credentials
    are refused here outright: bulk approval is by definition a human decision
    (automation approval has its own budgeted, guardrailed path)."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    to: str
    reviewer: Optional[str] = None
    note: Optional[str] = None
    acknowledge_unknown_attempt: bool = False


@router.post("/schedules/batch-transition")
async def batch_transition(body: BatchTransitionIn, request: Request) -> dict:
    if credential_class(request) not in (CREDENTIAL_REVIEWER, CREDENTIAL_DISABLED):
        raise HTTPException(
            status_code=403,
            detail="batch transitions are a human action — use a reviewer credential",
        )
    pool = db.get()
    results: list[dict] = []
    for schedule_id in dict.fromkeys(body.ids):
        single = ScheduleTransitionIn(
            to=body.to, reviewer=body.reviewer, note=body.note,
            acknowledge_unknown_attempt=body.acknowledge_unknown_attempt,
        )
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await _transition(conn, schedule_id, single, request)
            results.append({"id": str(schedule_id), "ok": True, **row})
        except HTTPException as exc:
            results.append({"id": str(schedule_id), "ok": False,
                            "detail": exc.detail, "status": exc.status_code})
    return {
        "to": body.to,
        "ok": all(r["ok"] for r in results),
        "approved": sum(1 for r in results if r["ok"]),
        "results": results,
    }


# ---------------------------------------------------------------- calendar


@router.get("/schedules")
async def list_schedules(
    response: Response,
    state: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    after_time = decode_datetime(parts[0]) if parts else None
    after_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT s.id, s.offer_id, o.title AS offer_title, o.provider AS offer_provider,
               s.platform, s.state::text AS state, s.local_time, s.timezone,
               s.privacy, s.caption_variant, s.version_hash, s.approved_by,
               s.metadata::text AS metadata, s.language, s.content_variant_id,
               s.cover_path, s.pinned_comment, s.metadata_variant,
               s.render_id, s.platform_account_id, s.package_hash, s.render_sha256,
               s.metadata_hash, s.cover_sha256, s.captions_sha256,
               s.youtube_playlist_id, s.remote_url, s.remote_processing_state,
               s.remote_privacy, s.published_confirmed_at, s.remote_metadata::text AS remote_metadata,
               s.retry_count, s.updated_at, s.description_patched_at,
               s.remote_post_id, s.outcome_detail::text AS outcome_detail, s.created_at
        FROM schedules s JOIN offers o ON o.id = s.offer_id
        WHERE ($1::text IS NULL OR s.state::text = $1)
          AND ($3::timestamptz IS NULL
               OR (s.local_time, s.id) > ($3::timestamptz, $4::uuid))
        ORDER BY s.local_time, s.id
        LIMIT $2
        """,
        state if state in ("draft", "needs_approval", "approved", "scheduled",
                           "published", "failed", "paused") else None,
        limit,
        after_time,
        after_id,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["local_time"], row["id"]),
    )
    return out


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
    # One transaction for validate + write: concurrent transitions lock the
    # same row (FOR UPDATE below) instead of check-then-acting on a stale read
    # and silently overwriting each other's state/pins.
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await _transition(conn, schedule_id, body, request)


async def _enqueue_publish_job(pool, schedule_id: uuid.UUID) -> None:
    """Durable owed-work record (§8.A) — armed when a post ENTERS the queue.

    The outbox-style job row is what makes owed publishing work visible after a
    restart (or an operator reading the attention view), instead of only
    polling row state. Idempotent per (schedule, package).
    """
    await pool.execute(
        """
        INSERT INTO jobs (kind, entity_id, payload, dedupe_key, max_attempts, run_after)
        SELECT 'publish_schedule', s.id,
               json_build_object('platform', s.platform, 'language', s.language,
                                 'package_hash', s.package_hash),
               'publish:' || s.id::text || ':' || COALESCE(s.package_hash, ''),
               3, COALESCE(s.local_time, now())
        FROM schedules s
        WHERE s.id = $1
        ON CONFLICT (dedupe_key) DO NOTHING
        """,
        schedule_id,
    )


async def _transition(pool, schedule_id: uuid.UUID, body: ScheduleTransitionIn,
                      request: Request) -> dict:
    # Lock the row first: validation below runs against the committed state,
    # and a concurrent transition blocks here until this transaction finishes.
    locked_state = await pool.fetchval(
        "SELECT state::text FROM schedules WHERE id = $1 FOR UPDATE", schedule_id)
    if locked_state is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    schedule = await _load(pool, schedule_id)
    reviewer_on_record = effective_reviewer(request, body.reviewer)
    policy = await load_policy()

    # Approval and queue entry are human decisions unless an explicit
    # automation:<stage> actor is authorized below. A service/worker credential
    # cannot name a person via the request body.
    if body.to in ("approved", "scheduled") and not is_automation_actor(reviewer_on_record) \
            and credential_class(request) not in (CREDENTIAL_REVIEWER, CREDENTIAL_DISABLED):
        raise HTTPException(
            status_code=403,
            detail=(
                f"schedule transition to '{body.to}' requires a human reviewer "
                "credential (or an authorized automation:<stage> actor)"
            ),
        )

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
            # The daily budget is "non-negotiable, enforced server-side" — so
            # count it inside this transaction behind an advisory lock.
            # Check-then-act with a separate count let N concurrent automation
            # approvals all read `used < limit` and exceed the cap (TOCTOU).
            await pool.execute(
                "SELECT pg_advisory_xact_lock(hashtext('mtk-automation-approved-budget'))")
            used = int(await pool.fetchval(
                """
                SELECT COUNT(*) FROM schedules
                WHERE approved_by LIKE 'automation:%'
                  AND updated_at >= date_trunc('day', now())
                """
            ) or 0)
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
        current_hash = await _current_script_hash(
            pool, schedule["offer_id"], schedule.get("language") or "en")
        if not current_hash:
            raise HTTPException(status_code=409, detail="no script exists to approve")
        params.append(current_hash)
        sets.append(f"version_hash = ${len(params)}")
        if reviewer_on_record:
            params.append(reviewer_on_record)
            sets.append(f"approved_by = ${len(params)}")

    if body.to == "scheduled":
        expected = await _current_script_hash(
            pool, schedule["offer_id"], schedule.get("language") or "en")
        if schedule["version_hash"] != expected:
            raise HTTPException(
                status_code=409,
                detail="script changed since approval — reapproval required (§17)",
            )
        # Revalidate the offer snapshot at scheduling time (§17). This is a
        # release gate, not an observation: a stale/expired offer must not be
        # stored as "scheduled with offer_evidence_ok=false". The operator gets
        # an actionable reason and the schedule stays in its prior state.
        problem = await _schedule_offer_problem(pool, schedule["offer_id"])
        if problem:
            raise HTTPException(
                status_code=409,
                detail=f"schedule blocked: {problem}; re-verify the offer, then schedule again (§17)",
            )
        params.append(True)
        sets.append(f"offer_evidence_ok = ${len(params)}")

    resolved_attempt = None
    if body.to == "scheduled":
        current_detail = _json_value(schedule.get("outcome_detail"), {})
        open_attempt = current_detail.get("attempt") \
            if isinstance(current_detail, dict) else None
        if isinstance(open_attempt, dict):
            if not body.acknowledge_unknown_attempt:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "an upload attempt has no recorded outcome — the post may "
                        "already be live. Verify it on the platform, then resend "
                        "with acknowledge_unknown_attempt=true to requeue, or leave "
                        "it paused (duplicate protection)."
                    ),
                )
            resolved_attempt = {
                "started_at": open_attempt.get("started_at"),
                "resolved_by": reviewer_on_record or "operator",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
            params.append(json.dumps({"hold": False,
                                      "attempt_resolved": resolved_attempt}))
            sets.append(f"outcome_detail = (outcome_detail - 'attempt') || "
                        f"${len(params)}::jsonb")
        else:
            # a post that was HELD (unknown upload outcome) is being re-queued
            # by a human decision — clear the hold so it may go out (v0.23)
            sets.append("outcome_detail = outcome_detail || '{\"hold\": false}'::jsonb")

    row = await pool.fetchrow(
        f"UPDATE schedules SET {', '.join(sets)}, updated_at = now() "
        f"WHERE id = $1 RETURNING state::text AS state, version_hash",
        *params,
    )
    if body.to == "scheduled":
        await _enqueue_publish_job(pool, schedule_id)
        await _rearm_publish_job(pool, schedule_id)
    await _audit(pool, actor=reviewer_on_record or "operator",
                 action=f"schedule:{schedule['state']}->{body.to}",
                 entity="schedules", entity_id=schedule_id,
                 detail={"note": body.note, "attempt_resolved": resolved_attempt})
    return {"id": schedule_id, "state": row["state"], "version_hash": row["version_hash"]}


@router.post("/schedules/{schedule_id}/pause")
async def pause(schedule_id: uuid.UUID, note: Optional[str] = None,
                request: Request = None) -> dict:
    """Operator-visible pause — available while a post is still actionable.

    `failed` is included so a worker can record a held failure first and then
    move the post to `paused` without losing the reason (failed → paused is an
    allowed transition).
    """
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] not in ("approved", "scheduled", "failed"):
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
                 acknowledge_unknown_attempt: bool = Query(default=False),
                 request: Request = None) -> dict:
    """Resume revalidates the version hash — modified content stays paused.

    Resuming a paused post is always a human decision: a paused post may be
    paused because the offer expired, a correction landed, or an upload's
    outcome is unknown. Automation must never put it back in the publishing
    queue on its own.
    """
    actor = effective_reviewer(request, reviewer, require=True)
    if is_automation_actor(actor):
        raise HTTPException(
            status_code=403,
            detail="automation may not resume a paused post — a named human must decide",
        )
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] != "paused":
        raise HTTPException(status_code=409, detail=f"cannot resume from '{schedule['state']}'")
    current_detail = _json_value(schedule.get("outcome_detail"), {})
    open_attempt = current_detail.get("attempt") \
        if isinstance(current_detail, dict) else None
    if isinstance(open_attempt, dict) and not acknowledge_unknown_attempt:
        raise HTTPException(
            status_code=409,
            detail=(
                "an upload attempt has no recorded outcome — the post may already "
                "be live. Verify it on the platform, then resume with "
                "acknowledge_unknown_attempt=true (duplicate protection)."
            ),
        )
    expected = await _current_script_hash(
        pool, schedule["offer_id"], schedule.get("language") or "en")
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
    await _rearm_publish_job(pool, schedule_id)
    # A human resumed the post: clear the hold so the worker may try again.
    # If an unknown attempt marker was explicitly acknowledged, clear it too
    # and keep an audit trail of who made that call.
    if isinstance(open_attempt, dict):
        resolution = {
            "hold": False,
            "attempt_resolved": {
                "started_at": open_attempt.get("started_at"),
                "resolved_by": actor,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        await pool.execute(
            "UPDATE schedules SET outcome_detail = "
            "(outcome_detail - 'attempt') || $2::jsonb, updated_at = now() "
            "WHERE id = $1",
            schedule_id, json.dumps(resolution),
        )
    else:
        await pool.execute(
            "UPDATE schedules SET outcome_detail = outcome_detail || '{\"hold\": false}'::jsonb, "
            "updated_at = now() WHERE id = $1",
            schedule_id,
        )
    await _audit(pool, actor=actor, action="schedule:resume",
                 entity="schedules", entity_id=schedule_id,
                 detail={"attempt_resolved": isinstance(open_attempt, dict)})
    return {"id": schedule_id, "state": row["state"]}


class AttemptIn(BaseModel):
    """The worker atomically claims an upload before it starts (v0.23/v0.28).

    If the worker dies mid-upload, the marker stays open: the next sweep knows
    the outcome is UNKNOWN and holds the post for a human instead of
    publishing a duplicate. An expired lease is NOT stolen automatically —
    the upload may have reached the platform even if the worker died."""
    detail: Optional[str] = None
    worker: Optional[str] = None
    lease_s: int = Field(default=900, ge=60, le=3600)


@router.post("/schedules/{schedule_id}/attempt")
async def attempt(schedule_id: uuid.UUID, body: AttemptIn) -> dict:
    """Atomically claim an upload attempt. Exactly one worker can hold it.

    The kill switch is enforced HERE, not only at sweep start: pausing
    automation must refuse a fresh upload authorization even if a worker is
    already mid-sweep.
    """
    pool = db.get()
    policy = await load_policy()
    if policy.get("paused") or policy.get("dry_run"):
        raise HTTPException(
            status_code=409,
            detail="upload authorization refused: automation is "
                   + ("paused" if policy.get("paused") else "in dry-run mode"),
        )
    # One authoritative release check (§17). Upload authorization used to
    # verify only the automation policy; freshness, package completeness and
    # playback sign-off were checked (differently) elsewhere or not at all.
    problems = await release_problems(pool, schedule_id)
    if problems:
        raise HTTPException(
            status_code=409,
            detail="release gate refused upload authorization: "
                   + describe_problems(problems),
        )
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(schedule_id))
            schedule = await conn.fetchrow(
                "SELECT state::text AS state, outcome_detail::text AS outcome_detail "
                "FROM schedules WHERE id = $1 FOR UPDATE",
                schedule_id,
            )
            if not schedule:
                raise HTTPException(status_code=404, detail="schedule not found")
            if schedule["state"] != "scheduled":
                raise HTTPException(
                    status_code=409,
                    detail=f"attempts only apply to scheduled posts (current: {schedule['state']})",
                )
            detail = _json_value(schedule["outcome_detail"], {})
            existing = detail.get("attempt") if isinstance(detail, dict) else None
            if isinstance(existing, dict):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "an upload attempt is already open "
                        f"(started {existing.get('started_at')}) — verify the platform "
                        "before clearing it"
                    ),
                )
            now = datetime.now(timezone.utc)
            token = uuid.uuid4().hex
            marker = {
                "token": token,
                "started_at": now.isoformat(),
                "lease_expires_at": (now + timedelta(seconds=body.lease_s)).isoformat(),
                "detail": body.detail,
                "worker": body.worker or "publishing-worker",
            }
            await conn.execute(
                "UPDATE schedules SET outcome_detail = outcome_detail || $2::jsonb, "
                "updated_at = now() WHERE id = $1",
                schedule_id, json.dumps({"attempt": marker}),
            )
    return {"id": str(schedule_id), "acquired": True,
            "attempt_token": token, "attempt": marker}


@router.get("/schedules/{schedule_id}/release-check")
async def release_check(schedule_id: uuid.UUID) -> dict:
    """Preview the release gate for a scheduled post (§17).

    The same check the upload authorization runs. The dashboard renders this
    as the package/readiness card; automation and a human see the same list,
    so "why is this held?" is never a guess.
    """
    problems = await release_problems(db.get(), schedule_id)
    return {
        "id": str(schedule_id),
        "ok": not problems,
        "problems": problems,
    }


class ScheduleCancelIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


@router.post("/schedules/{schedule_id}/cancel")
async def cancel_schedule(schedule_id: uuid.UUID, body: ScheduleCancelIn,
                          request: Request) -> dict:
    """Withdraw a queued post without pretending it failed (§17).

    Cancelling is a human editorial decision (and unlike a failure, it is
    terminal): retries and automation never touch a cancelled post. The note
    is recorded in the audit trail against the reviewer.
    """
    actor = effective_reviewer(request, None, require=True)
    pool = db.get()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state::text AS state FROM schedules WHERE id = $1 FOR UPDATE",
            schedule_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="schedule not found")
        if row["state"] in ("published", "cancelled"):
            raise HTTPException(
                status_code=409,
                detail=f"a {row['state']} post cannot be cancelled",
            )
        await conn.execute(
            "UPDATE schedules SET state = 'cancelled', "
            "outcome_detail = outcome_detail || $2::jsonb, updated_at = now() "
            "WHERE id = $1",
            schedule_id,
            json.dumps({"cancelled_by": actor, "cancel_note": body.note}),
        )
    await audit_actor_note(pool, schedule_id, actor, body.note)
    return {"id": str(schedule_id), "state": "cancelled", "by": actor}


class ScheduleRescheduleIn(BaseModel):
    local_time: datetime
    timezone: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/schedules/{schedule_id}/reschedule")
async def reschedule_schedule(schedule_id: uuid.UUID, body: ScheduleRescheduleIn,
                              request: Request) -> dict:
    """Move a queued post to a new publish time (human editorial decision).

    Keeps the review package and all pins intact — only the slot changes —
    and re-arms the durable publish job so the queue wakes the worker at the
    new time, not the old one. Works from scheduled/paused/failed; a published
    or cancelled post is not actionable. Automation may not reschedule: a
    moved slot is an operator decision about audiences, not a retry.
    """
    actor = effective_reviewer(request, None, require=True)
    pool = db.get()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state::text AS state, local_time FROM schedules "
            "WHERE id = $1 FOR UPDATE",
            schedule_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="schedule not found")
        if row["state"] not in ("scheduled", "paused", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"a {row['state']} post cannot be rescheduled",
            )
        if body.local_time <= datetime.now(timezone.utc) - timedelta(minutes=1):
            raise HTTPException(
                status_code=422,
                detail="reschedule target must be in the future — cancel instead "
                       "of queuing a post in the past",
            )
        updated = await conn.fetchrow(
            """
            UPDATE schedules
            SET local_time = $2,
                timezone = COALESCE($3, timezone),
                updated_at = now()
            WHERE id = $1
            RETURNING state::text AS state, local_time
            """,
            schedule_id, body.local_time, body.timezone,
        )
        # keep the durable publish job in lockstep with the new slot
        await _rearm_publish_job(pool, schedule_id)
    await audit_actor_note(pool, schedule_id, actor, body.note)
    return {
        "id": str(schedule_id),
        "state": updated["state"],
        "local_time": updated["local_time"].isoformat(),
        "rescheduled_by": actor,
    }


async def audit_actor_note(pool, schedule_id: uuid.UUID, actor: str, note: str) -> None:
    from settings_store import audit
    await audit(pool, actor=actor, action="schedule:cancel", entity="schedules",
                detail={"schedule_id": str(schedule_id), "note": note})


class ScheduleReconcileIn(BaseModel):
    """A human decision after checking the platform for a held upload.

    The publishing worker cannot resolve an unknown outcome (it may have
    uploaded before dying). Only a reviewer may say "it is live" or "it is not
    live", and that decision is recorded against their identity.
    """

    outcome: str = Field(pattern="^(published|not_live|still_processing)$")
    remote_post_id: Optional[str] = Field(default=None, max_length=500)
    remote_url: Optional[str] = Field(default=None, max_length=2000)
    note: str = Field(min_length=3, max_length=2000)


@router.post("/schedules/{schedule_id}/reconcile")
async def reconcile_held_upload(schedule_id: uuid.UUID, body: ScheduleReconcileIn,
                                request: Request) -> dict:
    """Resolve a HELD/unknown upload after a human checks the platform.

    This is deliberately separate from the worker result endpoint:
    - `published` requires the remote post id the human actually saw;
    - `not_live` clears the open attempt so a deliberate retry is safe;
    - `still_processing` keeps the hold and the attempt marker intact.
    """
    actor = effective_reviewer(request, None, require=True)
    if is_automation_actor(actor):
        raise HTTPException(
            status_code=403,
            detail="automation may not reconcile an unknown upload — a named human must check the platform",
        )
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] not in ("scheduled", "paused", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot reconcile a post in state '{schedule['state']}'",
        )
    detail = _json_value(schedule.get("outcome_detail"), {})
    open_attempt = detail.get("attempt") if isinstance(detail, dict) else None
    held = bool(detail.get("hold")) if isinstance(detail, dict) else False
    if not held and not isinstance(open_attempt, dict):
        raise HTTPException(
            status_code=409,
            detail="this post is not held; there is no unknown upload outcome to reconcile",
        )
    if body.outcome == "published" and not body.remote_post_id:
        raise HTTPException(
            status_code=422,
            detail="confirming a held upload as published requires the remote post id you verified",
        )

    now = datetime.now(timezone.utc).isoformat()
    if body.outcome == "published":
        patch = {
            "hold": False,
            "attempt": None,
            "detail": body.note,
            "reconciled_by": actor,
            "reconciled_at": now,
            "reconcile_outcome": body.outcome,
        }
        row = await pool.fetchrow(
            """
            UPDATE schedules
            SET state = 'published', remote_post_id = $2,
                remote_url = COALESCE($3, remote_url),
                published_confirmed_at = now(),
                outcome_detail = (outcome_detail - 'attempt') || $4::jsonb,
                updated_at = now()
            WHERE id = $1
            RETURNING state::text AS state, remote_post_id
            """,
            schedule_id, body.remote_post_id, body.remote_url, json.dumps(patch),
        )
    elif body.outcome == "not_live":
        patch = {
            "hold": False,
            "attempt": None,
            "detail": body.note,
            "reconciled_by": actor,
            "reconciled_at": now,
            "reconcile_outcome": body.outcome,
        }
        row = await pool.fetchrow(
            """
            UPDATE schedules
            SET state = 'failed', retry_count = retry_count + 1,
                outcome_detail = (outcome_detail - 'attempt') || $2::jsonb,
                updated_at = now()
            WHERE id = $1
            RETURNING state::text AS state, remote_post_id
            """,
            schedule_id, json.dumps(patch),
        )
    else:
        # Still processing: keep the post out of the queue and preserve the
        # open attempt so a later human decision remains explicit.
        patch = {
            "hold": True,
            "detail": body.note,
            "reconciled_by": actor,
            "reconciled_at": now,
            "reconcile_outcome": body.outcome,
        }
        row = await pool.fetchrow(
            """
            UPDATE schedules
            SET state = 'paused', outcome_detail = outcome_detail || $2::jsonb,
                updated_at = now()
            WHERE id = $1
            RETURNING state::text AS state, remote_post_id
            """,
            schedule_id, json.dumps(patch),
        )
    if body.outcome in ("published", "not_live"):
        # A definite human outcome ends the resumable capability. `still
        # processing` keeps it in case the worker/reviewer needs to resume.
        await pool.execute(
            "DELETE FROM upload_sessions WHERE schedule_id = $1", schedule_id)
    await _audit(pool, actor=actor, action=f"schedule:reconcile:{body.outcome}",
                 entity="schedules", entity_id=schedule_id,
                 detail={"note": body.note, "remote_post_id": body.remote_post_id,
                         "remote_url": body.remote_url})
    return {"id": schedule_id, "state": row["state"],
            "remote_post_id": row["remote_post_id"], "outcome": body.outcome}


@router.post("/schedules/{schedule_id}/result")
async def result(schedule_id: uuid.UUID, body: ScheduleResultIn) -> dict:
    """Publishing worker reports outcomes (idempotent by remote post id).

    v0.28: a success must be a CONFIRMED remote publication. For YouTube the
    worker only sends ok=true after videos.list reports the video processed
    with the expected privacy. An unconfirmed upload is reported as a held
    failure, never as published.
    """
    pool = db.get()
    schedule = await _load(pool, schedule_id)
    if schedule["state"] not in ("scheduled", "failed", "paused"):
        raise HTTPException(
            status_code=409,
            detail=f"results only accepted for scheduled/failed/paused posts "
                   f"(current: {schedule['state']})",
        )
    if body.ok and schedule["state"] == "paused":
        raise HTTPException(
            status_code=409,
            detail="a paused post cannot be marked published — resume it first",
        )
    if body.ok and not body.remote_post_id:
        raise HTTPException(status_code=400, detail="successful publish requires remote_post_id")
    if body.ok and not body.confirmed:
        raise HTTPException(
            status_code=409,
            detail="remote publication is not confirmed — refusing to mark the post published",
        )

    # A failure reported against a paused post records why it is paused and
    # keeps the paused state; it must not silently requeue the post.
    new_state = "published" if body.ok else "failed"
    # a definite outcome clears any open "attempt" marker (the upload either
    # succeeded or failed — retrying is safe). The token prevents one worker
    # from clearing another worker's in-flight claim.
    outcome = {"detail": body.detail, "reported_at": datetime.now(timezone.utc).isoformat(),
               "attempt": None, "hold": bool(body.hold)}
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(schedule_id))
            current = await conn.fetchrow(
                "SELECT state::text AS state, outcome_detail::text AS outcome_detail "
                "FROM schedules WHERE id = $1 FOR UPDATE",
                schedule_id,
            )
            if not current or current["state"] not in ("scheduled", "failed", "paused"):
                raise HTTPException(
                    status_code=409,
                    detail="schedule changed while the result was being recorded",
                )
            if body.ok and current["state"] == "paused":
                raise HTTPException(
                    status_code=409,
                    detail="schedule was paused while the result was being recorded",
                )
            if not body.ok and current["state"] == "paused":
                new_state = "paused"
            current_detail = _json_value(current["outcome_detail"], {})
            open_attempt = current_detail.get("attempt") if isinstance(current_detail, dict) else None
            if isinstance(open_attempt, dict):
                expected_token = open_attempt.get("token")
                if not expected_token or body.attempt_token != expected_token:
                    # A held ADVISORY is not an outcome: the worker may need to
                    # explain why an open attempt must be checked by a human.
                    # Record the reason but keep the attempt marker intact so a
                    # blind retry is still impossible.
                    if body.ok or not body.hold or body.attempt_token:
                        raise HTTPException(
                            status_code=409,
                            detail="result does not match the open upload attempt token",
                        )
                    advisory = {
                        "detail": body.detail,
                        "reported_at": datetime.now(timezone.utc).isoformat(),
                        "hold": True,
                    }
                    await conn.execute(
                        "UPDATE schedules SET outcome_detail = outcome_detail || "
                        "$2::jsonb, updated_at = now() WHERE id = $1",
                        schedule_id, json.dumps(advisory),
                    )
                    return {
                        "id": str(schedule_id),
                        "state": current["state"],
                        "advisory": True,
                        "detail": "held reason recorded; the open upload attempt is preserved",
                    }
            if body.remote_post_id:
                await conn.execute(
                    """
                    UPDATE schedules
                    SET state = $2::schedule_state,
                        remote_post_id = COALESCE(NULLIF($3, ''), remote_post_id),
                        remote_url = COALESCE($4, remote_url),
                        remote_processing_state = COALESCE($5, remote_processing_state),
                        remote_privacy = COALESCE($6, remote_privacy),
                        remote_metadata = remote_metadata || $7::jsonb,
                        published_confirmed_at = CASE WHEN $2 = 'published' THEN now()
                                                      ELSE published_confirmed_at END,
                        retry_count = CASE WHEN $2 = 'failed' THEN retry_count + 1 ELSE retry_count END,
                        outcome_detail = outcome_detail || $8::jsonb,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    schedule_id, new_state, body.remote_post_id or "", body.remote_url,
                    body.remote_processing_state, body.remote_privacy,
                    json.dumps(body.remote_metadata, default=str), json.dumps(outcome),
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
    if body.ok:
        # Success is terminal for the resumable upload capability.
        await pool.execute(
            "DELETE FROM upload_sessions WHERE schedule_id = $1", schedule_id)
    await _audit(pool, actor="publishing-worker", action=f"result:{new_state}",
                 entity="schedules", entity_id=schedule_id,
                 detail={"remote_post_id": body.remote_post_id,
                         "remote_processing_state": body.remote_processing_state,
                         "confirmed": body.confirmed})
    return {"id": schedule_id, "state": new_state}


# ------------------------------------------------- audience metrics (v0.18)


async def _rollup_hashtag_performance(conn, platform: str) -> None:
    """Recompute the per-tag feedback rollup for this platform (WP-E).

    Derived entirely from `schedules.metadata->'hashtags' ⋈ post_metrics` —
    recomputable, never incrementally drifted. Tags on posts without metrics
    still count as posts (they were shipped); impressions only accrue from
    measured snapshots."""
    await conn.execute(
        """
        WITH tagged AS (
            SELECT s.id, s.platform, kv.value AS tag
            FROM schedules s
            CROSS JOIN LATERAL jsonb_array_elements_text(
                CASE WHEN jsonb_typeof(s.metadata->'hashtags') = 'array'
                     THEN s.metadata->'hashtags' ELSE '[]'::jsonb END
            ) AS kv
            WHERE s.platform = $1::text
        ),
        measured AS (
            SELECT pm.schedule_id,
                   MAX(pm.impressions) AS impressions,
                   MAX(pm.views) AS views
            FROM post_metrics pm
            WHERE pm.platform = $1::text
            GROUP BY pm.schedule_id
        )
        INSERT INTO hashtag_performance
            (platform, tag, posts, impressions_total, views_total,
             last_seen_at, updated_at)
        SELECT t.platform, t.tag,
               COUNT(m.schedule_id)::int,
               COALESCE(SUM(m.impressions), 0)::bigint,
               COALESCE(SUM(m.views), 0)::bigint,
               now(), now()
        FROM tagged t LEFT JOIN measured m ON m.schedule_id = t.id
        GROUP BY t.platform, t.tag
        ON CONFLICT (platform, tag) DO UPDATE
        SET posts = EXCLUDED.posts,
            impressions_total = EXCLUDED.impressions_total,
            views_total = EXCLUDED.views_total,
            last_seen_at = EXCLUDED.last_seen_at,
            updated_at = now()
        """,
        platform,
    )



class MetricsIn(BaseModel):
    """One audience-metrics snapshot from the metrics worker (master plan §7).
    Normalized fields feed analytics; `raw` keeps the provider payload."""
    platform: str = Field(pattern="^(youtube|facebook|instagram|tiktok)$")
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    impressions: Optional[int] = None
    avg_watch_s: Optional[float] = None
    avg_view_duration_s: Optional[float] = None
    avg_view_percentage: Optional[float] = None
    ctr: Optional[float] = None
    retention_3s: Optional[float] = None
    link_clicks: Optional[int] = None
    subscribers_gained: Optional[int] = None
    source: str = Field(min_length=3, max_length=64)
    raw: dict = Field(default_factory=dict)
    # Provenance (plan §7.F.5): which period/definition produced the numbers,
    # and what the provider refused. Unknown stays null, never guessed.
    report_start: Optional[date] = None
    report_end: Optional[date] = None
    metric_definition: Optional[str] = Field(default=None, max_length=256)
    degraded: bool = False
    degradation_detail: Optional[str] = Field(default=None, max_length=2000)
    # retention_3s is a nearest-bucket estimate unless the provider exposes an
    # exact measurement; the dashboard must qualify it (plan §7.F.6).
    retention_3s_estimated: bool = False


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
                    (schedule_id, platform, views, likes, comments, shares, impressions,
                     avg_watch_s, avg_view_duration_s, avg_view_percentage, ctr,
                     retention_3s, link_clicks, subscribers_gained, source, raw,
                     report_start, report_end, metric_definition, degraded,
                     degradation_detail, retention_3s_estimated)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                        $16::jsonb, $17, $18, $19, $20, $21, $22)
                """,
                schedule_id, body.platform, body.views, body.likes, body.comments,
                body.shares, body.impressions, body.avg_watch_s, body.avg_view_duration_s,
                body.avg_view_percentage, body.ctr, body.retention_3s, body.link_clicks,
                body.subscribers_gained, body.source, json.dumps(body.raw),
                body.report_start, body.report_end, body.metric_definition,
                body.degraded, body.degradation_detail, body.retention_3s_estimated,
            )
            # Feedback rollup (WP-E): fold this snapshot into per-tag
            # performance. Recomputed from source-of-truth tables so a
            # corrected snapshot can never drift the rollup.
            await _rollup_hashtag_performance(conn, body.platform)
    latest = await pool.fetchrow(
        "SELECT views, likes, comments, shares, impressions, avg_watch_s, "
        "avg_view_duration_s, avg_view_percentage, ctr, retention_3s, link_clicks, "
        "subscribers_gained, source, captured_at, report_start, report_end, "
        "metric_definition, degraded, degradation_detail, retention_3s_estimated "
        "FROM post_metrics WHERE schedule_id = $1 "
        "ORDER BY captured_at DESC LIMIT 1",
        schedule_id,
    )
    return {"schedule_id": str(schedule_id), **dict(latest)}


@router.get("/schedules/{schedule_id}/metrics")
async def list_metrics(schedule_id: uuid.UUID) -> dict:
    """All snapshots for a post, newest first (dashboard trend display)."""
    pool = db.get()
    rows = await pool.fetch(
        """SELECT views, likes, comments, shares, impressions, avg_watch_s,
                  avg_view_duration_s, avg_view_percentage, ctr, retention_3s,
                  retention_3s_estimated, link_clicks, subscribers_gained, source,
                  captured_at, report_start, report_end, metric_definition,
                  degraded, degradation_detail
           FROM post_metrics WHERE schedule_id = $1
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


async def _rearm_publish_job(pool, schedule_id: uuid.UUID) -> None:
    """(Re)arm the durable publish job when a post (re)enters 'scheduled'.

    Covers retries (auto-retry transition), human resume, and re-scheduling
    after a rewrite: the existing job row goes back to 'pending' with a fresh
    attempt budget and its run_after aligned to the post's publish time. If
    the package changed, a NEW job was enqueued at schedule creation with a
    new dedupe key — this UPDATE only touches rows for this schedule. No-op
    when no job row exists (post predates 028; the classic sweep still
    drives it — the sweep remains the authoritative fallback).
    """
    await pool.execute(
        """
        UPDATE jobs j
        SET status = 'pending', run_after = COALESCE(s.local_time, j.run_after),
            attempts = 0, last_error = NULL, lease_holder = NULL,
            lease_expires_at = NULL, updated_at = now()
        FROM schedules s
        WHERE j.entity_id = $1 AND j.kind = 'publish_schedule'
          AND s.id = j.entity_id AND s.state = 'scheduled'
        """,
        schedule_id,
    )


async def _load(pool, schedule_id: uuid.UUID) -> dict:
    row = await pool.fetchrow(
        "SELECT id, offer_id, state::text AS state, version_hash, platform, privacy, "
        "language, render_id, platform_account_id, package_hash, render_sha256, "
        "metadata_hash, cover_sha256, captions_sha256, metadata::text AS metadata, "
        "outcome_detail::text AS outcome_detail, remote_post_id, youtube_playlist_id "
        "FROM schedules WHERE id = $1",
        schedule_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="schedule not found")
    return dict(row)


async def _current_script_hash(pool, offer_id: uuid.UUID,
                               language: str = "en") -> Optional[str]:
    """Hash the latest script for THIS language. A newer Urdu draft must not
    invalidate an approved English post (or vice versa)."""
    row = await pool.fetchrow(
        "SELECT markdown FROM offer_scripts WHERE offer_id = $1 AND language = $2 "
        "ORDER BY version DESC LIMIT 1",
        offer_id, language,
    )
    return script_version_hash(row["markdown"]) if row else None


async def _schedule_offer_problem(pool, offer_id: uuid.UUID) -> Optional[str]:
    """Why an offer may not enter (or stay in) the publish queue right now.

    Delegates to release_gate so there is ONE freshness/state implementation —
    previously this helper, the publishing worker and schedule validation each
    had their own, and they disagreed (the worker failed open on a NULL
    recheck deadline).
    """
    problems = await offer_problems(pool, offer_id)
    return describe_problems(problems) if problems else None


async def _revalidate_offer(pool, offer_id: uuid.UUID) -> bool:
    """§17: offer still fresh for scheduling, resume or upload — expiry, recheck state."""
    return await _schedule_offer_problem(pool, offer_id) is None


def _json_value(value, default):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except ValueError:
            return default
    return default


def _hash_local(ref: Optional[str]) -> Optional[str]:
    """sha256 of a plain local asset, if this API host can see it.

    Managed refs (s3://, local://) are hashed by the render worker that owns
    the bytes; the API never guesses a digest for an unreadable object.
    """
    if not ref or "://" in str(ref):
        return None
    path = Path(str(ref))
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _fmt_timestamp(seconds: int) -> str:
    hours, rem = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


_CHAPTER_TITLES = {
    "hook": "The offer",
    "eligibility": "Eligibility",
    "proof": "Official proof",
    "claim": "Live walkthrough",
    "result": "Result",
    "cta": "Next step",
}


def _attach_youtube_chapters(metadata: dict, beats: list, duration_s,
                             language: str = "en") -> dict:
    """Finalize valid YouTube chapters (0:00 first, >=10s apart, >=3 chapters).

    The chapter text is part of the description the reviewer hashes, so this
    must happen BEFORE the metadata hash is computed. The adapter uploads the
    package verbatim and never edits the description afterwards.
    """
    if not isinstance(metadata, dict):
        return metadata

    selected = _trim_short_tail(_valid_chapters(metadata.get("chapters"), duration_s),
                                duration_s)
    if len(selected) < 3 or selected[0]["start_s"] != 0:
        selected = []
        for beat in beats or []:
            if not isinstance(beat, dict):
                continue
            try:
                at = int(float(beat.get("at_s") or 0))
            except (TypeError, ValueError):
                continue
            if at < 0:
                continue
            if duration_s is not None:
                try:
                    if at >= float(duration_s):
                        continue
                except (TypeError, ValueError):
                    pass
            if selected and at < selected[-1]["start_s"] + 10:
                continue
            title = _CHAPTER_TITLES.get(
                str(beat.get("id") or "").lower(),
                str(beat.get("purpose") or "Chapter").strip().title())
            selected.append({"start_s": at, "title": _chapter_title(title)})
        selected = _trim_short_tail(selected, duration_s)
    if len(selected) < 3 or selected[0]["start_s"] != 0:
        return metadata

    chapter_lines = "\n".join(
        f"{_fmt_timestamp(chapter['start_s'])} {chapter['title']}" for chapter in selected
    )
    section = ("Chapters:\n" if language == "en" else "ابواب:\n") + chapter_lines
    caption = str(metadata.get("caption") or "")
    limit = PLATFORM_LIMITS["youtube"]["caption"]
    updated = dict(metadata)
    updated["chapters"] = selected
    if section not in caption:
        room = max(0, limit - len(section) - 2)
        updated["caption"] = (caption[:room].rstrip() + "\n\n" + section)[:limit]
    return updated


def _chapter_title(value) -> str:
    title = " ".join(str(value or "Chapter").replace("<", "").replace(">", "").split())
    return title[:80] or "Chapter"


def _valid_chapters(value, duration_s) -> list[dict]:
    if not isinstance(value, list):
        return []
    selected: list[dict] = []
    for chapter in value:
        if not isinstance(chapter, dict):
            return []
        try:
            at = int(float(chapter.get("start_s")))
        except (TypeError, ValueError):
            return []
        if at < 0 or (selected and at < selected[-1]["start_s"] + 10):
            return []
        if duration_s is not None:
            try:
                if at >= float(duration_s):
                    return []
            except (TypeError, ValueError):
                pass
        selected.append({"start_s": at, "title": _chapter_title(chapter.get("title"))})
    return selected


def _trim_short_tail(selected: list[dict], duration_s) -> list[dict]:
    """YouTube requires every chapter, including the last, to be >=10s long."""
    if not selected or duration_s is None:
        return selected
    try:
        end = float(duration_s)
    except (TypeError, ValueError):
        return selected
    trimmed = list(selected)
    while len(trimmed) > 1 and end - trimmed[-1]["start_s"] < 10:
        trimmed.pop()
    return trimmed


async def _pin_platform_account(pool, platform: str,
                                account_id: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
    if account_id is not None:
        row = await pool.fetchrow(
            "SELECT id FROM platform_accounts WHERE id = $1 AND platform = $2 "
            "AND status = 'active'",
            account_id, platform,
        )
        if not row:
            raise HTTPException(
                status_code=409,
                detail="platform account not found, not active, or belongs to another platform",
            )
        return row["id"]
    row = await pool.fetchrow(
        "SELECT id FROM platform_accounts WHERE platform = $1 AND status = 'active' "
        "ORDER BY created_at LIMIT 1",
        platform,
    )
    return row["id"] if row else None


async def _audit(pool, *, actor: str, action: str, entity: str,
                 entity_id: Optional[uuid.UUID] = None, detail: Optional[dict] = None) -> None:
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        actor, action, entity, entity_id, json.dumps(detail or {}, default=str),
    )
