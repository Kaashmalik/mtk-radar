"""Renders router — registered export pipeline results (weeks 7-8).

Gates enforced here (master plan §3/§4):
- Renders can only be registered for offers in video-allowed states.
- If the render references a capture session, that capture MUST have passed
  redaction review — no render enters the pipeline from unreviwed footage.
- v0.29: registration must carry a measured QC report; failed attempts are
  persisted as dead-letter records and can never be scheduled/published.

httpx is an indirect dependency (unused here but consistent with siblings).
"""

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

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
from schedules_state import script_version_hash
from scriptgen import ScriptGateError, assert_format_wording
from settings_store import get_language_policy
from state import can_generate_video
from api_hardening import effective_reviewer
from automation import is_automation_actor

router = APIRouter(tags=["renders"])


class RenderIn(BaseModel):
    preset: str = Field(min_length=3)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_s: Optional[float] = None
    video_path: str = Field(min_length=3)
    captions_path: Optional[str] = None
    script_version: Optional[int] = None
    # §17 approval pin: hash of the exact script markdown the render used
    script_version_hash: str = Field(min_length=64, max_length=64)
    # v0.28 package pins: digests of the exact bytes the render worker wrote.
    video_sha256: Optional[str] = None
    captions_sha256: Optional[str] = None
    cover_sha256: Optional[str] = None
    # M3: None only for an official_explainer render built from the research
    # brief (no screen recording exists). Every other format needs a capture.
    capture_id: Optional[uuid.UUID] = None
    disclosure: dict = Field(default_factory=dict)
    # v0.27 content packaging carried through to schedules.
    language: str = "en"
    cover_path: Optional[str] = None
    motion_template: str = "studio"
    metadata: dict = Field(default_factory=dict)
    # v0.29 measured QC: the worker registers even a rejected attempt so the
    # dead-letter view can explain it. Only rendered+passed is publishable.
    status: str = "rendered"
    qc_status: str = "not_checked"
    qc_report: dict = Field(default_factory=dict)
    qc_checked_at: Optional[datetime] = None
    # Speech-authoritative scene timeline (§6, plan §6.F): stored for the QC
    # trail so a reviewer can check what the export actually contains.
    timeline: Optional[dict] = None


class PlaybackReviewIn(BaseModel):
    """A human's recorded verdict after watching the FINAL export (§6.F)."""
    approved: bool
    note: str = Field(min_length=3, max_length=1000)


@router.post("/offers/{offer_id}/renders", status_code=201)
async def register_render(offer_id: uuid.UUID, render: RenderIn) -> dict:
    pool = db.get()
    offer = await pool.fetchrow("SELECT state::text AS state FROM offers WHERE id = $1", offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    if render.language not in ("en", "ur"):
        raise HTTPException(status_code=422, detail="language must be 'en' or 'ur'")
    language_policy = await get_language_policy(pool)
    if render.language not in language_policy["narration_languages"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{render.language} voiceover is disabled in Settings → "
                "Language policy"
            ),
        )
    if not can_generate_video(offer["state"]):
        raise HTTPException(
            status_code=409,
            detail=f"render blocked: offer state is '{offer['state']}' (§3)",
        )

    if render.capture_id is not None:
        capture = await pool.fetchrow(
            "SELECT redaction_reviewed FROM capture_sessions WHERE id = $1 AND offer_id = $2",
            render.capture_id, offer_id,
        )
        if not capture:
            raise HTTPException(status_code=404, detail="capture not found for this offer")
        if not capture["redaction_reviewed"]:
            raise HTTPException(
                status_code=409,
                detail="capture redaction review has not passed — review the footage first (§4)",
            )

    # The render must be bound to the exact script bytes it was produced from.
    script = await pool.fetchrow(
        "SELECT markdown, format FROM offer_scripts WHERE offer_id = $1 "
        "AND language = $2 AND ($3::int IS NULL OR version = $3) "
        "ORDER BY version DESC LIMIT 1",
        offer_id, render.language, render.script_version,
    )
    if not script:
        raise HTTPException(status_code=409, detail="script version not found for this render")
    expected_hash = script_version_hash(script["markdown"])
    if render.script_version_hash != expected_hash:
        raise HTTPException(
            status_code=409,
            detail="render script_version_hash does not match the selected script version",
        )

    # M3: a capture-less render is allowed ONLY for the official_explainer
    # format (cards built from the research brief; no footage to redact).
    # Playback review and measured QC still gate its release.
    if render.capture_id is None and script["format"] != "official_explainer":
        raise HTTPException(
            status_code=422,
            detail=f"a render without a capture is only allowed for the "
                   f"'official_explainer' format (script format is "
                   f"'{script['format'] or 'unset'}') — record and review a capture",
        )

    # Format binding at render time (plan §6.C): the declared format is
    # re-checked against the actual wording. A hand-edited script (or a future
    # generator bug) can no longer render "i claimed the offer" while claiming
    # to be an official_explainer.
    if script["format"]:
        try:
            assert_format_wording(script["markdown"], script["format"])
        except ScriptGateError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"script wording does not match its declared format "
                       f"('{script['format']}'): {exc}",
            ) from exc

    # v0.29: a render registration without a measured QC report is incomplete.
    # Fail closed here; legacy rows already in the DB are blocked downstream.
    if render.status not in ("rendered", "qc_failed", "render_failed"):
        raise HTTPException(status_code=422, detail="unknown render status")
    if render.qc_status not in ("passed", "failed"):
        raise HTTPException(
            status_code=422,
            detail="render registration requires a measured QC result (passed or failed)",
        )
    if render.status == "rendered" and render.qc_status != "passed":
        raise HTTPException(
            status_code=422,
            detail="a rendered output must carry qc_status=passed",
        )
    if render.status != "rendered" and render.qc_status != "failed":
        raise HTTPException(
            status_code=422,
            detail="a failed render attempt must carry qc_status=failed",
        )
    if not isinstance(render.qc_report, dict) or not render.qc_report:
        raise HTTPException(
            status_code=422,
            detail="render registration requires a non-empty QC report",
        )
    if render.qc_report.get("status") != render.qc_status:
        raise HTTPException(
            status_code=422,
            detail="qc_status does not match the persisted QC report status",
        )

    # Only a measured, passing render may pin asset bytes. A failed attempt can
    # leave a stale previous file or a partial encode at the same path.
    if render.status == "rendered":
        video_sha256 = render.video_sha256 or _hash_local(render.video_path)
        captions_sha256 = render.captions_sha256 or _hash_local(render.captions_path)
        cover_sha256 = render.cover_sha256 or _hash_local(render.cover_path)
    else:
        video_sha256 = captions_sha256 = cover_sha256 = None
    row = await pool.fetchrow(
        """
        INSERT INTO renders (offer_id, capture_id, script_version, script_version_hash,
                             preset, width, height, duration_s, video_path, captions_path,
                             disclosure, language, cover_path, motion_template, metadata,
                             video_sha256, captions_sha256, cover_sha256,
                             status, qc_status, qc_report, qc_checked_at, timeline)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb,
                $12, $13, $14, $15::jsonb, $16, $17, $18,
                $19, $20, $21::jsonb, COALESCE($22::timestamptz, now()), $23::jsonb)
        ON CONFLICT (offer_id, language, preset, script_version_hash, video_sha256)
            WHERE video_sha256 IS NOT NULL AND script_version_hash IS NOT NULL
        DO NOTHING
        RETURNING id, created_at
        """,
        offer_id, render.capture_id, render.script_version, render.script_version_hash,
        render.preset, render.width, render.height, render.duration_s, render.video_path,
        render.captions_path, _json(render.disclosure), render.language,
        render.cover_path, render.motion_template, _json(render.metadata),
        video_sha256, captions_sha256, cover_sha256,
        render.status, render.qc_status, _json(render.qc_report), render.qc_checked_at,
        _json(render.timeline) if render.timeline else None,
    )
    if not row and video_sha256:
        # Idempotent registration (§8.A): the unique index
        # renders_revision_output_key matched — this exact output for this
        # script revision is already registered. Return it instead of
        # double-registering (a retry after a lost response, or two workers on
        # one candidate, must not clone a render).
        row = await pool.fetchrow(
            "SELECT id, created_at FROM renders "
            "WHERE offer_id = $1 AND language = $2 AND preset = $3 "
            "AND script_version_hash = $4 AND video_sha256 = $5",
            offer_id, render.language, render.preset,
            render.script_version_hash, video_sha256,
        )
        if row:
            return {
                "id": row["id"],
                "created_at": row["created_at"].isoformat(),
                "duplicate": True,
                "language": render.language,
                "status": render.status,
                "qc_status": render.qc_status,
            }
        raise HTTPException(status_code=500, detail="render insert failed")
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "language": render.language,
        "cover_path": render.cover_path,
        "motion_template": render.motion_template,
        "video_sha256": video_sha256,
        "captions_sha256": captions_sha256,
        "cover_sha256": cover_sha256,
        "status": render.status,
        "qc_status": render.qc_status,
    }


@router.get("/renders")
async def list_renders(
    response: Response,
    offer_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_created = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT r.id, r.offer_id, o.title AS offer_title, r.preset, r.width, r.height,
               r.duration_s, r.video_path, r.captions_path, r.script_version,
               r.script_version_hash, r.video_sha256, r.captions_sha256,
               r.cover_sha256, r.language, r.cover_path, r.motion_template,
               r.metadata::text AS metadata,
               r.disclosure::text AS disclosure, r.status, r.qc_status,
               r.qc_report::text AS qc_report, r.qc_checked_at, r.created_at,
               r.playback_approved, r.playback_reviewer, r.playback_reviewed_at
        FROM renders r JOIN offers o ON o.id = r.offer_id
        WHERE ($1::uuid IS NULL OR r.offer_id = $1)
          AND ($3::text IS NULL OR r.status = $3)
          AND ($4::timestamptz IS NULL
               OR (r.created_at, r.id) < ($4::timestamptz, $5::uuid))
        ORDER BY r.created_at DESC, r.id DESC LIMIT $2
        """,
        offer_id,
        limit,
        status,
        before_created,
        before_id,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["created_at"], row["id"]),
    )
    return out


@router.get("/renders/{render_id}")
async def get_render(render_id: uuid.UUID) -> dict:
    """One render by id.

    Workers pin a render id at schedule time. Looking it up by scanning the
    first page of `/renders?offer_id=...` used to report a valid asset as
    missing once an offer had more renders than one page.
    """
    pool = db.get()
    row = await pool.fetchrow("SELECT * FROM renders WHERE id = $1", render_id)
    if not row:
        raise HTTPException(status_code=404, detail="render not found")
    out = dict(row)
    for key in ("metadata", "disclosure", "qc_report", "timeline"):
        value = out.get(key)
        if isinstance(value, str):
            try:
                out[key] = json.loads(value)
            except ValueError:
                pass
    return out


@router.post("/renders/{render_id}/playback-review")
async def review_playback(render_id: uuid.UUID, body: PlaybackReviewIn,
                          request: Request) -> dict:
    """Record a human verdict after watching the FINAL export (§6.F).

    Passing QC does not mean the video is right: a measured report cannot say
    the narration matches the approved script, the captions read correctly, or
    the disclosure is on screen. A named human signs off — and automation can
    never do it for them. The release gate refuses renders without this.
    """
    actor = effective_reviewer(request, None, require=True)
    if is_automation_actor(actor):
        raise HTTPException(
            status_code=403,
            detail="automation may not attest playback — a named human must "
                   "watch the export",
        )
    pool = db.get()
    row = await pool.fetchrow(
        """
        UPDATE renders
        SET playback_approved = $2, playback_reviewer = $3, playback_note = $4,
            playback_reviewed_at = now()
        WHERE id = $1
        RETURNING id, playback_approved, playback_reviewer, playback_reviewed_at
        """,
        render_id, body.approved, actor, body.note,
    )
    if not row:
        raise HTTPException(status_code=404, detail="render not found")
    return dict(row)


@router.get("/render-dead-letter")
async def render_dead_letter(
    response: Response,
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> dict:
    """Operator visibility for failed/QC-rejected render attempts.

    A QC failure is not silently retried forever: it remains visible with the
    measured report until an operator re-renders the offer. Candidate selection
    ignores failed rows, so the offer stays in the render queue. Paginated
    via the `X-Next-Cursor` header (counts always cover every row).
    """
    pool = db.get()
    counts = await pool.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'rendered' AND qc_status = 'passed')::int AS qc_passed,
          COUNT(*) FILTER (WHERE status = 'qc_failed')::int AS qc_failed,
          COUNT(*) FILTER (WHERE status = 'render_failed')::int AS render_failed,
          COUNT(*) FILTER (WHERE COALESCE(qc_status, 'not_checked') = 'not_checked')::int AS not_checked,
          COUNT(*)::int AS total
        FROM renders
        """
    )
    parts = decode_cursor(cursor, 2)
    before_created = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT r.id, r.offer_id, o.title AS offer_title, r.preset, r.language,
               r.status, r.qc_status, r.qc_report::text AS qc_report,
               r.video_path, r.duration_s, r.qc_checked_at, r.created_at
        FROM renders r JOIN offers o ON o.id = r.offer_id
        WHERE (r.status IN ('qc_failed', 'render_failed') OR r.qc_status = 'failed')
          AND ($2::timestamptz IS NULL
               OR (r.created_at, r.id) < ($2::timestamptz, $3::uuid))
        ORDER BY r.created_at DESC, r.id DESC LIMIT $1
        """,
        limit, before_created, before_id,
    )
    items = [dict(r) for r in rows]
    set_next_cursor(
        response, items, limit,
        lambda row: encode_cursor(row["created_at"], row["id"]),
    )
    return {"counts": dict(counts or {}), "items": items}


#: Presets the render worker knows about. Kept in sync with
#: workers/render/presets.py; the worker passes its own list explicitly.
KNOWN_RENDER_PRESETS = ("landscape", "vertical")
#: After this many failed attempts for the exact script revision/preset, the
#: sweep stops retrying automatically. The failed rows stay visible in
#: /render-dead-letter for a human; a new script revision resets the count.
MAX_RENDER_ATTEMPTS = 3


@router.get("/render-candidates")
async def render_candidates(
    response: Response,
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
    presets: Optional[str] = Query(default=None),
) -> list[dict]:
    """Offers that are READY to render (v0.19 automation queue).

    A candidate has: an approved-for-video/verified offer, a generated
    script, a capture session that passed redaction review, and at least one
    requested preset with no QC-passed render for that exact script version.

    v0.31: completion is tracked PER PRESET. A finished landscape export no
    longer hides a still-missing vertical one, and the `LIMIT` is applied
    after already-rendered variants are removed (keyset pagination via
    `cursor`), so a long backlog cannot starve the tail.
    """
    pool = db.get()
    language_policy = await get_language_policy(pool)

    requested = [p.strip() for p in (presets or ",".join(KNOWN_RENDER_PRESETS)).split(",")
                 if p.strip()]
    unknown = [p for p in requested if p not in KNOWN_RENDER_PRESETS]
    if not requested or unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                "presets must be a comma-separated subset of "
                + ", ".join(KNOWN_RENDER_PRESETS)
                + (f" (unknown: {', '.join(unknown)})" if unknown else "")
            ),
        )
    requested = list(dict.fromkeys(requested))

    parts = decode_cursor(cursor, 3)
    before_created = decode_datetime(parts[0]) if parts else None
    before_offer = decode_uuid(parts[1]) if parts else None
    before_language = parts[2] if parts else None

    # `sha256(convert_to(markdown,'UTF8'))` is the SQL equivalent of
    # schedules_state.script_version_hash, so the NOT EXISTS check binds to the
    # exact script bytes without sending content through the worker.
    rows = await pool.fetch(
        """
        WITH latest_script AS (
          SELECT DISTINCT ON (offer_id, language)
                 offer_id, language, version, markdown, format, created_at
          FROM offer_scripts ORDER BY offer_id, language, version DESC
        ),
        base AS (
          SELECT o.id AS offer_id, o.title, o.provider, o.state::text AS state,
                 ls.language, ls.version AS script_version, ls.markdown,
                 c.id AS capture_id, c.video_path,
                 -- M3: an explainer has no capture; its script time orders it.
                 COALESCE(c.created_at, ls.created_at) AS capture_created_at,
                 ARRAY(
                   SELECT p.preset
                   FROM unnest($3::text[]) AS p(preset)
                   WHERE NOT EXISTS (
                     SELECT 1 FROM renders r
                     WHERE r.offer_id = o.id
                       AND r.language = ls.language
                       AND r.preset = p.preset
                       AND r.status = 'rendered'
                       AND r.qc_status = 'passed'
                       AND r.script_version_hash =
                           encode(sha256(convert_to(ls.markdown, 'UTF8')), 'hex')
                   )
                     AND (
                       SELECT COUNT(*)
                       FROM renders failed
                       WHERE failed.offer_id = o.id
                         AND failed.language = ls.language
                         AND failed.preset = p.preset
                         AND failed.script_version_hash =
                             encode(sha256(convert_to(ls.markdown, 'UTF8')), 'hex')
                         AND failed.status IN ('render_failed', 'qc_failed')
                     ) < $7
                 ) AS missing_presets
          FROM offers o
          JOIN latest_script ls ON ls.offer_id = o.id
          LEFT JOIN LATERAL (
            SELECT c.* FROM capture_sessions c
            WHERE c.offer_id = o.id AND c.redaction_reviewed
            ORDER BY c.created_at DESC LIMIT 1
          ) c ON TRUE
          WHERE o.state IN ('verified', 'approved_for_video')
            AND ls.language = ANY($2::text[])
            -- A reviewed capture, OR (M3) a research explainer the render
            -- worker builds from the current brief: official_explainer
            -- script + current brief content_type 'explainer'.
            AND (c.id IS NOT NULL OR (
                  ls.format = 'official_explainer'
                  AND (SELECT b.content_type FROM research_briefs b
                       WHERE b.offer_id = o.id
                       ORDER BY b.version DESC LIMIT 1) = 'explainer'))
        )
        SELECT * FROM base
        WHERE cardinality(missing_presets) > 0
          AND ($4::timestamptz IS NULL
               OR (capture_created_at, offer_id, language) <
                  ($4::timestamptz, $5::uuid, $6::text))
        ORDER BY capture_created_at DESC, offer_id DESC, language DESC
        LIMIT $1
        """,
        limit,
        language_policy["narration_languages"],
        requested,
        before_created,
        before_offer,
        before_language,
        MAX_RENDER_ATTEMPTS,
    )
    candidates = [dict(r) for r in rows]
    out: list[dict] = []
    for candidate in candidates:
        candidate.pop("markdown", None)  # content never leaves the server
        candidate["missing_presets"] = list(candidate.get("missing_presets") or [])
        out.append(candidate)

    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(
            row["capture_created_at"], row["offer_id"], row["language"]
        ),
    )
    return out


def _json(value) -> str:
    return json.dumps(value, default=str)


def _hash_local(ref: Optional[str]) -> Optional[str]:
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
