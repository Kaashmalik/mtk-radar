"""Research briefs + versioned claim ledger (EP-03, G18 — plan §WP-C).

A promoted topic becomes research material, not instantly an offer: the brief
names the viewer question/angle/audience and the content_type track; the
claim ledger carries every SUBSTANTIVE sentence the content may use, class-
tagged (author_reported / independently_reproduced / tested_by_mtk /
editorial_analysis), scope-bound, and each claim resolves to its supporting
excerpt and source. Contradicted claims are fail-closed inputs to script
generation (scriptgen refuses to write copy while a contradiction stands).

Promotion NEVER means "verified": briefs live under offer rows stuck at
state `candidate` pending official evidence, exactly as before.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from settings_store import audit

router = APIRouter(tags=["research"])

CONTENT_TYPES = ("explainer", "tested_tutorial", "claim_walkthrough", "offer")
CLAIM_CLASSES = ("author_reported", "independently_reproduced",
                 "tested_by_mtk", "editorial_analysis")
CLAIM_STATUSES = ("supported", "contradicted", "unknown")


class BriefIn(BaseModel):
    """A new VERSION of the brief (the previous version is preserved)."""
    content_type: str = Field(pattern="^(explainer|tested_tutorial|claim_walkthrough|offer)$")
    viewer_question: Optional[str] = Field(default=None, max_length=500)
    angle: Optional[str] = Field(default=None, max_length=500)
    audience: Optional[str] = Field(default=None, max_length=300)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    counterevidence: list[dict[str, Any]] = Field(default_factory=list)
    limitations: Optional[str] = Field(default=None, max_length=2000)
    auto_shortlisted: bool = False
    claims: list["ClaimIn"] = Field(default_factory=list)


class ClaimIn(BaseModel):
    claim_text: str = Field(min_length=5, max_length=1000)
    claim_class: str = Field(
        pattern="^(author_reported|independently_reproduced|tested_by_mtk|editorial_analysis)$")
    supporting_excerpt: Optional[str] = Field(default=None, max_length=2000)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    source_owner: Optional[str] = Field(default=None, max_length=300)
    source_date: Optional[date] = None
    scope: Optional[str] = Field(default=None, max_length=300)
    status: str = Field(default="unknown",
                        pattern="^(supported|contradicted|unknown)$")
    permitted_wording: Optional[str] = Field(default=None, max_length=1000)
    recheck_at: Optional[datetime] = None


class ClaimStatusIn(BaseModel):
    """Human status resolution — automation actors may never settle a
    contradiction (the script gate unblocks the moment it is set)."""
    status: str = Field(pattern="^(supported|contradicted|unknown)$")
    permitted_wording: Optional[str] = Field(default=None, max_length=1000)
    recheck_at: Optional[datetime] = None


BriefIn.model_rebuild()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _decode_brief(row) -> dict:
    brief = dict(row)
    for key in ("sources", "counterevidence"):
        if isinstance(brief.get(key), str):
            try:
                brief[key] = json.loads(brief[key])
            except ValueError:
                brief[key] = []
    for key in ("id", "offer_id"):
        brief[key] = str(brief[key])
    return brief


async def latest_brief_with_claims(pool, offer_id: uuid.UUID) -> Optional[dict]:
    """The current (highest-version) brief + its claims, or None. Shared with
    scriptgen callers so the script gate always sees the SAME ledger."""
    row = await pool.fetchrow(
        """
        SELECT id, offer_id, version, content_type, viewer_question, angle,
               audience, sources::text AS sources,
               counterevidence::text AS counterevidence, limitations,
               auto_shortlisted, created_at, updated_at
        FROM research_briefs WHERE offer_id = $1
        ORDER BY version DESC LIMIT 1
        """,
        offer_id,
    )
    if not row:
        return None
    brief = _decode_brief(row)
    claims = await pool.fetch(
        """
        SELECT id, claim_text, claim_class, supporting_excerpt, source_url,
               source_owner, source_date, scope, status, permitted_wording,
               recheck_at, created_at
        FROM research_claims WHERE brief_id = $1 ORDER BY created_at, id
        """,
        row["id"],
    )
    brief["claims"] = []
    for c in claims:
        claim = dict(c)
        claim["id"] = str(claim["id"])
        claim["brief_id"] = str(row["id"])
        brief["claims"].append(claim)
    return brief


async def _require_offer(pool, offer_id: uuid.UUID) -> dict:
    offer = await pool.fetchrow(
        "SELECT id, state::text AS state, title FROM offers WHERE id = $1", offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    return dict(offer)


@router.get("/offers/{offer_id}/research")
async def get_research(offer_id: uuid.UUID) -> dict:
    """Every brief version (newest first) + the current version's claims."""
    pool = db.get()
    await _require_offer(pool, offer_id)
    rows = await pool.fetch(
        """
        SELECT id, offer_id, version, content_type, viewer_question, angle,
               audience, sources::text AS sources,
               counterevidence::text AS counterevidence, limitations,
               auto_shortlisted, created_at, updated_at
        FROM research_briefs WHERE offer_id = $1 ORDER BY version DESC
        """,
        offer_id,
    )
    current = await latest_brief_with_claims(pool, offer_id)
    return {
        "briefs": [_decode_brief(r) for r in rows],
        "current": current,
        # The gate state a reviewer needs: what would block script generation?
        "blocking_conflicts": [
            c["claim_text"] for c in (current or {}).get("claims", [])
            if c["status"] == "contradicted"],
    }


@router.post("/offers/{offer_id}/research", status_code=201)
async def create_brief_version(offer_id: uuid.UUID, body: BriefIn,
                               request: Request) -> dict:
    actor = effective_reviewer(request, None)
    if not actor:
        raise HTTPException(status_code=403, detail="a named reviewer is required")
    pool = db.get()
    offer = await _require_offer(pool, offer_id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            version = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM research_briefs "
                "WHERE offer_id = $1", offer_id)
            brief = await conn.fetchrow(
                """
                INSERT INTO research_briefs
                    (offer_id, version, content_type, viewer_question, angle,
                     audience, sources, counterevidence, limitations,
                     auto_shortlisted)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
                RETURNING id, version, content_type
                """,
                offer_id, version, body.content_type, body.viewer_question,
                body.angle, body.audience, _json(body.sources),
                _json(body.counterevidence), body.limitations,
                body.auto_shortlisted,
            )
            # The brief supersedes; the queue row (if any) follows the track.
            await conn.execute(
                "UPDATE production_queue SET content_type = $2, updated_at = now() "
                "WHERE offer_id = $1", offer_id, body.content_type)
            for claim in body.claims:
                await conn.execute(
                    """
                    INSERT INTO research_claims
                        (brief_id, offer_id, claim_text, claim_class,
                         supporting_excerpt, source_url, source_owner,
                         source_date, scope, status, permitted_wording,
                         recheck_at, status_changed_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    brief["id"], offer_id, claim.claim_text, claim.claim_class,
                    claim.supporting_excerpt, claim.source_url, claim.source_owner,
                    claim.source_date, claim.scope, claim.status,
                    claim.permitted_wording, claim.recheck_at, actor,
                )
            # Keep the offer container aligned with the track WITHOUT ever
            # implying verification: explainers/tutorials recorded as
            # 'trend_topic' stay candidate invites for evidence, promotions
            # stay gate-bound as before.
            await conn.execute(
                """
                INSERT INTO audit_log (actor, action, entity, entity_id, detail)
                VALUES ($1, 'research:brief-created', 'offers', $2, $3::jsonb)
                """,
                actor, offer_id,
                _json({"version": version, "content_type": body.content_type,
                       "offer_state": offer["state"],
                       "claims": len(body.claims)}),
            )
            await conn.execute(
                "UPDATE research_briefs SET updated_at = now() WHERE id = $1",
                brief["id"])
    created = await latest_brief_with_claims(pool, offer_id)
    return created


@router.patch("/offers/{offer_id}/research/claims/{claim_id}")
async def set_claim_status(offer_id: uuid.UUID, claim_id: uuid.UUID,
                           body: ClaimStatusIn, request: Request) -> dict:
    """Human claim resolution (supports / contradicts / marks unknown).

    Fail-closed contract with script generation: 'contradicted' is what BLOCKS
    unsupported copy; only a human (never automation:<stage>) can flip it —
    the reviewer identity is recorded on the claim and in the audit trail.
    """
    actor = effective_reviewer(request, None)
    if not actor:
        raise HTTPException(status_code=403, detail="a named reviewer is required")
    if actor.startswith("automation:"):
        raise HTTPException(
            status_code=403,
            detail="claim status is a human resolution — automation cannot "
                   "settle a contradiction")
    pool = db.get()
    await _require_offer(pool, offer_id)
    row = await pool.fetchrow(
        "UPDATE research_claims SET status = $2, permitted_wording = "
        "COALESCE($3, permitted_wording), recheck_at = COALESCE($4, recheck_at), "
        "status_changed_by = $5, status_changed_at = now() "
        "WHERE id = $1 AND offer_id = $6 RETURNING id, status",
        claim_id, body.status, body.permitted_wording, body.recheck_at, actor,
        offer_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="claim not found")
    await audit(pool, actor=actor, action="research:claim-status",
                entity="offers", entity_id=offer_id,
                detail={"claim_id": str(claim_id), "status": body.status})
    current = await latest_brief_with_claims(pool, offer_id)
    return {"claim_id": str(row["id"]), "status": row["status"],
            "blocking_conflicts": [
                c["claim_text"] for c in current["claims"]
                if c["status"] == "contradicted"]}
