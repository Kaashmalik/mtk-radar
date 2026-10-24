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
from research_api import latest_brief_with_claims
from schedules_state import script_version_hash
from seo import PLATFORMS, build_thumbnail_text, build_variants
from settings_store import audit, get_language_policy, get_value
from scriptgen import (
    SCRIPT_FORMATS,
    ScriptGateError,
    SUPPORTED_LANGUAGES,
    assert_format_wording,
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
    # The fact pack is derived server-side per claim field. Generation must
    # use it so a contradicted/unknown fact is written as such — never as
    # "open eligibility" / "never expires" (§6 step 7, A13). Mirrors the
    # offers_api script-generation path; without it the studio (the default
    # content action) rendered supported wording for contested facts.
    fact_pack = await pool.fetchrow(
        """
        SELECT fact_pack::text AS fact_pack FROM extractions
        WHERE offer_id = $1 ORDER BY created_at DESC, id DESC LIMIT 1
        """,
        offer_id,
    )
    if fact_pack and fact_pack["fact_pack"]:
        try:
            offer["fact_pack"] = json.loads(fact_pack["fact_pack"])
        except ValueError:
            offer["fact_pack"] = {}
    # EP-03 G18: attach the current versioned research brief + claim ledger so
    # script generation runs the contradicted-claim gate and the per-class
    # attribution (and never invents offer fields for a paper).
    brief = await latest_brief_with_claims(pool, offer_id)
    if brief:
        offer["research"] = brief
        offer["content_type"] = brief.get("content_type")
    return offer


@router.get("/offers/{offer_id}")
async def studio_overview(offer_id: uuid.UUID) -> dict:
    pool = db.get()
    offer = await _offer(pool, offer_id)
    brand = await _brand(pool)
    language_policy = await get_language_policy(pool)

    scripts = await pool.fetch(
        """
        SELECT id, version, language, format, markdown, metadata::text AS metadata,
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
                # The title may only assert what the script format allows.
                format_hint=body.format,
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
            # 2026 packaging rule: ≤3 words, never the title itself.
            "thumbnail_text": build_thumbnail_text(offer),
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
    # Approving copy is an editorial sign-off: a worker must not do it.
    actor = effective_reviewer(request, None, default="operator", require=True)
    status = "approved" if body.approved else "archived"
    await pool.execute(
        "UPDATE content_variants SET status = $2, updated_at = now() WHERE id = $1",
        variant_id, status,
    )
    await audit(pool, actor=actor, action=f"studio:variant:{status}",
                entity="content_variants", entity_id=variant_id,
                detail={"offer_id": str(variant["offer_id"]), "note": body.note})
    return {"id": str(variant_id), "status": status, "approved": body.approved}


class ScriptReviseIn(BaseModel):
    """An operator-edited script saved as a NEW immutable revision.

    Revisions are append-only: the previously approved version keeps its hash,
    so anything already rendered or scheduled stays pinned to the exact words
    it was approved with. A rewritten script simply becomes a new draft that
    must be re-reviewed.
    """

    markdown: str = Field(min_length=20, max_length=200_000, pattern=r"\S")
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/scripts/{script_id}/revise", status_code=201)
async def revise_script(script_id: uuid.UUID, body: ScriptReviseIn,
                        request: Request) -> dict:
    pool = db.get()
    script = await pool.fetchrow(
        """
        SELECT id, offer_id, language, version, format, markdown,
               metadata::text AS metadata
        FROM offer_scripts WHERE id = $1
        """,
        script_id,
    )
    if not script:
        raise HTTPException(status_code=404, detail="script not found")
    # Editing the spoken words is an editorial act: machine credentials must
    # not rewrite what a human signed off (or is about to sign off).
    actor = effective_reviewer(request, None, default="operator", require=True)
    markdown = body.markdown.strip()
    if markdown == script["markdown"].strip():
        raise HTTPException(
            status_code=422, detail="the revision is identical to the current script",
        )
    # The wording guard runs on the actual edited text, not the generator
    # output: a hand-edited script cannot smuggle in first-person result
    # claims the original format forbids.
    try:
        assert_format_wording(markdown, script["format"])
    except ScriptGateError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"wording guard rejected the revision: {exc}",
        ) from exc

    version_row = await pool.fetchrow(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM offer_scripts "
        "WHERE offer_id = $1 AND language = $2",
        script["offer_id"], script["language"],
    )
    version = int(version_row["next"])
    metadata = {}
    if isinstance(script["metadata"], str):
        try:
            metadata = json.loads(script["metadata"])
        except ValueError:
            metadata = {}
    carried = {
        key: metadata[key] for key in
        ("beats", "checklist", "command_cards", "language", "format",
         "voiceover_language", "copy_language", "captions_language")
        if key in metadata
    }
    carried["revision_note"] = body.note
    carried["revised_from_version"] = int(script["version"])
    row = await pool.fetchrow(
        """
        INSERT INTO offer_scripts
            (offer_id, version, language, format, markdown, checklist,
             command_cards, created_by, metadata)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb)
        RETURNING id
        """,
        script["offer_id"], version, script["language"], script["format"],
        markdown, _json(metadata.get("checklist") or []),
        _json(metadata.get("command_cards") or []), actor, _json(carried),
    )
    await pool.execute(
        """
        INSERT INTO content_variants
            (offer_id, language, kind, variant_key, payload, text_content,
             version, version_hash, created_by, status)
        VALUES ($1, $2, 'script', 'default', $3::jsonb, $4, $5, $6, $7, 'draft')
        ON CONFLICT (offer_id, language, kind, platform, variant_key, version)
        DO NOTHING
        """,
        script["offer_id"], script["language"], _json(carried), markdown,
        version, script_version_hash(markdown), actor,
    )
    await audit(pool, actor=actor, action="studio:script_revise",
                entity="offer_scripts", entity_id=row["id"],
                detail={"offer_id": str(script["offer_id"]),
                        "language": script["language"], "version": version,
                        "revised_from": int(script["version"]), "note": body.note})
    return {
        "id": str(row["id"]),
        "offer_id": str(script["offer_id"]),
        "language": script["language"],
        "version": version,
        "revised_from": int(script["version"]),
        "message": "Revision saved as a new draft. Re-review and re-approve before render.",
    }


EDITABLE_VARIANT_KINDS = ("metadata", "captions", "hook")


class VariantEditIn(BaseModel):
    """An operator-authored variant (title/description copy, captions,
    chapters, hook text) saved as a NEW draft version.

    `payload` carries structured data (e.g. `{"chapters": [{"time": "00:00",
    "label": "..."}]}`); `text_content` carries the flat text. Both pass the
    same wording guard as generated content.
    """

    kind: str
    language: str = "en"
    platform: Optional[str] = None
    variant_key: str = Field(
        default="default", min_length=1, max_length=60,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )
    text_content: str = Field(min_length=1, max_length=100_000, pattern=r"\S")
    payload: dict = Field(default_factory=dict)
    note: Optional[str] = Field(default=None, max_length=2000)


def _validate_chapters(payload: dict) -> list[dict]:
    chapters = payload.get("chapters")
    if chapters is None:
        return []
    if not isinstance(chapters, list) or len(chapters) > 100:
        raise HTTPException(status_code=422,
                            detail="chapters must be a list of at most 100 entries")
    cleaned = []
    for chapter in chapters:
        if (not isinstance(chapter, dict)
                or not isinstance(chapter.get("time"), str)
                or not chapter["time"].strip()
                or not isinstance(chapter.get("label"), str)
                or not chapter["label"].strip()
                or len(chapter["time"]) > 20 or len(chapter["label"]) > 200):
            raise HTTPException(
                status_code=422,
                detail="each chapter needs a 'time' (≤20 chars) and a 'label' (≤200 chars)",
            )
        cleaned.append({"time": chapter["time"].strip(),
                        "label": chapter["label"].strip()})
    payload["chapters"] = cleaned
    return cleaned


@router.post("/offers/{offer_id}/variants", status_code=201)
async def add_variant_edition(offer_id: uuid.UUID, body: VariantEditIn,
                              request: Request) -> dict:
    pool = db.get()
    await _offer(pool, offer_id)  # 404 if unknown
    if body.kind not in EDITABLE_VARIANT_KINDS:
        raise HTTPException(
            status_code=422,
            detail="kind must be one of: " + ", ".join(EDITABLE_VARIANT_KINDS)
                   + " — script and cover variants are generator-owned",
        )
    if body.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422,
                            detail=f"unknown language '{body.language}'")
    if body.kind == "metadata" and body.platform not in PLATFORMS:
        raise HTTPException(
            status_code=422,
            detail=f"metadata variants are per-platform; choose one of: {', '.join(PLATFORMS)}",
        )
    if body.kind == "metadata" and not body.payload and not body.text_content:
        raise HTTPException(status_code=422,
                            detail="metadata edits need payload fields or text_content")
    # Authoring copy is editorial: machine credentials must not add captions,
    # hooks or metadata text to the package.
    actor = effective_reviewer(request, None, default="operator", require=True)
    _validate_chapters(body.payload)

    script = await pool.fetchrow(
        "SELECT format FROM offer_scripts WHERE offer_id = $1 AND language = $2 "
        "ORDER BY version DESC LIMIT 1",
        offer_id, body.language,
    )
    if not script:
        raise HTTPException(
            status_code=409,
            detail=f"no '{body.language}' script yet — generate content first so the "
                   "wording guard knows the script format",
        )
    text = body.text_content.strip()
    try:
        assert_format_wording(text, script["format"])
    except ScriptGateError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"wording guard rejected the edited {body.kind}: {exc}",
        ) from exc

    version_row = await pool.fetchrow(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM content_variants "
        "WHERE offer_id = $1 AND language = $2 AND kind = $3 "
        "AND platform IS NOT DISTINCT FROM $4 AND variant_key = $5",
        offer_id, body.language, body.kind, body.platform, body.variant_key,
    )
    version = int(version_row["next"])
    row = await pool.fetchrow(
        """
        INSERT INTO content_variants
            (offer_id, language, kind, platform, variant_key, payload, text_content,
             version, version_hash, created_by, status)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, 'draft')
        RETURNING id
        """,
        offer_id, body.language, body.kind, body.platform, body.variant_key,
        _json(body.payload), text, version, script_version_hash(text), actor,
    )
    await audit(pool, actor=actor, action="studio:variant:edit",
                entity="content_variants", entity_id=row["id"],
                detail={"offer_id": str(offer_id), "kind": body.kind,
                        "language": body.language, "platform": body.platform,
                        "variant_key": body.variant_key, "version": version,
                        "note": body.note})
    return {
        "id": str(row["id"]), "kind": body.kind, "language": body.language,
        "platform": body.platform, "variant_key": body.variant_key,
        "version": version, "status": "draft",
        "message": "Saved as a new draft. Approve it before it can be scheduled.",
    }


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
    # Declaring an experiment result is a human judgement, not a worker task.
    actor = effective_reviewer(request, None, default="operator", require=True)
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
