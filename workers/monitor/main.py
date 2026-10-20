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

import httpx

API_URL_DEFAULT = "http://localhost:8000"
INTERVAL_S = 300
TOKEN_WARN_DAYS = 3

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


def run_once(client: httpx.Client) -> None:
    sweep_offers(client)
    check_platform_accounts(client)


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR expiry/token monitor")
    parser.add_argument("--once", action="store_true", help="run one sweep and exit")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--interval", type=int, default=INTERVAL_S)
    args = parser.parse_args()

    client = httpx.Client(timeout=60, base_url=args.api.rstrip("/"))
    if args.once:
        run_once(client)
        log.info("monitor sweep complete")
        return

    log.info("monitor started against %s (interval %ss)", client.base_url, args.interval)
    while True:
        try:
            run_once(client)
            time.sleep(args.interval)
        except Exception as exc:  # noqa: BLE001 — monitor must never die
            log.exception("monitor tick failed: %s", exc)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
