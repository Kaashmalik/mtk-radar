"""Operator notifications for the monitor worker.

The monitor already logs alerts. This module adds two optional delivery
channels so an alert does not depend on somebody watching a terminal:

  * an outbound JSON webhook (Slack/Discord/n8n/webhook.site/your receiver);
  * an email digest over SMTP.

Both are opt-in through environment variables. A missing configuration is not
an error — the monitor continues to log exactly as before.

The payload is deliberately small and contains no credentials. Alert details
must already be redacted by the caller.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Callable, Iterable, Mapping, Sequence

import httpx

log = logging.getLogger("monitor.notifications")

SCHEMA = "mtk-radar.notification.v1"
_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}
_DEFAULT_SUBJECT_PREFIX = "[MTK RADAR]"


@dataclass(frozen=True)
class NotificationConfig:
    """Delivery settings read from the environment.

    All fields are optional. Empty webhook/email fields simply disable that
    channel.
    """

    webhook_url: str = ""
    webhook_token: str = ""
    email_to: tuple[str, ...] = ()
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    timeout_s: float = 10.0
    cooldown_s: float = 3600.0
    subject_prefix: str = _DEFAULT_SUBJECT_PREFIX

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "NotificationConfig":
        values = os.environ if env is None else env

        def text(name: str, default: str = "") -> str:
            return str(values.get(name, default) or "").strip()

        recipients = tuple(
            part.strip()
            for part in text("MTK_NOTIFY_EMAIL_TO").split(",")
            if part.strip()
        )
        try:
            port = int(text("MTK_SMTP_PORT", "587") or "587")
        except ValueError:
            port = 587
        try:
            timeout = float(text("MTK_NOTIFY_TIMEOUT_S", "10") or "10")
        except ValueError:
            timeout = 10.0
        try:
            cooldown = float(text("MTK_NOTIFY_COOLDOWN_S", "3600") or "3600")
        except ValueError:
            cooldown = 3600.0

        smtp_ssl = _bool(values.get("MTK_SMTP_SSL"), port == 465)
        return cls(
            webhook_url=text("MTK_NOTIFY_WEBHOOK_URL"),
            webhook_token=text("MTK_NOTIFY_WEBHOOK_TOKEN"),
            email_to=recipients,
            smtp_host=text("MTK_SMTP_HOST"),
            smtp_port=port,
            smtp_user=text("MTK_SMTP_USER"),
            smtp_password=text("MTK_SMTP_PASSWORD"),
            smtp_from=text("MTK_SMTP_FROM") or text("MTK_SMTP_USER"),
            smtp_starttls=_bool(values.get("MTK_SMTP_STARTTLS"), not smtp_ssl),
            smtp_ssl=smtp_ssl,
            timeout_s=max(1.0, timeout),
            cooldown_s=max(0.0, cooldown),
            subject_prefix=text("MTK_NOTIFY_SUBJECT_PREFIX", _DEFAULT_SUBJECT_PREFIX)
            or _DEFAULT_SUBJECT_PREFIX,
        )

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.webhook_url)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_to and self.smtp_host and self.smtp_from)

    def public_summary(self) -> dict[str, Any]:
        """Safe diagnostics: never return passwords or bearer tokens."""
        return {
            "webhook_configured": self.webhook_enabled,
            "email_configured": self.email_enabled,
            "email_recipients": len(self.email_to),
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_starttls": self.smtp_starttls,
            "smtp_ssl": self.smtp_ssl,
            "cooldown_s": self.cooldown_s,
        }


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in ("", "0", "false", "no", "off")


_LAST_SENT: dict[str, float] = {}


def alert_fingerprint(alerts: Iterable[Mapping[str, Any]]) -> str:
    """Stable identity for a set of alerts.

    Do not hash volatile fields such as ``hours_old`` or ``days_remaining``:
    they change every tick and would defeat the cooldown for a persistent
    problem. Event + platform + account + status is enough to distinguish the
    operational failures the monitor reports.
    """
    identities: list[tuple[str, str, str, str]] = []
    for alert in alerts:
        details = alert.get("details") or {}
        if not isinstance(details, Mapping):
            details = {}
        identities.append((
            str(alert.get("event", "alert")),
            str(details.get("platform", "")),
            str(details.get("account_handle", "")),
            str(details.get("status", "")),
        ))
    raw = json.dumps(sorted(identities), separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def reset_cooldown_state() -> None:
    """Test helper: forget in-memory delivery timestamps."""
    _LAST_SENT.clear()


def _severity(alerts: Sequence[Mapping[str, Any]]) -> str:
    highest = 0
    for alert in alerts:
        highest = max(highest, _SEVERITY_ORDER.get(str(alert.get("severity", "info")), 0))
    for name, rank in _SEVERITY_ORDER.items():
        if rank == highest:
            return name
    return "info"


def build_payload(
    alerts: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
    host: str | None = None,
    dashboard_url: str | None = None,
) -> dict[str, Any]:
    """Build one digest payload for a batch of monitor alerts.

    The function is pure (apart from an optional clock/host read) so it can be
    tested without a network or mail server.
    """
    items = [dict(alert) for alert in alerts]
    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    base = (
        dashboard_url
        if dashboard_url is not None
        else os.environ.get("MTK_PUBLIC_BASE_URL", "").strip().rstrip("/")
    )
    return {
        "schema": SCHEMA,
        "source": "mtk-radar.monitor",
        "event": "monitor.digest",
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "host": host if host is not None else socket.gethostname(),
        "severity": _severity(items),
        "alert_count": len(items),
        "dashboard_url": base or None,
        "alerts": items,
    }


def send_webhook(
    url: str,
    payload: Mapping[str, Any],
    *,
    token: str = "",
    timeout_s: float = 10.0,
    client: httpx.Client | None = None,
) -> bool:
    """POST the payload as JSON. Returns False instead of raising."""
    if not url:
        return False

    own_client = client is None
    http = client or httpx.Client(timeout=timeout_s)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = http.post(url, json=payload, headers=headers, timeout=timeout_s)
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — alert delivery must not crash the monitor
        # Do not log the URL: webhook URLs often contain a secret path/token.
        log.error("webhook delivery failed (%s)", type(exc).__name__)
        return False
    finally:
        if own_client:
            http.close()


def _format_details(details: object) -> str:
    if details in (None, "", {}, []):
        return ""
    if isinstance(details, str):
        return details
    try:
        return json.dumps(details, indent=2, sort_keys=True, default=str)
    except TypeError:
        return str(details)


def render_text(payload: Mapping[str, Any]) -> str:
    """Plain-text digest used by email and available for tests/debugging."""
    lines = [
        "MTK RADAR monitor notification",
        f"Generated: {payload.get('generated_at', '')}",
        f"Severity: {str(payload.get('severity', 'info')).upper()}",
        f"Alerts: {payload.get('alert_count', 0)}",
        "",
    ]
    for index, alert in enumerate(payload.get("alerts", []) or [], start=1):
        lines.append(
            f"{index}. [{str(alert.get('severity', 'info')).upper()}] "
            f"{alert.get('event', 'alert')}"
        )
        message = str(alert.get("message", "")).strip()
        if message:
            lines.append(f"   {message}")
        details = _format_details(alert.get("details"))
        if details:
            for line in details.splitlines():
                lines.append(f"   {line}")
        lines.append("")
    dashboard = payload.get("dashboard_url")
    if dashboard:
        lines.append(f"Dashboard: {dashboard}")
    return "\n".join(lines).rstrip() + "\n"


def render_html(payload: Mapping[str, Any]) -> str:
    """Minimal escaped HTML digest for email clients."""
    rows: list[str] = []
    for alert in payload.get("alerts", []) or []:
        severity = html.escape(str(alert.get("severity", "info")).upper())
        event = html.escape(str(alert.get("event", "alert")))
        message = html.escape(str(alert.get("message", "")))
        details = html.escape(_format_details(alert.get("details")))
        detail_html = f"<pre>{details}</pre>" if details else ""
        rows.append(
            "<li>"
            f"<strong>[{severity}] {event}</strong><br>{message}{detail_html}"
            "</li>"
        )
    dashboard = payload.get("dashboard_url")
    dashboard_html = (
        f'<p><a href="{html.escape(str(dashboard))}">Open dashboard</a></p>'
        if dashboard
        else ""
    )
    return (
        "<html><body>"
        "<h2>MTK RADAR monitor notification</h2>"
        f"<p>Generated: {html.escape(str(payload.get('generated_at', '')))}<br>"
        f"Severity: {html.escape(str(payload.get('severity', 'info')).upper())}<br>"
        f"Alerts: {html.escape(str(payload.get('alert_count', 0)))}</p>"
        f"<ul>{''.join(rows)}</ul>{dashboard_html}"
        "</body></html>"
    )


def subject_for(payload: Mapping[str, Any], prefix: str = _DEFAULT_SUBJECT_PREFIX) -> str:
    count = int(payload.get("alert_count", 0) or 0)
    severity = str(payload.get("severity", "info")).upper()
    noun = "alert" if count == 1 else "alerts"
    return f"{prefix} {count} {noun} ({severity})"


def send_email(
    config: NotificationConfig,
    payload: Mapping[str, Any],
    *,
    smtp_factory: Callable[..., Any] | None = None,
) -> bool:
    """Send the digest over SMTP. Returns False instead of raising."""
    if not config.email_enabled:
        return False

    message = EmailMessage()
    message["Subject"] = subject_for(payload, config.subject_prefix)
    message["From"] = config.smtp_from
    message["To"] = ", ".join(config.email_to)
    message.set_content(render_text(payload))
    message.add_alternative(render_html(payload), subtype="html")

    factory = smtp_factory or (smtplib.SMTP_SSL if config.smtp_ssl else smtplib.SMTP)
    try:
        smtp = factory(config.smtp_host, config.smtp_port, timeout=config.timeout_s)
        try:
            if config.smtp_starttls and not config.smtp_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if config.smtp_user:
                smtp.login(config.smtp_user, config.smtp_password)
            smtp.send_message(message)
        finally:
            try:
                smtp.quit()
            except Exception:  # pragma: no cover — best-effort cleanup
                pass
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error("email delivery failed: %s", exc)
        return False


def notify(
    alerts: Iterable[Mapping[str, Any]],
    *,
    config: NotificationConfig | None = None,
    webhook_client: httpx.Client | None = None,
    smtp_factory: Callable[..., Any] | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Deliver one digest to every configured channel.

    Identical alert sets are suppressed for ``cooldown_s`` (default one hour)
    after a fully successful delivery, so a persistent dead token does not
    send an email every five-minute monitor tick. A partial failure is retried
    on the next tick. ``force=True`` bypasses the cooldown (used by the test
    command).

    Returns a small status map suitable for logging/tests:
      {"webhook": "sent"|"not_configured"|"failed"|"skipped"|"skipped_cooldown",
       "email": ...}
    """
    items = list(alerts)
    if not items:
        return {"webhook": "skipped", "email": "skipped"}

    cfg = config or NotificationConfig.from_env()
    if not (cfg.webhook_enabled or cfg.email_enabled):
        return {"webhook": "not_configured", "email": "not_configured"}

    fingerprint = alert_fingerprint(items)
    if not force and cfg.cooldown_s > 0:
        last = _LAST_SENT.get(fingerprint)
        if last is not None and time.monotonic() - last < cfg.cooldown_s:
            log.info("notification digest suppressed by cooldown (%.0fs)", cfg.cooldown_s)
            return {"webhook": "skipped_cooldown", "email": "skipped_cooldown"}

    payload = build_payload(items)
    result: dict[str, str] = {}

    if cfg.webhook_enabled:
        result["webhook"] = (
            "sent"
            if send_webhook(
                cfg.webhook_url,
                payload,
                token=cfg.webhook_token,
                timeout_s=cfg.timeout_s,
                client=webhook_client,
            )
            else "failed"
        )
    else:
        result["webhook"] = "not_configured"

    if cfg.email_enabled:
        result["email"] = "sent" if send_email(cfg, payload, smtp_factory=smtp_factory) else "failed"
    else:
        result["email"] = "not_configured"

    if result["webhook"] == "sent" or result["email"] == "sent":
        log.info("notification digest delivered: %s", result)
    configured = [
        channel
        for channel in ("webhook", "email")
        if result.get(channel) != "not_configured"
    ]
    if configured and all(result.get(channel) == "sent" for channel in configured):
        _LAST_SENT[fingerprint] = time.monotonic()
        if len(_LAST_SENT) > 128:
            # ponytail: tiny bounded cache; a monitor does not need history.
            oldest = min(_LAST_SENT, key=_LAST_SENT.get)
            _LAST_SENT.pop(oldest, None)
    return result
