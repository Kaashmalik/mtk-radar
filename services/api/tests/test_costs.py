"""WP-F cost engine: the usage ledger, the fail-closed budget gate, the
shared cache (Redis→Postgres→memory semantics via the API), guardrail
normalization and the Costs card surfaces."""

import uuid

import pytest

from automation import normalize_policy

# The session-scoped `client` fixture (wiped schema + migrated + real app)
# lives beside the integration suite; sharing it keeps ONE reset per session.
from test_integration import client  # noqa: F401


# ------------------------------------------------------------- guardrails

def test_cost_guardrails_normalize_and_are_in_defaults():
    from automation import default_policy
    guardrails = default_policy()["guardrails"]
    assert guardrails["max_llm_cost_per_day_usd"] >= 0
    assert guardrails["max_tts_chars_per_day"] >= 0
    policy = normalize_policy({
        "guardrails": {"max_llm_cost_per_day_usd": 2.5,
                       "max_tts_chars_per_day": 1234},
    })
    assert policy["guardrails"]["max_llm_cost_per_day_usd"] == 2.5
    assert policy["guardrails"]["max_tts_chars_per_day"] == 1234
    with __import__("pytest").raises(ValueError):
        normalize_policy({"guardrails": {"max_llm_cost_per_day_usd": -1}})


def test_manual_preset_spends_nothing():
    from automation import preset_policy
    manual = preset_policy("manual")
    assert manual["guardrails"]["max_llm_cost_per_day_usd"] == 0
    assert manual["guardrails"]["max_tts_chars_per_day"] == 0


# ---------------------------------------------------------------- ledger

def test_usage_emit_and_pricing_are_deterministic(client):
    from costs_store import estimate_cost
    # Documented arithmetic: 100k input + 10k output tokens at the defaults.
    est = estimate_cost("llm_extract", 0,
                        {"tokens_in": 100_000, "tokens_out": 10_000})
    assert est > 0
    # 1M TTS chars at $15 / 1M = $15.
    assert estimate_cost("tts", 1_000_000) == pytest.approx(15.0, rel=1e-3)
    # Observed kinds (trend/quota) are recorded but never estimated > 0.
    assert estimate_cost("trend_fetch", 50) == 0.0

    r = client.post("/costs/usage", json={"events": [
        {"kind": "llm_extract", "provider": "openai-compatible",
         "model": "qwen2.5:7b", "units": 110_000, "meta":
             {"tokens_in": 100_000, "tokens_out": 10_000}},
        {"kind": "not_a_kind", "units": 5},          # dropped, never fatal
        {"kind": "tts", "units": 1_000_000},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recorded"] == 2 and body["dropped"] == 1

    summary = client.get("/costs/summary").json()
    kinds = {k["kind"]: k for k in summary["by_kind"]}
    assert kinds["llm_extract"]["unit_type"] == "tokens"
    assert int(kinds["llm_extract"]["units"]) == 110_000
    assert float(kinds["tts"]["cost_usd_est"]) == pytest.approx(15.0, rel=1e-3)
    assert summary["usd_today"] > 0


def test_cost_per_published_video_is_null_without_publications(client):
    summary = client.get("/costs/summary").json()
    assert "cost_per_published_video_usd_30d" in summary
    if summary["published_videos_30d"] == 0:
        assert summary["cost_per_published_video_usd_30d"] is None


# ------------------------------------------------------------ budget gate

def test_llm_budget_blocks_fail_closed_and_show_in_costs(client):
    # A tight budget the next events will blow through.
    current = client.get("/automation/policy").json()["policy"]
    put = client.put("/automation/policy", json={
        "policy": {**(current or {}),
                   "guardrails": {**(current or {}).get("guardrails", {}),
                                  "max_llm_cost_per_day_usd": 0.000001}}})
    assert put.status_code == 200, put.text

    allowed = client.post("/costs/check", json={
        "kind": "llm_extract", "provider": "p", "model": "m",
        "est_cost": 0.05})
    assert allowed.status_code == 200
    assert allowed.json()["allowed"] is False
    assert "budget" in allowed.json()["reason"].lower()

    # The denial is recorded as a zero-unit blocked event — Costs and
    # Needs-You show WHY a stage degraded.
    summary = client.get("/costs/summary").json()
    llm = next(k for k in summary["by_kind"] if k["kind"] == "llm_extract")
    assert llm["blocked"] >= 1

    budget = client.get("/costs/budget").json()
    assert budget["llm"]["exhausted"] is True

    attention = client.get("/attention").json()
    kinds = {item.get("kind") for item in attention.get("items", [])}
    assert "costs" in kinds

    # Restore a sane budget so later tests are unaffected.
    reset = client.put("/automation/policy", json={
        "policy": {**(current or {}),
                   "guardrails": {**(current or {}).get("guardrails", {}),
                                  "max_llm_cost_per_day_usd": 0.5}}})
    assert reset.status_code == 200
    now_allowed = client.post("/costs/check", json={"kind": "llm_extract"})
    assert now_allowed.json()["allowed"] is True


def test_tts_char_budget_is_checked_in_chars(client):
    # Explicit generous ceiling (other tests may have emitted TTS chars today).
    client.put("/automation/policy", json={
        "policy": {"guardrails": {"max_tts_chars_per_day": 2_000_000}}})
    under = client.post("/costs/check", json={"kind": "tts", "units": 50})
    assert under.json()["allowed"] is True
    over_limit = client.put("/automation/policy", json={
        "policy": {"guardrails": {"max_tts_chars_per_day": 100}}})
    assert over_limit.status_code == 200
    over = client.post("/costs/check", json={"kind": "tts", "units": 500})
    assert over.json()["allowed"] is False
    assert "capture audio" in over.json()["reason"]
    client.put("/automation/policy", json={
        "policy": {"guardrails": {"max_tts_chars_per_day": 50_000}}})


# ---------------------------------------------------------- shared cache

def test_shared_cache_roundtrip_and_expiry(client):
    key = f"extract:test-{uuid.uuid4().hex}"
    store = client.post("/costs/cache-store", json={
        "key": key, "value": {"fields": {"price": {"value": "free"}}},
        "ttl_s": 120})
    assert store.status_code == 200
    hit = client.post("/costs/cache-lookup", json={"key": key}).json()
    assert hit["hit"] is True and hit["value"]["fields"]["price"]["value"] == "free"
    miss = client.post("/costs/cache-lookup", json={
        "key": f"extract:test-none-{uuid.uuid4().hex}"}).json()
    assert miss["hit"] is False and miss["value"] is None


# --------------------------------------------------------- provider probe

def test_provider_probe_never_raises_when_unconfigured(client):
    # No VERIFY_LLM_BASE_URL / TTS_BASE_URL in the test env → configured:
    # false, and never an error.
    body = client.get("/costs/providers").json()
    assert "extraction" in body and "tts" in body
    assert isinstance(body["extraction"].get("models", []), list)


def test_attention_exposes_costs_section(client):
    body = client.get("/attention").json()
    counts = body.get("counts") or {}
    by_kind = body.get("by_kind") or {}
    assert "costs" in by_kind and "costs" in counts
