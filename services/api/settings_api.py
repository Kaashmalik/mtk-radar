"""Operator settings (v0.18, master plan §17 "configure publish windows in
settings"; v0.26 automation policy; v0.27 language policy). A deliberately
tiny keyed JSONB store:

  GET  /settings/{key}          → {key, value} (null when unset)
  PUT  /settings/{key}          → upsert {key, value, updated_by} (audited)

Known keys (validated on write):
  publish_windows   → {"windows": ["18:00", "20:30"]}
  automation_policy → the full automation policy (services/api/automation.py)
  brand             → website CTA, hashtag sets and copy defaults
  media_backup      → media backup schedule + last run status
  language_policy   → English-first package/captions + opt-in Urdu voiceover
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import db
from api_hardening import effective_reviewer
from automation import PolicyError, normalize_policy
from schedules_state import parse_publish_windows
from settings_store import audit, get_language_policy, get_value, put_value

router = APIRouter(prefix="/settings", tags=["settings"])

KNOWN_KEYS: dict[str, str] = {
    "publish_windows": "list of local (Asia/Karachi) HH:MM times",
    "automation_policy": "human-vs-automation control for every pipeline stage",
    "brand": "website CTA, CTA copy, languages and hashtag sets used by the studio",
    "media_backup": "laptop/media backup schedule + last run status",
    "language_policy": "English-first metadata/captions + opt-in Urdu voiceover",
}

SUPPORTED_LANGUAGES = ("en", "ur")


class SettingIn(BaseModel):
    value: Any


def normalize_setting(key: str, value: Any) -> Any:
    """Validate + normalize a known settings key. Raises ValueError/PolicyError."""
    if key == "publish_windows":
        return {"windows": parse_publish_windows(value)}
    if key == "automation_policy":
        return normalize_policy(value)
    if key == "brand":
        return _normalize_brand(value)
    if key == "media_backup":
        return _normalize_media_backup(value)
    if key == "language_policy":
        return _normalize_language_policy(value)
    raise UnknownSetting(key)


def _normalize_language_policy(value: Any) -> dict:
    """English-first publishing with opt-in Urdu narration.

    `metadata_language` and `captions_language` default to English for every
    video, including Urdu-voiceover videos — this matches the common South
    Asian YouTube pattern of English titles/captions with a local voiceover.
    """
    if not isinstance(value, dict):
        raise ValueError("language_policy must be an object")

    def language(name: str, default: str) -> str:
        normalized = str(value.get(name) or default)
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"language_policy.{name} must be one of: {', '.join(SUPPORTED_LANGUAGES)}"
            )
        return normalized

    metadata_language = language("metadata_language", "en")
    captions_language = language("captions_language", "en")

    raw_narration = value.get("narration_languages") or ["en"]
    if not isinstance(raw_narration, list) or not raw_narration:
        raise ValueError("language_policy.narration_languages must be a non-empty list")
    narration_languages: list[str] = []
    for entry in raw_narration:
        normalized = str(entry)
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported narration language '{normalized}'")
        if normalized not in narration_languages:
            narration_languages.append(normalized)

    default_narration = str(value.get("default_narration_language")
                            or narration_languages[0])
    if default_narration not in narration_languages:
        raise ValueError(
            "language_policy.default_narration_language must be in narration_languages"
        )

    return {
        "metadata_language": metadata_language,
        "captions_language": captions_language,
        "narration_languages": narration_languages,
        "default_narration_language": default_narration,
        "urdu_voiceover_enabled": "ur" in narration_languages,
    }


def _normalize_brand(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("brand must be an object")
    name = str(value.get("name") or "MTK RADAR").strip()[:80]
    website = str(value.get("website_url") or "").strip()
    if website and not website.startswith(("https://", "http://")):
        raise ValueError("brand.website_url must start with http:// or https://")
    cta = str(value.get("cta") or "").strip()[:240]
    default_language = str(value.get("default_language") or "en")
    if default_language not in SUPPORTED_LANGUAGES:
        raise ValueError("brand.default_language must be one of: en, ur")
    raw_languages = value.get("languages") or list(SUPPORTED_LANGUAGES)
    if not isinstance(raw_languages, list) or not raw_languages:
        raise ValueError("brand.languages must be a non-empty list")
    languages: list[str] = []
    for language in raw_languages:
        normalized = str(language)
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported brand language '{normalized}'")
        if normalized not in languages:
            languages.append(normalized)
    if default_language not in languages:
        languages.insert(0, default_language)
    raw_sets = value.get("hashtag_sets") or {}
    if not isinstance(raw_sets, dict):
        raise ValueError("brand.hashtag_sets must be an object")
    hashtag_sets: dict[str, list[str]] = {}
    for name, tags in raw_sets.items():
        if not isinstance(tags, list):
            raise ValueError("each hashtag set must be a list")
        hashtag_sets[str(name)[:40]] = [
            str(tag).strip()[:60] for tag in tags[:30] if str(tag).strip()
        ]
    return {
        "name": name,
        "website_url": website,
        "cta": cta,
        "default_language": default_language,
        "languages": languages,
        "hashtag_sets": hashtag_sets,
    }


def _normalize_media_backup(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("media_backup must be an object")
    enabled = bool(value.get("enabled", False))
    schedule = str(value.get("schedule") or "daily")
    if schedule not in ("daily", "weekly", "manual"):
        raise ValueError("media_backup.schedule must be daily, weekly or manual")
    try:
        retention_days = int(value.get("retention_days", 14))
    except (TypeError, ValueError) as exc:
        raise ValueError("media_backup.retention_days must be an integer") from exc
    if not 1 <= retention_days <= 365:
        raise ValueError("media_backup.retention_days must be between 1 and 365")
    status = str(value.get("last_status") or "not_configured")
    if status not in ("not_configured", "running", "ok", "failed", "verified"):
        raise ValueError("media_backup.last_status is invalid")
    return {
        "enabled": enabled,
        "schedule": schedule,
        "retention_days": retention_days,
        "destination": str(value.get("destination") or "")[:500],
        "last_run_at": value.get("last_run_at"),
        "last_status": status,
        "last_manifest": str(value.get("last_manifest") or "")[:500],
    }


class UnknownSetting(KeyError):
    pass


@router.get("/{key}")
async def get_setting(key: str) -> dict:
    if key not in KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"unknown setting '{key}'")
    pool = db.get()
    stored = await get_value(pool, key)
    if not stored:
        return {"key": key, "value": None}
    if key == "language_policy":
        # Reads expose the effective policy (including the computed
        # urdu_voiceover_enabled flag), not just the raw JSONB.
        return {
            "key": key,
            "value": await get_language_policy(pool),
            "updated_at": stored["updated_at"],
            "updated_by": stored["updated_by"],
        }
    return {"key": key, **stored}


@router.put("/{key}", status_code=200)
async def put_setting(key: str, body: SettingIn, request: Request) -> dict:
    if key not in KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"unknown setting '{key}'")
    try:
        normalized = normalize_setting(key, body.value)
    except (ValueError, PolicyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pool = db.get()
    updated_by = effective_reviewer(request, None, default="operator")
    await put_value(pool, key, normalized, updated_by=updated_by)
    await audit(pool, actor=updated_by, action="settings:update", entity="settings",
                detail={"key": key, "value": normalized})
    return {"key": key, "value": normalized, "updated_by": updated_by}


@router.get("", include_in_schema=False)
async def list_settings() -> list[dict]:
    """Discovery endpoint: which keys exist and what they mean."""
    return [{"key": key, "description": description}
            for key, description in KNOWN_KEYS.items()]


__all__ = ["router", "KNOWN_KEYS", "normalize_setting"]
