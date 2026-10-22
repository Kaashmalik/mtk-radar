"""Renders router — registered export pipeline results (weeks 7-8).

Gates enforced here (master plan §3/§4):
- Renders can only be registered for offers in video-allowed states.
- If the render references a capture session, that capture MUST have passed
  redaction review — no render enters the pipeline from unreviwed footage.

httpx is an indirect dependency (unused here but consistent with siblings).
"""

import hashlib
import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db
from schedules_state import script_version_hash
from settings_store import get_language_policy
from state import can_generate_video

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
    capture_id: uuid.UUID
    disclosure: dict = Field(default_factory=dict)
    # v0.27 content packaging carried through to schedules.
    language: str = "en"
    cover_path: Optional[str] = None
    motion_template: str = "studio"
    metadata: dict = Field(default_factory=dict)


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
        "SELECT markdown FROM offer_scripts WHERE offer_id = $1 AND language = $2 "
        "AND ($3::int IS NULL OR version = $3) ORDER BY version DESC LIMIT 1",
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

    video_sha256 = render.video_sha256 or _hash_local(render.video_path)
    captions_sha256 = render.captions_sha256 or _hash_local(render.captions_path)
    cover_sha256 = render.cover_sha256 or _hash_local(render.cover_path)
    row = await pool.fetchrow(
        """
        INSERT INTO renders (offer_id, capture_id, script_version, script_version_hash,
                             preset, width, height, duration_s, video_path, captions_path,
                             disclosure, language, cover_path, motion_template, metadata,
                             video_sha256, captions_sha256, cover_sha256)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb,
                $12, $13, $14, $15::jsonb, $16, $17, $18)
        RETURNING id, created_at
        """,
        offer_id, render.capture_id, render.script_version, render.script_version_hash,
        render.preset, render.width, render.height, render.duration_s, render.video_path,
        render.captions_path, _json(render.disclosure), render.language,
        render.cover_path, render.motion_template, _json(render.metadata),
        video_sha256, captions_sha256, cover_sha256,
    )
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "status": "rendered",
        "language": render.language,
        "cover_path": render.cover_path,
        "motion_template": render.motion_template,
        "video_sha256": video_sha256,
        "captions_sha256": captions_sha256,
        "cover_sha256": cover_sha256,
    }


@router.get("/renders")
async def list_renders(
    offer_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT r.id, r.offer_id, o.title AS offer_title, r.preset, r.width, r.height,
               r.duration_s, r.video_path, r.captions_path, r.script_version,
               r.script_version_hash, r.video_sha256, r.captions_sha256,
               r.cover_sha256, r.language, r.cover_path, r.motion_template,
               r.metadata::text AS metadata,
               r.disclosure::text AS disclosure, r.status, r.created_at
        FROM renders r JOIN offers o ON o.id = r.offer_id
        WHERE ($1::uuid IS NULL OR r.offer_id = $1)
        ORDER BY r.created_at DESC LIMIT $2
        """,
        offer_id,
        limit,
    )
    return [dict(r) for r in rows]


@router.get("/render-candidates")
async def render_candidates(limit: int = Query(default=50, le=200)) -> list[dict]:
    """Offers that are READY to render (v0.19 automation queue).

    A candidate has: an approved-for-video/verified offer, a generated
    script, and a capture session that passed redaction review — but no
    render registered for that exact script version yet. The render worker
    polls this endpoint (`workers/render/main.py --sweep`) and the dashboard
    shows it as a work queue, so rendering no longer needs a human at a
    terminal. Idempotency: a render for the same script version (same
    content hash) disqualifies the offer.
    """
    pool = db.get()
    language_policy = await get_language_policy(pool)
    rows = await pool.fetch(
        """
        WITH latest_script AS (
          SELECT DISTINCT ON (offer_id, language)
                 offer_id, language, version, markdown
          FROM offer_scripts ORDER BY offer_id, language, version DESC
        )
        SELECT o.id AS offer_id, o.title, o.provider, o.state::text AS state,
               ls.language, ls.version AS script_version, ls.markdown,
               c.id AS capture_id, c.video_path, c.created_at AS capture_created_at
        FROM offers o
        JOIN latest_script ls ON ls.offer_id = o.id
        JOIN LATERAL (
          SELECT c.* FROM capture_sessions c
          WHERE c.offer_id = o.id AND c.redaction_reviewed
          ORDER BY c.created_at DESC LIMIT 1
        ) c ON TRUE
        WHERE o.state IN ('verified', 'approved_for_video')
          AND ls.language = ANY($2::text[])
        ORDER BY c.created_at DESC
        LIMIT $1
        """,
        limit, language_policy["narration_languages"],
    )
    candidates = [dict(r) for r in rows]
    if not candidates:
        return []

    # the approval hash is derived from the script CONTENT (never stored), so
    # it is computed here and compared against registered renders
    offer_ids = [c["offer_id"] for c in candidates]
    rendered = await pool.fetch(
        "SELECT offer_id, language, script_version_hash FROM renders "
        "WHERE offer_id = ANY($1::uuid[])",
        offer_ids,
    )
    done = {(r["offer_id"], r["language"], r["script_version_hash"]) for r in rendered
            if r["script_version_hash"]}

    out: list[dict] = []
    for candidate in candidates:
        version_hash = script_version_hash(candidate.get("markdown") or "")
        if (candidate["offer_id"], candidate.get("language", "en"), version_hash) in done:
            continue  # this exact script version is already rendered for this language
        candidate.pop("markdown", None)  # content never leaves the server
        candidate["script_version_hash"] = version_hash
        out.append(candidate)
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
