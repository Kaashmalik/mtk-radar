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
