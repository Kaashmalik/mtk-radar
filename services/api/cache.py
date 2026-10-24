"""Optional Redis cache layer (v0.22).

Redis was part of the stack from the start but nothing used it. It now backs
the ONE thing that benefits from a cache: the aggregate analytics endpoint,
which runs eight queries per dashboard refresh.

Design rules:
- **Optional**: no `redis` package, no REDIS_URL, or an unreachable server →
  the cache is simply disabled and every request computes fresh. Nothing in
  the system depends on it being up.
- **Fail-open everywhere**: a cache error must never turn into a 5xx.
- **Short TTL**: analytics is a dashboard read, not a system of record.
- **Async client**: a blocking Redis call inside the event loop would stall
  every request, so the asyncio client is used.
"""

import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger("cache")

_client = None
_checked = False
_disabled = False

ANALYTICS_KEY = "cache:analytics"
ANALYTICS_TTL_S = int(os.environ.get("MTK_ANALYTICS_CACHE_S", "30"))


async def _redis_client():
    """Lazily build the client once; disabled permanently if it cannot work."""
    global _client, _checked, _disabled
    if _checked:
        return _client
    _checked = True

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        _disabled = True
        return None
    try:
        from redis.asyncio import Redis  # optional dependency (redis-py, MIT)
    except ImportError:
        log.warning("REDIS_URL is set but the redis package is missing — cache disabled")
        _disabled = True
        return None
    try:
        client = Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        await client.ping()
        _client = client
        log.info("redis cache enabled")
    except Exception as exc:  # noqa: BLE001 — the cache is optional
        log.warning("redis unavailable (%s) — cache disabled", exc)
        _client = None
        _disabled = True
    return _client


async def cache_get_json(key: str) -> Optional[Any]:
    """Cached JSON value, or None on a miss / any failure."""
    value, _ = await cache_get_json_with_ttl(key)
    return value


async def cache_get_json_with_ttl(key: str) -> tuple[Optional[Any], Optional[int]]:
    """Cached JSON value plus its REMAINING TTL in seconds (G11).

    Callers that promote a Redis hit into a nearer layer (the per-process
    memory cache in costs_store) must carry the original expiry with the
    value, or a fresh Redis write would be pinned with the wrong lifetime.
    Returns ``(None, None)`` on a miss or on any failure — a cache read
    never breaks a request.
    """
    client = await _redis_client()
    if client is None:
        return None, None
    try:
        raw = await client.get(key)
        if not raw:
            return None, None
        try:
            ttl = await client.ttl(key)
            ttl_s = int(ttl) if isinstance(ttl, int) and ttl > 0 else None
        except Exception:  # noqa: BLE001 — ttl is an optimization
            ttl_s = None
        return json.loads(raw), ttl_s
    except Exception as exc:  # noqa: BLE001 — a cache read never breaks a request
        log.debug("cache read failed for %s: %s", key, exc)
        return None, None


async def cache_set_json(key: str, value: Any, ttl_s: int = ANALYTICS_TTL_S) -> bool:
    """Store JSON; returns whether it was stored (False = cache disabled)."""
    client = await _redis_client()
    if client is None:
        return False
    try:
        await client.setex(key, max(1, int(ttl_s)), json.dumps(value, default=str))
        return True
    except Exception as exc:  # noqa: BLE001 — a cache write never breaks a request
        log.debug("cache write failed for %s: %s", key, exc)
        return False


def cache_status() -> dict:
    """Operator view: is the cache actually doing anything?"""
    return {
        "url_configured": bool(os.environ.get("REDIS_URL", "").strip()),
        "disabled": _disabled,
    }
