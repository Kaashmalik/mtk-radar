"""WP-G LLM client hardening (§5.6.3): bounded retries with backoff + jitter,
a per-run request budget, and honest `rules_fallback` attribution when the
LLM was attempted but the deterministic rules path produced the fields.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import extractors  # noqa: E402
from extractors import RunBudget, extract_fields_llm  # noqa: E402

URL = "https://example.com/terms"
DATA = {"fields": {"value": {"value": "free", "evidence_url": URL,
                             "excerpt": "free", "confidence": 0.9}},
        "conflicts": []}


def _env(monkeypatch):
    monkeypatch.setenv("VERIFY_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("VERIFY_LLM_API_KEY", "k-test")
    monkeypatch.setenv("VERIFY_LLM_MODEL", "qwen2.5:7b")


def _resp(status_code, body):
    return httpx.Response(status_code, json=body,
                          request=httpx.Request("POST", "https://llm.invalid/v1/chat/completions"))


def _ok_payload():
    return {"choices": [{"message": {"content": json.dumps(DATA)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def test_transient_5xx_is_retried_with_backoff(monkeypatch):
    _env(monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def flaky(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return _resp(503, {"error": "overloaded"})
        return _resp(200, _ok_payload())

    monkeypatch.setattr(httpx, "post", flaky)
    out = extract_fields_llm("terms text", URL)
    assert out == DATA
    assert attempts["n"] == 3
    assert len(sleeps) == 2, "two retries → two backoff sleeps (with jitter)"


def test_malformed_payload_is_not_retried(monkeypatch):
    _env(monkeypatch)
    attempts = {"n": 0}

    def bad_json(url, **kwargs):
        attempts["n"] += 1
        # valid HTTP, valid JSON envelope, but fields is not a dict
        return _resp(200, {"choices": [{"message": {"content": json.dumps({"fields": 7})}}]})

    monkeypatch.setattr(httpx, "post", bad_json)
    assert extract_fields_llm("text", URL) is None
    assert attempts["n"] == 1, "re-asking returns the same garbage — the rules path continues"


def test_per_run_request_budget_bounds_a_document(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _resp(200, _ok_payload()))
    stats: dict = {}
    budget = RunBudget(max_calls=1, stats=stats)

    first = extract_fields_llm("section one", URL, run_budget=budget)
    second = extract_fields_llm("section two", URL, run_budget=budget)
    assert first is not None
    assert second is None, "the budget bounds the WHOLE run, per section"
    assert stats["llm_budget_exhausted"] is True


def test_attempts_without_success_mean_rules_fallback(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _resp(503, {"error": "down"}))
    monkeypatch.setattr("time.sleep", lambda s: None)
    stats: dict = {}
    out = extract_fields_llm("text", URL, run_budget=RunBudget(stats=stats))
    assert out is None
    assert stats["llm_attempted"] >= 1
    assert stats.get("llm_failures", 0) >= 1
    # The worker maps exactly this shape to method="rules_fallback":
    assert not stats.get("llm_succeeded")
    assert stats.get("llm_attempted") or stats.get("llm_budget_exhausted")


def test_cache_hit_counts_as_llm_success(monkeypatch):
    _env(monkeypatch)

    class FakeCost:
        def cache_lookup(self, ns, key):
            return DATA

        def report(self, *a, **kw):
            pass

    stats: dict = {}
    out = extract_fields_llm("text", URL, cost=FakeCost(), run_budget=RunBudget(stats=stats))
    assert out == DATA
    assert stats["llm_succeeded"] == 1
