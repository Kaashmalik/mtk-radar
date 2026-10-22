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
import hashlib
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
    TransportUnauthorized,
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
        self.policy: dict | None = None

    # -------------------------------------------------------------- policy

    def _load_policy(self) -> dict | None:
        """Read the operator's automation policy. None (old/unreachable API)
        keeps the legacy behaviour — publishing already-approved posts."""
        try:
            resp = self.api.get("/automation/policy")
            if resp.status_code >= 300:
                return None
            return (resp.json() or {}).get("policy")
        except Exception as exc:  # noqa: BLE001
            log.warning("automation policy unavailable, using legacy behaviour: %s", exc)
            return None

    def _limits(self) -> dict:
        return (self.policy or {}).get("guardrails") or {}

    # ------------------------------------------------------------ adapters

    def build_adapters(self) -> dict[str, object]:
        """Instantiate adapters per platform ACCOUNT, not per platform.

        `credential_source` is a reference like `env:YOUTUBE_MAIN_`. A schedule
        pins `platform_account_id`, so two YouTube channels can coexist without
        one silently uploading to the other. A platform-level key remains as a
        fallback for legacy schedules.
        """
        adapters: dict[str, object] = {}

        try:
            accounts = self.api.get("/platform-accounts").json()
        except httpx.HTTPError as exc:
            log.error("cannot list platform accounts: %s", exc)
            return adapters
        if not isinstance(accounts, list):
            log.error("platform account lookup returned an unexpected payload — no adapters")
            return adapters

        for account in accounts:
            if account.get("status") not in (None, "active"):
                continue
            platform = account.get("platform")
            adapter = self._adapter_for_account(account)
            if adapter is None:
                continue
            account_id = str(account.get("id"))
            adapters[f"{platform}:{account_id}"] = adapter
            adapters.setdefault(platform, adapter)
        return adapters

    def _adapter_for_account(self, account: dict):
        source = str(account.get("credential_source") or "")
        platform = account.get("platform")
        account_id = str(account.get("id"))
        if not source.startswith("env:"):
            log.warning("%s account %s uses unsupported credential source %s",
                        platform, account.get("account_handle"), source)
            return None
        prefix = source.split(":", 1)[1].rstrip("_*") + "_"
        if platform == "youtube":
            oauth = OAuthConfig.from_env(prefix)
            if not oauth:
                log.warning("YouTube account %s: %sCLIENT_ID/SECRET/REFRESH_TOKEN missing",
                            account.get("account_handle"), prefix)
                return None
            return YouTubeAdapter(
                oauth=oauth, account_id=account_id,
                on_refresh=self._make_refresh_hook(account_id),
            )
        if platform == "facebook":
            page_id = os.environ.get(f"{prefix}PAGE_ID", "")
            token = os.environ.get(f"{prefix}PAGE_ACCESS_TOKEN", "")
            if not (page_id and token):
                log.warning("Facebook account %s: %sPAGE_ID/PAGE_ACCESS_TOKEN missing",
                            account.get("account_handle"), prefix)
                return None
            return FacebookAdapter(
                page_id=page_id, page_access_token=token, account_id=account_id)
        if platform == "instagram":
            user_id = os.environ.get(f"{prefix}USER_ID", "")
            token = os.environ.get(f"{prefix}ACCESS_TOKEN", "")
            if not (user_id and token):
                log.warning("Instagram account %s: %sUSER_ID/ACCESS_TOKEN missing",
                            account.get("account_handle"), prefix)
                return None
            return InstagramAdapter(
                user_id=user_id, access_token=token, account_id=account_id)
        if platform == "tiktok":
            cfg = TikTokConfig.from_env(prefix)
            if not cfg:
                log.warning("TikTok account %s: %sCLIENT_KEY/SECRET/REFRESH_TOKEN missing",
                            account.get("account_handle"), prefix)
                return None
            return TikTokAdapter(
                config=cfg, account_id=account_id,
                on_refresh=self._make_refresh_hook(account_id),
            )
        return None

    def _adapter_for(self, post: dict, adapters: dict):
        platform = post.get("platform")
        account_id = post.get("platform_account_id")
        if account_id:
            # A pinned account NEVER falls back to another account: uploading
            # the package to the wrong channel is worse than a held failure.
            return adapters.get(f"{platform}:{account_id}")
        return adapters.get(platform)

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

    def _acquire_sweep_lock(self, name: str, ttl_s: int = 300) -> bool:
        """Claim the sweep lock so a second publisher instance cannot work the
        same queue (v0.22/v0.28). Fails CLOSED: if exclusivity cannot be
        proven, no upload starts — duplicating a public post is worse than a
        delayed sweep."""
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
        now = datetime.now(timezone.utc)
        self.policy = self._load_policy()
        if self.policy and self.policy.get("paused"):
            log.info("automation is PAUSED in Settings — publishing sweep skipped "
                     "(already-approved posts stay queued)")
            return 0
        if not self._acquire_sweep_lock("publishing"):
            return 0
        try:
            return self._sweep(now)
        finally:
            self._release_sweep_lock("publishing")

    def _sweep(self, now: datetime) -> int:
        adapters = self.build_adapters()

        posts = self.api.get("/schedules", params={"state": "scheduled", "limit": 200}).json()
        if not isinstance(posts, list):
            log.error("scheduled-post lookup returned an unexpected payload — sweep skipped")
            return 0
        due = [p for p in posts if _is_due(p.get("local_time"), now)]
        if self.policy and self.policy.get("dry_run"):
            log.info("automation is in DRY-RUN mode — %d due post(s) would publish; "
                     "no upload, retry, or correction was performed", len(due))
            return 0
        if due:
            log.info("%d scheduled post(s) due", len(due))

        published = 0
        for post in due:
            if _STOP:
                log.info("stop requested — %d scheduled post(s) left for the next run",
                         len(due) - published)
                break
            try:
                if self._publish(post, adapters):
                    published += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("publish failed for schedule %s", post["id"])
                # No token here: if the failure happened after the attempt
                # claim, this result is refused and the open marker keeps the
                # post held for a human (safer than a blind retry).
                self._report(post["id"], ok=False,
                             detail=f"unexpected: {exc}", hold=True)

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
        if not isinstance(posts, list):
            log.error("published-post lookup returned an unexpected payload — corrections skipped")
            return 0

        if not any(key == "youtube" or key.startswith("youtube:")
                   for key in adapters):
            return 0

        patched = 0
        for post in posts:
            if post.get("platform") != "youtube" or not post.get("remote_post_id"):
                continue
            if post.get("description_patched_at"):
                continue
            adapter = self._adapter_for(post, adapters)
            if adapter is None:
                log.warning("schedule %s: correction skipped — its YouTube account "
                            "is not configured", post["id"])
                continue
            try:
                offer = self.api.get(f"/offers/{post['offer_id']}").json()
                note = (offer.get("correction_note") or "").strip()
                if offer.get("state") != "corrected" or not note:
                    continue
                notice = (f"⚠ CORRECTION ({datetime.now(timezone.utc).date().isoformat()}): "
                          f"{note}")
                adapter.apply_correction_notice(post["remote_post_id"], notice)
            except (TokenExpiredError, TransportUnauthorized) as exc:
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
        limits = self._limits()
        if limits.get("auto_retry") is False:
            log.info("auto-retry is disabled in Settings — failed posts wait for a human")
            return 0
        max_retries = int(limits.get("retry_max_attempts", self.MAX_RETRIES))
        retry_base = int(limits.get("retry_base_seconds", self.RETRY_BASE_S))
        try:
            failed = self.api.get("/schedules", params={"state": "failed", "limit": 500}).json()
        except httpx.HTTPError as exc:
            log.warning("retry sweep skipped (API unreachable): %s", exc)
            return 0
        if not isinstance(failed, list):
            log.error("failed-post lookup returned an unexpected payload — retry skipped")
            return 0

        requeued = 0
        for post in failed:
            # v0.23: a post on hold needs a human (e.g. an interrupted upload
            # whose outcome is unknown) — auto-retry must not touch it.
            if self._is_held(post):
                log.info("schedule %s: on hold — operator review required, not auto-retried",
                         post["id"])
                continue
            attempts = post.get("retry_count", 0) or 0
            if attempts >= max_retries:
                log.info("schedule %s: giving up auto-retry after %d attempts — operator review",
                         post["id"], attempts)
                continue
            delay = retry_base * (2 ** attempts)
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
                          "note": f"auto-retry {attempts + 1}/{max_retries} "
                                  f"(backoff {delay}s)"},
                )
                if resp.status_code == 200:
                    requeued += 1
                    log.info("schedule %s: auto-retry %d/%d requeued",
                             post["id"], attempts + 1, max_retries)
                else:
                    # 409 = script hash changed / illegal transition → human review
                    log.warning("schedule %s: auto-retry refused (%s) — operator review",
                                post["id"], resp.status_code)
            except httpx.HTTPError as exc:
                log.warning("schedule %s: auto-retry transition failed: %s", post["id"], exc)
        return requeued

    def _publish(self, post: dict, adapters: dict) -> bool:
        platform = post["platform"]
        adapter = self._adapter_for(post, adapters)
        if adapter is None:
            # A pinned account with no credentials must never fall back to a
            # different channel. Hold (do not auto-retry every sweep) until an
            # operator registers the exact account and resumes the post.
            self._report(post["id"], ok=False, hold=True,
                         detail=f"platform account for '{platform}' is not configured "
                                "(register its env credentials, then resume)")
            return False

        # v0.23: an upload attempt that never reported its outcome is
        # UNKNOWN — the post may already be live on the platform. Publishing
        # again would create a duplicate public post, so the post is held for
        # a human to verify (one click on the platform) instead.
        open_attempt = self._open_attempt(post)
        if open_attempt:
            log.warning("schedule %s: an upload attempt from %s has no recorded outcome — "
                        "the post may already be published; holding for operator review",
                        post["id"], open_attempt.get("started_at"))
            self._report(post["id"], ok=False, hold=True,
                         detail="previous upload attempt has no recorded outcome — the post "
                                "may already be live; verify on the platform, then resume with "
                                "the unknown-attempt acknowledgement (or cancel this post) "
                                "(duplicate protection)")
            return False

        render = self._render_for_post(post)
        if render is None:
            self._report(post["id"], ok=False,
                         detail="the pinned render no longer exists — re-render and re-schedule")
            return False

        # §17: recheck offer validity again immediately before publish. The DB
        # trigger pauses scheduled posts when an offer expires/changes; this is
        # the second, moment-of-upload defense.
        try:
            offer = self.api.get(f"/offers/{post['offer_id']}").json()
            if offer.get("state") not in PUBLISHABLE_OFFER_STATES:
                self._block(
                    post["id"],
                    f"offer state '{offer.get('state')}' — publish blocked (§17 recheck)")
                return False
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
                    self._block(
                        post["id"],
                        f"{label} ({field}={due}) — publish blocked, auto-paused (§11 recheck)")
                    return False
        except httpx.HTTPError as exc:
            self._report(post["id"], ok=False, detail=f"cannot verify offer state: {exc}")
            return False

        # §17 Approved rule: "A reviewer approved this exact version hash."
        # The uploaded render must have been produced from the exact script the
        # approval pins — a script edit after scheduling requires re-approval
        # AND a re-render. FAIL-CLOSED: renders without a bound hash (pre-v0.16
        # rows) cannot be published blind; re-render to bind the approval hash.
        rendered_hash = render.get("script_version_hash")
        approved_hash = post.get("version_hash")
        if not rendered_hash or rendered_hash != approved_hash:
            self._block(
                post["id"],
                "approval integrity: render script hash does not match the "
                "approved version hash (script changed after approval or "
                "legacy render) — re-render, re-approve, re-schedule (§17)")
            return False

        # v0.28 immutable package: the scheduler pinned this exact render,
        # metadata and asset digests. Never re-select the "latest" render at
        # upload time — that is how an unreviewed edit reaches the channel.
        if not post.get("render_id") or not post.get("render_sha256") \
                or not post.get("metadata_hash") or not post.get("package_hash"):
            self._block(
                post["id"],
                "legacy schedule has no immutable package pins — "
                "re-render, re-approve and re-schedule before publishing")
            return False
        if str(render.get("id")) != str(post.get("render_id")):
            self._block(
                post["id"],
                "render pin mismatch — the pinned render is not the offer's "
                "current render; re-schedule the reviewed package")
            return False

        meta = post.get("metadata")
        meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
        if _canonical_hash(meta) != post["metadata_hash"]:
            self._block(
                post["id"],
                "metadata changed after scheduling — re-approve the exact "
                "metadata hash before publishing")
            return False
        if not _package_matches(post):
            self._block(
                post["id"],
                "publish package hash does not match its pinned fields — "
                "re-schedule to restore a reviewable package")
            return False
        # Never fill in missing copy after the hash check: the upload must be
        # exactly the package a reviewer approved. An empty caption/title is a
        # broken package, not an invitation to invent one.
        if not str(meta.get("caption") or "").strip():
            self._block(post["id"],
                        "approved metadata has no caption — re-approve the package")
            return False
        if platform in ("youtube", "facebook") \
                and not str(meta.get("title") or "").strip():
            self._block(post["id"],
                        "approved metadata has no title — re-approve the package")
            return False

        # A previous attempt may have uploaded successfully but failed before
        # confirmation. Never upload again: re-confirm the existing remote id.
        existing_remote = post.get("remote_post_id")
        if existing_remote:
            prior = post.get("remote_metadata")
            prior = json.loads(prior) if isinstance(prior, str) else (prior or {})
            if not isinstance(prior, dict):
                prior = {}
            if hasattr(adapter, "confirm_publication"):
                timeout_s = int(os.environ.get("MTK_YOUTUBE_CONFIRM_TIMEOUT_S", "300"))
                confirmation = adapter.confirm_publication(
                    existing_remote,
                    expected_privacy=post.get("privacy", "private"),
                    timeout_s=timeout_s,
                    interval_s=float(os.environ.get("MTK_YOUTUBE_CONFIRM_INTERVAL_S", "5")),
                )
                remote_metadata = {**prior, "confirmation": confirmation,
                                   "reconfirmed": True}
                if confirmation and confirmation.get("confirmed"):
                    self._report(
                        post["id"], ok=True, remote_post_id=existing_remote,
                        confirmed=True,
                        detail=f"confirmed existing {platform} upload",
                        remote_url=confirmation.get("remote_url"),
                        remote_processing_state=confirmation.get("processing_state")
                        or confirmation.get("upload_status"),
                        remote_privacy=confirmation.get("privacy"),
                        remote_metadata=remote_metadata,
                    )
                    log.info("confirmed existing %s upload %s (no duplicate)",
                             platform, existing_remote)
                    return True
                reason = (confirmation or {}).get("error") \
                    or "remote processing/visibility still unconfirmed"
                self._report(
                    post["id"], ok=False, hold=True, remote_post_id=existing_remote,
                    detail=f"existing upload is still unconfirmed: {reason}",
                    remote_url=(confirmation or {}).get("remote_url"),
                    remote_processing_state=(confirmation or {}).get("processing_state")
                    or (confirmation or {}).get("processing_status"),
                    remote_privacy=(confirmation or {}).get("privacy"),
                    remote_metadata=remote_metadata,
                )
                log.warning("schedule %s: existing %s upload %s still unconfirmed — held",
                            post["id"], platform, existing_remote)
                return False
            # No confirmation API on this platform: a remote id means a post
            # may already exist. Do not risk a duplicate; ask a human to check.
            self._report(
                post["id"], ok=False, hold=True, remote_post_id=existing_remote,
                detail=f"a remote {platform} post already exists ({existing_remote}) — "
                       "verify it on the platform; the worker will not upload again",
                remote_url=post.get("remote_url"),
                remote_processing_state=post.get("remote_processing_state"),
                remote_privacy=post.get("remote_privacy"),
                remote_metadata=prior,
            )
            return False

        cache = Path(os.environ.get("MTK_STORAGE_CACHE", "./.storage-cache"))
        video_path = render["video_path"]
        # v0.15: managed refs (s3://, local://) are materialized to a local
        # cache before upload; legacy plain paths resolve against the CWD
        # (single-host flow). A ref that can't be produced here fails the post
        # with an actionable message instead of a bare "not found".
        video_file = materialize(video_path, cache)
        if video_file is None:
            self._report(post["id"], ok=False,
                         detail=f"render file not available on this host: {video_path} "
                                "(set MTK_STORAGE_BACKEND or run on the render host)")
            return False
        actual_video_hash = _sha256_file(video_file)
        if actual_video_hash != post["render_sha256"]:
            self._block(
                post["id"],
                "render bytes no longer match the pinned sha256 — the file "
                "changed after review; re-render and re-schedule")
            return False

        cover_path = post.get("cover_path") or render.get("cover_path")
        cover_file = self._materialize_checked(
            cover_path, post.get("cover_sha256"), cache / "covers", post, "cover")
        captions_path = render.get("captions_path")
        captions_file = self._materialize_checked(
            captions_path, post.get("captions_sha256"), cache / "captions", post, "captions")
        if cover_file is False or captions_file is False:
            return False

        if platform == "instagram":
            # Instagram's Graph API fetches the media itself — it needs a
            # PUBLIC https URL, not a file on this host (§6).
            public_url = public_media_url(video_path)
            if public_url:
                meta["public_url"] = public_url

        attempt_token = self._announce_attempt(post["id"])
        if not attempt_token:
            # No claim = no upload. A lost response may have created a marker;
            # the next sweep will see it and hold rather than duplicate.
            log.error("schedule %s: could not claim an upload attempt — not uploading",
                      post["id"])
            return False

        remote_id: str | None = None
        try:
            remote_id = str(adapter.upload(
                video_file,
                meta,
                privacy=post.get("privacy", "private"),
                idempotency_key=post.get("idempotency_key") or post["id"],
            ))
            package: dict = {}
            if hasattr(adapter, "finalize_package"):
                package = adapter.finalize_package(
                    remote_id,
                    meta,
                    thumbnail_path=cover_file or None,
                    captions_path=captions_file or None,
                    playlist_id=post.get("youtube_playlist_id"),
                    pinned_comment=post.get("pinned_comment"),
                    captions_language=(meta.get("captions_language")
                                       or post.get("language") or "en"),
                )

            # Remote confirmation is mandatory for adapters that expose it
            # (YouTube). "Uploaded" is not "published": processing + privacy
            # must be verified. A timeout is a HELD failure, not success.
            if hasattr(adapter, "confirm_publication"):
                timeout_s = int(os.environ.get("MTK_YOUTUBE_CONFIRM_TIMEOUT_S", "300"))
                confirmation = adapter.confirm_publication(
                    remote_id,
                    expected_privacy=post.get("privacy", "private"),
                    timeout_s=timeout_s,
                    interval_s=float(os.environ.get("MTK_YOUTUBE_CONFIRM_INTERVAL_S", "5")),
                )
            else:
                confirmation = {
                    "confirmed": True,
                    "processing_state": "accepted",
                    "privacy": post.get("privacy", "private"),
                    "remote_url": public_media_url(video_path),
                }

            remote_metadata = {**package, "confirmation": confirmation}
            if not confirmation or not confirmation.get("confirmed"):
                reason = (confirmation or {}).get("error") or "remote processing/visibility unconfirmed"
                self._report(
                    post["id"], ok=False, hold=True, remote_post_id=remote_id,
                    attempt_token=attempt_token,
                    detail=f"uploaded but not confirmed: {reason}",
                    remote_url=(confirmation or {}).get("remote_url"),
                    remote_processing_state=(confirmation or {}).get("processing_state")
                    or (confirmation or {}).get("processing_status"),
                    remote_privacy=(confirmation or {}).get("privacy"),
                    remote_metadata=remote_metadata,
                )
                log.warning("schedule %s: uploaded to %s as %s but NOT confirmed — held",
                            post["id"], platform, remote_id)
                return False

            self._report(
                post["id"], ok=True, remote_post_id=remote_id,
                attempt_token=attempt_token, confirmed=True,
                detail=f"confirmed on {platform} ({post.get('privacy', 'private')})",
                remote_url=confirmation.get("remote_url"),
                remote_processing_state=confirmation.get("processing_state")
                or confirmation.get("upload_status"),
                remote_privacy=confirmation.get("privacy"),
                remote_metadata=remote_metadata,
            )
            log.info("published %s → %s (%s)", post["id"], platform, remote_id)
            return True
        except TokenExpiredError as exc:
            log.error("ALERT token expiry on %s: %s — account marked expired, post paused",
                      platform, exc)
            account_id = getattr(adapter, "account_id", None) or post.get("platform_account_id")
            if account_id:
                self.api.post(f"/platform-accounts/{account_id}/mark-expired",
                              json={"detail": str(exc)})
            self._report(post["id"], ok=False, hold=True, remote_post_id=remote_id,
                         attempt_token=attempt_token,
                         detail=f"token expired during upload: {exc}")
            self.api.post(f"/schedules/{post['id']}/pause")
            return False
        except NotConfiguredError as exc:
            self._report(post["id"], ok=False, hold=True, attempt_token=attempt_token,
                         detail=str(exc))
            return False
        except Exception as exc:  # noqa: BLE001
            # The upload/confirmation may have reached the platform. Hold for
            # a human instead of risking a duplicate auto-retry.
            self._report(post["id"], ok=False, hold=True, remote_post_id=remote_id,
                         attempt_token=attempt_token,
                         detail=f"upload/confirmation failed: {exc}")
            log.exception("schedule %s: upload/confirmation failed", post["id"])
            return False

    def _render_for_post(self, post: dict) -> dict | None:
        render_id = post.get("render_id")
        if not render_id:
            return None
        try:
            renders = self.api.get("/renders",
                                   params={"offer_id": post["offer_id"]}).json()
        except httpx.HTTPError:
            return None
        for render in renders or []:
            if str(render.get("id")) == str(render_id):
                return render
        return None

    def _materialize_checked(self, ref: str | None, expected_sha: str | None,
                             cache: Path, post: dict, label: str):
        """Materialize a pinned asset and verify its digest.

        Returns the local Path, None when there is no asset, or False when a
        pinned asset is missing/mismatched (after reporting a held failure).
        """
        if not ref:
            if expected_sha:
                self._report(post["id"], ok=False, hold=True,
                             detail=f"pinned {label} sha256 exists but the schedule has no path")
                return False
            return None
        local = materialize(ref, cache)
        if local is None:
            if expected_sha:
                self._report(post["id"], ok=False, hold=True,
                             detail=f"pinned {label} is not available on this host: {ref}")
                return False
            return None
        if expected_sha and _sha256_file(local) != expected_sha:
            self._report(post["id"], ok=False, hold=True,
                         detail=f"{label} bytes do not match the pinned sha256 — re-schedule "
                                "the reviewed package")
            return False
        return local

    @staticmethod
    def _is_held(post: dict) -> bool:
        """True when a human must review this post before it goes out (v0.23)."""
        detail = post.get("outcome_detail")
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except (TypeError, ValueError):
                return False
        if not isinstance(detail, dict):
            return False
        return bool(detail.get("hold"))

    @staticmethod
    def _open_attempt(post: dict) -> dict | None:
        """The open attempt marker of a schedule, if any (v0.23)."""
        detail = post.get("outcome_detail")
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except (TypeError, ValueError):
                return None
        if not isinstance(detail, dict):
            return None
        attempt = detail.get("attempt")
        return attempt if isinstance(attempt, dict) else None

    def _announce_attempt(self, schedule_id: str) -> str | None:
        """Atomically claim an upload before it starts (v0.23/v0.28).

        Returns the attempt token, or None when the claim was refused. No token
        means no upload: a second worker may already be uploading, or the API
        cannot prove exclusivity. A lost response is also fail-closed — the
        next sweep sees any marker and holds for a human.
        """
        try:
            res = self.api.post(f"/schedules/{schedule_id}/attempt",
                                json={"detail": "upload started",
                                      "worker": "publishing-worker",
                                      "lease_s": 900})
        except httpx.HTTPError as exc:
            log.error("could not claim upload attempt for %s: %s", schedule_id, exc)
            return None
        if getattr(res, "status_code", 200) >= 300:
            log.error("upload attempt refused for %s (%s): %s", schedule_id,
                      getattr(res, "status_code", "?"), getattr(res, "text", "")[:300])
            return None
        token = (res.json() or {}).get("attempt_token")
        if not token:
            log.error("upload attempt for %s returned no token — refusing to upload",
                      schedule_id)
            return None
        return str(token)

    def _block(self, schedule_id: str, detail: str) -> None:
        """Record a held failure FIRST, then pause.

        The result endpoint only accepts scheduled/failed/paused posts; pausing
        before reporting previously lost the operator-visible reason. Holding
        the failure also prevents an auto-retry if the pause call itself fails.
        """
        self._report(schedule_id, ok=False, detail=detail, hold=True)
        try:
            self.api.post(f"/schedules/{schedule_id}/pause")
        except httpx.HTTPError as exc:
            log.error("could not pause blocked schedule %s: %s", schedule_id, exc)

    def _report(self, schedule_id: str, *, ok: bool, detail: str | None = None,
                remote_post_id: str | None = None, hold: bool = False,
                attempt_token: str | None = None, confirmed: bool = False,
                remote_url: str | None = None,
                remote_processing_state: str | None = None,
                remote_privacy: str | None = None,
                remote_metadata: dict | None = None) -> None:
        try:
            res = self.api.post(
                f"/schedules/{schedule_id}/result",
                json={"ok": ok, "remote_post_id": remote_post_id, "detail": detail,
                      "hold": hold, "attempt_token": attempt_token,
                      "confirmed": confirmed, "remote_url": remote_url,
                      "remote_processing_state": remote_processing_state,
                      "remote_privacy": remote_privacy,
                      "remote_metadata": remote_metadata or {}},
            )
            if getattr(res, "status_code", 200) >= 300:
                log.error("result for %s refused (%s): %s", schedule_id,
                          getattr(res, "status_code", "?"), getattr(res, "text", "")[:300])
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


def _canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_matches(post: dict) -> bool:
    """Recompute the scheduler's package pin from the fetched row."""
    account_id = post.get("platform_account_id")
    expected = _canonical_hash({
        "offer_id": str(post.get("offer_id")),
        "platform": post.get("platform"),
        "account_id": str(account_id) if account_id else None,
        "render_id": str(post.get("render_id")),
        "render_sha256": post.get("render_sha256"),
        "metadata_hash": post.get("metadata_hash"),
        "cover_sha256": post.get("cover_sha256"),
        "captions_sha256": post.get("captions_sha256"),
        "script_version_hash": post.get("version_hash"),
        "language": post.get("language"),
        "privacy": post.get("privacy"),
        "caption_variant": post.get("caption_variant"),
        "metadata_variant": post.get("metadata_variant"),
        "pinned_comment": post.get("pinned_comment"),
        "youtube_playlist_id": post.get("youtube_playlist_id"),
    })
    return bool(post.get("package_hash")) and expected == post.get("package_hash")


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
