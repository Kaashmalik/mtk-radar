"""Audience-metrics worker (v0.18, master plan §7 "analyse views, engagement,
… and use those signals to improve output") — the measurement half of the
analytics loop, alongside the API's pipeline aggregates.

Sweep (read-only on the platforms, write-only on our API):
  1. GET /schedules?state=published — posts with a remote_post_id.
  2. For each, pull the platform's per-video metrics:
       youtube  → YouTube Analytics API v2 via YouTubeAdapter.fetch_video_metrics
       facebook → Graph video_insights via FacebookAdapter.insights
       tiktok   → SKIPPED: TikTok's insights endpoints need an approved
                  developer app + undocumented scopes (runbook §9 gap).
  3. POST /schedules/{id}/metrics — a daily snapshot (the API upserts per
     UTC day, so re-pulls within a day are idempotent).

Credentials come from the same env the publishing worker uses (YOUTUBE_*,
FACEBOOK_*); tokens are refreshed in-memory only. A 403 on the analytics
scope is a logged skip, not a crash — the post simply stays unmeasured.

Usage:
    python main.py [--once] [--api http://localhost:8000] [--interval 3600]
"""

import argparse
import logging
import os
import signal
import sys
import time

import httpx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "workers", "publishing"))

from platforms.facebook import FacebookAdapter, TokenExpiredError  # noqa: E402
from platforms.instagram import InstagramAdapter  # noqa: E402
from platforms.youtube import OAuthConfig, YouTubeAdapter  # noqa: E402

from platform_metrics import parse_graph_insights, parse_youtube_analytics  # noqa: E402


def _int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

API_URL_DEFAULT = os.environ.get("MTK_API_URL", "http://localhost:8000")

log = logging.getLogger("metrics")

_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()


def _api_auth_headers() -> dict:
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}


class MetricsWorker:
    def __init__(self, api_url: str = API_URL_DEFAULT,
                 adapters: dict | None = None):
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"),
                                headers=_api_auth_headers())
        self._adapters = adapters  # injected for tests; built lazily otherwise

    @property
    def adapters(self) -> dict:
        if self._adapters is None:
            self._adapters = self.build_adapters()
        return self._adapters

    def build_adapters(self) -> dict:
        """Same credential references as publishing (§6): env only, token
        material never leaves the process."""
        adapters: dict = {}
        oauth = OAuthConfig.from_env()
        if oauth:
            adapters["youtube"] = YouTubeAdapter(oauth=oauth)
        else:
            log.warning("YOUTUBE_* env missing — youtube metrics disabled")
        page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
        token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        if page_id and token:
            adapters["facebook"] = FacebookAdapter(page_id=page_id, page_access_token=token)
        else:
            log.warning("FACEBOOK_* env missing — facebook metrics disabled")
        ig_user = os.environ.get("INSTAGRAM_USER_ID", "")
        ig_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
        if ig_user and ig_token:
            adapters["instagram"] = InstagramAdapter(user_id=ig_user, access_token=ig_token)
        else:
            log.warning("INSTAGRAM_* env missing — instagram metrics disabled")
        return adapters

    def _acquire_sweep_lock(self, name: str, ttl_s: int = 300) -> bool:
        """One metrics sweep at a time (v0.22) — two instances would pull the
        same platform numbers twice. Fails OPEN when the lock endpoint is
        unavailable."""
        try:
            res = self.api.post("/locks/acquire",
                                 json={"name": name, "holder": f"{name}-worker", "ttl_s": ttl_s})
        except Exception as exc:  # noqa: BLE001 — a lock must never stop the sweep
            log.warning("sweep lock unavailable (%s) — continuing without it", exc)
            return True
        if res.status_code >= 300:
            log.warning("sweep lock refused (%s) — continuing without it", res.status_code)
            return True
        # a response without the flag is treated as "proceed" (fail-open)
        acquired = bool(res.json().get("acquired", True))
        if not acquired:
            log.info("another worker holds the %s lock — this sweep is skipped", name)
        return acquired

    def _release_sweep_lock(self, name: str) -> None:
        try:
            self.api.post("/locks/release", json={"name": name})
        except Exception:  # noqa: BLE001 — the lock expires on its own
            pass

    def run_once(self) -> int:
        if not self._acquire_sweep_lock("metrics"):
            return 0
        try:
            return self._sweep()
        finally:
            self._release_sweep_lock("metrics")

    def _sweep(self) -> int:
        try:
            posts = self.api.get("/schedules", params={"state": "published", "limit": 200}).json()
        except httpx.HTTPError as exc:
            log.warning("metrics sweep skipped (API unreachable): %s", exc)
            return 0
        measured = 0
        for post in posts:
            if not post.get("remote_post_id"):
                continue
            platform = post.get("platform")
            if platform == "tiktok":
                continue  # documented gap — no insights access without an app
            adapter = self.adapters.get(platform)
            if adapter is None:
                continue  # credentials not configured for this platform
            try:
                snapshot = self._measure(platform, adapter, post["remote_post_id"])
            except PermissionError as exc:
                log.warning("schedule %s: metrics scope missing (%s)", post["id"], exc)
                continue
            except TokenExpiredError as exc:
                log.warning("schedule %s: dead %s session — monitor will alert (%s)",
                            post["id"], platform, exc)
                continue
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                log.warning("schedule %s: metrics pull failed: %s", post["id"], exc)
                continue
            if snapshot is None:
                continue
            resp = self.api.post(f"/schedules/{post['id']}/metrics", json={
                "platform": platform,
                "source": "youtube-analytics" if platform == "youtube" else "graph-insights",
                **snapshot,
            })
            if resp.status_code < 300:
                measured += 1
            else:
                log.warning("schedule %s: metrics write refused (%s)",
                            post["id"], resp.status_code)
        log.info("metrics sweep: %d/%d measured", measured, len(posts))
        return measured

    def _measure(self, platform: str, adapter, video_id: str) -> dict | None:
        """Provider payload → normalized snapshot; None when there is no data
        yet (fresh upload before the platform has numbers)."""
        if platform == "youtube":
            report = adapter.fetch_video_metrics(video_id)
            # empty rows raise inside the parser; catch that here by treating
            # an empty report as no-data (fetch returns {} when rows == [])
            if not report:
                return None
            return parse_youtube_analytics(
                {"columnHeaders": [{"name": k} for k in report], "rows": [[report[k] for k in report]]}
            )
        if platform == "facebook":
            payload = adapter.insights(video_id)
            if not payload:
                return None
            return parse_graph_insights({"data": [
                {"name": k, "values": [{"value": v}]} for k, v in payload.items()
            ]})
        if platform == "instagram":
            payload = adapter.insights(video_id)
            if not payload:
                return None
            return {
                "views": _int(payload.get("plays")),
                "likes": _int(payload.get("likes")),
                "comments": _int(payload.get("comments")),
                "impressions": _int(payload.get("reach")),
                "avg_watch_s": None,
            }
        return None

    def run_forever(self, interval: int) -> None:
        gap = int(os.environ.get("MTK_METRICS_INTERVAL", str(interval)))
        while not _STOP:
            started = time.monotonic()
            try:
                self.run_once()
            except httpx.HTTPError as exc:
                log.warning("sweep aborted (API unreachable): %s", exc)
            if _STOP:
                break
            elapsed = time.monotonic() - started
            time.sleep(max(5, gap - elapsed))


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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="MTK RADAR audience-metrics worker")
    parser.add_argument("--once", action="store_true", help="run one sweep and exit")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()

    _install_stop_handlers()
    worker = MetricsWorker(args.api)
    if args.once:
        worker.run_once()
        return
    worker.run_forever(args.interval)


if __name__ == "__main__":
    main()
