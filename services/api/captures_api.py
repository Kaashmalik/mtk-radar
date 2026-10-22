"""Captures router — real-browser capture sessions + redaction review (weeks 5-6).

Rules enforced here (master plan §4):
- Captures can only be recorded for offers whose state allows video.
- The redaction scan runs SERVER-SIDE over the step log; findings are stored
  as pattern names + counts — secret values are never persisted.
- `redaction_reviewed` is the release-blocking attestation; renders/publishing
  (later phases) must require it.
"""

import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from pagination import (
    decode_cursor,
    decode_datetime,
    decode_uuid,
    encode_cursor,
    set_next_cursor,
)
from offer_freshness import freshness_problem
from redact import scan as scan_secrets
from state import can_generate_video

router = APIRouter(tags=["captures"])

MATERIAL_FIELDS_NOTE = "redaction review is release-blocking (master plan §4)"


class CaptureIn(BaseModel):
    video_path: Optional[str] = None  # object storage key; asset itself stays in storage
    step_log: list[dict] = Field(default_factory=list)
    notes: Optional[str] = None


ClaimOutcome = Literal["demonstrated", "not_demonstrated", "not_attempted"]


class RedactionReviewIn(BaseModel):
    # v0.16: optional when a reviewer token binds identity (enforced server-side)
    reviewer: Optional[str] = None
    approved: bool
    note: Optional[str] = None
    # v0.31: what the reviewer actually saw happen in the footage. Approval of
    # the redaction is not evidence that the claim succeeded; a claim-walkthrough
    # script needs `demonstrated`, and tested tutorials word the result honestly
    # when it was not demonstrated.
    claim_outcome: Optional[ClaimOutcome] = None


@router.post("/offers/{offer_id}/captures", status_code=201)
async def record_capture(offer_id: uuid.UUID, capture: CaptureIn) -> dict:
    pool = db.get()
    offer = await pool.fetchrow("SELECT state::text AS state FROM offers WHERE id = $1", offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    if not can_generate_video(offer["state"]):
        raise HTTPException(
            status_code=409,
            detail=f"capture blocked: offer state is '{offer['state']}' (§3)",
        )
    # Recording footage is acting on the claims: never for an offer past its
    # expiry or recheck deadline, even if the state sweep has not run yet.
    problem = await freshness_problem(pool, offer_id)
    if problem:
        raise HTTPException(
            status_code=409,
            detail=f"capture blocked: {problem} (§11 freshness)",
        )

    # Server-side scan over the serialized step log. Findings NEVER contain values.
    serialized = json.dumps(capture.step_log, default=str)
    findings = scan_secrets(serialized)

    row = await pool.fetchrow(
        """
        INSERT INTO capture_sessions (offer_id, video_path, step_log, secret_findings)
        VALUES ($1, $2, $3::jsonb, $4::jsonb)
        RETURNING id
        """,
        offer_id, capture.video_path, json.dumps(capture.step_log, default=str),
        json.dumps(findings),
    )
    return {
        "id": row["id"],
        "redaction": {
            "clean": not findings,
            "findings": findings,  # pattern + count only
            "review_required": True,
        },
    }


@router.get("/captures")
async def list_captures(
    response: Response,
    offer_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=50, le=200),
    cursor: Optional[str] = Query(default=None),
) -> list[dict]:
    pool = db.get()
    parts = decode_cursor(cursor, 2)
    before_created = decode_datetime(parts[0]) if parts else None
    before_id = decode_uuid(parts[1]) if parts else None
    rows = await pool.fetch(
        """
        SELECT c.id, c.offer_id, o.title AS offer_title, c.video_path,
               c.step_log::text AS step_log, c.secret_findings::text AS secret_findings,
               c.redaction_reviewed, c.reviewer, c.review_note,
               c.claim_outcome, c.claim_outcome_reviewer, c.claim_outcome_at,
               c.created_at
        FROM capture_sessions c JOIN offers o ON o.id = c.offer_id
        WHERE ($1::uuid IS NULL OR c.offer_id = $1)
          AND ($3::timestamptz IS NULL
               OR (c.created_at, c.id) < ($3::timestamptz, $4::uuid))
        ORDER BY c.created_at DESC, c.id DESC LIMIT $2
        """,
        offer_id,
        limit,
        before_created,
        before_id,
    )
    out = [dict(r) for r in rows]
    set_next_cursor(
        response, out, limit,
        lambda row: encode_cursor(row["created_at"], row["id"]),
    )
    return out


@router.post("/captures/{capture_id}/redaction-review")
async def redaction_review(capture_id: uuid.UUID, review: RedactionReviewIn,
                           request: Request) -> dict:
    """Reviewer attests the footage/transcript is clean (re-checked the video,
    terminal output, and captions — not just this scan)."""
    pool = db.get()
    capture = await pool.fetchrow(
        "SELECT secret_findings::text AS findings, redaction_reviewed FROM capture_sessions WHERE id = $1",
        capture_id,
    )
    if not capture:
        raise HTTPException(status_code=404, detail="capture not found")
    if not review.approved and capture["redaction_reviewed"]:
        raise HTTPException(status_code=409, detail="already reviewed — re-run via a new review")
    if review.approved and review.claim_outcome is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "an approved redaction review must record what happened: "
                "claim_outcome is demonstrated, not_demonstrated, or not_attempted"
            ),
        )

    reviewer_on_record = effective_reviewer(request, review.reviewer, require=True)
    row = await pool.fetchrow(
        """
        UPDATE capture_sessions
        SET redaction_reviewed = $2, reviewer = $3, review_note = COALESCE($4, review_note),
            claim_outcome = CASE WHEN $2 THEN $5 ELSE NULL END,
            claim_outcome_reviewer = CASE WHEN $2 THEN $3 ELSE NULL END,
            claim_outcome_at = CASE WHEN $2 THEN clock_timestamp() ELSE NULL END
        WHERE id = $1
        RETURNING id, redaction_reviewed, claim_outcome
        """,
        capture_id, review.approved, reviewer_on_record, review.note,
        review.claim_outcome,
    )
    return {
        "id": row["id"],
        "redaction_reviewed": row["redaction_reviewed"],
        "claim_outcome": row["claim_outcome"],
    }
