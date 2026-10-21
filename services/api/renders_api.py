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


def _json(value) -> str:
    return json.dumps(value, default=str)
