"""Monitor webhook/email notifications.

The monitor must keep working when notification delivery is not configured or
the remote endpoint is down. These tests cover payload shape, webhook auth,
SMTP digest rendering, and the no-alert/no-config paths.
"""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notifications

_spec = importlib.util.spec_from_file_location(
    "mtk_monitor_main_notifications", Path(__file__).resolve().parent.parent / "main.py")
monitor = importlib.util.module_from_spec(_spec)
sys.modules["mtk_monitor_main_notifications"] = monitor
_spec.loader.exec_module(monitor)


ALERTS = [
    {
        "severity": "warning",
        "event": "platform_account.expiring",
        "message": "Token for @demo (youtube) expires in 1.0 day(s).",
        "details": {"platform": "youtube", "account_handle": "@demo"},
    },
    {
        "severity": "error",
        "event": "metrics.missing",
        "message": "Published posts have no audience metrics.",
        "details": {"published_total": 4, "posts_measured": 0},
    },
]


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://hooks.example.test/mtk")
            raise httpx.HTTPStatusError(
                "boom", request=request, response=httpx.Response(self.status_code)
            )


class FakeHttpClient:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.status_code)


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.message = None
        self.quit_called = False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.message = message

    def quit(self):
        self.quit_called = True


def _config(**overrides):
    values = {
        "webhook_url": "https://hooks.example.test/mtk",
        "webhook_token": "secret-token",
        "email_to": ("ops@example.com",),
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_user": "bot@example.test",
        "smtp_password": "smtp-secret",
        "smtp_from": "bot@example.test",
        "cooldown_s": 0,
    }
    values.update(overrides)
    return notifications.NotificationConfig(**values)


@pytest.fixture(autouse=True)
def _clear_cooldown():
    notifications.reset_cooldown_state()
    yield
    notifications.reset_cooldown_state()


def test_config_reads_env_and_never_exposes_secrets():
    cfg = notifications.NotificationConfig.from_env({
        "MTK_NOTIFY_WEBHOOK_URL": "https://hooks.example.test/mtk",
        "MTK_NOTIFY_WEBHOOK_TOKEN": "webhook-secret",
        "MTK_NOTIFY_EMAIL_TO": "one@example.com, two@example.com",
        "MTK_SMTP_HOST": "smtp.example.test",
        "MTK_SMTP_PORT": "465",
        "MTK_SMTP_USER": "bot@example.test",
        "MTK_SMTP_PASSWORD": "smtp-secret",
    })

    assert cfg.webhook_enabled
    assert cfg.email_enabled
    assert cfg.email_to == ("one@example.com", "two@example.com")
    assert cfg.smtp_from == "bot@example.test"
    assert cfg.smtp_ssl is True
    assert cfg.smtp_starttls is False
    summary = json.dumps(cfg.public_summary())
    assert "webhook-secret" not in summary
    assert "smtp-secret" not in summary


def test_config_is_disabled_by_default():
    cfg = notifications.NotificationConfig.from_env({})
    assert not cfg.webhook_enabled
    assert not cfg.email_enabled


def test_build_payload_is_a_versioned_digest():
    payload = notifications.build_payload(
        ALERTS,
        generated_at=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        host="monitor-1",
        dashboard_url="https://mtk.example.test",
    )

    assert payload["schema"] == "mtk-radar.notification.v1"
    assert payload["source"] == "mtk-radar.monitor"
    assert payload["severity"] == "error"
    assert payload["alert_count"] == 2
    assert payload["generated_at"] == "2026-10-22T12:00:00+00:00"
    assert payload["host"] == "monitor-1"
    assert payload["dashboard_url"] == "https://mtk.example.test"
    assert payload["alerts"][1]["event"] == "metrics.missing"


def test_webhook_posts_json_with_bearer_token():
    client = FakeHttpClient()
    payload = notifications.build_payload(ALERTS, host="monitor-1")

    assert notifications.send_webhook(
        "https://hooks.example.test/mtk",
        payload,
        token="secret-token",
        client=client,
    )
    url, kwargs = client.calls[0]
    assert url == "https://hooks.example.test/mtk"
    assert kwargs["json"] == payload
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_webhook_failure_returns_false_instead_of_raising():
    client = FakeHttpClient(status_code=500)
    assert not notifications.send_webhook(
        "https://hooks.example.test/mtk",
        notifications.build_payload(ALERTS),
        client=client,
    )


def test_email_digest_contains_details_and_html():
    sent = []

    def factory(host, port, timeout=None):
        smtp = FakeSMTP(host, port, timeout=timeout)
        sent.append(smtp)
        return smtp

    cfg = _config()
    payload = notifications.build_payload(ALERTS, host="monitor-1")
    assert notifications.send_email(cfg, payload, smtp_factory=factory)

    smtp = sent[0]
    assert smtp.host == "smtp.example.test"
    assert smtp.started_tls
    assert smtp.login_args == ("bot@example.test", "smtp-secret")
    assert smtp.quit_called
    message = smtp.message
    assert message["To"] == "ops@example.com"
    assert "2 alerts" in message["Subject"]
    text = message.get_body(preferencelist=("plain",)).get_content()
    assert "metrics.missing" in text
    assert "Published posts have no audience metrics." in text
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "<strong>[ERROR] metrics.missing</strong>" in html


def test_notify_skips_when_there_are_no_alerts():
    assert notifications.notify([], config=_config()) == {
        "webhook": "skipped",
        "email": "skipped",
    }


def test_notify_reports_unconfigured_channels():
    result = notifications.notify([ALERTS[0]], config=notifications.NotificationConfig())
    assert result == {"webhook": "not_configured", "email": "not_configured"}


def test_notify_cooldown_suppresses_a_repeated_digest():
    cfg = notifications.NotificationConfig(
        webhook_url="https://hooks.example.test/mtk",
        email_to=(),
        cooldown_s=3600,
    )
    client = FakeHttpClient()

    first = notifications.notify([ALERTS[0]], config=cfg, webhook_client=client)
    # Volatile details change every tick; the fingerprint must ignore them.
    repeated = dict(ALERTS[0])
    repeated["details"] = {**ALERTS[0]["details"], "days_remaining": 0.9}
    second = notifications.notify([repeated], config=cfg, webhook_client=client)
    forced = notifications.notify([repeated], config=cfg, webhook_client=client, force=True)

    assert first == {"webhook": "sent", "email": "not_configured"}
    assert second == {"webhook": "skipped_cooldown", "email": "skipped_cooldown"}
    assert forced == {"webhook": "sent", "email": "not_configured"}
    assert len(client.calls) == 2


def test_notify_sends_both_channels():
    http_client = FakeHttpClient()
    sent_smtp = []

    def factory(host, port, timeout=None):
        smtp = FakeSMTP(host, port, timeout=timeout)
        sent_smtp.append(smtp)
        return smtp

    result = notifications.notify(
        ALERTS,
        config=_config(),
        webhook_client=http_client,
        smtp_factory=factory,
    )
    assert result == {"webhook": "sent", "email": "sent"}
    assert len(http_client.calls) == 1
    assert len(sent_smtp) == 1


def test_run_once_collects_alerts_and_notifies(monkeypatch):
    class Client:
        def post(self, path):
            return type("Response", (), {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"expired": 1, "recheck_queued": 0},
            })()

        def get(self, path):
            if path == "/platform-accounts":
                return type("Response", (), {"json": lambda self: []})()
            return type("Response", (), {
                "json": lambda self: {"metrics_totals": {
                    "published_total": 2,
                    "posts_measured": 0,
                }},
            })()

    delivered = []
    monkeypatch.setattr(
        monitor.notifications,
        "notify",
        lambda alerts: delivered.append(alerts) or {"webhook": "sent", "email": "sent"},
    )

    alerts = monitor.run_once(Client())
    assert {a["event"] for a in alerts} == {"offers.sweep", "metrics.missing"}
    assert len(delivered) == 1
    assert len(delivered[0]) == 2
