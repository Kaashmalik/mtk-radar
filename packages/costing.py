"""Shared cost client for workers (enhancement plan 2026-10-24, WP-F §5.5).

Workers meter their spend through the API (the ledger lives there, next to
the budgets), and share its cache — so a re-verification or re-render done by
one process is free for every process:

  * `budget_ok(kind, units, est_cost)` — POST /costs/check BEFORE spending.
    FAIL-CLOSED: when the daily budget says no, the stage must not spend
    (extraction falls back to the deterministic rules path, narration to
    capture audio) and the block is recorded so Needs-You shows it.
  * `cache_lookup` / `cache_store` — the shared extract/tts entries.
    FAIL-OPEN: an unreachable API is a cache miss, never an error.
  * `report(...)` — POST /costs/usage; fire-and-forget.

httpx is the only dependency — every worker already ships it. Per-process
memory sits in front of the API cache so repeated calls in one sweep don't
even pay the round-trip.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Any, Optional

log = logging.getLogger("costing")

# G12 (evidence-to-video plan): match the workers' conventions. Workers speak
# MTK_API_URL + MTK_WORKER_TOKEN; the legacy API_URL/API_TOKEN names stay as
# fallbacks so nothing breaks mid-migration, but the documented names win.
DEFAULT_API_URL = (os.environ.get("MTK_API_URL")
                   or os.environ.get("API_URL")
                   or "http://localhost:8000")

#: Shared-cache TTLs per namespace (documented in the plan §5.5).
TTL_S = {
    "extract": 7 * 86400,    # re-verification of an unchanged page → free
    "tts": 7 * 86400,        # re-render of unchanged narration → free
    "trend": 6 * 3600,
    "hashtags": 6 * 3600,
}

_MEM: dict[str, tuple[float, str]] = {}
_MEM_LOCK = threading.Lock()
_MEM_MAX = 128


def sha256_of(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _mem_get(key: str) -> tuple[bool, Any]:
    import time
    with _MEM_LOCK:
        entry = _MEM.get(key)
        if not entry:
            return False, None
        expires_at, raw = entry
        if time.time() >= expires_at:
            _MEM.pop(key, None)
            return False, None
        return True, json.loads(raw)


def _mem_put(key: str, value: Any, ttl_s: int) -> None:
    import time
    with _MEM_LOCK:
        if len(_MEM) >= _MEM_MAX:
            oldest = min(_MEM.items(), key=lambda kv: kv[1][0])[0]
            _MEM.pop(oldest, None)
        _MEM[key] = (time.time() + max(1, int(ttl_s)),
                     json.dumps(value, default=str))


class CostClient:
    """Fail-open cache/report client with a fail-closed budget gate."""

    def __init__(self, api_url: str = DEFAULT_API_URL, *,
                 token: str | None = None, timeout: float = 5.0):
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self.token = (token
                      or os.environ.get("MTK_WORKER_TOKEN")
                      or os.environ.get("MTK_API_TOKEN")
                      or os.environ.get("API_TOKEN")
                      or "").strip()
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "CostClient":
        return cls(os.environ.get("MTK_API_URL")
                   or os.environ.get("API_URL")
                   or DEFAULT_API_URL)

    # ------------------------------------------------------------- transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _post(self, path: str, body: dict) -> Optional[dict]:
        import httpx
        try:
            resp = httpx.post(f"{self.api_url}{path}", json=body,
                              headers=self._headers(), timeout=self.timeout)
            if resp.status_code >= 300:
                log.debug("costs %s -> HTTP %s", path, resp.status_code)
                return None
            return resp.json()
        except Exception as exc:  # noqa: BLE001 — the ledger is never on the
            log.debug("costs %s unavailable: %s", path, exc)  # critical path
            return None

    # ------------------------------------------------------------ budget gate

    def budget_ok(self, kind: str, *, units: int = 0,
                  est_cost: float | None = None,
                  provider: str = "", model: str = "",
                  ref_type: str | None = None, ref_id: str | None = None,
                  meta: dict[str, Any] | None = None) -> bool:
        """Truly FAIL-CLOSED money check (G03).

        Only an explicit `allowed: true` from the budget service permits paid
        work. An unreachable API, a non-200 answer, or a payload without a
        boolean `allowed` all deny: unknown budget = zero paid calls. NO paid
        call may run on an unchecked budget. Callers route a False to the
        deterministic/no-cost fallback (extraction rules path, capture audio)
        and the block is recorded so Needs-You surfaces it.
        """
        body: dict[str, Any] = {"kind": kind, "units": int(units or 0),
                                "provider": provider, "model": model,
                                "meta": meta or {}}
        if est_cost is not None:
            body["est_cost"] = float(est_cost)
        if ref_type:
            body["ref_type"] = ref_type
        if ref_id:
            body["ref_id"] = ref_id
        result = self._post("/costs/check", body)
        if result is None:
            log.warning("budget check for %s unavailable — failing CLOSED", kind)
            return False
        return result.get("allowed") is True

    # ----------------------------------------------------------------- cache

    def cache_lookup(self, namespace: str, key: str) -> Optional[Any]:
        full = f"{namespace}:{key}"
        hit, value = _mem_get(full)
        if hit:
            return value
        answer = self._post("/costs/cache-lookup", {"key": full})
        if not answer or not answer.get("hit"):
            return None
        value = answer.get("value")
        _mem_put(full, value, TTL_S.get(namespace, 86400))
        return value

    def cache_store(self, namespace: str, key: str, value: Any,
                    ttl_s: int | None = None) -> None:
        full = f"{namespace}:{key}"
        ttl = int(ttl_s or TTL_S.get(namespace, 86400))
        _mem_put(full, value, ttl)
        self._post("/costs/cache-store",
                   {"key": full, "value": value, "ttl_s": ttl})

    # ---------------------------------------------------------------- report

    def report(self, kind: str, *, units: int = 0, provider: str = "",
               model: str = "", unit_type: str | None = None,
               ref_type: str | None = None, ref_id: str | None = None,
               meta: dict[str, Any] | None = None) -> None:
        """Fire-and-forget usage emission; never raises, never blocks."""
        event: dict[str, Any] = {"kind": kind, "units": int(units or 0),
                                 "provider": provider, "model": model,
                                 "meta": meta or {}}
        if unit_type:
            event["unit_type"] = unit_type
        if ref_type:
            event["ref_type"] = ref_type
        if ref_id:
            event["ref_id"] = ref_id
        self._post("/costs/usage", {"events": [event]})


def extraction_cache_key(model: str, text: str) -> str:
    """`extract:{content-hash}:{model}` — unchanged page ⇒ same key ⇒ free."""
    return f"{sha256_of(text[:8000])}:{model}"


def tts_cache_key(text: str, *, voice: str, model: str,
                  response_format: str = "mp3") -> str:
    """`tts:{sha256(text+voice+model)}` — unchanged narration ⇒ free."""
    return sha256_of(text, voice, model, response_format)
