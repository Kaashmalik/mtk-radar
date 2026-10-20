"""Offers router — the verification desk (Weeks 3-4, master plan §3/§18).

Rules enforced here, not trusted from callers:
- Verified requires >= 1 evidence snapshot with official=true AND domain_ok=true.
- Transitions follow the state machine (state.py); approval targets require a
  recorded reviewer.
- Material edits demote verified+ offers back to evidence_needed (correction
  workflow) and reset recheck_at.
- Every state change writes an audit_log row (actor, action, entity, note).
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import asyncpg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

import db
from redact import scan as scan_secrets
from schemas import (
    EvidenceIn,
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

router = APIRouter(prefix="/offers", tags=["offers"])

MATERIAL_FIELDS = {
    "eligibility", "value", "claim_steps", "promo_code", "redemption_url",
    "expires_at", "renewal",
}
RECHECK_INTERVAL = "2 days"  # verified offers must be rechecked before this elapses


# ---------------------------------------------------------------- create


@router.post("/from-item/{item_id}", status_code=201)
async def promote_item(item_id: uuid.UUID, offer: OfferIn) -> dict:
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
    await _audit(pool, actor="reviewer", action="promote_item", entity="offers",
                 entity_id=row["id"], detail={"item_id": str(item_id)})
    return {"id": row["id"], "state": row["state"]}


@router.post("", status_code=201)
async def create_offer(offer: OfferIn) -> dict:
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
    await _audit(pool, actor="reviewer", action="create_offer", entity="offers", entity_id=row["id"])
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
               s.provider AS source_provider, s.trust_tier::text AS trust_tier
        FROM evidence e LEFT JOIN sources s ON s.id = e.source_id
        WHERE e.offer_id = $1 ORDER BY e.captured_at DESC
        """,
        offer_id,
    )
    extraction = await pool.fetchrow(
        """
        SELECT fields::text AS fields, conflicts::text AS conflicts, complete, model, created_at
        FROM extractions WHERE offer_id = $1 ORDER BY created_at DESC LIMIT 1
        """,
        offer_id,
    )
    return {
        **dict(offer),
        "evidence": [dict(r) for r in evidence],
        "extraction": dict(extraction) if extraction else None,
    }


# ---------------------------------------------------------------- update


@router.patch("/{offer_id}")
async def update_offer(offer_id: uuid.UUID, update: OfferUpdate) -> dict:
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
    await _audit(pool, actor="reviewer", action="update_offer", entity="offers",
                 entity_id=offer_id, detail={"demoted": demoted, "fields": list(payload)})
    return {"id": row["id"], "state": row["state"], "demoted": demoted}


# ---------------------------------------------------------------- evidence


@router.post("/{offer_id}/evidence", status_code=201)
async def add_evidence(offer_id: uuid.UUID, evidence: EvidenceIn) -> dict:
    """Immutable evidence snapshot. Hash is computed server-side; identical
    content dedupes. domain_ok is decided HERE via the provider allowlist —
    callers cannot self-certify an official source."""
    pool = db.get()
    offer = await pool.fetchrow(
        "SELECT provider FROM offers WHERE id = $1", offer_id
    )
    if not offer:
        raise HTTPException(status_code=404, detail="offer not found")

    captured = evidence.captured_content or evidence.excerpt or ""
    content_hash = hashlib.sha256(captured.encode("utf-8")).hexdigest()
    domain_ok = await _provider_domain_ok(pool, offer["provider"], str(evidence.url))

    if evidence.official and not domain_ok:
        raise HTTPException(
            status_code=422,
            detail="official evidence URL is not on the provider's registered domains "
                   "(register the official source in the source registry first)",
        )

    row = await pool.fetchrow(
        """
        INSERT INTO evidence (offer_id, source_id, url, content_hash, excerpt,
                              screenshot_path, supported_fields, official, domain_ok, reviewer)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        offer_id, evidence.source_id, str(evidence.url), content_hash,
        evidence.excerpt, evidence.screenshot_path, _json(evidence.supported_fields),
        evidence.official, domain_ok, evidence.reviewer,
    )
    await _audit(pool, actor=evidence.reviewer or "worker", action="add_evidence",
                 entity="evidence", entity_id=row["id"] if row else None,
                 detail={"offer_id": str(offer_id), "official": evidence.official,
                         "domain_ok": domain_ok, "content_hash": content_hash})
    if not row:
        return {"created": False, "duplicate": True, "content_hash": content_hash, "domain_ok": domain_ok}
    return {"id": row["id"], "created": True, "duplicate": False,
            "content_hash": content_hash, "domain_ok": domain_ok}


# ---------------------------------------------------------------- extraction


@router.post("/{offer_id}/extraction", status_code=201)
async def add_extraction(offer_id: uuid.UUID, extraction: ExtractionIn) -> dict:
    pool = db.get()
    if not await pool.fetchrow("SELECT id FROM offers WHERE id = $1", offer_id):
        raise HTTPException(status_code=404, detail="offer not found")
    row = await pool.fetchrow(
        """
        INSERT INTO extractions (offer_id, fields, conflicts, complete, model)
        VALUES ($1, $2::jsonb, $3::jsonb, $4, $5)
        RETURNING id
        """,
        offer_id, _json(extraction.fields), _json(extraction.conflicts),
        extraction.complete, extraction.model,
    )
    if extraction.conflicts:
        await pool.execute(
            "UPDATE offers SET correction_note = $2, updated_at = now() WHERE id = $1",
            offer_id, f"{len(extraction.conflicts)} extraction conflict(s) need review",
        )
    await _audit(pool, actor="worker", action="add_extraction", entity="extractions",
                 entity_id=row["id"], detail={"complete": extraction.complete,
                                              "conflicts": len(extraction.conflicts)})
    return {"id": row["id"]}


# ---------------------------------------------------------------- transitions


@router.post("/{offer_id}/transition")
async def transition(offer_id: uuid.UUID, t: TransitionIn) -> dict:
    pool = db.get()
    offer = await pool.fetchrow(
        "SELECT state::text AS state, title, provider FROM offers WHERE id = $1", offer_id
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

    if requires_review(target) and not t.reviewer:
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
        recheck_clause = f", recheck_at = now() + ${len(params)}::interval"

    row = await pool.fetchrow(
        f"UPDATE offers SET state = ${2}::offer_state{recheck_clause}, updated_at = now() "
        f"WHERE id = $1 RETURNING state::text AS state",
        *params,
    )
    await _audit(pool, actor=t.reviewer or "worker", action=f"transition:{current}->{target}",
                 entity="offers", entity_id=offer_id, detail={"note": t.note})
    return {"id": offer_id, "state": row["state"], "previous": current}


# ---------------------------------------------------------------- corrections + impact (week 11)


class CorrectionIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)
    corrected_by: str = Field(min_length=1)
    version_hash: Optional[str] = None


@router.post("/{offer_id}/corrections", status_code=201)
async def add_correction(offer_id: uuid.UUID, body: CorrectionIn) -> dict:
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

    row = await pool.fetchrow(
        """
        INSERT INTO offer_corrections (offer_id, note, corrected_by, version_hash)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        offer_id, body.note, body.corrected_by, body.version_hash,
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

    await _audit(pool, actor=body.corrected_by,
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
async def create_script(offer_id: uuid.UUID, created_by: str = Query(default="reviewer")) -> dict:
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
    payload = generate_script_payload(dict(offer), [dict(r) for r in evidence])

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
        _json(payload["command_cards"]), created_by,
    )
    await _audit(pool, actor=created_by, action="generate_script", entity="offer_scripts",
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
    return [dict(r) for r in rows]


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
    """'verified' requires official, domain-checked evidence AND a complete
    extraction with every field linked to its evidence URL (§3)."""
    stats = await pool.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM evidence e
            WHERE e.offer_id = $1 AND e.official AND e.domain_ok) AS official_ok,
          (SELECT COUNT(*) FROM evidence e WHERE e.offer_id = $1) AS total_evidence,
          (SELECT x.complete FROM extractions x
            WHERE x.offer_id = $1 ORDER BY x.created_at DESC LIMIT 1) AS extraction_complete
        """,
        offer_id,
    )
    problems = []
    if not stats["official_ok"]:
        problems.append("requires at least one official, provider-domain-checked evidence snapshot")
    if stats["total_evidence"] == 0:
        problems.append("requires evidence snapshots")
    if stats["extraction_complete"] is not True:
        problems.append("requires a complete structured extraction (fields → evidence URLs)")

    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))


async def _provider_domain_ok(pool: asyncpg.Pool, provider: str, url: str) -> bool:
    """Allowlist check: URL host must be (a subdomain of) a canonical domain
    registered for this provider in the source registry (§3)."""
    rows = await pool.fetch(
        "SELECT canonical_domain, account_handle FROM sources WHERE provider ILIKE $1",
        provider,
    )
    domains = {
        r["canonical_domain"].lower()
        for r in rows
        if r["canonical_domain"]
    }
    if not domains:
        return False
    host = (urlsplit(url).hostname or "").lower()
    for domain in domains:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


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
