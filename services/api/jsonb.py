"""jsonb decoding helpers for the API service.

Postgres `jsonb` columns reach Python in one of two shapes:

- as TEXT — the convention used throughout `services/api`, where queries select
  `eligibility::text AS eligibility` so the REST responses carry raw JSON;
- as a plain `str` — asyncpg's default codec for `json`/`jsonb` also returns
  the serialized JSON, not a parsed object.

Business logic (script generation, platform metadata) needs real mappings and
lists, so it decodes through these helpers instead of assuming a shape.
"""

import json
from typing import Any


def decode(value: Any, default: Any = None) -> Any:
    """Decode a jsonb value that may be text, bytes, or already parsed."""
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        if not value.strip():
            return default
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def decode_mapping(value: Any) -> dict:
    """Decode a jsonb object column; anything else becomes an empty dict."""
    decoded = decode(value)
    return decoded if isinstance(decoded, dict) else {}


def decode_list(value: Any) -> list:
    """Decode a jsonb array column; anything else becomes an empty list."""
    decoded = decode(value)
    return decoded if isinstance(decoded, list) else []
