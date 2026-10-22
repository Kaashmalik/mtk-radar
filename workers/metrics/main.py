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
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from platforms.facebook import FacebookAdapter, TokenExpiredError  # noqa: E402
from platforms.instagram import InstagramAdapter  # noqa: E402
from platforms.youtube import OAuthConfig, YouTubeAdapter  # noqa: E402

from api_paging import fetch_all  # noqa: E402
from platform_metrics import parse_graph_insights, parse_youtube_analytics  # noqa: E402
from worker_heartbeat import WorkerHeartbeat  # noqa: E402


def _int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

API_URL_DEFAULT = os.environ.get("MTK_API_URL", "http://localhost:8000")

log = logging.getLogger("metrics")

_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()


def _adapter_for_account(account: dict):
    """Resolve an env credential reference into a read-only metrics adapter."""
    source = str(account.get("credential_source") or "")
    platform = account.get("platform")
    if not source.startswith("env:"):
        log.warning("%s account %s uses unsupported credential source %s",
                    platform, account.get("account_handle"), source)
        return None
    raw = source.split(":", 1)[1]
    prefix = raw.rstrip("_*") + "_"
    if platform == "youtube":
        oauth = OAuthConfig.from_env(prefix)
        return YouTubeAdapter(oauth=oauth) if oauth else None
    if platform == "facebook":
        page_id = os.environ.get(f"{prefix}PAGE_ID", "")
        token = os.environ.get(f"{prefix}PAGE_ACCESS_TOKEN", "")
        return FacebookAdapter(page_id=page_id, page_access_token=token) if page_id and token else None
    if platform == "instagram":
        user_id = os.environ.get(f"{prefix}USER_ID", "")
        token = os.environ.get(f"{prefix}ACCESS_TOKEN", "")
        return InstagramAdapter(user_id=user_id, access_token=token) if user_id and token else None
    return None


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
        """Per-account adapters from `platform_accounts` credential references.

        The schedule pins a platform_account_id, so metrics for two YouTube
        channels (or two Facebook pages) never share the first configured
        credential. A platform-level default remains for legacy schedules.
        """
        adapters: dict = {}
        try:
            accounts = self.api.get("/platform-accounts").json()
        except Exception as exc:  # noqa: BLE001 — env fallback still works
            log.warning("platform account lookup failed (%s) — env fallback only", exc)
            accounts = []
        if not isinstance(accounts, list):
            log.warning("platform account lookup returned an unexpected payload — env fallback only")
            accounts = []
        for account in accounts:
            if account.get("status") not in (None, "active"):
                continue
            adapter = _adapter_for_account(account)
            if adapter is None:
                continue
            platform = account.get("platform")
            account_id = str(account.get("id"))
            adapters[f"{platform}:{account_id}"] = adapter
            adapters.setdefault(platform, adapter)

        # Legacy/env-only fallback for platforms without registered accounts.
        oauth = OAuthConfig.from_env()
        if oauth and "youtube" not in adapters:
            adapters["youtube"] = YouTubeAdapter(oauth=oauth)
        elif not oauth and "youtube" not in adapters:
            log.warning("YOUTUBE_* env missing — youtube metrics disabled")
        page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
        token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        if page_id and token and "facebook" not in adapters:
            adapters["facebook"] = FacebookAdapter(page_id=page_id, page_access_token=token)
        ig_user = os.environ.get("INSTAGRAM_USER_ID", "")
        ig_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
        if ig_user and ig_token and "instagram" not in adapters:
            adapters["instagram"] = InstagramAdapter(user_id=ig_user, access_token=ig_token)
        return adapters

    def _acquire_sweep_lock(self, name: str, ttl_s: int = 300) -> bool:
        """One metrics sweep at a time (v0.22) — two instances would pull the
        same platform numbers twice. Fails CLOSED: if the lock service is
        unreachable we cannot prove exclusivity, so this sweep is skipped and
        retried on the next interval."""
        try:
            res = self.api.post("/locks/acquire",
                                 json={"name": name, "holder": f"{name}-worker", "ttl_s": ttl_s})
        except Exception as exc:  # noqa: BLE001 — no proof of exclusivity
            log.warning("sweep lock unavailable (%s) — skipping this sweep", exc)
            return False
        if res.status_code >= 300:
            log.warning("sweep lock refused (%s) — skipping this sweep", res.status_code)
            return False
        acquired = bool(res.json().get("acquired", False))
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
            posts = fetch_all(self.api, "/schedules", {"state": "published"}, limit=200)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("metrics sweep skipped (API unreachable): %s", exc)
            return 0
        if not isinstance(posts, list):
            log.error("published-post lookup returned an unexpected payload — metrics skipped")
            return 0
        measured = 0
        for post in posts:
            if not post.get("remote_post_id"):
                continue
            platform = post.get("platform")
            if platform == "tiktok":
                continue  # documented gap — no insights access without an app
            account_id = post.get("platform_account_id")
            # A pinned account never falls back to another configured account;
            # metrics from the wrong channel are worse than no metrics.
            adapter = (self.adapters.get(f"{platform}:{account_id}")
                       if account_id else self.adapters.get(platform))
            if adapter is None:
                log.warning("schedule %s: no adapter for pinned %s account %s — skipped",
                            post["id"], platform, account_id or "(legacy default)")
                continue
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
            report = dict(adapter.fetch_video_metrics(video_id) or {})
            meta = report.pop("_meta", {}) or {}
            retention_estimated = bool(report.pop("retention_3s_estimated", False))
            report.pop("retention_3s_bucket_ratio", None)
            report.pop("retention_3s_bucket_seconds", None)
            # empty rows raise inside the parser; catch that here by treating
            # an empty report as no-data (fetch returns {} when rows == [])
            if not report:
                return None
            snapshot = parse_youtube_analytics(
                {"columnHeaders": [{"name": k} for k in report], "rows": [[report[k] for k in report]]}
            )
            # Provenance travels with the numbers: which period, which metric
            # definition, and whether any group was rejected/degraded. Without
            # this a stored value cannot be reconciled with YouTube Studio.
            snapshot.update({
                "retention_3s_estimated": retention_estimated,
                "report_start": meta.get("report_start"),
                "report_end": meta.get("report_end"),
                "metric_definition": meta.get("metric_definition"),
                "degraded": bool(meta.get("degraded")),
                "degradation_detail": meta.get("degradation_detail"),
                "raw": {"report": report, "meta": meta},
            })
            return snapshot
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
                "shares": _int(payload.get("shares")),
                "impressions": _int(payload.get("reach")),
                "avg_watch_s": None,
                "avg_view_duration_s": None,
                "avg_view_percentage": None,
                "ctr": None,
                "retention_3s": None,
                "subscribers_gained": None,
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
    hb = WorkerHeartbeat(args.api, "metrics")
    if args.once:
        hb.beat("ok", detail="one-shot metrics sweep")
        try:
            worker.run_once()
        finally:
            hb.beat("stopped", detail="one-shot metrics complete")
        return
    hb.start()
    try:
        worker.run_forever(args.interval)
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
