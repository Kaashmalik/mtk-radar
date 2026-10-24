"""Trend-fetch cache shared by signal collectors (enhancement plan 2026-10-24, WP-A).

Trend APIs (Hugging Face papers, Hacker News, Reddit, Google Trends) are free
but rate-shaped, and every collector sweep re-requesting the same payloads is
wasted politeness — and wasted quota. This module gives adapters a tiny JSON
cache with per-source TTLs.

Design rules (mirrors services/api/cache.py):
- **Optional**: no REDIS_URL or an unreachable server → the process-memory
  layer alone keeps working. Nothing depends on Redis being up.
- **Fail-open everywhere**: a cache error must never break a collection run.
- **Bounded memory**: the in-process layer evicts the oldest entries at a cap,
  so a long-lived worker cannot leak.
- The cache stores raw decoded payloads (lists/dicts), never credentials.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Optional

log = logging.getLogger("trendcache")

DEFAULT_TTL_S = 30 * 60
_MAX_MEMORY_ENTRIES = 512


class JsonCache:
    """Two-layer optional JSON cache: process memory + optional Redis."""

    def __init__(
        self,
        namespace: str = "trend",
        default_ttl_s: int = DEFAULT_TTL_S,
        clock: Optional[Callable[[], float]] = None,
        max_entries: int = _MAX_MEMORY_ENTRIES,
    ):
        self._namespace = namespace
        self._default_ttl_s = max(1, int(default_ttl_s))
        self._clock = clock or time.time
        self._max_entries = max(1, int(max_entries))
        # key -> (expires_at_monotonic, raw_json)
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis: Any = None
        self._redis_checked = False
        # Cost-engine counters (WP-F): the collectors report how many network
        # fetches a sweep actually made vs served from cache (usage_events
        # kind='trend_fetch'), so politeness-shaped rate limits are visible.
        self.hits = 0
        self.misses = 0

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    def _redis_client(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            return None
        try:
            import redis  # optional dependency (redis-py, MIT)

            client = redis.Redis.from_url(
                url, socket_timeout=2, socket_connect_timeout=2
            )
            client.ping()
            self._redis = client
            log.info("trend cache: redis enabled")
        except Exception as exc:  # noqa: BLE001 — the cache is optional
            log.info("trend cache: redis unavailable (%s) — process memory only", exc)
            self._redis = None
        return self._redis

    def get_json(self, key: str):
        now = self._clock()
        full_key = self._key(key)
        entry = self._memory.get(full_key)
        if entry is not None:
            expires_at, raw = entry
            if now < expires_at:
                try:
                    self.hits += 1
                    return json.loads(raw)
                except ValueError:
                    self._memory.pop(full_key, None)
            else:
                self._memory.pop(full_key, None)

        client = self._redis_client()
        if client is not None:
            try:
                raw = client.get(full_key)
                if raw:
                    self.hits += 1
                    return json.loads(raw)
            except Exception as exc:  # noqa: BLE001 — cache misses fall through
                log.debug("trend cache get failed (%s)", exc)
        self.misses += 1
        return None

    def set_json(self, key: str, value: Any, ttl_s: Optional[int] = None) -> None:
        ttl = max(1, int(ttl_s or self._default_ttl_s))
        raw = json.dumps(value)
        full_key = self._key(key)
        self._memory[full_key] = (self._clock() + ttl, raw)
        while len(self._memory) > self._max_entries:
            # FIFO eviction: drop the first-inserted entry (dicts are ordered).
            oldest = next(iter(self._memory))
            self._memory.pop(oldest, None)

        client = self._redis_client()
        if client is not None:
            try:
                client.setex(full_key, ttl, raw)
            except Exception as exc:  # noqa: BLE001 — memory layer already holds it
                log.debug("trend cache set failed (%s)", exc)

    # ---------------------------------------------------------- text (G10)
    # Adapter payloads are not always JSON: Google Trends serves RSS/XML.
    # `set_json`/`get_json` json-encode whatever they receive, which 500s on
    # bytes — so text sources get a symmetric raw-string path. Memory and
    # Redis hold the SAME string, and `cached_text` hands the loader's exact
    # text back on a hit, guaranteeing live and cached parses are identical.

    def get_text(self, key: str) -> Optional[str]:
        now = self._clock()
        full_key = self._key(key)
        entry = self._memory.get(full_key)
        if entry is not None:
            expires_at, raw = entry
            if now < expires_at:
                self.hits += 1
                return raw
            self._memory.pop(full_key, None)

        client = self._redis_client()
        if client is not None:
            try:
                raw = client.get(full_key)
                if raw:
                    self.hits += 1
                    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    # Repopulate the memory layer like a Redis get_json hit.
                    self._memory[full_key] = (
                        now + self._default_ttl_s, text)
                    return text
            except Exception as exc:  # noqa: BLE001 — cache misses fall through
                log.debug("trend cache get failed (%s)", exc)
        self.misses += 1
        return None

    def set_text(self, key: str, value: str, ttl_s: Optional[int] = None) -> None:
        if not isinstance(value, str):
            raise TypeError("set_text stores str payloads only "
                            "(use set_json for structured data)")
        ttl = max(1, int(ttl_s or self._default_ttl_s))
        full_key = self._key(key)
        self._memory[full_key] = (self._clock() + ttl, value)
        while len(self._memory) > self._max_entries:
            oldest = next(iter(self._memory))
            self._memory.pop(oldest, None)

        client = self._redis_client()
        if client is not None:
            try:
                client.setex(full_key, ttl, value)
            except Exception as exc:  # noqa: BLE001 — memory layer already holds it
                log.debug("trend cache set failed (%s)", exc)

    def clear(self) -> None:
        self._memory.clear()

    def take_stats(self) -> dict[str, int]:
        """Hit/miss counters since the last call (delta semantics so a sweep
        can report exactly what IT fetched)."""
        stats = {"hits": self.hits, "misses": self.misses}
        self.hits = self.misses = 0
        return stats


def cached_json(
    cache: Optional[JsonCache],
    key: str,
    ttl_s: Optional[int],
    loader: Callable[[], Any],
) -> Any:
    """Return the cached payload or run ``loader`` and cache the result.

    A JSON value of ``None`` is never cached (it means "loader failed or the
    source answered empty"), so the next sweep retries the fetch.
    """
    if cache is not None:
        hit = cache.get_json(key)
        if hit is not None:
            return hit
    payload = loader()
    if cache is not None and payload is not None:
        cache.set_json(key, payload, ttl_s)
    return payload


def cached_text(
    cache: Optional["JsonCache"],
    key: str,
    ttl_s: Optional[int],
    loader: Callable[[], str],
) -> str:
    """Text twin of :func:`cached_json` (G10): for sources whose payloads are
    XML/RSS/HTML. The loader's exact text is stored, so a cache hit parses
    byte-for-byte identically to the live response."""
    if cache is not None:
        hit = cache.get_text(key)
        if hit is not None:
            return hit
    payload = loader()
    if cache is not None and payload is not None:
        cache.set_text(key, payload, ttl_s)
    return payload
