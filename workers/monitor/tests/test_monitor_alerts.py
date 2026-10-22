"""Monitor alerts (v0.20): audience metrics that silently stop arriving must
be visible — the operator should not believe reach numbers that are days old
or missing entirely. The alert must also stay quiet when there is nothing
published yet.
"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_monitor_main", Path(__file__).resolve().parent.parent / "main.py")
monitor = importlib.util.module_from_spec(_spec)
sys.modules["mtk_monitor_main"] = monitor
_spec.loader.exec_module(monitor)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, analytics):
        self.analytics = analytics
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path == "/analytics":
            return FakeResponse(self.analytics)
        return FakeResponse([])


def _totals(measured=3, published=3, last_hours_ago=None):
    last = None
    if last_hours_ago is not None:
        last = (datetime.now(timezone.utc) - timedelta(hours=last_hours_ago)).isoformat()
    return {
        "metrics_totals": {
            "posts_measured": measured,
            "published_total": published,
            "last_captured_at": last,
        }
    }


def test_no_published_posts_is_not_an_alert(caplog):
    client = FakeClient(_totals(measured=0, published=0))
    with caplog.at_level("ERROR"):
        monitor.check_metrics_freshness(client)
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_published_posts_without_any_metrics_alerts(caplog):
    client = FakeClient(_totals(measured=0, published=4))
    with caplog.at_level("ERROR"):
        monitor.check_metrics_freshness(client)
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert errors, "published posts with zero measured posts must alert"
    assert "no audience metrics" in errors[0].getMessage()


def test_stale_metrics_alert(caplog):
    client = FakeClient(_totals(measured=2, published=3, last_hours_ago=72))
    with caplog.at_level("WARNING"):
        monitor.check_metrics_freshness(client)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "72h-old metrics must warn"
    assert "audience metrics are" in warnings[0].getMessage()


def test_fresh_metrics_stay_quiet(caplog):
    client = FakeClient(_totals(measured=3, published=3, last_hours_ago=2))
    with caplog.at_level("WARNING"):
        monitor.check_metrics_freshness(client)
    assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]


class AttentionClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, path, params=None):
        if path == "/attention":
            return FakeResponse(self.payload)
        return FakeResponse([])


def test_attention_counts_become_grouped_immediate_and_digest_alerts(caplog):
    payload = {
        "counts": {
            "redaction": 2,
            "offer_approval": 1,
            "worker": 1,
            "render_failed": 1,
            "token": 1,  # credential alerts are owned by check_platform_accounts
        },
        "by_kind": {
            "redaction": {"label": "Redaction reviews", "href": "/attention"},
            "offer_approval": {"label": "Offers ready to approve", "href": "/attention"},
            "worker": {"label": "Worker health", "href": "/settings"},
            "render_failed": {"label": "Render / QC failures", "href": "/queue"},
            "token": {"label": "Platform connections", "href": "/connections"},
        },
        "items": [
            {"kind": "redaction", "title": "Review redaction: A"},
            {"kind": "redaction", "title": "Review redaction: B"},
            {"kind": "offer_approval", "title": "Approve offer: C"},
            {"kind": "worker", "title": "Metrics worker heartbeat is stale"},
            {"kind": "render_failed", "title": "Render failed: D"},
        ],
    }
    with caplog.at_level("WARNING"):
        alerts = monitor.check_attention(AttentionClient(payload))

    by_event = {a["event"]: a for a in alerts}
    assert "attention.token" not in by_event
    assert by_event["attention.redaction"]["delivery"] == "digest"
    assert by_event["attention.offer_approval"]["delivery"] == "digest"
    assert by_event["attention.worker"]["delivery"] == "immediate"
    assert by_event["attention.worker"]["severity"] == "error"
    assert by_event["attention.render_failed"]["severity"] == "error"
    assert by_event["attention.redaction"]["details"]["count"] == 2
    assert "Review redaction: A" in by_event["attention.redaction"]["message"]


def test_legacy_api_without_attention_is_quiet():
    class Legacy:
        def get(self, path, params=None):
            return FakeResponse([])

    assert monitor.check_attention(Legacy()) == []
