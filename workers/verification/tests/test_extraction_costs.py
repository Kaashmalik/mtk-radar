"""WP-F cost engine on the extraction path: re-verification of an unchanged
page costs 0 tokens (shared cache), an exhausted budget fails closed to the
deterministic rules path, and real token usage lands in the ledger."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import extractors  # noqa: E402
from extractors import extract_fields_llm  # noqa: E402

URL = "https://example.com/terms"
EXTRACT_DATA = {"fields": {"value": {"value": "free", "evidence_url": URL,
                                     "excerpt": "free", "confidence": 0.9}},
                "conflicts": []}


class FakeCost:
    """The CostClient contract with the network stripped out."""

    def __init__(self):
        self.store: dict[str, object] = {}
        self.events: list[dict] = []
        self.budget_call_count = 0
        self.allow = True

    def cache_lookup(self, namespace, key):
        return self.store.get(f"{namespace}:{key}")

    def cache_store(self, namespace, key, value, ttl_s=None):
        self.store[f"{namespace}:{key}"] = value

    def budget_ok(self, kind, **kwargs):
        self.budget_call_count += 1
        return self.allow

    def report(self, kind, **kwargs):
        self.events.append({"kind": kind, **kwargs})


def _llm_env(monkeypatch):
    monkeypatch.setenv("VERIFY_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("VERIFY_LLM_API_KEY", "k-test")
    monkeypatch.setenv("VERIFY_LLM_MODEL", "qwen2.5:7b")


def test_reverification_of_unchanged_page_costs_zero_tokens(monkeypatch):
    _llm_env(monkeypatch)
    cost = FakeCost()
    key = "extract:" + __import__("sys").modules["extractors"] \
        .costing.extraction_cache_key("qwen2.5:7b", "same page text")

    def no_network(*a, **kw):
        raise AssertionError("a cached extraction must not call the provider")

    monkeypatch.setattr(httpx, "post", no_network)
    cached = dict(EXTRACT_DATA)
    cost.store[key] = cached

    out = extract_fields_llm("same page text", URL, cost=cost)
    assert out == cached
    (event,) = cost.events
    assert event["kind"] == "llm_extract" and event["units"] == 0
    assert event["meta"]["cache_hit"] is True
    assert cost.budget_call_count == 0, "cache hits never ask the budget"


def test_exhausted_budget_fails_closed_to_the_rules_path(monkeypatch):
    _llm_env(monkeypatch)
    cost = FakeCost()
    cost.allow = False

    def no_network(*a, **kw):
        raise AssertionError("a denied budget must not spend")

    monkeypatch.setattr(httpx, "post", no_network)
    assert extract_fields_llm("some terms", URL, cost=cost) is None
    assert cost.budget_call_count == 1


def test_first_extraction_reports_real_token_usage(monkeypatch):
    _llm_env(monkeypatch)
    cost = FakeCost()

    class Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": __import__("json").dumps(EXTRACT_DATA)}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 180},
            }

    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    out = extract_fields_llm("brand new terms text", URL, cost=cost,
                             ref_offer_id="off-1")
    assert out == EXTRACT_DATA
    (event,) = cost.events
    assert event["kind"] == "llm_extract" and event["units"] == 1380
    assert event["meta"]["tokens_in"] == 1200
    assert event["meta"]["tokens_out"] == 180
    assert event["ref_id"] == "off-1"
    # the result is cached under extract:{content-hash}:{model}
    assert any(k.startswith("extract:") for k in cost.store)


def test_extract_document_threads_the_cost_client(monkeypatch):
    _llm_env(monkeypatch)
    seen = []

    def fake_extract(text, url, *, cost=None, ref_offer_id=None, run_budget=None):
        seen.append(cost)
        return {}, [], None

    monkeypatch.setattr(extractors, "extract", fake_extract)
    cost = FakeCost()
    extractors.extract_document("a b c. " * 200, URL, cost=cost, ref_offer_id="off-2")
    assert seen and all(c is cost for c in seen)
