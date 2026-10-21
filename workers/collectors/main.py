"""Collector worker — polls registered Tier-A sources and feeds the inbox.

Week 2 target (master plan §18): "A candidate appears once with canonical URL,
timestamp, and deduplication key."

Design:
- Sources are read from the API registry (GET /sources?enabled=true) — the
  dashboard is the source of truth, collectors hold no state of their own.
- Each source keeps its own due time (polling_cadence); one bad source never
  crashes the loop.
- Fresh observations are POSTed to /items; the API performs canonicalization
  and dedup, so re-running a poll never creates duplicates.
- After each poll the worker reports back (POST /sources/{id}/poll-result)
  so last_checked_at stays accurate for source-health monitoring.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Optional

import httpx

# Make the shared adapters package importable (monorepo layout).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "packages")))

from source_adapters import (  # noqa: E402
    Fetcher,
    fetch_github_releases,
    fetch_page_snapshot,
    fetch_rss,
)

API_URL = os.environ.get("API_URL", "http://localhost:8000")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # optional; raises rate limits
MTK_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()


def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py) — same contract as the other workers."""
    return {"Authorization": f"Bearer {MTK_API_TOKEN}"} if MTK_API_TOKEN else {}
HOUSEKEEPING_INTERVAL = 60  # seconds between due-source sweeps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("collector")

_CADENCE_RE = re.compile(r"^\s*(\d+)\s*(second|minute|hour|day)s?\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_cadence(cadence: Optional[str], default: int = 6 * 3600) -> int:
    """Postgres interval text like '6 hours' → seconds."""
    if not cadence:
        return default
    match = _CADENCE_RE.match(cadence)
    if not match:
        return default
    value, unit = match.groups()
    return int(value) * _UNIT_SECONDS[unit.lower()]


def collect(source: dict, fetcher: Fetcher) -> list[dict]:
    """Run the source's adapter. Returns raw item payloads (API dedups)."""
    adapter = source["adapter"]
    config = source.get("config") or {}
    if isinstance(config, str):
        # jsonb columns reach the worker as serialized JSON in some API versions.
        try:
            config = json.loads(config)
        except ValueError:
            config = {}
    if not isinstance(config, dict):
        config = {}

    if adapter == "rss":
        feed_url = config.get("feed_url")
        if not feed_url:
            raise ValueError("rss source missing config.feed_url")
        raw = fetch_rss(feed_url, fetcher=fetcher)
    elif adapter == "github_releases":
        repo = config.get("repo")
        if not repo:
            raise ValueError("github_releases source missing config.repo")
        raw = fetch_github_releases(repo, fetcher=fetcher, token=GITHUB_TOKEN)
    elif adapter == "page_watch":
        url = config.get("url") or source.get("canonical_domain")
        if not url:
            raise ValueError("page_watch source missing config.url")
        raw = fetch_page_snapshot(url, fetcher=fetcher)
    else:
        # 'manual' and 'extension' sources are not collector-polled.
        return []

    return [
        {
            "external_item_id": item.external_item_id,
            "url": item.url,
            "title": item.title,
            "text": item.text,
            "published_at": item.published_at.isoformat() if item.published_at else None,
        }
        for item in raw
    ]


class Collector:
    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url.rstrip("/")
        self.client = httpx.Client(timeout=30, headers=_api_auth_headers())
        self.fetcher = Fetcher()
        self.next_due: dict[str, float] = {}

    def run_forever(self) -> None:
        log.info("collector started against %s", self.api_url)
        while True:
            try:
                asyncio.run(self.sweep())
                time.sleep(HOUSEKEEPING_INTERVAL)
            except httpx.HTTPError as exc:
                log.error("API unreachable, retrying in %ss: %s", HOUSEKEEPING_INTERVAL, exc)
                time.sleep(HOUSEKEEPING_INTERVAL)

    async def sweep(self) -> None:
        resp = self.client.get(f"{self.api_url}/sources", params={"enabled": "true"})
        resp.raise_for_status()
        sources = resp.json()
        now = time.time()

        for source in sources:
            sid = source["id"]
            if self.next_due.get(sid, 0) > now:
                continue
            try:
                await self._poll(source)
            except Exception:  # noqa: BLE001 — one bad source never stops the sweep
                log.exception("source %s (%s) failed", sid, source["provider"])
                self._report(sid, ok=False, detail="poll failed; see collector logs")
            finally:
                cadence = parse_cadence(source.get("polling_cadence"))
                self.next_due[sid] = time.time() + cadence

    async def _poll(self, source: dict) -> None:
        payloads = await asyncio.to_thread(collect, source, self.fetcher)
        created = 0
        for payload in payloads:
            resp = self.client.post(
                f"{self.api_url}/items",
                json={"source_id": source["id"], **payload},
            )
            resp.raise_for_status()
            if resp.json().get("created"):
                created += 1
        self._report(sid=source["id"], ok=True, created=created)
        log.info(
            "polled %s (%s): %d items, %d new",
            source["provider"], source["adapter"], len(payloads), created,
        )

    def _report(self, sid: str, ok: bool, detail: Optional[str] = None, created: int = 0) -> None:
        try:
            self.client.post(
                f"{self.api_url}/sources/{sid}/poll-result",
                json={"ok": ok, "created": created, "detail": detail},
            )
        except httpx.HTTPError:
            log.warning("failed to report poll result for source %s", sid)


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR collector worker")
    parser.add_argument("--once", action="store_true",
                        help="run one due-source sweep and exit (same contract "
                             "as monitor/publishing/metrics; a scheduled "
                             "`--once` cron is the deployment default)")
    parser.add_argument("--api", default=API_URL)
    args = parser.parse_args()

    collector = Collector(args.api)
    if args.once:
        asyncio.run(collector.sweep())
        return
    collector.run_forever()


if __name__ == "__main__":
    main()
