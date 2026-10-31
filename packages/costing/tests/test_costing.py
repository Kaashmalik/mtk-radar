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


# ------------------------------------------------ durable usage outbox (EP-07)

def _client_with_box(tmp_path, monkeypatch, statuses):
    """CostClient whose /costs/usage answers come from `statuses` in order."""
    from outbox import FileOutbox

    sent = []

    def fake_status(self, path, body):
        sent.append(body)
        status = statuses.pop(0) if statuses else 200
        return status, ({} if status and status < 300 else None)

    monkeypatch.setattr(CostClient, "_post_status", fake_status)
    client = CostClient("http://api")
    client._box = FileOutbox("costs-usage", tmp_path, base_backoff_s=0)
    return client, sent


def test_usage_during_api_outage_is_spooled_then_replayed_once(tmp_path, monkeypatch):
    client, sent = _client_with_box(tmp_path, monkeypatch, [None, 503])
    client.report("tts", units=100)          # transport failure → spooled
    client.report("tts", units=200)          # 503 → spooled
    assert client._box.pending_count() == 2
    event_ids = {b["events"][0]["event_id"] for b in sent}
    assert len(event_ids) == 2

    client.report("tts", units=300)          # API back → delivered + drains spool
    assert client._box.pending_count() == 0
    replayed = [b["events"][0]["event_id"] for b in sent[3:]]
    assert set(replayed) == event_ids, "replays carry the ORIGINAL event ids"


def test_usage_refused_with_4xx_is_not_retried_forever(tmp_path, monkeypatch):
    client, sent = _client_with_box(tmp_path, monkeypatch, [422])
    client.report("tts", units=1)
    assert client._box.pending_count() == 0, "a refusal is not an outage"


def test_settlement_rides_in_the_spooled_body(tmp_path, monkeypatch):
    client, sent = _client_with_box(tmp_path, monkeypatch, [None])
    client.report("llm_extract", units=10, settle_reservation="res-1")
    spooled = client._box.due()[0].payload
    assert spooled["settle_reservation"] == "res-1"
