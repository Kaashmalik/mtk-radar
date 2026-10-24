"""CostClient money gate (G03) and config conventions (G12).

The gate must be TRULY fail-closed: only an explicit `allowed: true` permits
paid work. Unreachable API / non-2xx / missing or non-boolean `allowed` all
deny — unknown budget = zero paid calls, with the caller degrading to the
deterministic no-cost path. A cache/report outage still stays fail-open
(cache miss is free).
"""

import httpx
import pytest

import costing
from costing import CostClient


def _patch_transport(monkeypatch, handler):
    def fake_post(self, path, body):
        request = httpx.Request("POST", f"{self.api_url}{path}")
        resp = handler(request)
        if resp.status_code >= 300:
            return None
        return resp.json()

    monkeypatch.setattr(CostClient, "_post", fake_post)


def test_budget_denied_when_api_unreachable(monkeypatch):
    monkeypatch.setattr(CostClient, "_post", lambda self, path, body: None)
    assert CostClient("http://costs.test").budget_ok("llm_extract") is False, \
        "unknown budget = zero paid calls (G03)"


@pytest.mark.parametrize("payload", [
    {},                              # missing allowed
    {"allowed": None},
    {"allowed": "yes"},              # truthy non-boolean is NOT consent
    {"allowed": 1},
    {"error": "boom"},               # invalid/error payload
])
def test_budget_denied_without_explicit_boolean_allow(monkeypatch, payload):
    monkeypatch.setattr(CostClient, "_post", lambda self, path, body: payload)
    assert CostClient("http://costs.test").budget_ok("llm_extract") is False


def test_budget_allows_only_explicit_true(monkeypatch):
    monkeypatch.setattr(CostClient, "_post",
                        lambda self, path, body: {"allowed": True})
    assert CostClient("http://costs.test").budget_ok("llm_extract") is True


def test_budget_denial_passes_through(monkeypatch):
    monkeypatch.setattr(CostClient, "_post",
                        lambda self, path, body: {"allowed": False})
    assert CostClient("http://costs.test").budget_ok("tts") is False


# ------------------------------------------------- G12 config conventions

def test_worker_token_wins_and_mtk_api_url_is_the_documented_name(monkeypatch):
    monkeypatch.setenv("MTK_API_URL", "http://worker-route.test")
    monkeypatch.setenv("API_URL", "http://legacy.test")
    monkeypatch.setenv("MTK_WORKER_TOKEN", "worker-tok")
    monkeypatch.setenv("MTK_API_TOKEN", "service-tok")

    client = CostClient.from_env()
    assert client.api_url == "http://worker-route.test"
    assert client.token == "worker-tok"


def test_fallbacks_still_work_when_documented_names_absent(monkeypatch):
    monkeypatch.delenv("MTK_API_URL", raising=False)
    monkeypatch.setenv("API_URL", "http://legacy.test")
    monkeypatch.delenv("MTK_WORKER_TOKEN", raising=False)
    monkeypatch.delenv("MTK_API_TOKEN", raising=False)
    monkeypatch.setenv("API_TOKEN", "legacy-tok")

    client = CostClient.from_env()
    assert client.api_url == "http://legacy.test"
    assert client.token == "legacy-tok"


def test_explicit_arguments_beat_environment(monkeypatch):
    monkeypatch.setenv("MTK_WORKER_TOKEN", "worker-tok")
    client = CostClient("http://explicit.test", token="explicit-tok")
    assert client.token == "explicit-tok"
    assert client.api_url == "http://explicit.test"
