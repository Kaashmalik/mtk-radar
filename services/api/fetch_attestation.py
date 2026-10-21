"""Signed fetch provenance (WP01 slice 7): canonical form + HMAC-SHA256.

`fetch_identity` is a string the caller chooses, so on its own it proves nothing.
Signing the provenance with a deployment-held key makes the record attributable
to a holder of that key — the acquisition component — so an arbitrary API client
cannot fabricate machine evidence.

What this proves: "a process holding the deployment's signing key produced this
exact record". What it does **not** prove: that the bytes were actually fetched.
A compromised key holder can still sign a lie. Asymmetric signing (API holds only
a public key) or server-side fetching is the follow-up that closes that gap.

The module is pure stdlib and is shared by both sides: the API imports it
directly, and the verification worker adds ``services/api`` to ``sys.path``. The
canonical form therefore has exactly one implementation.

Canonicalisation rules (must stay stable; existing signatures depend on them):

- only :data:`SIGNED_FIELDS` are covered — unknown keys are ignored;
- URLs are lower-cased, default ports dropped, an empty path becomes ``/`` and
  fragments are dropped;
- timestamps are converted to UTC and written in ISO-8601;
- JSON is written with sorted keys, no whitespace and ASCII escapes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

#: Shorter keys are refused rather than silently used.
MIN_KEY_CHARS = 32

#: Fields covered by the signature. Adding a field changes every future
#: signature, so only extend this together with a version bump if needed.
SIGNED_FIELDS = (
    "requested_url",
    "final_url",
    "http_status",
    "content_type",
    "fetched_at",
    "redirects",
    "raw_sha256",
    "parser_version",
    "fetch_identity",
    "encoding",
    "robots",
)

_ROBOTS_FIELDS = ("robots_url", "checked_at", "allowed", "status")


def _get(payload: Any, name: str) -> Any:
    """Read a field from either a mapping or a pydantic model."""
    if isinstance(payload, Mapping):
        return payload.get(name)
    return getattr(payload, name, None)


def _url(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return text
    default = 443 if scheme == "https" else 80
    netloc = host if port in (None, default) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def _timestamp(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        if not text:
            return ""
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if moment.tzinfo is None:
        return ""
    return moment.astimezone(timezone.utc).isoformat()


def _robots(value: Any) -> Optional[dict]:
    if value is None:
        return None
    return {
        "robots_url": _url(_get(value, "robots_url")),
        "checked_at": _timestamp(_get(value, "checked_at")),
        "allowed": bool(_get(value, "allowed")),
        "status": (
            int(_get(value, "status"))
            if _get(value, "status") is not None else None
        ),
    }


def _canonical_field(name: str, value: Any) -> Any:
    if name in ("requested_url", "final_url"):
        return _url(value)
    if name == "fetched_at":
        return _timestamp(value)
    if name == "redirects":
        return [_url(item) for item in (value or [])]
    if name == "robots":
        return _robots(value)
    if name == "http_status":
        return int(value) if value is not None else None
    if value is None:
        return ""
    return str(value)


def canonical_provenance(payload: Any) -> bytes:
    """The exact bytes both sides hash. Stable across dict/model inputs."""
    material = {
        name: _canonical_field(name, _get(payload, name))
        for name in SIGNED_FIELDS
    }
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _key_bytes(key: "str | bytes") -> bytes:
    raw = key.encode("utf-8") if isinstance(key, str) else bytes(key)
    if len(raw) < MIN_KEY_CHARS:
        raise ValueError(f"signing key must be at least {MIN_KEY_CHARS} bytes")
    return raw


def sign_provenance(payload: Any, key: "str | bytes") -> str:
    """HMAC-SHA256 over the canonical provenance (lower-case hex)."""
    digest = hmac.new(_key_bytes(key), canonical_provenance(payload), hashlib.sha256)
    return digest.hexdigest()


def verify_provenance(payload: Any, signature: Optional[str],
                      key: "str | bytes") -> bool:
    """Constant-time check; a missing signature or short key is never valid."""
    if not signature:
        return False
    try:
        expected = sign_provenance(payload, key)
    except ValueError:
        return False
    return hmac.compare_digest(expected, str(signature).strip().lower())
