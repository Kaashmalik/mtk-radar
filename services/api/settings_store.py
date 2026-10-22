"""Small shared helpers for the keyed JSONB settings store.

Both the generic ``/settings`` router and the automation policy router write
here, so validation/audit/upsert behaviour cannot drift between them.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg


class UnknownSetting(KeyError):
    pass


# English-first packaging: titles/details/captions stay English for every video.
# Urdu (or another language) is only spoken when explicitly added to
# narration_languages in Settings → Language policy.
DEFAULT_LANGUAGE_POLICY: dict[str, Any] = {
    "metadata_language": "en",
    "captions_language": "en",
    "narration_languages": ["en"],
    "default_narration_language": "en",
    "urdu_voiceover_enabled": False,
}


async def get_language_policy(pool: asyncpg.Pool) -> dict[str, Any]:
    stored = await get_value(pool, "language_policy")
    value = (stored or {}).get("value") or {}
    policy = {**DEFAULT_LANGUAGE_POLICY, **value}
    allowed = [str(lang) for lang in (policy.get("narration_languages") or ["en"])]
    policy["narration_languages"] = allowed or ["en"]
    policy["metadata_language"] = policy.get("metadata_language") or "en"
    policy["captions_language"] = policy.get("captions_language") or "en"
    policy["default_narration_language"] = (
        policy.get("default_narration_language") or policy["narration_languages"][0]
    )
    policy["urdu_voiceover_enabled"] = "ur" in policy["narration_languages"]
    return policy


async def get_value(pool: asyncpg.Pool, key: str) -> Optional[dict[str, Any]]:
    row = await pool.fetchrow(
        "SELECT value::text AS value, updated_at, updated_by FROM settings WHERE key = $1",
        key,
    )
    if not row:
        return None
    try:
        value = json.loads(row["value"])
    except (TypeError, ValueError):
        return None
    return {
        "value": value,
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
    }


async def put_value(pool: asyncpg.Pool, key: str, value: Any, *, updated_by: str) -> None:
    await pool.execute(
        """
        INSERT INTO settings (key, value, updated_by) VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
            updated_by = EXCLUDED.updated_by, updated_at = now()
        """,
        key, json.dumps(value, default=str), updated_by,
    )


async def audit(pool: asyncpg.Pool, *, actor: str, action: str, entity: str,
                entity_id=None, detail: Optional[dict[str, Any]] = None) -> None:
    await pool.execute(
        "INSERT INTO audit_log (actor, action, entity, entity_id, detail) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        actor, action, entity, entity_id, json.dumps(detail or {}, default=str),
    )
