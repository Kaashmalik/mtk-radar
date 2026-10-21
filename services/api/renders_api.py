"""Renders router — registered export pipeline results (weeks 7-8).

Gates enforced here (master plan §3/§4):
- Renders can only be registered for offers in video-allowed states.
- If the render references a capture session, that capture MUST have passed
  redaction review — no render enters the pipeline from unreviwed footage.

httpx is an indirect dependency (unused here but consistent with siblings).
"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db
from schedules_state import script_version_hash
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
    script_version_hash: Optional[str] = None
    capture_id: Optional[uuid.UUID] = None
    disclosure: dict = Field(default_factory=dict)


@router.post("/offers/{offer_id}/renders", status_code=201)
async def register_render(offer_id: uuid.UUID, render: RenderIn) -> dict:
    pool = db.get()
    offer = await pool.fetchrow("SELECT state::text AS state FROM offers WHERE id = $1", offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    if not can_generate_video(offer["state"]):
        raise HTTPException(
            status_code=409,
            detail=f"render blocked: offer state is '{offer['state']}' (§3)",
        )

    if render.capture_id:
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

    row = await pool.fetchrow(
        """
        INSERT INTO renders (offer_id, capture_id, script_version, script_version_hash,
                             preset, width, height, duration_s, video_path, captions_path,
                             disclosure)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
        RETURNING id, created_at
        """,
        offer_id, render.capture_id, render.script_version, render.script_version_hash,
        render.preset, render.width, render.height, render.duration_s, render.video_path,
        render.captions_path, _json(render.disclosure),
    )
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "status": "rendered",
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
               r.script_version_hash,
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
    rows = await pool.fetch(
        """
        WITH latest_script AS (
          SELECT DISTINCT ON (offer_id) offer_id, version, markdown
          FROM offer_scripts ORDER BY offer_id, version DESC
        )
        SELECT o.id AS offer_id, o.title, o.provider, o.state::text AS state,
               ls.version AS script_version, ls.markdown,
               c.id AS capture_id, c.video_path, c.created_at AS capture_created_at
        FROM offers o
        JOIN latest_script ls ON ls.offer_id = o.id
        JOIN LATERAL (
          SELECT c.* FROM capture_sessions c
          WHERE c.offer_id = o.id AND c.redaction_reviewed
          ORDER BY c.created_at DESC LIMIT 1
        ) c ON TRUE
        WHERE o.state IN ('verified', 'approved_for_video')
        ORDER BY c.created_at DESC
        LIMIT $1
        """,
        limit,
    )
    candidates = [dict(r) for r in rows]
    if not candidates:
        return []

    # the approval hash is derived from the script CONTENT (never stored), so
    # it is computed here and compared against registered renders
    offer_ids = [c["offer_id"] for c in candidates]
    rendered = await pool.fetch(
        "SELECT offer_id, script_version_hash FROM renders WHERE offer_id = ANY($1::uuid[])",
        offer_ids,
    )
    done = {(r["offer_id"], r["script_version_hash"]) for r in rendered
            if r["script_version_hash"]}

    out: list[dict] = []
    for candidate in candidates:
        version_hash = script_version_hash(candidate.get("markdown") or "")
        if (candidate["offer_id"], version_hash) in done:
            continue  # this exact script version is already rendered
        candidate.pop("markdown", None)  # content never leaves the server
        candidate["script_version_hash"] = version_hash
        out.append(candidate)
    return out


def _json(value) -> str:
    return json.dumps(value, default=str)
