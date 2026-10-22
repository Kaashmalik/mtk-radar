"""Opaque keyset cursors for list endpoints (v0.31).

Fixed `LIMIT` values used to starve a backlog: the API applied the limit before
callers could see what was left. Every growing collection now accepts an
opaque `cursor` and returns the next one in the `X-Next-Cursor` response
header, so a worker can walk the whole set instead of re-reading the same
first page forever.

Cursors are signed-free base64url JSON: they contain no secrets, but callers
must treat them as opaque. Decoding is strict (type and arity) so a malformed
or hand-edited cursor is a client error, not a silently wrong page.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

MAX_CURSOR_CHARS = 1024


def _encode_part(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def encode_cursor(*parts: Any) -> str:
    """Encode an ordered tuple of sort-key values into an opaque cursor."""
    payload = json.dumps([_encode_part(part) for part in parts],
                         separators=(",", ":"), ensure_ascii=True)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _bad_cursor(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"invalid cursor: {detail}")


def decode_cursor(value: str | None, arity: int) -> list[str] | None:
    """Decode and validate a cursor. Returns None when no cursor was given."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > MAX_CURSOR_CHARS:
        raise _bad_cursor("too long")
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        parts = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        raise _bad_cursor("not a valid opaque value") from None
    if not isinstance(parts, list) or len(parts) != arity:
        raise _bad_cursor(f"expected {arity} sort keys")
    if not all(isinstance(part, str) and part for part in parts):
        raise _bad_cursor("empty sort key")
    return parts


def decode_datetime(value: str, label: str = "timestamp") -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise _bad_cursor(f"{label} is not ISO-8601") from None


def decode_uuid(value: str, label: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        raise _bad_cursor(f"{label} is not a UUID") from None


def next_header(cursor: str | None) -> dict[str, str]:
    """Response headers for a page. An empty page has no next cursor."""
    return {"X-Next-Cursor": cursor} if cursor else {}


def set_next_cursor(response, rows: list[Any], limit: int,
                    cursor_for) -> None:
    """Attach X-Next-Cursor when a full page suggests more rows exist.

    `cursor_for(row)` returns the cursor string for the last returned row.
    """
    headers = next_header(cursor_for(rows[-1]) if len(rows) >= limit and rows else None)
    for key, value in headers.items():
        response.headers[key] = value
