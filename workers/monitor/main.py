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

Usage:
    python main.py [--once] [--api http://localhost:8000] [--interval 300]
"""

import argparse
import logging
import time
from datetime import datetime, timezone

import os
import signal
import httpx


_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()

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


def sweep_offers(client: httpx.Client) -> None:
    """Expire past-due offers + queue overdue rechecks via the API."""
    try:
        res = client.post("/offers/sweep-stale")
        res.raise_for_status()
        data = res.json()
        if data.get("expired") or data.get("recheck_queued"):
            log.info("sweep: %d offer(s) expired, %d recheck(s) queued "
                     "(scheduled posts auto-paused by trigger)",
                     data["expired"], data["recheck_queued"])
    except httpx.HTTPError as exc:
        log.error("offer sweep failed: %s", exc)


def check_platform_accounts(client: httpx.Client) -> None:
    """Token-expiry monitor: dead sessions block publishing — alert loudly."""
    try:
        accounts = client.get("/platform-accounts").json()
    except httpx.HTTPError as exc:
        log.error("cannot list platform accounts: %s", exc)
        return

    now = datetime.now(timezone.utc)
    for account in accounts:
        status = account.get("status")
        if status in ("token_expired", "revoked"):
            log.error("ALERT platform account %s (%s) is %s — publishing paused; "
                      "refresh credentials then re-register: %s",
                      account.get("account_handle"), account.get("platform"),
                      status, account.get("last_error"))
        elif status == "active" and account.get("expires_at"):
            try:
                exp = datetime.fromisoformat(str(account["expires_at"]).replace("Z", "+00:00"))
                days = (exp - now).total_seconds() / 86400
                if days <= TOKEN_WARN_DAYS:
                    log.warning("ALERT token for %s (%s) expires in %.1f day(s) — refresh soon",
                                account.get("account_handle"), account.get("platform"), days)
            except ValueError:
                pass


def check_metrics_freshness(client: httpx.Client) -> None:
    """Audience-metrics freshness (v0.20): published posts that nobody
    measures are a silent blind spot — the operator thinks reach is known
    while the numbers are days old (or missing because a scope/reason
    stopped the pull)."""
    try:
        data = client.get("/analytics").json()
    except httpx.HTTPError as exc:
        log.warning("cannot read analytics for metrics freshness: %s", exc)
        return

    totals = data.get("metrics_totals") or {}
    published = int(totals.get("published_total") or 0)
    if published == 0:
        return
    measured = int(totals.get("posts_measured") or 0)
    if measured == 0:
        log.error("ALERT %d published post(s) but no audience metrics at all — "
                  "the metrics worker has no access (OAuth scope / credentials) "
                  "or has not run yet", published)
        return
    last = totals.get("last_captured_at")
    if not last:
        return
    try:
        captured = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
    if hours > METRICS_STALE_HOURS:
        log.warning("ALERT audience metrics are %.0fh old (%d/%d posts measured) — "
                    "the metrics sweep may have stopped", hours, measured, published)


def run_once(client: httpx.Client) -> None:
    sweep_offers(client)
    check_platform_accounts(client)
    check_metrics_freshness(client)


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
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--interval", type=int, default=INTERVAL_S)
    args = parser.parse_args()

    client = httpx.Client(timeout=60, base_url=args.api.rstrip("/"), headers=_api_auth_headers())
    _install_stop_handlers()
    if args.once:
        run_once(client)
        log.info("monitor sweep complete")
        return

    log.info("monitor started against %s (interval %ss)", client.base_url, args.interval)
    while not _STOP:
        try:
            run_once(client)
            if _STOP:
                break
            time.sleep(args.interval)
        except Exception as exc:  # noqa: BLE001 — monitor must never die
            log.exception("monitor tick failed: %s", exc)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
