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


_API_TOKEN = (os.environ.get("MTK_WORKER_TOKEN")
              or os.environ.get("MTK_API_TOKEN") or "").strip()

def _api_auth_headers() -> dict:
    """Authorization headers for the API when MTK_API_TOKEN is configured
    (services/api/api_hardening.py). Empty dict = open local dev API."""
    return {"Authorization": f"Bearer {_API_TOKEN}"} if _API_TOKEN else {}
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "workers", "publishing"))
sys.path.insert(0, os.path.join(REPO_ROOT, "packages"))

from api_paging import fetch_all  # noqa: E402
from object_storage import materialize  # noqa: E402
from upload_sessions import APIUploadSessionStore  # noqa: E402
from worker_heartbeat import WorkerHeartbeat  # noqa: E402

from platforms import (  # noqa: E402
    FacebookAdapter,
    InstagramAdapter,
    NotConfiguredError,
    OAuthConfig,
    RateLimited,
    TikTokAdapter,
    TikTokConfig,
    TokenExpiredError,
    TransportUnauthorized,
    YouTubeAdapter,
)

def _facebook_exchange(token: str, app_id: str, secret: str) -> dict:
    """Long-lived Page token exchange (WP-G §5.6.1) — thin module bridge."""
    from platforms.facebook import exchange_long_lived_token
    return exchange_long_lived_token(token, app_id, secret)


def _instagram_exchange(token: str, app_id: str, secret: str) -> dict:
    """Long-lived Instagram token exchange (WP-G §5.6.1) — same Graph grant.
    The IG professional account inherits the Page's FB token mechanics."""
    from platforms.base import exchange_long_lived_token
    from platforms.instagram import GRAPH_ENDPOINT
    return exchange_long_lived_token(GRAPH_ENDPOINT, token, app_id, secret)


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

    def _automation_allowed(self) -> bool:
        """Re-read the kill switch before each irreversible operation.

        A pause must stop an in-progress sweep, not only the next one. A
        missing policy (old/unreachable API) keeps the legacy behaviour; the
        upload itself will fail closed if the API is actually down.
        """
        policy = self._load_policy()
        if policy is None:
            return True
        self.policy = policy
        if policy.get("paused") or policy.get("dry_run"):
            log.info("automation was paused/dry-run mid-sweep — stopping before the "
                     "next irreversible operation")
            return False
        return True

    def _release_gate_ok(self, schedule_id: str) -> bool:
        """The API owns the release decision (§17). Unreachable gate = no upload.

        Unlike the local pre-filters, this must NOT degrade to legacy behaviour:
        a blocked gate is exactly the moment the operator needs to know."""
        try:
            resp = self.api.get(f"/schedules/{schedule_id}/release-check")
            status = getattr(resp, "status_code", 500)
            if status >= 300:
                self._block(schedule_id, f"release gate unreachable (HTTP {status})")
                return False
            body = resp.json()
            problems = body.get("problems") or []
            if body.get("ok") is not True:
                detail = "; ".join(
                    f"{p.get('code')}: {p.get('detail')}" for p in problems
                ) or "release gate returned not-ok without details"
                self._block(schedule_id, f"release gate: {detail}")
                return False
            return True
        except Exception as exc:  # noqa: BLE001 — gate errors must stop the upload
            self._block(schedule_id, f"release gate unavailable ({exc}) — "
                                     "upload blocked (fail closed)")
            return False

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

    def _acquire_sweep_lock(self, name: str, ttl_s: int = 3600) -> bool:
        """Claim the sweep lock so a second publisher instance cannot work the
        same queue (v0.22/v0.28). Fails CLOSED: if exclusivity cannot be
        proven, no upload starts — duplicating a public post is worse than a
        delayed sweep.

        The TTL must cover the WORST sweep (job drain + due posts + up to
        600s YouTube uploads each); a sweep that outlives its lock would let a
        second publisher join mid-flight. Use `_renew_sweep_lock` between
        items; a lost renewal aborts the sweep fail-closed.
        """
        if not getattr(self, "_sweep_holder", None):
            self._sweep_holder = f"{name}-worker-{os.getpid()}"
        try:
            res = self.api.post("/locks/acquire",
                                 json={"name": name, "holder": self._sweep_holder,
                                       "ttl_s": ttl_s})
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

    def _renew_sweep_lock(self, name: str) -> bool:
        """Re-assert exclusivity mid-sweep; False means the lock was lost."""
        try:
            res = self.api.post("/locks/acquire",
                                 json={"name": name, "holder": self._sweep_holder,
                                       "ttl_s": 3600})
        except Exception as exc:  # noqa: BLE001 — cannot prove exclusivity
            log.warning("sweep lock renewal failed (%s) — aborting this sweep", exc)
            return False
        if res.status_code >= 300 or not bool(res.json().get("acquired", False)):
            log.warning("sweep lock lost — aborting this sweep")
            return False
        return True

    def _release_sweep_lock(self, name: str) -> None:
        try:
            # Always name the holder: releasing by name alone would free
            # another worker's lock after our own had expired.
            self.api.post("/locks/release",
                          json={"name": name, "holder": self._sweep_holder})
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
            drained = self._drain_publish_jobs(now)
            self.token_maintenance(now)
            return drained + self._sweep(now)
        finally:
            self._release_sweep_lock("publishing")

    # ------------------------------------------- token lifecycle (WP-G §5.6.1)

    #: Meta long-lived tokens last ~60 days; renew well before the cliff so a
    #: two-week outage never leaves a dead token nobody noticed.
    TOKEN_REFRESH_CADENCE_D = int(os.environ.get("MTK_TOKEN_REFRESH_CADENCE_D", "45"))
    TOKEN_REFRESH_MARGIN_D = int(os.environ.get("MTK_TOKEN_REFRESH_MARGIN_D", "14"))
    #: At most one maintenance attempt per account per day (a refusal must
    #: not become a per-sweep hammering loop against the OAuth endpoint).
    TOKEN_RETRY_AFTER_FAIL_S = 86400

    def token_maintenance(self, now: datetime) -> int:
        """Renew Facebook/Instagram long-lived tokens on a ~45-day cadence.

        Meta's `fb_exchange_token` grant extends the token WITHOUT re-auth
        while the app id/secret are configured (TikTok/YouTube refresh
        themselves in-flight already). On success the new expiry goes to
        /platform-accounts/{id}/refreshed; on refusal the account is marked
        expired — which surfaces in Needs-You — never a silent stall.
        """
        self._token_next_try: dict[str, float] = getattr(self, "_token_next_try", {})
        try:
            accounts = self.api.get("/platform-accounts").json()
        except (httpx.HTTPError, ValueError) as exc:
            log.debug("token maintenance skipped (accounts unreachable): %s", exc)
            return 0
        if not isinstance(accounts, list):
            return 0
        refreshed = 0
        for account in accounts:
            if account.get("platform") not in ("facebook", "instagram"):
                continue  # youtube/tiktok refresh in-flight (on_refresh hooks)
            if account.get("status") not in (None, "active"):
                continue
            account_id = str(account.get("id") or "")
            if not account_id:
                continue
            due_at = self._token_next_try.get(account_id, 0)
            if now.timestamp() < due_at:
                continue
            if not self._token_due(account, now):
                continue
            self._token_next_try[account_id] = now.timestamp() + self.TOKEN_RETRY_AFTER_FAIL_S
            if self._refresh_account(account):
                refreshed += 1
        if refreshed:
            log.info("token maintenance: %d long-lived token(s) renewed", refreshed)
        return refreshed

    def _token_due(self, account: dict, now: datetime) -> bool:
        """Inside the refresh window? Missing expiry = due after the cadence
        since the last refresh (or immediately when never refreshed)."""
        margin = timedelta(days=self.TOKEN_REFRESH_MARGIN_D)
        expires_at = account.get("expires_at")
        if expires_at:
            try:
                when = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return now + margin >= when
            except ValueError:
                return True  # unparseable expiry — check rather than trust
        last = account.get("last_refreshed_at") or account.get("created_at")
        if not last:
            return True
        try:
            when = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        except ValueError:
            return True
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return now - when >= timedelta(days=self.TOKEN_REFRESH_CADENCE_D)

    def _refresh_account(self, account: dict) -> bool:
        """Exchange one account's long-lived token; report success/failure."""
        account_id = str(account["id"])
        platform = account.get("platform")
        prefix = str(account.get("credential_source") or "").split(":", 1)[-1].rstrip("_*") + "_"
        if platform == "facebook":
            token = os.environ.get(f"{prefix}PAGE_ACCESS_TOKEN", "")
            app_id = (os.environ.get(f"{prefix}APP_ID")
                      or os.environ.get("FACEBOOK_APP_ID") or "")
            secret = (os.environ.get(f"{prefix}APP_SECRET")
                      or os.environ.get("FACEBOOK_APP_SECRET") or "")
        else:
            token = os.environ.get(f"{prefix}ACCESS_TOKEN", "")
            app_id = (os.environ.get(f"{prefix}APP_ID")
                      or os.environ.get("INSTAGRAM_APP_ID")
                      or os.environ.get("FACEBOOK_APP_ID") or "")
            secret = (os.environ.get(f"{prefix}APP_SECRET")
                      or os.environ.get("INSTAGRAM_APP_SECRET")
                      or os.environ.get("FACEBOOK_APP_SECRET") or "")
        if not (token and app_id and secret):
            log.info("account %s (%s): token maintenance skipped — APP_ID/APP_SECRET "
                     "not configured; the monitor stays the expiry fallback",
                     account_id, platform)
            return False
        try:
            from platforms.base import exchange_long_lived_token
            if platform == "instagram":
                result = _instagram_exchange(token, app_id, secret)
            else:
                result = _facebook_exchange(token, app_id, secret)
        except (TokenExpiredError, httpx.HTTPError) as exc:
            log.error("ALERT: token maintenance refused for %s account %s (%s) — "
                      "account marked expired for operator attention", platform,
                      account_id, exc)
            try:
                self.api.post(f"/platform-accounts/{account_id}/mark-expired",
                              json={"detail": f"token maintenance failed: {exc}"})
            except httpx.HTTPError:
                pass
            return False
        expires_at = result.get("expires_at")
        try:
            self.api.post(
                f"/platform-accounts/{account_id}/refreshed",
                json={"expires_at": expires_at.isoformat()
                      if hasattr(expires_at, "isoformat") else str(expires_at or "")},
            )
        except httpx.HTTPError as exc:
            log.warning("account %s: could not report renewed expiry: %s", account_id, exc)
        log.info("account %s (%s): long-lived token renewed; expires %s",
                 account_id, platform,
                 expires_at.date().isoformat() if hasattr(expires_at, "date") else expires_at)
        return True

    # ------------------------------------ durable jobs queue drain (v0.33)
    # "Owed work" is recorded in the jobs table (028) and enqueued at
    # schedule creation; this drain makes the worker actually CLAIM that
    # work (SKIP LOCKED, lease, result) instead of relying on list polling.
    # Placement inside the sweep lock is deliberate: job drain and classic
    # sweep run sequentially, so one worker can never double-attempt the
    # same post. The classic sweep below REMAINS the authoritative fallback —
    # a queue outage degrades to polling, never to lost posts.
    def _publish_jobs_enabled(self) -> bool:
        return os.environ.get("MTK_PUBLISH_JOB_QUEUE", "1").strip().lower() \
            not in {"0", "false", "no"}

    def _drain_publish_jobs(self, now: datetime) -> int:
        """Claim and run publish_schedule jobs until the queue is dry.

        Fail-open contract: if the queue endpoint is missing (older API)
        or unreachable, the sweep below still drives publishing. Failures
        are Fail-CLOSED at the release gate/attempt layer, so nothing here
        can bypass a safety check.
        """
        if not self._publish_jobs_enabled():
            return 0
        published = 0
        for _ in range(200):  # bounded per sweep; results remove claimed jobs
            if _STOP:
                break
            if self.policy and self.policy.get("dry_run"):
                return published
            try:
                res = self.api.post(
                    "/jobs/claim",
                    json={"worker": "publishing-worker", "lease_s": 900,
                          "kinds": ["publish_schedule"]},
                )
            except httpx.HTTPError as exc:
                log.warning("job queue unreachable (%s) — sweep-only mode", exc)
                return published
            if res.status_code == 404:
                log.info("job queue not available on this API — sweep-only mode")
                return published
            if res.status_code >= 300:
                log.warning("job claim refused (%s) — sweep-only this run",
                            res.status_code)
                return published
            try:
                body = res.json()
            except ValueError:
                log.warning("job claim returned a non-JSON payload — sweep-only mode")
                return published
            if not body.get("claimed"):
                return published
            job_id = body["id"]
            try:
                published += self._run_publish_job(
                    job_id, body.get("entity_id"), now)
            except Exception as exc:  # noqa: BLE001 — a job failure must not kill the sweep
                log.exception("publish job %s failed unexpectedly", job_id)
                self._job_result(job_id, ok=False,
                                 detail=f"unexpected: {exc}", retry_after_s=1800)
        return published

    def _job_result(self, job_id: str, *, ok: bool, detail: str | None = None,
                    retry_after_s: int | None = None) -> None:
        payload: dict = {"ok": ok}
        if detail:
            payload["detail"] = detail[:1900]
        if retry_after_s is not None:
            payload["retry_after_s"] = max(1, min(int(retry_after_s), 86400))
        try:
            self.api.post(f"/jobs/{job_id}/result", json=payload)
        except httpx.HTTPError as exc:
            # lease expiry re-arms the claim; the sweep remains the fallback
            log.warning("could not report result for job %s: %s", job_id, exc)

    def _run_publish_job(self, job_id: str, schedule_id: str | None,
                         now: datetime) -> int:
        """Run one claimed publish_schedule job. Returns 1 when a post was
        published. The schedule row — not the job payload — is the source of
        truth for state and due-ness."""
        if not schedule_id:
            self._job_result(job_id, ok=False,
                             detail="job has no schedule entity_id",
                             retry_after_s=3600)
            return 0
        try:
            res = self.api.get(f"/schedules/{schedule_id}")
        except httpx.HTTPError as exc:
            log.warning("schedule %s lookup failed (%s) — job re-queued", schedule_id, exc)
            self._job_result(job_id, ok=False,
                             detail=f"schedule lookup failed: {exc}",
                             retry_after_s=600)
            return 0
        if res.status_code == 404:
            self._job_result(job_id, ok=True,
                             detail="schedule no longer exists — nothing owed")
            return 0
        if res.status_code >= 300:
            self._job_result(job_id, ok=False,
                             detail=f"schedule lookup refused ({res.status_code})",
                             retry_after_s=600)
            return 0
        try:
            post = res.json()
        except ValueError:
            self._job_result(job_id, ok=False, detail="non-JSON schedule payload",
                             retry_after_s=600)
            return 0
        state = post.get("state")
        if state != "scheduled":
            # cancelled / paused / failed / already published — the owed work
            # either moved or was decided by a human; record it and move on.
            self._job_result(job_id, ok=True,
                             detail=f"nothing owed — schedule state is {state!r}")
            return 0
        if not _is_due(post.get("local_time"), now):
            try:
                when = datetime.fromisoformat(
                    str(post["local_time"]).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                wait_s = max(int((when - now).total_seconds()) + 1, 1)
            except ValueError:
                wait_s = 3600
            self._job_result(job_id, ok=False, detail="publish time not reached",
                             retry_after_s=wait_s)
            return 0
        adapters = self.build_adapters()
        if not self._automation_allowed():
            log.info("automation policy paused mid-drain — job %s left leased", job_id)
            return 0
        if self._publish(post, adapters):
            self._job_result(job_id, ok=True, detail="published")
            return 1
        # _publish already reported the outcome (hold/retry/failure) — the
        # job re-checks shortly and resolves itself from the schedule state.
        self._job_result(job_id, ok=False,
                         detail="publish attempt did not complete — see schedule outcome",
                         retry_after_s=600)
        return 0

    def _sweep(self, now: datetime) -> int:
        adapters = self.build_adapters()

        posts = fetch_all(self.api, "/schedules", {"state": "scheduled"}, limit=200)
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
            if not self._automation_allowed():
                break
            # Re-assert exclusivity before each upload: a sweep can outlive any
            # fixed TTL (uploads run 600s+). Losing the lock mid-sweep means a
            # second publisher may have joined — abort fail-closed.
            if not self._renew_sweep_lock("publishing"):
                log.error("sweep lock lost after %d post(s) — aborting the rest "
                          "of this sweep", published)
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
            posts = fetch_all(self.api, "/schedules", {"state": "published"}, limit=500)
        except (httpx.HTTPError, ValueError) as exc:
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
            if not self._automation_allowed():
                break
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
            failed = fetch_all(self.api, "/schedules", {"state": "failed"}, limit=500)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("retry sweep skipped (API unreachable): %s", exc)
            return 0
        if not isinstance(failed, list):
            log.error("failed-post lookup returned an unexpected payload — retry skipped")
            return 0

        requeued = 0
        for post in failed:
            if not self._automation_allowed():
                break
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
            # WP-G: the last failure may carry the platform's own retry-after
            # (RateLimited). Never requeue sooner than the server said, even
            # when our exponential backoff is already shorter.
            server_after = self._server_retry_after(post)
            if server_after is not None:
                delay = max(delay, server_after)
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
        platform = post.get("platform")
        if not platform:
            raise ValueError("schedule is missing its platform pin — re-schedule")

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
            for field, label, required in (
                ("expires_at", "offer expired", False),
                ("recheck_at", "offer recheck overdue", True),
            ):
                due = offer.get(field)
                if not due:
                    if required:
                        # Fail closed: the API treats a missing recheck deadline
                        # as overdue, and the worker must agree. An old row with
                        # no deadline is not evidence that the offer is fresh.
                        self._block(
                            post["id"],
                            "offer has no recheck deadline — publish blocked "
                            "until a human re-verifies it (§11/§17)",
                        )
                        return False
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

        # v0.29: a render must have a measured, passing QC report. Legacy rows
        # (qc_status NULL/not_checked) fail closed too: re-render and re-approve.
        if render.get("status") != "rendered" or render.get("qc_status") != "passed":
            self._block(
                post["id"],
                "render did not pass measured QC — inspect the render "
                "dead-letter, fix the cause and re-render before publishing")
            return False

        meta = post.get("metadata")
        meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
        pinned_metadata_hash = post.get("metadata_hash")
        if not pinned_metadata_hash:
            raise ValueError("schedule is missing its metadata_hash pin — re-approve the "
                             "packaging and re-schedule")
        if _canonical_hash(meta) != pinned_metadata_hash:
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
        pinned_render_sha = post.get("render_sha256")
        if not pinned_render_sha:
            raise ValueError("schedule is missing its render_sha256 pin — re-render and "
                             "re-approve the package")
        if actual_video_hash != pinned_render_sha:
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

        # §17: the API-side release gate is the ONE authority on "may this go
        # out" (freshness + package completeness + playback sign-off + format
        # binding). The local checks above stay as a cheap pre-filter, but the
        # upload never happens if the gate is unreachable — fail closed.
        if not self._release_gate_ok(post["id"]):
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

        if hasattr(adapter, "set_upload_session_store"):
            # YouTube resumable sessions survive a worker restart. The URI is
            # service/worker-only and cleared as soon as the upload completes.
            adapter.set_upload_session_store(
                APIUploadSessionStore(self.api, post["id"]))

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
            if package and package.get("complete") is False:
                failures = package.get("failures") or {}
                reason = "; ".join(
                    f"{name}: {detail}" for name, detail in sorted(failures.items())
                ) or "package assets were not accepted"
                self._report(
                    post["id"], ok=False, hold=True, remote_post_id=remote_id,
                    attempt_token=attempt_token,
                    detail=f"uploaded but release package incomplete: {reason}",
                    remote_url=(confirmation or {}).get("remote_url"),
                    remote_processing_state=(confirmation or {}).get("processing_state")
                    or (confirmation or {}).get("processing_status"),
                    remote_privacy=(confirmation or {}).get("privacy"),
                    remote_metadata=remote_metadata,
                )
                log.warning("schedule %s: package incomplete on %s — held: %s",
                            post["id"], platform, reason)
                return False
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
        except (TokenExpiredError, TransportUnauthorized) as exc:
            # A 401 late in the package finalize (thumbnail/captions/playlist)
            # is the same dead session — without this, the account stays
            # 'active' and every later post repeats the upload-then-hold cycle.
            log.error("ALERT credentials rejected on %s: %s — account marked expired, "
                      "post paused", platform, exc)
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
        except RateLimited as exc:
            # WP-G: the platform refused the call with a rate limit — the
            # post is NOT published (no duplicate risk) and auto-retry may
            # requeue it, but only after the server-shaped delay. Recorded in
            # outcome_detail so `retry_failed` waits max(backoff, retry_after).
            log.warning("schedule %s: %s rate limited (retry after %ss) — failed, "
                        "auto-retry honors the server delay", post["id"], platform,
                        exc.retry_after_s or "its own backoff")
            self._report(post["id"], ok=False, attempt_token=attempt_token,
                         remote_post_id=remote_id,
                         detail=f"platform rate limit: {exc}",
                         retry_after_s=exc.retry_after_s)
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
            render = self.api.get(f"/renders/{render_id}").json()
        except (httpx.HTTPError, ValueError):
            return None
        if str(render.get("id")) != str(render_id):
            return None
        if str(render.get("offer_id")) != str(post.get("offer_id") or ""):
            log.error("pinned render %s belongs to a different offer — refusing", render_id)
            return None
        return render

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
        if not expected_sha:
            # The video is always digest-pinned; covers and captions must be
            # too. Uploading whatever bytes currently sit at the ref would
            # break the approval hash chain silently.
            self._report(post["id"], ok=False, hold=True,
                         detail=f"{label} has no pinned sha256 — re-approve the package so "
                                "the upload is bound to reviewed bytes")
            return False
        return local

    @staticmethod
    def _server_retry_after(post: dict) -> int | None:
        """The platform-provided delay recorded with the last failure (WP-G)."""
        detail = post.get("outcome_detail")
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except (TypeError, ValueError):
                return None
        if not isinstance(detail, dict):
            return None
        try:
            value = int(detail.get("retry_after_s"))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

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
            log.error("upload attempt refused for %s (%s)", schedule_id,
                      getattr(res, "status_code", "?"))
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
                remote_metadata: dict | None = None,
                retry_after_s: int | None = None) -> None:
        body: dict = {"ok": ok, "remote_post_id": remote_post_id, "detail": detail,
                      "hold": hold, "attempt_token": attempt_token,
                      "confirmed": confirmed, "remote_url": remote_url,
                      "remote_processing_state": remote_processing_state,
                      "remote_privacy": remote_privacy,
                      "remote_metadata": remote_metadata or {}}
        if retry_after_s is not None:
            body["retry_after_s"] = max(0, min(int(retry_after_s), 7 * 86400))
        try:
            res = self.api.post(
                f"/schedules/{schedule_id}/result", json=body,
            )
            if getattr(res, "status_code", 200) >= 300:
                log.error("result for %s refused (%s)", schedule_id,
                          getattr(res, "status_code", "?"))
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
    hb = WorkerHeartbeat(args.api, "publishing")
    if args.once:
        hb.beat("ok", detail="one-shot publish sweep")
        try:
            count = publisher.run_once()
            log.info("sweep complete: %d published", count)
        finally:
            hb.beat("stopped", detail="one-shot publish sweep complete")
        return
    hb.start()
    try:
        publisher.run_forever()
    finally:
        hb.stop()


if __name__ == "__main__":
    main()
