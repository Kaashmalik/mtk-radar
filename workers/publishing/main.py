"""Publishing worker — scheduled multi-platform uploads (week 10, master plan §6/§17).

Official APIs only (YouTube Data API, Meta Graph). NO browser automation to
evade platform rules.

Sweep (every tick, or once with --once):
  1. Load platform accounts from the API; build adapters for configured ones.
  2. Fetch 'scheduled' posts that are due (local_time <= now).
  3. For each: locate the render file, upload via the adapter, report the
     result (idempotent by schedule id).
  4. Token-expiry recovery: on TokenExpiredError → mark the account expired,
     pause the queue, raise an operator-visible alert. On later successful
     refresh, accounts auto-return to 'active' via the on_refresh hook —
     schedules stay paused for explicit operator resume (human gate, §17).
  5. Approval + validity gates (v0.16): the render's script hash must match
     the schedule's approved version hash (§17), and the offer must not be
     expired / recheck-overdue (§11) — otherwise the post is auto-paused.
  6. Auto-retry (v0.17, §17): failed posts requeue with exponential backoff
     (max MTK_PUBLISH_MAX_RETRIES); refusals stay failed for operator review.

Usage:
    pip install -r workers/publishing/requirements.txt
    python main.py [--once] [--api http://localhost:8000]
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


_API_TOKEN = os.environ.get("MTK_API_TOKEN", "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "workers", "publishing"))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from object_storage import materialize  # noqa: E402

from platforms import (  # noqa: E402
    FacebookAdapter,
    InstagramAdapter,
    NotConfiguredError,
    OAuthConfig,
    TikTokAdapter,
    TikTokConfig,
    TokenExpiredError,
    YouTubeAdapter,
)

API_URL_DEFAULT = "http://localhost:8000"
SWEEP_INTERVAL_S = 60

# §17: scheduling/publishing is only allowed from these offer states; the
# worker rechecks the LIVE state immediately before every upload.
PUBLISHABLE_OFFER_STATES = ("verified", "approved_for_video", "published")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("publishing")


class Publisher:
    def __init__(self, api_url: str = API_URL_DEFAULT):
        self.api = httpx.Client(timeout=60, base_url=api_url.rstrip("/"), headers=_api_auth_headers())

    # ------------------------------------------------------------ adapters

    def build_adapters(self) -> dict[str, object]:
        """Instantiate adapters from credential REFERENCES in platform_accounts
        (credential_source like 'env:YOUTUBE_*'). Raw tokens never come from DB."""
        adapters: dict[str, object] = {}

        try:
            accounts = self.api.get("/platform-accounts").json()
        except httpx.HTTPError as exc:
            log.error("cannot list platform accounts: %s", exc)
            return adapters

        for account in accounts:
            platform = account["platform"]
            if platform == "youtube":
                oauth = OAuthConfig.from_env()
                if oauth:
                    adapters[platform] = YouTubeAdapter(
                        oauth=oauth, account_id=account["id"],
                        on_refresh=self._make_refresh_hook(account["id"]),
                    )
                else:
                    log.warning("YouTube account registered but YOUTUBE_* env missing")
            elif platform == "facebook":
                page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
                token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
                if page_id and token:
                    adapters[platform] = FacebookAdapter(
                        page_id=page_id, page_access_token=token,
                        account_id=account["id"],
                    )
                else:
                    log.warning("Facebook account registered but FACEBOOK_* env missing")
            elif platform == "instagram":
                user_id = os.environ.get("INSTAGRAM_USER_ID", "")
                token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
                if user_id and token:
                    adapters[platform] = InstagramAdapter(
                        user_id=user_id, access_token=token,
                        account_id=account["id"],
                    )
                else:
                    log.warning("Instagram account registered but INSTAGRAM_* env missing "
                                "(requires a professional account bound to a Page)")
            elif platform == "tiktok":
                cfg = TikTokConfig.from_env()
                if cfg:
                    adapters[platform] = TikTokAdapter(
                        config=cfg, account_id=account["id"],
                        on_refresh=self._make_refresh_hook(account["id"]),
                    )
                else:
                    log.warning("TikTok account registered but TIKTOK_* env missing "
                                "(requires an approved developer app)")
        return adapters

    def _make_refresh_hook(self, account_id: str):
        def hook(expires_at) -> None:
            try:
                self.api.post(
                    f"/platform-accounts/{account_id}/refreshed",
                    json={"expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)},
                )
                log.info("account %s token refreshed (expiry reported, token kept in memory)", account_id)
            except httpx.HTTPError as exc:
                log.warning("could not report refresh for account %s: %s", account_id, exc)
        return hook

    # ---------------------------------------------------------------- sweep

    def run_once(self) -> int:
        now = datetime.now(timezone.utc)
        adapters = self.build_adapters()

        posts = self.api.get("/schedules", params={"state": "scheduled", "limit": 200}).json()
        due = [p for p in posts if _is_due(p.get("local_time"), now)]
        if due:
            log.info("%d scheduled post(s) due", len(due))

        published = 0
        for post in due:
            if _STOP:
                log.info("stop requested — %d scheduled post(s) left for the next run",
                         len(due) - published)
                break
            try:
                self._publish(post, adapters)
                published += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("publish failed for schedule %s", post["id"])
                self._report(post["id"], ok=False, detail=f"unexpected: {exc}")

        self.retry_failed(now)
        self.apply_corrections(adapters)
        return published

    # ------------------------------------------ §11 description patch (v0.18)

    def apply_corrections(self, adapters: dict) -> int:
        """§11 close-out: when an offer is corrected AFTER publishing, push a
        correction notice into the already-published YouTube description
        (platform write-back; other platforms' description-update APIs are
        not available to us — documented gap). Idempotent: the API marks each
        schedule description_patched_at, and the sweep skips marked posts.
        """
        try:
            posts = self.api.get("/schedules", params={"state": "published", "limit": 500}).json()
        except httpx.HTTPError as exc:
            log.warning("correction sweep skipped (API unreachable): %s", exc)
            return 0

        adapter = adapters.get("youtube")
        if adapter is None:
            return 0

        patched = 0
        for post in posts:
            if post.get("platform") != "youtube" or not post.get("remote_post_id"):
                continue
            if post.get("description_patched_at"):
                continue
            try:
                offer = self.api.get(f"/offers/{post['offer_id']}").json()
                note = (offer.get("correction_note") or "").strip()
                if offer.get("state") != "corrected" or not note:
                    continue
                notice = (f"⚠ CORRECTION ({datetime.now(timezone.utc).date().isoformat()}): "
                          f"{note}")
                adapter.apply_correction_notice(post["remote_post_id"], notice)
            except TokenExpiredError as exc:
                log.warning("schedule %s: correction patch stopped — dead YouTube session (%s)",
                            post["id"], exc)
                break  # every other attempt will fail the same way this sweep
            except (httpx.HTTPError, RuntimeError) as exc:
                log.warning("schedule %s: correction patch failed: %s", post["id"], exc)
                continue
            resp = self.api.post(f"/schedules/{post['id']}/mark-description-patched",
                                 json={"detail": "correction notice applied to description"})
            if resp.status_code < 300:
                patched += 1
                log.info("schedule %s: correction notice applied to description", post["id"])
        return patched

    # ------------------------------------------------- auto-retry (§17, v0.17)

    MAX_RETRIES = int(os.environ.get("MTK_PUBLISH_MAX_RETRIES", "3"))
    RETRY_BASE_S = int(os.environ.get("MTK_PUBLISH_RETRY_BASE_S", "300"))

    def retry_failed(self, now: datetime | None = None) -> int:
        """§17: "Schedule retries with idempotency keys, backoff…" — failed
        posts requeue automatically with exponential backoff
        (base × 2^retry_count), up to MAX_RETRIES. Terminal conditions stay
        terminal: posts past the cap wait for a human, and a 409 (script
        changed since approval) leaves the post failed for operator review.
        """
        now = now or datetime.now(timezone.utc)
        try:
            failed = self.api.get("/schedules", params={"state": "failed", "limit": 500}).json()
        except httpx.HTTPError as exc:
            log.warning("retry sweep skipped (API unreachable): %s", exc)
            return 0

        requeued = 0
        for post in failed:
            attempts = post.get("retry_count", 0) or 0
            if attempts >= self.MAX_RETRIES:
                log.info("schedule %s: giving up auto-retry after %d attempts — operator review",
                         post["id"], attempts)
                continue
            delay = self.RETRY_BASE_S * (2 ** attempts)
            updated = post.get("updated_at")
            if updated:
                tried = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                if tried.tzinfo is None:
                    tried = tried.replace(tzinfo=timezone.utc)
                if now - tried < timedelta(seconds=delay):
                    continue
            try:
                resp = self.api.post(
                    f"/schedules/{post['id']}/transition",
                    json={"to": "scheduled",
                          "note": f"auto-retry {attempts + 1}/{self.MAX_RETRIES} "
                                  f"(backoff {delay}s)"},
                )
                if resp.status_code == 200:
                    requeued += 1
                    log.info("schedule %s: auto-retry %d/%d requeued",
                             post["id"], attempts + 1, self.MAX_RETRIES)
                else:
                    # 409 = script hash changed / illegal transition → human review
                    log.warning("schedule %s: auto-retry refused (%s) — operator review",
                                post["id"], resp.status_code)
            except httpx.HTTPError as exc:
                log.warning("schedule %s: auto-retry transition failed: %s", post["id"], exc)
        return requeued

    def _publish(self, post: dict, adapters: dict) -> None:
        platform = post["platform"]
        adapter = adapters.get(platform)
        if adapter is None:
            self._report(post["id"], ok=False,
                         detail=f"platform '{platform}' not configured (register env credentials)")
            return

        render = self._latest_render(post["offer_id"])
        if render is None:
            self._report(post["id"], ok=False, detail="no render available for this offer")
            return

        # §17: recheck offer validity again immediately before publish. The DB
        # trigger pauses scheduled posts when an offer expires/changes; this is
        # the second, moment-of-upload defense.
        try:
            offer = self.api.get(f"/offers/{post['offer_id']}").json()
            if offer.get("state") not in PUBLISHABLE_OFFER_STATES:
                self.api.post(f"/schedules/{post['id']}/pause")
                self._report(post["id"], ok=False,
                             detail=f"offer state '{offer.get('state')}' — publish blocked (§17 recheck)")
                return
            # v0.16 defense-in-depth (§11: "if a deal expires or changes, pause
            # queued posts automatically"): the sweep-stale monitor flips offer
            # states on its cadence; these direct timestamp checks close the
            # window between sweeps. Pausing (not failing) keeps the post
            # recoverable the moment the offer is re-verified.
            now = datetime.now(timezone.utc)
            for field, label in (("expires_at", "offer expired"),
                                 ("recheck_at", "offer recheck overdue")):
                due = offer.get(field)
                if not due:
                    continue
                due_dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                if due_dt <= now:
                    self.api.post(f"/schedules/{post['id']}/pause")
                    self._report(post["id"], ok=False,
                                 detail=f"{label} ({field}={due}) — publish blocked, auto-paused (§11 recheck)")
                    return
        except httpx.HTTPError as exc:
            self._report(post["id"], ok=False, detail=f"cannot verify offer state: {exc}")
            return

        # §17 Approved rule: "A reviewer approved this exact version hash."
        # The uploaded render must have been produced from the exact script the
        # approval pins — a script edit after scheduling requires re-approval
        # AND a re-render. FAIL-CLOSED: renders without a bound hash (pre-v0.16
        # rows) cannot be published blind; re-render to bind the approval hash.
        rendered_hash = render.get("script_version_hash")
        approved_hash = post.get("version_hash")
        if not rendered_hash or rendered_hash != approved_hash:
            self.api.post(f"/schedules/{post['id']}/pause")
            self._report(post["id"], ok=False,
                         detail="approval integrity: render script hash does not match the "
                                "approved version hash (script changed after approval or "
                                "legacy render) — re-render, re-approve, re-schedule (§17)")
            return

        video_path = render["video_path"]
        # v0.15: managed refs (s3://, local://) are materialized to a local
        # cache before upload; legacy plain paths resolve against the CWD
        # (single-host flow). A ref that can't be produced here fails the post
        # with an actionable message instead of a bare "not found".
        video_file = materialize(video_path, Path(os.environ.get("MTK_STORAGE_CACHE", "./.storage-cache")))
        if video_file is None:
            self._report(post["id"], ok=False,
                         detail=f"render file not available on this host: {video_path} "
                                "(set MTK_STORAGE_BACKEND or run on the render host)")
            return

        meta = post.get("metadata")
        meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
        meta.setdefault("title", f"{post.get('offer_title', 'MTK RADAR AI')}")
        if platform == "instagram":
            # Instagram's Graph API fetches the media itself — it needs a
            # PUBLIC https URL, not a file on this host (§6).
            public_url = public_media_url(video_path)
            if public_url:
                meta["public_url"] = public_url

        try:
            remote_id = adapter.upload(
                video_file,
                meta,
                privacy=post.get("privacy", "private"),
                idempotency_key=post.get("idempotency_key") or post["id"],
            )
        except TokenExpiredError as exc:
            log.error("ALERT token expiry on %s: %s — account marked expired, post paused",
                      platform, exc)
            account_id = getattr(adapter, "account_id", None)
            if account_id:
                self.api.post(f"/platform-accounts/{account_id}/mark-expired",
                              json={"detail": str(exc)})
            self.api.post(f"/schedules/{post['id']}/pause")
            return
        except NotConfiguredError as exc:
            self._report(post["id"], ok=False, detail=str(exc))
            return

        self._report(post["id"], ok=True, remote_post_id=remote_id,
                     detail=f"uploaded to {platform} ({post.get('privacy', 'private')})")
        log.info("published %s → %s (%s)", post["id"], platform, remote_id)

    def _latest_render(self, offer_id: str) -> dict | None:
        try:
            renders = self.api.get("/renders", params={"offer_id": offer_id}).json()
            return renders[0] if renders else None
        except httpx.HTTPError:
            return None

    def _report(self, schedule_id: str, *, ok: bool, detail: str | None = None,
                remote_post_id: str | None = None) -> None:
        try:
            self.api.post(
                f"/schedules/{schedule_id}/result",
                json={"ok": ok, "remote_post_id": remote_post_id, "detail": detail},
            )
        except httpx.HTTPError as exc:
            log.error("failed to report result for %s: %s", schedule_id, exc)

    # ------------------------------------------------------------ main loop

    def run_forever(self, interval_s: int = SWEEP_INTERVAL_S) -> None:
        log.info("publishing worker started against %s", self.api.base_url)
        _install_stop_handlers()
        while not _STOP:
            try:
                self.run_once()
                if _STOP:
                    break
                time.sleep(interval_s)
            except httpx.HTTPError as exc:
                log.error("API unreachable, retrying in %ss: %s", interval_s, exc)
                time.sleep(interval_s)


def _is_due(local_time: str | None, now: datetime) -> bool:
    if not local_time:
        return False
    try:
        when = datetime.fromisoformat(local_time.replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= now


def _account_hint(adapters: dict, platform: str) -> str | None:
    adapter = adapters.get(platform)
    return getattr(adapter, "account_id", None)


def public_media_url(ref: str) -> str | None:
    """Public https URL for a managed media ref (Instagram/TikTok need the
    platform to FETCH the file, not receive an upload). MTK_PUBLIC_MEDIA_BASE_URL
    points at the public origin of the object store (CDN / public bucket /
    reverse proxy). None when unset — the adapter then states the requirement.
    """
    base = os.environ.get("MTK_PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
    if not base or not ref:
        return None
    for scheme in ("s3://", "local://"):
        if ref.startswith(scheme):
            key = ref[len(scheme):].lstrip("/")
            return f"{base}/{key}" if key else None
    return None


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
    parser = argparse.ArgumentParser(description="MTK RADAR publishing worker")
    parser.add_argument("--once", action="store_true", help="run one sweep and exit")
    parser.add_argument("--api", default=API_URL_DEFAULT)
    args = parser.parse_args()

    publisher = Publisher(args.api)
    if args.once:
        count = publisher.run_once()
        log.info("sweep complete: %d published", count)
        return
    publisher.run_forever()


if __name__ == "__main__":
    main()
