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
from scriptgen import SUPPORTED_LANGUAGES, generate_multilingual
from state import can_generate_video

router = APIRouter(prefix="/studio", tags=["studio"])


class StudioGenerateIn(BaseModel):
    # Empty = every voiceover language enabled in Settings → Language policy.
    languages: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=lambda: ["youtube", "instagram", "tiktok"])
    website_url: Optional[str] = None
    create_variants: bool = True


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

    actor = effective_reviewer(request, None, default="operator")
    generated = generate_multilingual(offer, evidence_rows, tuple(languages))

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
            "voiceover_language": language,
            "copy_language": language_policy["metadata_language"],
            "captions_language": language_policy["captions_language"],
        }
        row = await pool.fetchrow(
            """
            INSERT INTO offer_scripts
                (offer_id, version, language, markdown, checklist, command_cards,
                 created_by, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8::jsonb)
            RETURNING id
            """,
            offer_id, version, language, payload["markdown"],
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
