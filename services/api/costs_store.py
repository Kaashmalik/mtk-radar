"""Cost engine store (v0.37 — enhancement plan 2026-10-24, WP-F).

The money ledger and the shared cache backing:

  * `record_events` — append metered spend to `usage_events`. When the caller
    did not price the event, an ESTIMATE is computed from the documented env
    pricing knobs (`COST_LLM_*`, `COST_TTS_*`). Estimates are labelled as
    such everywhere they surface; they are never a bill.
  * `spend_summary` — today / 7d / 30d totals, per-kind split (the kind IS
    the pipeline stage), cache-hit rate per stage, blocked-spend counts.
  * `check_budget` — the fail-closed guardrail check workers perform BEFORE
    spending: not allowed → the stage degrades (rules-only extraction,
    capture-audio narration) and the block is recorded as a zero-unit event
    so the Costs card and Needs-You see it.

Shared cache (Redis-first, Postgres fallback, per-process memory last):
`extract:*` (re-verification of an unchanged page costs 0 tokens),
`tts:*` (re-render of unchanged narration costs 0 chars). Workers reach the
same entries over HTTP (`/costs/cache-lookup|store`), never with their own
DB credentials.

Everything here fails OPEN on infrastructure errors — a cache or ledger
hiccup must never break verification or rendering. The ONLY failure-closed
path is an exhausted explicit budget.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Optional

from automation import POLICY_KEY, default_policy, normalize_policy
from settings_store import get_value

# --------------------------------------------------------------- pricing knobs

#: USD per million tokens — conservative 2026 small-model estimates. A
#: deployment sets its real model's prices; unset → these floors.
_LLM_INPUT_PER_MTOK = float(os.environ.get("COST_LLM_INPUT_PER_MTOK", "0.15"))
_LLM_OUTPUT_PER_MTOK = float(os.environ.get("COST_LLM_OUTPUT_PER_MTOK", "0.60"))
#: USD per million characters (OpenAI tts-1 class: $15 / 1M chars).
_TTS_PER_MCHAR = float(os.environ.get("COST_TTS_PER_MCHAR", "15.0"))

#: Known usage kinds — the kind doubles as the pipeline stage label.
KINDS = ("llm_extract", "tts", "trend_fetch", "youtube_quota")
UNIT_TYPES = {"llm_extract": "tokens", "tts": "chars",
              "trend_fetch": "requests", "youtube_quota": "quota_units"}

_VALID_UNIT_TYPES = set(UNIT_TYPES.values()) | {"units"}


def estimate_cost(kind: str, units: int, meta: dict[str, Any] | None = None) -> float:
    """Documented, deterministic cost estimate for one usage event.

    Arithmetic is cite-able: the formula and the per-million rates come from
    env (`COST_LLM_INPUT_PER_MTOK` / `COST_LLM_OUTPUT_PER_MTOK` /
    `COST_TTS_PER_MCHAR`) and are surfaced on the Costs card.
    """
    meta = meta or {}
    if kind == "llm_extract":
        tokens_in = int(meta.get("tokens_in") or 0)
        tokens_out = int(meta.get("tokens_out") or 0)
        if tokens_in or tokens_out:
            return round((tokens_in * _LLM_INPUT_PER_MTOK
                          + tokens_out * _LLM_OUTPUT_PER_MTOK) / 1_000_000, 6)
        return round((units or 0) * (_LLM_INPUT_PER_MTOK + _LLM_OUTPUT_PER_MTOK)
                     / 1_000_000, 6)
    if kind == "tts":
        return round((units or 0) * _TTS_PER_MCHAR / 1_000_000, 6)
    # Trend fetches are (typically) free APIs; YouTube quota is billed monthly
    # against a free allotment — recorded for visibility, estimated at 0.
    return 0.0


def pricing_view() -> dict[str, Any]:
    return {
        "llm_input_usd_per_mtok": _LLM_INPUT_PER_MTOK,
        "llm_output_usd_per_mtok": _LLM_OUTPUT_PER_MTOK,
        "tts_usd_per_mchar": _TTS_PER_MCHAR,
        "note": "estimates only — set COST_* env to your provider's real prices",
    }


# ------------------------------------------------------------------- recording

def _coerce_event(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    kind = str(raw.get("kind") or "").strip()
    if kind not in KINDS:
        return None
    unit_type = str(raw.get("unit_type") or UNIT_TYPES.get(kind) or "units")
    if unit_type not in _VALID_UNIT_TYPES:
        unit_type = "units"
    units = int(raw.get("units") or 0)
    units = max(0, units)
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    est = raw.get("cost_usd_est")
    if est is None:
        est = estimate_cost(kind, units, meta)
    return {
        "kind": kind,
        "provider": str(raw.get("provider") or "")[:120],
        "model": str(raw.get("model") or "")[:120],
        "units": units,
        "unit_type": unit_type,
        "cost_usd_est": max(0.0, float(est or 0.0)),
        "ref_type": str(raw.get("ref_type") or "")[:60] or None,
        "ref_id": raw.get("ref_id") or None,
        "meta": meta,
    }


async def record_events(pool, events: list[dict[str, Any]]) -> dict[str, int]:
    """Append a batch of usage events; unknown/malformed rows are dropped."""
    prepared: list[dict[str, Any]] = []
    dropped = 0
    for raw in events or []:
        event = _coerce_event(raw)
        if event is None:
            dropped += 1
            continue
        prepared.append(event)
    if prepared:
        await pool.executemany(
            """
            INSERT INTO usage_events
                (kind, provider, model, units, unit_type, cost_usd_est,
                 ref_type, ref_id, meta)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            """,
            [(e["kind"], e["provider"], e["model"], e["units"], e["unit_type"],
              e["cost_usd_est"], e["ref_type"], e["ref_id"],
              __import__("json").dumps(e["meta"])) for e in prepared],
        )
    return {"recorded": len(prepared), "dropped": dropped}


# ---------------------------------------------------------------------- spend

def _num(row, key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return 0.0


async def spend_summary(pool) -> dict[str, Any]:
    """Costs-card payload: totals, per-stage split, cache-hit rates, blocks."""
    totals = await pool.fetchrow(
        """
        SELECT
          COALESCE(SUM(cost_usd_est) FILTER (
            WHERE created_at >= date_trunc('day', now())), 0)::float8 AS usd_today,
          COALESCE(SUM(cost_usd_est) FILTER (
            WHERE created_at >= now() - interval '7 days'), 0)::float8 AS usd_7d,
          COALESCE(SUM(cost_usd_est) FILTER (
            WHERE created_at >= now() - interval '30 days'), 0)::float8 AS usd_30d
        FROM usage_events
        """
    )
    by_kind = await pool.fetch(
        """
        SELECT kind, unit_type,
               SUM(units)::bigint AS units,
               COALESCE(SUM(cost_usd_est), 0)::float8 AS cost_usd_est,
               COUNT(*)::int AS events,
               COALESCE(AVG(CASE WHEN meta->>'cache_hit' = 'true'
                            THEN 1.0 ELSE 0.0 END), 0)::float8 AS cache_hit_rate,
               COUNT(*) FILTER (WHERE meta->>'blocked' = 'true')::int AS blocked
        FROM usage_events
        WHERE created_at >= now() - interval '30 days'
        GROUP BY kind, unit_type ORDER BY kind
        """
    )
    # Cost per published video (30 d) — published posts over spend.
    published_raw = await pool.fetchval(
        """
        SELECT COUNT(*) FROM schedules
        WHERE state = 'published' AND updated_at >= now() - interval '30 days'
        """
    )
    try:
        published = int(published_raw or 0)
    except (TypeError, ValueError):
        published = 0
    usd_30d = _num(totals, "usd_30d") if totals else 0.0
    return {
        "usd_today": _num(totals, "usd_today") if totals else 0.0,
        "usd_7d": _num(totals, "usd_7d") if totals else 0.0,
        "usd_30d": usd_30d,
        "by_kind": [dict(r) for r in by_kind if "kind" in r],
        "published_videos_30d": published,
        "cost_per_published_video_usd_30d":
            round(usd_30d / published, 4) if published else None,
        "pricing": pricing_view(),
    }


async def _load_guardrails(pool) -> dict[str, Any]:
    """Today's guardrails from the automation policy (fail to defaults)."""
    try:
        stored = await get_value(pool, POLICY_KEY)
        if stored and normalize_policy is not None:
            return normalize_policy(stored["value"])["guardrails"]
    except Exception:  # noqa: BLE001 — bad policy text must not block checks
        pass
    if default_policy is not None:
        return default_policy()["guardrails"]
    return {"max_llm_cost_per_day_usd": 0.5, "max_tts_chars_per_day": 50_000}


async def budget_state(pool) -> dict[str, Any]:
    """Spend-today vs the two cost guardrails (the Costs card budget rows)."""
    guardrails = await _load_guardrails(pool)
    rows = await pool.fetch(
        """
        SELECT kind,
               COALESCE(SUM(cost_usd_est) FILTER (WHERE kind = 'llm_extract'), 0)::float8 AS usd,
               COALESCE(SUM(units) FILTER (WHERE kind = 'tts'), 0)::bigint AS chars,
               COUNT(*) FILTER (WHERE meta->>'blocked' = 'true')::int AS blocked
        FROM usage_events
        WHERE created_at >= date_trunc('day', now())
        GROUP BY kind
        """
    )
    spend = {r["kind"]: dict(r) for r in rows if "kind" in r}
    llm = spend.get("llm_extract", {"usd": 0.0, "blocked": 0})
    tts = spend.get("tts", {"chars": 0, "blocked": 0})
    llm_limit = float(guardrails.get("max_llm_cost_per_day_usd") or 0)
    tts_limit = int(guardrails.get("max_tts_chars_per_day") or 0)
    return {
        "llm": {
            "used_usd_today": round(float(llm.get("usd") or 0.0), 6),
            "limit_usd_per_day": llm_limit,
            "exhausted": float(llm.get("usd") or 0.0) >= llm_limit,
            "blocked_today": int(llm.get("blocked") or 0),
        },
        "tts": {
            "chars_today": int(tts.get("chars") or 0),
            "limit_chars_per_day": tts_limit,
            "exhausted": int(tts.get("chars") or 0) >= tts_limit,
            "blocked_today": int(tts.get("blocked") or 0),
        },
    }


# ------------------------------------------------------------ the budget gate

def _budget_lock_key(kind: str) -> int:
    """Stable per-kind advisory-lock key so the read-decide-insert cycle is
    serialized per budget line (G04): concurrent workers can no longer each
    read the same spend and both exceed the cap."""
    digest = hashlib.sha256(f"mtk-budget:{kind}".encode()).digest()
    return int.from_bytes(digest[:8], "big") - (1 << 63)  # signed bigint


async def check_budget(pool, kind: str, *, units: int = 0,
                       est_cost: float | None = None,
                       provider: str = "", model: str = "",
                       ref_type: str | None = None,
                       ref_id=None, meta: dict[str, Any] | None = None,
                       ) -> dict[str, Any]:
    """FAIL-CLOSED gate: may this stage spend right now? (G04-hardened)

    Asked BEFORE the money is spent. The read-decide-insert cycle runs in ONE
    transaction under a per-kind advisory lock, so concurrent attempts cannot
    each observe the same spend and jointly oversubscribe the cap.

    On `allowed`, a conservative RESERVATION event (the projected units/cost,
    `meta.reservation = true`) is inserted and its id returned; the caller
    settles it with actual usage via `settle_reservation`. A reservation that
    is never settled stays standing — that IS the recorded liability for a
    paid call whose outcome is unknown (provider timeout, crashed worker).
    Unknown usage never counts as free.

    A denial is recorded as a zero-unit `blocked` event so the block is
    visible in Costs and Needs-You instead of silently degrading.
    """
    spend_meta = dict(meta or {})
    est = float(est_cost) if est_cost is not None else estimate_cost(kind, units, spend_meta)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)",
                               _budget_lock_key(kind))
            state = await budget_state(conn)

            ok = True
            reason: str | None = None
            if kind == "llm_extract":
                line = state["llm"]
                projected = line["used_usd_today"] + max(0.0, est)
                if line["exhausted"] or projected > line["limit_usd_per_day"]:
                    ok, reason = False, (
                        f"daily LLM budget exhausted: ${line['used_usd_today']:.2f} used of "
                        f"${line['limit_usd_per_day']:.2f} — extraction falls back to the "
                        "deterministic rules path"
                    )
            elif kind == "tts":
                line = state["tts"]
                projected = line["chars_today"] + max(0, int(units or 0))
                if line["exhausted"] or projected > line["limit_chars_per_day"]:
                    ok, reason = False, (
                        f"daily TTS budget exhausted: {line['chars_today']} chars used of "
                        f"{line['limit_chars_per_day']} — narration falls back to capture audio"
                    )
            else:
                ok = True  # trend fetches / quota units are observed, not gated

            reservation_id: str | None = None
            if not ok:
                await conn.execute(
                    """
                    INSERT INTO usage_events
                        (kind, provider, model, units, unit_type, cost_usd_est,
                         ref_type, ref_id, meta)
                    VALUES ($1, $2, $3, 0, $4, 0, $5, $6, $7::jsonb)
                    """,
                    kind, provider, model, UNIT_TYPES.get(kind, "units"),
                    ref_type, ref_id,
                    __import__("json").dumps(
                        {**spend_meta, "blocked": True, "reason": reason}),
                )
            elif kind in ("llm_extract", "tts") and (units or est):
                # G04: an allowed request reserves its projected cost
                # immediately — the eventual usage report SETTLES this row.
                row = await conn.fetchrow(
                    """
                    INSERT INTO usage_events
                        (kind, provider, model, units, unit_type, cost_usd_est,
                         ref_type, ref_id, meta)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid, $9::jsonb)
                    RETURNING id
                    """,
                    kind, provider, model, max(0, int(units or 0)),
                    UNIT_TYPES.get(kind, "units"), round(max(0.0, est), 6),
                    ref_type, ref_id,
                    __import__("json").dumps(
                        {**spend_meta, "reservation": True, "predicted": True}),
                )
                reservation_id = str(row["id"]) if row else None

    return {"allowed": ok, "reason": reason, "budget": state,
            "reservation_id": reservation_id}


async def settle_reservation(pool, reservation_id: str,
                             event: dict[str, Any]) -> dict[str, Any]:
    """Replace a reservation with the actual usage (G04).

    The settled row keeps its past (meta.settled = true) and takes the
    ACTUAL units/cost — the ledger counts the spend once. If the reservation
    row is missing or already settled, the actual event is appended raw:
    worse to double-count than to under-count paid work.
    """
    event = _coerce_event(event)
    if event is None or not reservation_id:
        return {"settled": False, "reason": "invalid reservation settlement"}
    result = await pool.execute(
        """
        UPDATE usage_events
        SET units = $2, unit_type = $3,
            cost_usd_est = $4,
            meta = meta || $5::jsonb
        WHERE id = $1::uuid
          AND meta->>'reservation' = 'true'
          AND meta->>'settled' IS NULL
        """,
        __import__("uuid").UUID(reservation_id),
        event["units"], event["unit_type"], event["cost_usd_est"],
        __import__("json").dumps({"settled": True}),
    )
    if result.endswith("UPDATE 1"):
        return {"settled": True}
    await record_events(pool, [event])
    return {"settled": False, "appended": True}


# ------------------------------------------------------------- shared cache

_MEM_CACHE: dict[str, tuple[float, str]] = {}
_MEM_MAX = 256


async def _pg_cache_get(pool, key: str) -> Optional[Any]:
    row = await pool.fetchrow(
        "SELECT value::text AS value FROM cache_entries "
        "WHERE key = $1 AND expires_at > now()",
        key,
    )
    if not row:
        return None
    import json as _json
    return _json.loads(row["value"])


async def _pg_cache_put(pool, key: str, value: Any, ttl_s: int) -> None:
    import json as _json
    await pool.execute(
        """
        INSERT INTO cache_entries (key, value, expires_at)
        VALUES ($1, $2::jsonb, now() + make_interval(secs => $3::int))
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at,
            created_at = now()
        """,
        key, _json.dumps(value, default=str), max(1, int(ttl_s)),
    )


async def cache_get(pool, key: str) -> Optional[Any]:
    """Per-process memory → Redis → Postgres. Any failure → miss (fail-open)."""
    now = time.time()
    entry = _MEM_CACHE.get(key)
    if entry and entry[0] > now:
        import json as _json
        return _json.loads(entry[1])

    from cache import cache_get_json
    try:
        value = await cache_get_json(key)
    except Exception:  # noqa: BLE001
        value = None
    if value is not None:
        _mem_put(key, value)
        return value

    try:
        if pool is not None:
            value = await _pg_cache_get(pool, key)
    except Exception:  # noqa: BLE001
        value = None
    if value is not None:
        _mem_put(key, value)
    return value


def _mem_put(key: str, value: Any, ttl_s: int) -> None:
    import json as _json
    if len(_MEM_CACHE) >= _MEM_MAX:
        oldest = min(_MEM_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _MEM_CACHE.pop(oldest, None)
    _MEM_CACHE[key] = (time.time() + max(1, int(ttl_s)),
                       _json.dumps(value, default=str))


async def cache_put(pool, key: str, value: Any, ttl_s: int) -> None:
    """Store on every layer we can reach; a partial write is still a win."""
    _mem_put(key, value, ttl_s)
    from cache import cache_set_json
    try:
        await cache_set_json(key, value, ttl_s)
    except Exception:  # noqa: BLE001
        pass
    try:
        if pool is not None:
            await _pg_cache_put(pool, key, value, ttl_s)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------- capability probing

def _probe_headers(key_env: str) -> dict[str, str]:
    import os as _os
    key = (_os.environ.get(key_env) or "").strip()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def probe_providers() -> dict[str, Any]:
    """Capability probe for the Settings → Costs card.

    Extraction: VERIFY_LLM_* — OpenAI-compatible `GET /models`, with the
    Ollama-native `GET /api/tags` fallback (model list when reachable).
    TTS: TTS_* — the same /models probe (Kokoro's OpenAI-compatible speech
    shim exposes it). Never raises: an unreachable provider is 'reachable:
    false', never an error.
    """
    import httpx

    out: dict[str, Any] = {}

    async def _probe(base: str, key_env: str) -> dict[str, Any]:
        if not base:
            return {"configured": False, "reachable": False, "models": []}
        result: dict[str, Any] = {"configured": True, "reachable": False,
                                  "models": []}
        for path, parser in (
                ("/models", lambda j: [str(m.get("id") or m.get("name") or "")
                                       for m in (j.get("data") or j.get("models")
                                                 or []) if isinstance(m, dict)]),
                ("/api/tags", lambda j: [str(m.get("name") or m.get("model") or "")
                                         for m in (j.get("models") or [])
                                         if isinstance(m, dict)])):
            if result["reachable"]:
                break
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(
                        base.rstrip("/") + path, headers=_probe_headers(key_env))
                if resp.status_code < 300:
                    models = [m for m in parser(resp.json() or {}) if m]
                    result.update(reachable=True, models=models[:20],
                                  probe=path)
            except Exception:  # noqa: BLE001 — probing never raises
                continue
        return result

    llm_base = (os.environ.get("VERIFY_LLM_BASE_URL") or "").strip().rstrip("/")
    tts_base = (os.environ.get("TTS_BASE_URL") or "").strip().rstrip("/")
    out["extraction"] = await _probe(llm_base, "VERIFY_LLM_API_KEY")
    if out["extraction"]["reachable"]:
        out["extraction"]["model"] = (os.environ.get("VERIFY_LLM_MODEL")
                                      or "gpt-4o-mini")
    out["tts"] = await _probe(tts_base, "TTS_API_KEY")
    if out["tts"]["reachable"]:
        out["tts"]["model"] = os.environ.get("TTS_MODEL", "tts-1")
        out["tts"]["voice"] = os.environ.get("TTS_VOICE", "onyx")
    return out
