"""Offers router — the verification desk (Weeks 3-4, master plan §3/§18).

Rules enforced here, not trusted from callers:
- Verified requires >= 1 evidence snapshot with official=true AND domain_ok=true.
- Transitions follow the state machine (state.py); approval targets require a
  recorded reviewer.
- Material edits demote verified+ offers back to evidence_needed (correction
  workflow) and reset recheck_at.
- Every state change writes an audit_log row (actor, action, entity, note).
"""

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

import db
from jsonb import decode
from api_hardening import effective_reviewer
import tos_review
from document_sections import MAX_SECTION_CHARS, SECTIONS_VERSION, split_sections
from fetch_attestation import verify_provenance
from redact import scan as scan_secrets
from schedules_state import script_version_hash
from schemas import (
    EvidenceIn,
    EvidenceProvenance,
    ExtractionCoverage,
    ExtractionIn,
    OfferIn,
    OfferUpdate,
    TransitionIn,
)
from scriptgen import generate as generate_script_payload
from state import (
    OFFER_STATES,
    VIDEO_ALLOWED_STATES,
    TransitionError,
    can_generate_video,
    can_transition,
    requires_review,
)
from verification_checks import domain_matches, established_fields, extraction_problems, field_problems
from offer_terms import build_fact_pack, derive_completeness

router = APIRouter(prefix="/offers", tags=["offers"])

MATERIAL_FIELDS = {
    "eligibility", "value", "claim_steps", "promo_code", "redemption_url",
    "expires_at", "renewal",
    # Re-typing an offer changes which terms are required (offer-type contract),
    # so it must demote a verified offer instead of inheriting its old check.
    "offer_type",
}
RECHECK_INTERVAL = "2 days"  # verified offers must be rechecked before this elapses


# ---------------------------------------------------------------- create


@router.post("/from-item/{item_id}", status_code=201)
async def promote_item(item_id: uuid.UUID, offer: OfferIn, request: Request) -> dict:
    """Reviewer promotes an inbox item to a tracked offer (state: candidate)."""
    pool = db.get()
    item = await pool.fetchrow(
        """
        SELECT i.id, i.url, i.title, s.provider AS source_provider
        FROM items i LEFT JOIN sources s ON s.id = i.source_id
        WHERE i.id = $1
        """,
        item_id,
    )
    if not item:
        raise HTTPException(status_code=404, detail="item not found")

    title = offer.title or item["title"] or str(item["url"])
    row = await pool.fetchrow(
        """
        INSERT INTO offers (title, provider, category, offer_type, promo_code,
                            redemption_url, expires_at, eligibility, value, claim_steps, state)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, 'candidate')
        RETURNING id, state::text AS state
        """,
        title, offer.provider, offer.category, offer.offer_type,
        offer.promo_code, offer.redemption_url, offer.expires_at,
        _json(offer.eligibility), _json(offer.value), _json(offer.claim_steps),
    )
    await pool.execute("UPDATE items SET processed = TRUE WHERE id = $1", item_id)
    await _audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                 action="promote_item", entity="offers",
                 entity_id=row["id"], detail={"item_id": str(item_id)})
    return {"id": row["id"], "state": row["state"]}


@router.post("", status_code=201)
async def create_offer(offer: OfferIn, request: Request) -> dict:
    pool = db.get()
    row = await pool.fetchrow(
        """
        INSERT INTO offers (title, provider, category, offer_type, promo_code,
                            redemption_url, expires_at, eligibility, value, claim_steps, state)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, 'candidate')
        RETURNING id, state::text AS state
        """,
        offer.title or f"{offer.provider} offer", offer.provider, offer.category,
        offer.offer_type, offer.promo_code, offer.redemption_url, offer.expires_at,
        _json(offer.eligibility), _json(offer.value), _json(offer.claim_steps),
    )
    await _audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                 action="create_offer", entity="offers", entity_id=row["id"])
    return {"id": row["id"], "state": row["state"]}


# ---------------------------------------------------------------- read


@router.get("")
async def list_offers(
    state: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT o.id, o.title, o.provider, o.category, o.offer_type, o.state::text AS state,
               o.confidence, o.expires_at, o.recheck_at, o.correction_note, o.updated_at,
               (SELECT COUNT(*) FROM evidence e
                 WHERE e.offer_id = o.id AND e.official AND e.domain_ok) AS official_evidence,
               (SELECT COUNT(*) FROM evidence e WHERE e.offer_id = o.id) AS evidence_count,
               (SELECT x.conflicts FROM extractions x
                 WHERE x.offer_id = o.id ORDER BY x.created_at DESC LIMIT 1) AS conflicts
        FROM offers o
        WHERE ($1::text IS NULL OR o.state::text = $1)
        ORDER BY o.updated_at DESC
        LIMIT $2
        """,
        state if state in OFFER_STATES else None,
        limit,
    )
    return [dict(r) for r in rows]


@router.get("/stale")
async def stale_offers() -> list[dict]:
    """Offer recheck desk: verified+ offers overdue for recheck or expired."""
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, title, provider, state::text AS state, expires_at, recheck_at,
               CASE WHEN expires_at IS NOT NULL AND expires_at <= now() THEN 'expired'
                    ELSE 'recheck_due' END AS reason
        FROM offers
        WHERE state IN ('verified', 'approved_for_video', 'published')
          AND (expires_at <= now() OR recheck_at <= now())
        ORDER BY recheck_at
        """
    )
    return [dict(r) for r in rows]


@router.get("/{offer_id}")
async def get_offer(offer_id: uuid.UUID) -> dict:
    pool = db.get()
    offer = await pool.fetchrow(
        """
        SELECT id, title, provider, category, offer_type, eligibility::text AS eligibility,
               value::text AS value, claim_steps::text AS claim_steps, promo_code,
               redemption_url, starts_at, expires_at, timezone, renewal::text AS renewal,
               state::text AS state, confidence, recheck_at, correction_note, updated_at
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    evidence = await pool.fetch(
        """
        SELECT e.id, e.url, e.captured_at, e.content_hash, e.excerpt, e.screenshot_path,
               e.supported_fields::text AS supported_fields,
               e.official, e.domain_ok, e.reviewer,
               e.raw_hash, e.requested_url, e.fetch_status, e.fetch_content_type,
               e.fetched_at, e.fetch_redirects::text AS fetch_redirects,
               e.parser_version, e.fetch_identity,
               e.robots_url, e.robots_checked_at, e.robots_allowed, e.robots_status,
               e.fetch_signature,
               (e.raw_content IS NOT NULL) AS raw_preserved,
               s.provider AS source_provider, s.trust_tier::text AS trust_tier
        FROM evidence e LEFT JOIN sources s ON s.id = e.source_id
        WHERE e.offer_id = $1 ORDER BY e.captured_at DESC
        """,
        offer_id,
    )
    extraction = await pool.fetchrow(
        """
        SELECT fields::text AS fields, conflicts::text AS conflicts, complete, model, created_at,
               fact_pack::text AS fact_pack, offer_type, coverage::text AS coverage
        FROM extractions WHERE offer_id = $1 ORDER BY created_at DESC LIMIT 1
        """,
        offer_id,
    )
    extraction_payload = dict(extraction) if extraction else None
    if extraction_payload is not None:
        extraction_payload["coverage"] = decode(extraction_payload.get("coverage"))
    return {
        **dict(offer),
        "evidence": [dict(r) for r in evidence],
        "extraction": extraction_payload,
    }


# ---------------------------------------------------------------- update


@router.patch("/{offer_id}")
async def update_offer(offer_id: uuid.UUID, update: OfferUpdate, request: Request) -> dict:
    pool = db.get()
    current = await pool.fetchrow(
        "SELECT state::text AS state, provider FROM offers WHERE id = $1", offer_id
    )
    if not current:
        raise HTTPException(status_code=404, detail="offer not found")

    sets, params, material_changed = [], [], False
    payload = update.model_dump(exclude_unset=True, exclude_none=True)
    column_map = {
        "title": "title", "provider": "provider", "category": "category",
        "offer_type": "offer_type", "promo_code": "promo_code",
        "redemption_url": "redemption_url", "expires_at": "expires_at",
        "correction_note": "correction_note",
    }
    json_map = {"eligibility": "eligibility", "value": "value",
                "claim_steps": "claim_steps", "renewal": "renewal"}

    for key, value in payload.items():
        if key in column_map:
            params.append(value)
            sets.append(f"{column_map[key]} = ${len(params)}")
        elif key in json_map:
            params.append(_json(value))
            sets.append(f"{json_map[key]} = ${len(params)}::jsonb")
        if key in MATERIAL_FIELDS:
            material_changed = True

    # Correction workflow: material edits send verified+ offers back for re-check.
    demoted = False
    if material_changed and current["state"] in ("verified", "approved_for_video", "published"):
        sets.append("state = 'evidence_needed'")
        sets.append("recheck_at = now()")
        if not payload.get("correction_note"):
            params.append("material change; re-verification required")
            sets.append(f"correction_note = ${len(params)}")
        demoted = True

    if not sets:
        raise HTTPException(status_code=400, detail="no fields to update")

    params.append(offer_id)
    row = await pool.fetchrow(
        f"UPDATE offers SET {', '.join(sets)}, updated_at = now() WHERE id = ${len(params)} "
        "RETURNING id, state::text AS state",
        *params,
    )
    await _audit(pool, actor=effective_reviewer(request, None, default="reviewer"),
                 action="update_offer", entity="offers",
                 entity_id=offer_id, detail={"demoted": demoted, "fields": list(payload)})
    return {"id": row["id"], "state": row["state"], "demoted": demoted}


# ---------------------------------------------------------------- evidence


@router.post("/{offer_id}/evidence", status_code=201)
async def add_evidence(offer_id: uuid.UUID, evidence: EvidenceIn, request: Request) -> dict:
    """Immutable evidence snapshot. Hash is computed server-side; identical
    content dedupes. domain_ok is decided HERE via the provider allowlist —
    callers cannot self-certify an official source."""
    pool = db.get()
    offer = await pool.fetchrow(
        "SELECT provider FROM offers WHERE id = $1", offer_id
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    if evidence.official and not evidence.captured_content:
        raise HTTPException(status_code=422, detail="official evidence requires captured snapshot text")
    captured = evidence.captured_content or evidence.excerpt or ""
    content_hash = hashlib.sha256(captured.encode("utf-8")).hexdigest()
    domain_ok = await _provider_domain_ok(pool, offer["provider"], str(evidence.url), evidence.source_id)

    if evidence.official and not domain_ok:
        raise HTTPException(
            status_code=422,
            detail="official evidence URL is not on the provider's registered domains "
                   "(register the official source in the source registry first)",
        )

    # Raw bytes + fetch provenance (WP01 slice 3). Nothing here is trusted:
    # the server decodes, re-hashes and re-checks every URL in the chain.
    raw = base64.b64decode(evidence.raw_content_b64) if evidence.raw_content_b64 else None
    raw_hash = hashlib.sha256(raw).hexdigest() if raw is not None else None
    provenance = await _validate_provenance(
        pool, offer["provider"], evidence, raw_hash,
    )
    if provenance is not None and _require_tos_attestation():
        await _require_source_tos_attestation(pool, evidence)

    evidence_reviewer = effective_reviewer(request, evidence.reviewer)
    row = await pool.fetchrow(
        """
        INSERT INTO evidence (offer_id, source_id, url, content_hash, excerpt,
                              screenshot_path, supported_fields, official, domain_ok, reviewer,
                              captured_content, raw_content, raw_hash, requested_url,
                              fetch_status, fetch_content_type, fetched_at, fetch_redirects,
                              parser_version, fetch_identity,
                              robots_url, robots_checked_at, robots_allowed, robots_status,
                              fetch_signature)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11,
                $12, $13, $14, $15, $16, $17, $18::jsonb, $19, $20,
                $21, $22, $23, $24, $25)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        offer_id, evidence.source_id, str(evidence.url), content_hash,
        evidence.excerpt, evidence.screenshot_path, _json(evidence.supported_fields),
        evidence.official, domain_ok, evidence_reviewer, evidence.captured_content,
        raw, raw_hash,
        provenance["requested_url"] if provenance else None,
        provenance["fetch_status"] if provenance else None,
        provenance["fetch_content_type"] if provenance else None,
        provenance["fetched_at"] if provenance else None,
        _json(provenance["redirects"]) if provenance else None,
        provenance["parser_version"] if provenance else None,
        provenance["fetch_identity"] if provenance else None,
        provenance["robots_url"] if provenance else None,
        provenance["robots_checked_at"] if provenance else None,
        provenance["robots_allowed"] if provenance else None,
        provenance["robots_status"] if provenance else None,
        provenance["fetch_signature"] if provenance else None,
    )
    created = row is not None
    if row is None:
        row = await pool.fetchrow(
            "SELECT id FROM evidence WHERE offer_id = $1 AND url = $2 AND content_hash = $3 "
            "AND (captured_content IS NOT NULL) = $4 AND official = $5 "
            "AND source_id IS NOT DISTINCT FROM $6::uuid",
            offer_id, str(evidence.url), content_hash, evidence.captured_content is not None,
            evidence.official, evidence.source_id,
        )
    await _audit(pool, actor=evidence_reviewer or "worker", action="add_evidence",
                 entity="evidence", entity_id=row["id"],
                 detail={"offer_id": str(offer_id), "official": evidence.official,
                         "domain_ok": domain_ok, "content_hash": content_hash})
    return {"id": row["id"], "created": created, "duplicate": not created,
            "content_hash": content_hash, "domain_ok": domain_ok,
            "raw_preserved": raw is not None, "raw_hash": raw_hash,
            "provenance": provenance}


# ---------------------------------------------------------------- extraction


@router.post("/{offer_id}/extraction", status_code=201)
async def add_extraction(offer_id: uuid.UUID, extraction: ExtractionIn) -> dict:
    pool = db.get()
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await _add_extraction(conn, offer_id, extraction)


async def _add_extraction(pool, offer_id: uuid.UUID, extraction: ExtractionIn) -> dict:
    # Serialize new proposals with verification transitions for this offer.
    offer = await pool.fetchrow(
        "SELECT id, state::text AS state, offer_type FROM offers WHERE id = $1 FOR UPDATE", offer_id,
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    offer_type = offer["offer_type"] or ""
    per_field, problems, established = await _extraction_problems(pool, offer_id, extraction)
    # The server derives a per-claim fact pack and checks it against the
    # offer-type terms contract. A required claim that is unknown or
    # contradicted blocks verification instead of becoming marketing copy.
    fact_pack = build_fact_pack(offer_type, extraction.fields, established=established)
    complete, type_problems = derive_completeness(offer_type, fact_pack)
    problems = list(problems) + type_problems
    complete = complete and not problems
    coverage = await _validate_coverage(pool, offer_id, extraction.coverage)
    serialized = extraction.model_dump(mode="json")
    row = await pool.fetchrow(
        """
        INSERT INTO extractions (offer_id, fields, conflicts, complete, model, created_at,
                                   fact_pack, offer_type, coverage)
        VALUES ($1, $2::jsonb, $3::jsonb, $4, $5, clock_timestamp(), $6::jsonb, $7,
                $8::jsonb)
        RETURNING id
        """,
        offer_id, _json(serialized["fields"]), _json(extraction.conflicts),
        complete, extraction.model, _json(fact_pack), offer_type,
        _json(coverage) if coverage else None,
    )
    if extraction.conflicts:
        await pool.execute(
            "UPDATE offers SET correction_note = $2, updated_at = now() WHERE id = $1",
            offer_id, f"{len(extraction.conflicts)} extraction conflict(s) need review",
        )
    # A new proposal supersedes the old verification even if its core passes;
    # approval of old content must not survive replacement extraction inputs.
    # The existing DB trigger pauses scheduled posts on this revocation.
    await pool.execute(
        "UPDATE offers SET state = 'evidence_needed', recheck_at = now(), updated_at = now(), "
        "correction_note = 'new extraction requires re-verification' "
        "WHERE id = $1 AND state IN ('verified', 'approved_for_video', 'published')",
        offer_id,
    )
    if offer["state"] in ("verified", "approved_for_video", "published"):
        await _audit(pool, actor="worker", action=f"transition:{offer['state']}->evidence_needed",
                     entity="offers", entity_id=offer_id,
                     detail={"reason": "new extraction", "extraction_id": str(row["id"])})
    await _audit(pool, actor="worker", action="add_extraction", entity="extractions",
                  entity_id=row["id"], detail={"complete": complete,
                                               "conflicts": len(extraction.conflicts)})
    return {"id": row["id"], "complete": complete, "validation_errors": problems,
            "fact_pack": fact_pack, "coverage": coverage}


# ---------------------------------------------------------------- transitions


@router.post("/{offer_id}/transition")
async def transition(offer_id: uuid.UUID, t: TransitionIn, request: Request) -> dict:
    pool = db.get()
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await _transition(conn, offer_id, t, request)


async def _transition(pool, offer_id: uuid.UUID, t: TransitionIn, request: Request) -> dict:
    offer = await pool.fetchrow(
        "SELECT state::text AS state, title, provider FROM offers WHERE id = $1 FOR UPDATE", offer_id
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    current, target = offer["state"], t.to
    if current not in OFFER_STATES or target not in OFFER_STATES:
        raise HTTPException(status_code=400, detail="unknown state")
    if not can_transition(current, target):
        raise HTTPException(
            status_code=409,
            detail=f"illegal transition {current} → {target}",
        )

    # §3: approval targets must name a human — a bound reviewer token satisfies
    # this even when the body omits the field.
    reviewer_on_record = effective_reviewer(request, t.reviewer)
    if requires_review(target) and not reviewer_on_record:
        raise HTTPException(
            status_code=403,
            detail=f"transition to '{target}' requires a recorded reviewer",
        )

    if target == "verified":
        await _gate_verified(pool, offer_id)

    recheck_clause = ""
    params: list = [offer_id, target]
    if target == "verified":
        params.append(RECHECK_INTERVAL)
        recheck_clause = f", recheck_at = now() + ${len(params)}::text::interval"

    row = await pool.fetchrow(
        f"UPDATE offers SET state = ${2}::offer_state{recheck_clause}, updated_at = now() "
        f"WHERE id = $1 RETURNING state::text AS state",
        *params,
    )
    await _audit(pool, actor=reviewer_on_record or "worker", action=f"transition:{current}->{target}",
                 entity="offers", entity_id=offer_id, detail={"note": t.note})
    return {"id": offer_id, "state": row["state"], "previous": current}


# ---------------------------------------------------------------- corrections + impact (week 11)


class CorrectionIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)
    # v0.16: optional when a reviewer token binds identity (enforced server-side)
    corrected_by: Optional[str] = None
    version_hash: Optional[str] = None


@router.post("/{offer_id}/corrections", status_code=201)
async def add_correction(offer_id: uuid.UUID, body: CorrectionIn, request: Request) -> dict:
    """Log a correction (§3 Learn step) and demote the offer to 'corrected' when
    the state machine allows. Pausing of affected scheduled posts is enforced by
    the trg_pause_on_offer_change database trigger (007) — this endpoint only
    reports how many were caught."""
    pool = db.get()
    offer = await pool.fetchrow(
        "SELECT state::text AS state, title FROM offers WHERE id = $1", offer_id
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    corrected_by = effective_reviewer(request, body.corrected_by, require=True)
    row = await pool.fetchrow(
        """
        INSERT INTO offer_corrections (offer_id, note, corrected_by, version_hash)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        offer_id, body.note, corrected_by, body.version_hash,
    )
    await pool.execute(
        "UPDATE offers SET correction_note = $2, updated_at = now() WHERE id = $1",
        offer_id, body.note,
    )

    current = offer["state"]
    state_changed = False
    new_state = current
    if can_transition(current, "corrected"):
        new_row = await pool.fetchrow(
            "UPDATE offers SET state = 'corrected', updated_at = now() "
            "WHERE id = $1 RETURNING state::text AS state",
            offer_id,
        )
        new_state = new_row["state"]
        state_changed = True

    await _audit(pool, actor=corrected_by,
                 action="correction:recorded" if not state_changed else "transition:%s->corrected" % current,
                 entity="offers", entity_id=offer_id,
                 detail={"note": body.note, "version_hash": body.version_hash})

    return {
        "correction_id": row["id"],
        "offer_id": offer_id,
        "offer_state": new_state,
        "state_changed": state_changed,
        "auto_paused_posts": await _count_scheduled(pool, offer_id),
    }


@router.get("/{offer_id}/corrections")
async def list_corrections(offer_id: uuid.UUID) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, offer_id, note, corrected_by, version_hash, created_at
        FROM offer_corrections WHERE offer_id = $1
        ORDER BY created_at DESC
        """,
        offer_id,
    )
    return [dict(r) for r in rows]


@router.get("/{offer_id}/impact")
async def offer_impact(offer_id: uuid.UUID) -> dict:
    """'Corrections link to affected videos' (§18 week 11): everything produced
    from this offer — renders, captures, and the platform posts they became."""
    pool = db.get()
    offer = await pool.fetchrow(
        "SELECT id, title, state::text AS state, correction_note FROM offers WHERE id = $1",
        offer_id,
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    renders = await pool.fetch(
        """
        SELECT r.id, r.preset, r.width, r.height, r.video_path,
               r.script_version, r.status, r.created_at
        FROM renders r WHERE r.offer_id = $1
        ORDER BY r.created_at DESC
        """,
        offer_id,
    )
    captures = await pool.fetch(
        """
        SELECT id, redaction_reviewed, created_at
        FROM capture_sessions WHERE offer_id = $1
        ORDER BY created_at DESC
        """,
        offer_id,
    )
    schedules = await pool.fetch(
        """
        SELECT s.id, s.platform, s.state::text AS state, s.local_time, s.privacy,
               s.remote_post_id, s.outcome_detail::text AS outcome_detail
        FROM schedules s WHERE s.offer_id = $1
        ORDER BY s.local_time
        """,
        offer_id,
    )
    correction_count = await pool.fetchval(
        "SELECT COUNT(*) FROM offer_corrections WHERE offer_id = $1", offer_id
    )
    return {
        "offer": dict(offer),
        "renders": [dict(r) for r in renders],
        "captures": [dict(c) for c in captures],
        "schedules": [dict(s) for s in schedules],
        "correction_count": correction_count,
    }


async def _count_scheduled(pool: asyncpg.Pool, offer_id: uuid.UUID) -> int:
    return await pool.fetchval(
        "SELECT COUNT(*) FROM schedules WHERE offer_id = $1 AND state = 'scheduled'",
        offer_id,
    )


# ---------------------------------------------------------------- scripts (weeks 5-6)


@router.post("/{offer_id}/script", status_code=201)
async def create_script(offer_id: uuid.UUID, request: Request,
                        created_by: str = Query(default="reviewer")) -> dict:
    created_by_actor = effective_reviewer(request, created_by, default="reviewer")
    """Generate a versioned claim script + checklist + command cards.

    HARD GATE: blocked unless the offer state allows video (§3) — this is the
    enforcement point of "unverified records cannot enter script generation".
    """
    pool = db.get()
    offer = await pool.fetchrow(
        """
        SELECT id, title, provider, category, offer_type,
               eligibility::text AS eligibility, value::text AS value,
               claim_steps::text AS claim_steps, promo_code, redemption_url,
               expires_at, renewal::text AS renewal, state::text AS state
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")
    if not can_generate_video(offer["state"]):
        raise HTTPException(
            status_code=409,
            detail=f"script generation blocked: offer state is '{offer['state']}' "
                   "(master plan §3 — verified with official evidence required)",
        )

    evidence = await pool.fetch(
        """
        SELECT url, captured_at, excerpt FROM evidence
        WHERE offer_id = $1 AND official AND domain_ok
        ORDER BY captured_at DESC
        """,
        offer_id,
    )
    # The fact pack is derived server-side per claim field. The script must
    # use it so an unknown fact is written as unknown, never as "free",
    # "open eligibility" or "never expires" (master plan §6 step 7, A13).
    fact_pack = await pool.fetchrow(
        """
        SELECT fact_pack::text AS fact_pack FROM extractions
        WHERE offer_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        offer_id,
    )
    offer_row = dict(offer)
    offer_row["fact_pack"] = decode(fact_pack["fact_pack"]) if fact_pack else {}
    payload = generate_script_payload(offer_row, [dict(r) for r in evidence])

    unsafe = [c for c in payload["command_cards"] if c["unsafe_reasons"]]
    version_row = await pool.fetchrow(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM offer_scripts WHERE offer_id = $1",
        offer_id,
    )
    version = version_row["next"]
    row = await pool.fetchrow(
        """
        INSERT INTO offer_scripts (offer_id, version, markdown, checklist, command_cards, created_by)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        RETURNING id, version
        """,
        offer_id, version, payload["markdown"], _json(payload["checklist"]),
        _json(payload["command_cards"]), created_by_actor,
    )
    await _audit(pool, actor=created_by_actor, action="generate_script", entity="offer_scripts",
                 entity_id=row["id"],
                 detail={"version": version, "unsafe_command_cards": len(unsafe)})
    return {
        "id": row["id"],
        "version": version,
        "markdown": payload["markdown"],
        "checklist": payload["checklist"],
        "command_cards": payload["command_cards"],
        "unsafe_command_cards": len(unsafe),
    }


@router.get("/{offer_id}/scripts")
async def list_scripts(offer_id: uuid.UUID) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        """
        SELECT id, version, markdown, command_cards::text AS command_cards,
               created_by, created_at
        FROM offer_scripts WHERE offer_id = $1 ORDER BY version DESC
        """,
        offer_id,
    )
    out = []
    for r in rows:
        item = dict(r)
        # §17: the approval-pinning hash, computed from the exact markdown —
        # the render worker binds it into each render row at registration so
        # the publishing worker can verify render ↔ approval integrity.
        item["version_hash"] = script_version_hash(r["markdown"])
        out.append(item)
    return out


@router.post("/sweep-stale")
async def sweep_stale() -> dict:
    """Correction workflow: expired deals auto-pause; overdue rechecks demote."""
    pool = db.get()
    expired = await pool.fetch(
        """
        UPDATE offers SET state = 'expired', updated_at = now()
        WHERE state IN ('verified', 'approved_for_video', 'published')
          AND expires_at IS NOT NULL AND expires_at <= now()
        RETURNING id
        """
    )
    rechecks = await pool.fetch(
        """
        UPDATE offers SET state = 'evidence_needed',
                          correction_note = COALESCE(correction_note, '')
                          || 'scheduled recheck due',
                          updated_at = now()
        WHERE state IN ('verified', 'approved_for_video')
          AND recheck_at <= now()
        RETURNING id
        """
    )
    for r in expired:
        await _audit(pool, actor="system", action="transition:stale→expired",
                     entity="offers", entity_id=r["id"])
    for r in rechecks:
        await _audit(pool, actor="system", action="transition:stale→evidence_needed",
                     entity="offers", entity_id=r["id"])
    return {"expired": len(expired), "recheck_queued": len(rechecks)}


# ---------------------------------------------------------------- gates


async def _gate_verified(pool: asyncpg.Pool, offer_id: uuid.UUID) -> None:
    """Revalidate stored proposals, including legacy rows, never trust complete."""
    latest = await pool.fetchrow(
        """
        SELECT fields, conflicts, coverage::text AS coverage FROM extractions
        WHERE offer_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        offer_id,
    )
    if latest is None:
        raise HTTPException(status_code=422, detail="requires structured extraction with official snapshot evidence")
    try:
        extraction = ExtractionIn.model_validate({
            "fields": decode(latest["fields"]), "conflicts": decode(latest["conflicts"]),
        })
    except ValidationError:
        raise HTTPException(status_code=422, detail="legacy or invalid extraction; recapture and re-extract") from None
    # The contract is checked against the CURRENT offer type, not the one
    # stored with the proposal: re-typing an offer must invalidate the old
    # pack instead of letting a stale one be inherited.
    row = await pool.fetchrow("SELECT offer_type FROM offers WHERE id = $1", offer_id)
    offer_type = (row["offer_type"] if row else "") or ""
    per_field, problems, established = await _extraction_problems(pool, offer_id, extraction)
    fact_pack = build_fact_pack(offer_type, extraction.fields, established=established)
    _, type_problems = derive_completeness(offer_type, fact_pack)
    problems = list(problems) + type_problems
    if _require_fetch_provenance():
        problems = list(problems) + await _provenance_problems(pool, offer_id, extraction)
    if _require_extraction_coverage():
        problems = list(problems) + await _coverage_problems(
            pool, offer_id, extraction, latest["coverage"],
        )
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))


async def _validate_coverage(pool, offer_id: uuid.UUID,
                             coverage: Optional[ExtractionCoverage]) -> Optional[dict]:
    """Verify that the extractor examined every section of the stored snapshots.

    The section count depends only on the snapshot text and the boundary rule, so
    the API can recompute it. A producer that silently truncated the document
    reports fewer sections and is rejected here — a claim of coverage is not
    accepted on the caller's word.
    """
    if coverage is None:
        return None
    if coverage.version != SECTIONS_VERSION:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported extraction coverage version; expected {SECTIONS_VERSION!r}",
        )
    if coverage.max_section_chars != MAX_SECTION_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"coverage max_section_chars must be {MAX_SECTION_CHARS}",
        )
    evidence_ids = list(dict.fromkeys(coverage.evidence_ids))
    rows = await pool.fetch(
        "SELECT id, captured_content FROM evidence "
        "WHERE offer_id = $1 AND id = ANY($2::uuid[])",
        offer_id, evidence_ids,
    )
    if len(rows) != len(evidence_ids):
        raise HTTPException(
            status_code=422,
            detail="coverage references evidence outside this offer",
        )
    expected = sum(len(split_sections(row["captured_content"] or "")) for row in rows)
    if coverage.sections_total != expected:
        raise HTTPException(
            status_code=422,
            detail=(
                "coverage section count does not match the stored snapshots "
                f"({coverage.sections_total} claimed, {expected} expected); the "
                "document may have been truncated"
            ),
        )
    return {
        "version": SECTIONS_VERSION,
        "sections_total": expected,
        "max_section_chars": MAX_SECTION_CHARS,
        "evidence_ids": [str(item) for item in evidence_ids],
    }


async def _extraction_problems(pool, offer_id: uuid.UUID, extraction: ExtractionIn) -> tuple[dict[str, list[str]], list[str], set[str]]:
    """Per-field problems, the flat problem list, and the established field names."""
    ids = list({field.evidence_id for field in extraction.fields.values()})
    evidence = await pool.fetch(
        "SELECT e.id, e.url, e.official, e.domain_ok, e.captured_content, e.content_hash, "
        "o.provider, e.source_id FROM evidence e JOIN offers o ON o.id = e.offer_id "
        "WHERE e.offer_id = $1 AND e.id = ANY($2::uuid[]) AND e.official AND e.domain_ok",
        offer_id, ids,
    )
    authorized = []
    for row in evidence:
        if await _provider_domain_ok(pool, row["provider"], row["url"], row["source_id"]):
            authorized.append(row)
    per_field = field_problems(extraction, authorized)
    return per_field, extraction_problems(extraction, authorized), established_fields(extraction, authorized)


def _same_url(left: str, right: str) -> bool:
    """Compare URLs for identity, tolerating default ports and case."""

    def parts(value: str):
        split = urlsplit(value)
        scheme = split.scheme.lower()
        return (
            scheme,
            (split.hostname or "").lower().rstrip("."),
            split.port or (443 if scheme == "https" else 80),
            split.path or "/",
            split.query,
        )

    return parts(left) == parts(right)


#: Small allowance for worker/host clock skew, never a reason to trust the future.
PROVENANCE_FUTURE_SKEW = timedelta(minutes=5)


async def _validate_provenance(pool, provider: str, evidence: EvidenceIn,
                               raw_hash: Optional[str]) -> Optional[dict]:
    """Re-check fetch provenance server-side. Every URL in the chain is gated."""
    provenance = evidence.provenance
    if provenance is None:
        return None
    if raw_hash is None:
        raise HTTPException(status_code=422, detail="provenance requires the raw snapshot bytes")
    if provenance.raw_sha256 != raw_hash:
        raise HTTPException(
            status_code=422,
            detail="raw snapshot hash does not match the supplied provenance",
        )
    if not _same_url(str(evidence.url), str(provenance.final_url)):
        raise HTTPException(
            status_code=422,
            detail="evidence url must be the final fetched URL",
        )
    redirects = [str(url) for url in provenance.redirects]
    if redirects and not _same_url(redirects[-1], str(provenance.final_url)):
        raise HTTPException(
            status_code=422,
            detail="redirect chain must end at the final fetched URL",
        )
    if provenance.fetched_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="fetched_at must include a timezone")
    if provenance.fetched_at > datetime.now(timezone.utc) + PROVENANCE_FUTURE_SKEW:
        raise HTTPException(status_code=422, detail="fetched_at is in the future")

    # Permission is part of the record: a page may only become official
    # evidence when the host's robots policy was readable and permitted the
    # read *before* it happened (master plan §3, §6 step 2).
    robots = provenance.robots
    if robots is None:
        raise HTTPException(
            status_code=422,
            detail="provenance requires the robots.txt decision recorded with the fetch",
        )
    if not robots.allowed:
        raise HTTPException(
            status_code=422,
            detail="robots.txt did not permit reading this page; it cannot become evidence",
        )
    if robots.checked_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="robots checked_at must include a timezone")
    if robots.checked_at > datetime.now(timezone.utc) + PROVENANCE_FUTURE_SKEW:
        raise HTTPException(status_code=422, detail="robots checked_at is in the future")
    if robots.checked_at > provenance.fetched_at:
        raise HTTPException(
            status_code=422,
            detail="the robots check must not postdate the page fetch",
        )
    robots_url = str(robots.robots_url)
    robots_parts = urlsplit(robots_url)
    final_parts = urlsplit(str(provenance.final_url))
    if robots_parts.scheme.lower() != "https":
        raise HTTPException(status_code=422, detail="robots URL must be https")
    if (robots_parts.hostname or "") != (final_parts.hostname or "") \
            or robots_parts.path != "/robots.txt":
        raise HTTPException(
            status_code=422,
            detail="robots decision must come from the fetched host's /robots.txt",
        )

    chain = [str(provenance.requested_url), *redirects, str(provenance.final_url)]
    for url in chain:
        if urlsplit(url).scheme.lower() != "https":
            raise HTTPException(status_code=422, detail="provenance URLs must be https")
        if not await _provider_domain_ok(pool, provider, url, evidence.source_id):
            raise HTTPException(
                status_code=422,
                detail=f"provenance URL {url} is not on the provider's registered domains",
            )

    # Who says so? A signature binds the record to the deployment's acquisition
    # key; without it `fetch_identity` is only a string the caller chose. Checked
    # last so an off-provider chain is still reported as what it is.
    signature = _verified_signature(provenance)

    return {
        "requested_url": str(provenance.requested_url),
        "fetch_status": provenance.http_status,
        "fetch_content_type": provenance.content_type,
        "fetched_at": provenance.fetched_at,
        "redirects": redirects,
        "parser_version": provenance.parser_version,
        "fetch_identity": provenance.fetch_identity,
        "robots_url": robots_url,
        "robots_checked_at": robots.checked_at,
        "robots_allowed": robots.allowed,
        "robots_status": robots.status,
        "fetch_signature": signature,
    }


def _require_fetch_provenance() -> bool:
    """Raw-byte provenance is required by default; only an explicit opt-out
    (migration of a legacy deployment) disables it."""
    value = os.environ.get("MTK_REQUIRE_FETCH_PROVENANCE", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _fetch_signing_key() -> str:
    return os.environ.get("MTK_FETCH_SIGNING_KEY", "").strip()


def _require_fetch_signature() -> bool:
    """Signed provenance is required by default for the same reason."""
    value = os.environ.get("MTK_REQUIRE_FETCH_SIGNATURE", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _require_extraction_coverage() -> bool:
    """Machine evidence must record what the extractor examined (slice 9)."""
    value = os.environ.get("MTK_REQUIRE_EXTRACTION_COVERAGE", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _require_tos_attestation() -> bool:
    """Machine reading needs contractual permission, not just robots.txt."""
    value = os.environ.get("MTK_REQUIRE_TOS_ATTESTATION", "1")
    return value.strip().lower() not in {"0", "false", "no", "off"}


async def _require_source_tos_attestation(pool, evidence: EvidenceIn) -> None:
    """Refuse machine-collected evidence for a source with no recorded review."""
    if evidence.source_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "machine-collected evidence must name the registered source "
                "whose terms were reviewed"
            ),
        )
    row = await pool.fetchrow(
        "SELECT tos_reviewed_at FROM sources WHERE id = $1", evidence.source_id,
    )
    if row is None or row["tos_reviewed_at"] is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "machine collection of this source requires a recorded "
                "terms-of-service review; a reviewer must record one at "
                "POST /sources/{id}/tos-review before evidence is stored"
            ),
        )
    if not tos_review.is_valid(row["tos_reviewed_at"]):
        raise HTTPException(
            status_code=422,
            detail=(
                "the recorded terms-of-service review for this source has "
                "expired; a reviewer must record a current review at "
                "POST /sources/{id}/tos-review before evidence is stored"
            ),
        )


async def _coverage_problems(pool, offer_id: uuid.UUID, extraction: ExtractionIn,
                             coverage_text) -> list[str]:
    """Every machine snapshot a claim uses must be listed as examined."""
    ids = list({field.evidence_id for field in extraction.fields.values()})
    rows = await pool.fetch(
        "SELECT id, reviewer FROM evidence "
        "WHERE offer_id = $1 AND id = ANY($2::uuid[]) AND official AND domain_ok",
        offer_id, ids,
    )
    machine = {str(row["id"]) for row in rows if row["reviewer"] is None}
    if not machine:
        # Reviewer-attested snapshots are a recorded human action; there is no
        # acquisition run to account for.
        return []
    coverage = decode(coverage_text)
    if not isinstance(coverage, dict) or not coverage.get("evidence_ids"):
        return [
            "verified requires an extraction coverage record for "
            "machine-collected evidence; re-run sectioned extraction"
        ]
    listed = {str(item) for item in coverage["evidence_ids"]}
    if machine - listed:
        return [
            "extraction coverage does not include every machine-collected "
            "snapshot its claims use"
        ]
    return []


def _verified_signature(provenance: EvidenceProvenance) -> Optional[str]:
    """Re-check that the acquisition identity really produced this record."""
    if not _require_fetch_signature():
        return provenance.signature
    key = _fetch_signing_key()
    if len(key) < 32:
        # A server misconfiguration, not a bad request: refuse to accept
        # machine evidence rather than silently downgrade to an unsigned claim.
        raise HTTPException(
            status_code=503,
            detail="fetch provenance signing is not configured "
                   "(MTK_FETCH_SIGNING_KEY); machine evidence cannot be accepted",
        )
    if not provenance.signature:
        raise HTTPException(
            status_code=422,
            detail="provenance is not signed by a trusted acquisition identity",
        )
    if not verify_provenance(provenance, provenance.signature, key):
        raise HTTPException(
            status_code=422,
            detail="provenance signature does not match its contents",
        )
    return provenance.signature


async def _provenance_problems(pool, offer_id: uuid.UUID,
                               extraction: ExtractionIn) -> list[str]:
    """Official machine evidence must prove the bytes it was derived from."""
    ids = list({field.evidence_id for field in extraction.fields.values()})
    rows = await pool.fetch(
        "SELECT e.id, e.reviewer, e.raw_content IS NOT NULL AS raw_preserved, "
        "e.requested_url, e.parser_version, e.robots_url, e.robots_allowed, "
        "e.fetch_signature "
        "FROM evidence e "
        "WHERE e.offer_id = $1 AND e.id = ANY($2::uuid[]) AND e.official AND e.domain_ok",
        offer_id, ids,
    )
    require_signature = _require_fetch_signature()
    missing = [
        str(row["id"]) for row in rows
        # A reviewer-attested snapshot is a human action recorded in the audit
        # log; machine-collected evidence must carry the bytes it was parsed from,
        # the permission decision that allowed the read and the signature that
        # attributes the record to the acquisition identity.
        if row["reviewer"] is None
        and (not row["raw_preserved"] or not row["requested_url"]
             or not row["parser_version"] or not row["robots_url"]
             or row["robots_allowed"] is not True
             or (require_signature and not row["fetch_signature"]))
    ]
    if missing:
        return [
            "verified requires preserved raw page bytes, fetch provenance, a "
            "permitted robots.txt check and a signed acquisition record for "
            f"official evidence ({len(missing)} snapshot(s) missing); recapture "
            "with the acquisition worker"
        ]
    return []


async def _provider_domain_ok(pool: asyncpg.Pool, provider: str, url: str,
                              source_id: Optional[uuid.UUID] = None) -> bool:
    """Only currently enabled Tier-A sources can confer official ownership."""
    rows = await pool.fetch(
        "SELECT canonical_domain FROM sources WHERE lower(btrim(provider)) = lower(btrim($1)) "
        "AND enabled AND trust_tier = 'A_provider_owned' "
        "AND ($2::uuid IS NULL OR id = $2)",
        provider, source_id,
    )
    return domain_matches(url, [r["canonical_domain"] for r in rows if r["canonical_domain"]])


async def _audit(pool: asyncpg.Pool, *, actor: str, action: str, entity: str,
                 entity_id: Optional[uuid.UUID] = None,
                 detail: Optional[dict] = None) -> None:
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        actor, action, entity, entity_id, _json(detail or {}),
    )


def _json(value) -> str:
    return json.dumps(value, default=str)
