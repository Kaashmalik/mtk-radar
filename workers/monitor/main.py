"""Expiry/token monitor worker (week 11, master plan §17/§18).

Week-11 exit criterion: "Posts pause when an offer expires; corrections link
to affected videos." The PAUSING itself is enforced by the trg_pause_on_offer_
change database trigger (007) — this worker is the operator-facing sweep that
drives detection and surfaces alerts:

  1. POST /offers/sweep-stale — expires offers past expires_at, flags offers
     with overdue recheck_at (server-side; the trigger auto-pauses their
     scheduled posts).
  2. GET /platform-accounts — alert on token_expired/revoked accounts and
     soon-expiring tokens.
  3. GET /analytics — alert when published posts have no metrics, or when
     the last audience snapshot is stale.

Alerts are always logged. If MTK_NOTIFY_WEBHOOK_URL and/or SMTP settings are
configured, one digest is also POSTed to the webhook and emailed (subject to
MTK_NOTIFY_COOLDOWN_S so a persistent alert does not repeat every tick).

Usage:
    python main.py [--once] [--api http://localhost:8000] [--interval 300]
    python main.py --test-notification
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

import httpx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

import notifications
from worker_heartbeat import WorkerHeartbeat  # noqa: E402


_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
API_URL_DEFAULT = "http://localhost:8000"
INTERVAL_S = 300
TOKEN_WARN_DAYS = 3
METRICS_STALE_HOURS = 48  # audience numbers older than this are an alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("monitor")


def sweep_offers(client: httpx.Client) -> list[dict]:
    """Expire past-due offers + queue overdue rechecks via the API."""
    alerts: list[dict] = []
    try:
        res = client.post("/offers/sweep-stale")
        res.raise_for_status()
        data = res.json()
        if data.get("expired") or data.get("recheck_queued"):
            log.info("sweep: %d offer(s) expired, %d recheck(s) queued "
                     "(scheduled posts auto-paused by trigger)",
                     data["expired"], data["recheck_queued"])
            alerts.append({
                "severity": "warning",
                "event": "offers.sweep",
                "message": ("%d offer(s) expired and %d recheck(s) were queued; "
                            "affected scheduled posts are auto-paused."
                            % (int(data.get("expired") or 0),
                               int(data.get("recheck_queued") or 0))),
                "details": {
                    "expired": int(data.get("expired") or 0),
                    "recheck_queued": int(data.get("recheck_queued") or 0),
                },
            })
    except (httpx.HTTPError, ValueError) as exc:
        log.error("offer sweep failed: %s", exc)
    return alerts


def check_platform_accounts(client: httpx.Client) -> list[dict]:
    """Token-expiry monitor: dead sessions block publishing — alert loudly."""
    alerts: list[dict] = []
    try:
        accounts = client.get("/platform-accounts").json()
    except (httpx.HTTPError, ValueError) as exc:
        log.error("cannot list platform accounts: %s", exc)
        return alerts

    now = datetime.now(timezone.utc)
    for account in accounts:
        status = account.get("status")
        if status in ("token_expired", "revoked"):
            log.error("ALERT platform account %s (%s) is %s — publishing paused; "
                      "refresh credentials then re-register: %s",
                      account.get("account_handle"), account.get("platform"),
                      status, account.get("last_error"))
            alerts.append({
                "severity": "error",
                "event": f"platform_account.{status}",
                "message": ("Platform account %s (%s) is %s; publishing is paused."
                            % (account.get("account_handle"), account.get("platform"),
                               status)),
                "details": {
                    "platform": account.get("platform"),
                    "account_handle": account.get("account_handle"),
                    "status": status,
                    "last_error": account.get("last_error"),
                },
            })
        elif status == "active" and account.get("expires_at"):
            try:
                exp = datetime.fromisoformat(str(account["expires_at"]).replace("Z", "+00:00"))
                days = (exp - now).total_seconds() / 86400
                if days <= TOKEN_WARN_DAYS:
                    log.warning("ALERT token for %s (%s) expires in %.1f day(s) — refresh soon",
                                account.get("account_handle"), account.get("platform"), days)
                    alerts.append({
                        "severity": "warning",
                        "event": "platform_account.expiring",
                        "message": ("Token for %s (%s) expires in %.1f day(s)."
                                    % (account.get("account_handle"),
                                       account.get("platform"), days)),
                        "details": {
                            "platform": account.get("platform"),
                            "account_handle": account.get("account_handle"),
                            "expires_at": account.get("expires_at"),
                            "days_remaining": round(days, 1),
                        },
                    })
            except ValueError:
                pass
    return alerts


def check_metrics_freshness(client: httpx.Client) -> list[dict]:
    """Audience-metrics freshness (v0.20): published posts that nobody
    measures are a silent blind spot — the operator thinks reach is known
    while the numbers are days old (or missing because a scope/reason
    stopped the pull)."""
    alerts: list[dict] = []
    try:
        data = client.get("/analytics").json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("cannot read analytics for metrics freshness: %s", exc)
        return alerts

    totals = data.get("metrics_totals") or {}
    published = int(totals.get("published_total") or 0)
    if published == 0:
        return alerts
    measured = int(totals.get("posts_measured") or 0)
    if measured == 0:
        log.error("ALERT %d published post(s) but no audience metrics at all — "
                  "the metrics worker has no access (OAuth scope / credentials) "
                  "or has not run yet", published)
        alerts.append({
            "severity": "error",
            "event": "metrics.missing",
            "message": ("%d published post(s) have no audience metrics; the "
                        "metrics worker has no access or has not run yet."
                        % published),
            "details": {"published_total": published, "posts_measured": 0},
        })
        return alerts
    last = totals.get("last_captured_at")
    if not last:
        return alerts
    try:
        captured = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return alerts
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
    if hours > METRICS_STALE_HOURS:
        log.warning("ALERT audience metrics are %.0fh old (%d/%d posts measured) — "
                    "the metrics sweep may have stopped", hours, measured, published)
        alerts.append({
            "severity": "warning",
            "event": "metrics.stale",
            "message": ("Audience metrics are %.0fh old (%d/%d posts measured); "
                        "the metrics sweep may have stopped."
                        % (hours, measured, published)),
            "details": {
                "hours_old": round(hours, 1),
                "posts_measured": measured,
                "published_total": published,
                "last_captured_at": last,
            },
        })
    return alerts


_DIGEST_KINDS = {
    "redaction",
    "offer_approval",
    "schedule_approval",
    "verification",
    "budget",
}
_IMMEDIATE_ERROR_KINDS = {
    "render_failed",
    "publish_failed",
    "offer_expiry",
    "worker",
}


def check_attention(client: httpx.Client) -> list[dict]:
    """Turn the dashboard's Needs You counts into alert-group summaries.

    One alert per category, not one per row: a dozen pending approvals should
    be one actionable email, not a mailbox full of noise. Credential alerts
    are omitted here because check_platform_accounts already reports them with
    more detail.
    """
    try:
        data = client.get("/attention").json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("cannot read attention inbox: %s", exc)
        return []
    if not isinstance(data, dict):  # legacy API without /attention
        return []

    alerts: list[dict] = []
    by_kind = data.get("by_kind") or {}
    items = data.get("items") or []
    for kind, raw_count in (data.get("counts") or {}).items():
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0 or kind == "token":
            continue
        meta = by_kind.get(kind) or {}
        examples = [
            str(item.get("title")) for item in items if item.get("kind") == kind
        ][:3]
        label = str(meta.get("label") or kind.replace("_", " "))
        noun = "item" if count == 1 else "items"
        verb = "needs" if count == 1 else "need"
        message = f"{label}: {count} {noun} {verb} attention."
        if examples:
            message += " Examples: " + "; ".join(examples) + "."
        delivery = "digest" if kind in _DIGEST_KINDS else "immediate"
        severity = "error" if kind in _IMMEDIATE_ERROR_KINDS else "warning"
        log_fn = log.error if severity == "error" else log.warning
        log_fn("ALERT %s", message)
        alerts.append({
            "severity": severity,
            "event": f"attention.{kind}",
            "message": message,
            "details": {
                "kind": kind,
                "count": count,
                "href": meta.get("href") or "/attention",
                "examples": examples,
            },
            "delivery": delivery,
        })
    return alerts


def run_once(client: httpx.Client) -> list[dict]:
    alerts: list[dict] = []
    alerts.extend(sweep_offers(client))
    alerts.extend(check_platform_accounts(client))
    alerts.extend(check_metrics_freshness(client))
    alerts.extend(check_attention(client))
    # Deliver what an earlier outage left behind before today's digests.
    try:
        notifications.flush_outbox()
    except Exception as exc:  # noqa: BLE001 — alerting must not stop the sweep
        log.exception("notification outbox replay crashed: %s", exc)
    # Immediate failures page now; pending human work travels in a digest.
    for delivery in ("immediate", "digest"):
        group = [a for a in alerts if a.get("delivery", "immediate") == delivery]
        if not group:
            continue
        try:
            result = notifications.notify(group)
            log.info("%s notification result: %s", delivery, result)
        except Exception as exc:  # noqa: BLE001 — alerting must not stop the sweep
            log.exception("%s notification delivery crashed: %s", delivery, exc)
    return alerts


# ---------------------------------------------------------- graceful stop
# SIGTERM (docker stop / systemd) must NOT abandon a post mid-upload: the
# worker finishes the item it is on, reports the outcome, then exits.
_STOP = False


def _install_stop_handlers() -> None:
    def _handler(signum, _frame):
        global _STOP
        _STOP = True
        log.info("signal %s received — finishing the current item, then exiting", signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):  # pragma: no cover — non-main thread
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR expiry/token monitor")
    parser.add_argument("--once", action="store_true", help="run one sweep and exit")
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="send one test alert to the configured webhook/email and exit",
    )
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--interval", type=int, default=INTERVAL_S)
    args = parser.parse_args()

    config = notifications.NotificationConfig.from_env()
    log.info("notification config: %s", config.public_summary())

    if args.test_notification:
        alert = {
            "severity": "info",
            "event": "monitor.test",
            "message": "Test notification from the MTK RADAR monitor worker.",
            "details": {
                "service": "monitor",
                "note": "No production alert was raised.",
            },
        }
        result = notifications.notify([alert], config=config, force=True)
        print(json.dumps({
            "notification_config": config.public_summary(),
            "delivery": result,
        }, indent=2, sort_keys=True))
        if "failed" in result.values():
            raise SystemExit(1)
        return

    client = httpx.Client(timeout=60, base_url=args.api.rstrip("/"), headers=_api_auth_headers())
    _install_stop_handlers()
    hb = WorkerHeartbeat(
        args.api, "monitor",
        metadata={"notification_channels": {
            "webhook": config.webhook_enabled,
            "email": config.email_enabled,
        }},
    )
    if args.once:
        hb.beat("ok", detail="one-shot monitor sweep")
        try:
            run_once(client)
            log.info("monitor sweep complete")
        finally:
            hb.beat("stopped", detail="one-shot monitor complete")
        return

    log.info("monitor started against %s (interval %ss)", client.base_url, args.interval)
    hb.start()
    try:
        while not _STOP:
            try:
                run_once(client)
                if _STOP:
                    break
                time.sleep(args.interval)
            except Exception as exc:  # noqa: BLE001 — monitor must never die
                log.exception("monitor tick failed: %s", exc)
                time.sleep(args.interval)
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
