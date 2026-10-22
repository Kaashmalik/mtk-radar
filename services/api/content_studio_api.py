"""Content Studio API (v0.27).

One explicit generation action produces the complete reviewable content set
for an offer:

  * English + Urdu scripts (same verified facts, separate approval hashes)
  * per-platform metadata variants (A/B hooks, hashtags, CTA, pinned comment)
  * cover/thumbnail specifications for 16:9 and 9:16
  * structured beat sheets used by the motion renderer

Nothing is published here. The existing approval → render → schedule gates
remain the only path to a live post.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

import db
from api_hardening import effective_reviewer
from schedules_state import script_version_hash
from seo import PLATFORMS, build_variants
from settings_store import audit, get_language_policy, get_value
from scriptgen import (
    SCRIPT_FORMATS,
    ScriptGateError,
    SUPPORTED_LANGUAGES,
    generate_multilingual,
)
from state import can_generate_video

router = APIRouter(prefix="/studio", tags=["studio"])


class StudioGenerateIn(BaseModel):
    # Empty = every voiceover language enabled in Settings → Language policy.
    languages: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["youtube", "instagram", "tiktok"])
    website_url: Optional[str] = None
    create_variants: bool = True
    # Safe default: explain the official terms. First-person formats require a
    # human-reviewed capture (and, for claim_walkthrough, a demonstrated claim).
    format: str = Field(default="official_explainer")


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


async def _brand(pool) -> dict[str, Any]:
    stored = await get_value(pool, "brand")
    return (stored or {}).get("value") or {}


async def _offer(pool, offer_id: uuid.UUID) -> dict[str, Any]:
    row = await pool.fetchrow(
        """
        SELECT id, title, provider, category, offer_type,
               eligibility::text AS eligibility, value::text AS value,
               claim_steps::text AS claim_steps, promo_code, redemption_url,
               expires_at, renewal::text AS renewal, state::text AS state,
               correction_note
        FROM offers WHERE id = $1
        """,
        offer_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="offer not found")
    offer = dict(row)
    for key in ("eligibility", "value", "claim_steps", "renewal"):
        if isinstance(offer.get(key), str):
            try:
                offer[key] = json.loads(offer[key])
            except ValueError:
                offer[key] = {} if key in ("eligibility", "value", "renewal") else []
    return offer


@router.get("/offers/{offer_id}")
async def studio_overview(offer_id: uuid.UUID) -> dict:
    pool = db.get()
    offer = await _offer(pool, offer_id)
    brand = await _brand(pool)
    language_policy = await get_language_policy(pool)

    scripts = await pool.fetch(
        """
        SELECT id, version, language, markdown, metadata::text AS metadata,
               created_by, created_at
        FROM offer_scripts WHERE offer_id = $1
        ORDER BY language, version DESC
        """,
        offer_id,
    )
    variants = await pool.fetch(
        """
        SELECT id, language, kind, platform, variant_key, payload::text AS payload,
               text_content, status, version, version_hash, created_at
        FROM content_variants WHERE offer_id = $1
        ORDER BY language, kind, platform, variant_key, version DESC
        """,
        offer_id,
    )
    def decode_payload(row) -> dict:
        item = dict(row)
        for key in ("payload", "metadata"):
            if isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except ValueError:
                    item[key] = {} if key == "metadata" else item[key]
        return item

    return {
        "offer": offer,
        "brand": brand,
        "languages": list(SUPPORTED_LANGUAGES),
        "allowed_narration_languages": language_policy["narration_languages"],
        "language_policy": language_policy,
        "platforms": list(PLATFORMS),
        "scripts": [decode_payload(r) for r in scripts],
        "variants": [decode_payload(r) for r in variants],
        "has_content": bool(scripts),
    }


@router.post("/offers/{offer_id}/generate", status_code=201)
async def generate_content(offer_id: uuid.UUID, body: StudioGenerateIn,
                           request: Request) -> dict:
    pool = db.get()
    offer = await _offer(pool, offer_id)
    if not can_generate_video(offer.get("state", "")):
        raise HTTPException(
            status_code=409,
            detail=f"content generation blocked: offer state is '{offer.get('state')}' "
                   "— verified official evidence is required (§3)",
        )

    language_policy = await get_language_policy(pool)
    allowed = language_policy["narration_languages"]
    requested = body.languages or allowed
    unknown = [lang for lang in requested if lang not in SUPPORTED_LANGUAGES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported language(s): {', '.join(unknown)}",
        )
    blocked = [lang for lang in requested if lang not in allowed]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=(
                f"voiceover disabled for {', '.join(blocked)} — enable it in "
                "Settings → Language policy first"
            ),
        )
    languages = list(dict.fromkeys(requested))
    if not languages:
        raise HTTPException(status_code=422, detail="choose at least one of: en, ur")
    platforms = [platform for platform in body.platforms if platform in PLATFORMS]
    if not platforms:
        raise HTTPException(status_code=422, detail=f"choose at least one of: {', '.join(PLATFORMS)}")

    evidence = await pool.fetch(
        """
        SELECT url, captured_at, excerpt FROM evidence
        WHERE offer_id = $1 AND official AND domain_ok
        ORDER BY captured_at DESC
        """,
        offer_id,
    )
    evidence_rows = [dict(r) for r in evidence]
    if not evidence_rows:
        raise HTTPException(status_code=409, detail="no official evidence — cannot generate content")

    brand = await _brand(pool)
    website = body.website_url or brand.get("website_url") or offer.get("redemption_url") or ""
    correction_base = os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    correction_url = f"{correction_base}/offers/{offer_id}" if correction_base else None
    disclosure = {"synthetic_narration": True}

    if body.format not in SCRIPT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown script format '{body.format}' — known: {', '.join(SCRIPT_FORMATS)}",
        )
    captures = await pool.fetch(
        """
        SELECT id, redaction_reviewed, reviewer, claim_outcome
        FROM capture_sessions WHERE offer_id = $1
        ORDER BY (claim_outcome = 'demonstrated') DESC, created_at DESC
        """,
        offer_id,
    )
    capture = next(
        (dict(r) for r in captures if r["redaction_reviewed"]),
        None,
    )
    actor = effective_reviewer(request, None, default="operator")
    try:
        generated = generate_multilingual(
            offer, evidence_rows, tuple(languages),
            script_format=body.format, capture=capture,
        )
    except ScriptGateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    created_scripts = 0
    created_variants = 0
    script_versions: dict[str, int] = {}
    for language in languages:
        payload = generated["languages"][language]
        version_row = await pool.fetchrow(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM offer_scripts "
            "WHERE offer_id = $1 AND language = $2",
            offer_id, language,
        )
        version = int(version_row["next"])
        script_versions[language] = version
        metadata = {
            "beats": payload["beats"],
            "checklist": payload["checklist"],
            "command_cards": payload["command_cards"],
            "language": language,
            "format": body.format,
            "voiceover_language": language,
            "copy_language": language_policy["metadata_language"],
            "captions_language": language_policy["captions_language"],
        }
        row = await pool.fetchrow(
            """
            INSERT INTO offer_scripts
                (offer_id, version, language, format, markdown, checklist,
                 command_cards, created_by, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb)
            RETURNING id
            """,
            offer_id, version, language, body.format, payload["markdown"],
            _json(payload["checklist"]), _json(payload["command_cards"]),
            actor, _json(metadata),
        )
        created_scripts += 1
        await pool.execute(
            """
            INSERT INTO content_variants
                (offer_id, language, kind, variant_key, payload, text_content,
                 version, version_hash, created_by, status)
            VALUES ($1, $2, 'script', 'default', $3::jsonb, $4, $5, $6, $7, 'draft')
            ON CONFLICT (offer_id, language, kind, platform, variant_key, version)
            DO NOTHING
            """,
            offer_id, language, _json(metadata), payload["markdown"], version,
            script_version_hash(payload["markdown"]), actor,
        )
        created_variants += 1

        if not body.create_variants:
            continue
        for platform in platforms:
            variants = build_variants(
                platform, offer, evidence_urls=[e["url"] for e in evidence_rows],
                disclosure=disclosure, correction_url=correction_url,
                website_url=website,
                # English-first package even for an Urdu voiceover video.
                language=language_policy["metadata_language"],
            )
            for index, meta in enumerate(variants):
                key = "a" if index == 0 else "b"
                await pool.execute(
                    """
                    INSERT INTO content_variants
                        (offer_id, language, kind, platform, variant_key, payload,
                         text_content, version, version_hash, created_by, status)
                    VALUES ($1, $2, 'metadata', $3, $4, $5::jsonb, $6, $7, $8, $9, 'draft')
                    ON CONFLICT (offer_id, language, kind, platform, variant_key, version)
                    DO NOTHING
                    """,
                    offer_id, language, platform, key, _json(meta),
                    meta.get("caption") or meta.get("title"),
                    version, script_version_hash(_json(meta)), actor,
                )
                created_variants += 1

        copy_language = language_policy["metadata_language"]
        cover_spec = {
            "language": copy_language,
            "voiceover_language": language,
            "title": offer.get("title", "Offer walkthrough"),
            "provider": offer.get("provider", ""),
            "eyebrow": "VERIFIED CLAIM" if copy_language == "en" else "تصدیق شدہ کلیم",
            "cta": "Real walkthrough · sources below" if copy_language == "en"
                   else "حقیقی کلیم · ذرائع نیچے",
            "website_url": website,
            "palette": {"bg": "#07111f", "accent": "#38bdf8", "warm": "#fbbf24",
                        "text": "#f8fafc", "muted": "#94a3b8"},
            "presets": [
                {"key": "landscape", "width": 1280, "height": 720},
                {"key": "vertical", "width": 1080, "height": 1920},
            ],
        }
        await pool.execute(
            """
            INSERT INTO content_variants
                (offer_id, language, kind, variant_key, payload, text_content,
                 version, version_hash, created_by, status)
            VALUES ($1, $2, 'cover', 'default', $3::jsonb, $4, $5, $6, $7, 'draft')
            ON CONFLICT (offer_id, language, kind, platform, variant_key, version)
            DO NOTHING
            """,
            offer_id, language, _json(cover_spec), cover_spec["title"],
            version, script_version_hash(_json(cover_spec)), actor,
        )
        created_variants += 1

    await audit(pool, actor=actor, action="studio:generate", entity="content_variants",
                entity_id=offer_id,
                detail={"languages": languages, "platforms": platforms,
                        "scripts": created_scripts, "variants": created_variants})
    return {
        "offer_id": str(offer_id),
        "languages": languages,
        "metadata_language": language_policy["metadata_language"],
        "captions_language": language_policy["captions_language"],
        "allowed_narration_languages": allowed,
        "platforms": platforms,
        "script_versions": script_versions,
        "scripts_created": created_scripts,
        "variants_created": created_variants,
        "website_url": website,
        "message": "Content generated as drafts. Review, approve, render, then schedule.",
    }


class VariantApprovalIn(BaseModel):
    approved: bool = True
    note: Optional[str] = None


class ExperimentIn(BaseModel):
    offer_id: uuid.UUID
    variant_id: Optional[uuid.UUID] = None
    schedule_id: Optional[uuid.UUID] = None
    language: str = "en"
    platform: Optional[str] = None
    hypothesis: str = Field(min_length=8, max_length=2000)
    metric: str = Field(default="views", min_length=2, max_length=64)
    status: str = "planned"


class ExperimentAssignIn(BaseModel):
    schedule_id: uuid.UUID


class ExperimentDecisionIn(BaseModel):
    status: str
    note: Optional[str] = None
    result: dict = Field(default_factory=dict)


@router.post("/variants/{variant_id}/approve")
async def approve_variant(variant_id: uuid.UUID, body: VariantApprovalIn,
                          request: Request) -> dict:
    """Approve/archive the exact generated variant a reviewer inspected.

    Scheduling only accepts `approved` metadata variants, so this is the human
    gate between Content Studio drafts and the calendar."""
    pool = db.get()
    variant = await pool.fetchrow(
        "SELECT id, offer_id, kind, status, payload::text AS payload FROM content_variants "
        "WHERE id = $1", variant_id,
    )
    if not variant:
        raise HTTPException(status_code=404, detail="content variant not found")
    actor = effective_reviewer(request, None, default="operator")
    status = "approved" if body.approved else "archived"
    await pool.execute(
        "UPDATE content_variants SET status = $2, updated_at = now() WHERE id = $1",
        variant_id, status,
    )
    await audit(pool, actor=actor, action=f"studio:variant:{status}",
                entity="content_variants", entity_id=variant_id,
                detail={"offer_id": str(variant["offer_id"]), "note": body.note})
    return {"id": str(variant_id), "status": status, "approved": body.approved}


@router.get("/offers/{offer_id}/experiments")
async def list_experiments(offer_id: uuid.UUID) -> list[dict]:
    pool = db.get()
    rows = await pool.fetch(
        "SELECT id, offer_id, schedule_id, variant_id, language, platform, hypothesis, "
        "metric, status, result::text AS result, decision_note, decided_by, decided_at, "
        "created_at, updated_at FROM content_experiments WHERE offer_id = $1 "
        "ORDER BY created_at DESC",
        offer_id,
    )
    return [{**dict(row), "result": json.loads(row["result"]) if row["result"] else {}}
            for row in rows]


@router.post("/experiments", status_code=201)
async def create_experiment(body: ExperimentIn, request: Request) -> dict:
    if body.status not in ("planned", "running"):
        raise HTTPException(status_code=422, detail="a new experiment is planned or running")
    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail=f"unknown language '{body.language}'")
    if body.platform and body.platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail=f"unknown platform '{body.platform}'")
    pool = db.get()
    if body.variant_id:
        variant = await pool.fetchrow(
            "SELECT id, offer_id, status, platform, language FROM content_variants "
            "WHERE id = $1",
            body.variant_id,
        )
        if not variant or variant["offer_id"] != body.offer_id:
            raise HTTPException(status_code=404, detail="variant not found for this offer")
        if variant["status"] != "approved":
            raise HTTPException(status_code=409, detail="experiment variant must be approved")
        if body.platform and variant["platform"] not in (None, body.platform):
            raise HTTPException(status_code=409, detail="variant belongs to another platform")
        if body.language and variant["language"] != body.language:
            raise HTTPException(status_code=409, detail="variant belongs to another language")
    if body.schedule_id:
        schedule = await pool.fetchrow(
            "SELECT id, offer_id, platform, language FROM schedules WHERE id = $1",
            body.schedule_id,
        )
        if not schedule or schedule["offer_id"] != body.offer_id:
            raise HTTPException(status_code=404, detail="schedule not found for this offer")
        if body.platform and schedule["platform"] != body.platform:
            raise HTTPException(status_code=409, detail="schedule belongs to another platform")
        if body.language and schedule["language"] != body.language:
            raise HTTPException(status_code=409, detail="schedule belongs to another language")
    actor = effective_reviewer(request, None, default="operator")
    row = await pool.fetchrow(
        "INSERT INTO content_experiments "
        "(offer_id, schedule_id, variant_id, language, platform, hypothesis, metric, "
        " status, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
        "RETURNING id, status",
        body.offer_id, body.schedule_id, body.variant_id, body.language,
        body.platform, body.hypothesis, body.metric, body.status, actor,
    )
    await audit(pool, actor=actor, action="studio:experiment:create",
                entity="content_experiments", entity_id=row["id"],
                detail={"offer_id": str(body.offer_id), "metric": body.metric})
    return {"id": str(row["id"]), "status": row["status"]}


@router.post("/experiments/{experiment_id}/assign")
async def assign_experiment(experiment_id: uuid.UUID, body: ExperimentAssignIn,
                            request: Request) -> dict:
    pool = db.get()
    experiment = await pool.fetchrow(
        "SELECT id, offer_id, variant_id, status FROM content_experiments WHERE id = $1",
        experiment_id,
    )
    if not experiment:
        raise HTTPException(status_code=404, detail="experiment not found")
    if experiment["status"] in ("won", "lost", "inconclusive"):
        raise HTTPException(status_code=409, detail="a decided experiment cannot be reassigned")
    schedule = await pool.fetchrow(
        "SELECT id, offer_id, content_variant_id FROM schedules WHERE id = $1",
        body.schedule_id,
    )
    if not schedule or schedule["offer_id"] != experiment["offer_id"]:
        raise HTTPException(status_code=404, detail="schedule not found for this offer")
    # The schedule's package is immutable. An experiment can only claim a
    # variant that was pinned when the schedule was created; assigning a
    # different variant after the fact would credit metrics to copy that was
    # never uploaded.
    if experiment["variant_id"] and schedule["content_variant_id"] != experiment["variant_id"]:
        raise HTTPException(
            status_code=409,
            detail="schedule was not created with this variant — re-schedule it "
                   "with the variant pinned before assigning the experiment",
        )
    updated = await pool.fetchrow(
        "UPDATE content_experiments SET schedule_id = $2, status = CASE "
        "WHEN status = 'planned' THEN 'running' ELSE status END, updated_at = now() "
        "WHERE id = $1 RETURNING status", experiment_id, body.schedule_id,
    )
    actor = effective_reviewer(request, None, default="operator")
    await audit(pool, actor=actor, action="studio:experiment:assign",
                entity="content_experiments", entity_id=experiment_id,
                detail={"schedule_id": str(body.schedule_id)})
    return {"id": str(experiment_id), "schedule_id": str(body.schedule_id),
            "status": updated["status"]}


@router.post("/experiments/{experiment_id}/decide")
async def decide_experiment(experiment_id: uuid.UUID, body: ExperimentDecisionIn,
                            request: Request) -> dict:
    if body.status not in ("won", "lost", "inconclusive"):
        raise HTTPException(status_code=422, detail="decision must be won, lost, or inconclusive")
    pool = db.get()
    actor = effective_reviewer(request, None, default="operator")
    row = await pool.fetchrow(
        "UPDATE content_experiments SET status = $2, result = $3::jsonb, "
        "decision_note = $4, decided_by = $5, decided_at = now(), updated_at = now() "
        "WHERE id = $1 RETURNING id, status",
        experiment_id, body.status, _json(body.result), body.note, actor,
    )
    if not row:
        raise HTTPException(status_code=404, detail="experiment not found")
    await audit(pool, actor=actor, action=f"studio:experiment:{body.status}",
                entity="content_experiments", entity_id=experiment_id,
                detail={"note": body.note, "result": body.result})
    return {"id": str(row["id"]), "status": row["status"]}


@router.get("/offers/{offer_id}/metadata")
async def metadata_preview(
    offer_id: uuid.UUID,
    platform: str = Query(default="youtube"),
    language: str = Query(default="en"),
) -> dict:
    pool = db.get()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail=f"unknown platform '{platform}'")
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail=f"unknown language '{language}'")
    rows = await pool.fetch(
        """
        SELECT variant_key, payload::text AS payload, status, created_at
        FROM content_variants
        WHERE offer_id = $1 AND kind = 'metadata'
          AND platform = $2 AND language = $3
        ORDER BY variant_key
        """,
        offer_id, platform, language,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="no metadata yet — generate content first")
    return {
        "offer_id": str(offer_id),
        "platform": platform,
        "language": language,
        "variants": [
            {**dict(r), "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]}
            for r in rows
        ],
    }
