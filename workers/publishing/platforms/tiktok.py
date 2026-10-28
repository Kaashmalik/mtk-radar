"""TikTok adapter — Content Posting API v2 (§6, docs:
https://developers.tiktok.com/doc/content-posting-api-get-started).

URGENT permission note: TikTok requires an approved developer app with
video.publish scopes. This adapter is implemented "as permissions allow"
(§18 week 11) — it stays unconfigured until TIKTOK_* env credentials exist.

Flow: refresh-token auth (tokens in memory only) -> creator_info/query ->
video/init (FILE_UPLOAD, single chunk for clips under our size cap) -> PUT
bytes to the returned upload_url -> publish_id. Test uploads default to
SELF_ONLY (private).

Direct Post rules (G23, evidence-to-video plan; TikTok "Content Sharing
Guidelines"): every post must first query creator_info and may only use a
privacy level the creator currently offers, must honor the creator's
disabled comment/duet/stitch settings and maximum duration, and an
UNAUDITED client may only post SELF_ONLY. Public posting therefore stays
off until the operator sets TIKTOK_APP_AUDITED=1 after TikTok approves the
app; until then the default delivery for TikTok is the export bundle +
native/manual scheduling.
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    RateLimited,
    TokenExpiredError,
    TransportUnauthorized,
    UnsupportedPrivacyError,
    retry_after_from_response,
)

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TOKEN_MIN_TTL_S = 120
MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024  # API allows 128MB/chunk; stay under

PRIVACY_LEVELS = {
    "public": "PUBLIC_TO_EVERYONE",
    "unlisted": "SELF_ONLY",   # TikTok has no unlisted tier; closest is SELF_ONLY
    "private": "SELF_ONLY",
}

#: Creator-side refusals that mean "not now", not "broken": retry later.
_CREATOR_THROTTLE_CODES = frozenset({
    "spam_risk_too_many_posts",
    "spam_risk_user_banned_from_posting",
    "reached_active_user_cap",
    "rate_limit_exceeded",
})


def app_audited() -> bool:
    """Operator attestation that TikTok approved this app for public posts."""
    return os.environ.get("TIKTOK_APP_AUDITED", "").strip().lower() in ("1", "true", "yes")


@dataclass
class TikTokConfig:
    client_key: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, prefix: str = "TIKTOK_") -> Optional["TikTokConfig"]:
        import os

        prefix = (prefix or "TIKTOK_").rstrip("_*") + "_"
        cfg = cls(
            client_key=os.environ.get(f"{prefix}CLIENT_KEY", ""),
            client_secret=os.environ.get(f"{prefix}CLIENT_SECRET", ""),
            refresh_token=os.environ.get(f"{prefix}REFRESH_TOKEN", ""),
        )
        return cfg if all([cfg.client_key, cfg.client_secret, cfg.refresh_token]) else None


class TikTokAdapter(PublishAdapter):
    platform = "tiktok"

    def __init__(self, config: Optional[TikTokConfig] = None,
                 access_token: Optional[str] = None,
                 account_id: Optional[str] = None,
                 on_refresh=None,
                 http: Optional[httpx.Client] = None):
        super().__init__(account_id=account_id, on_refresh=on_refresh)
        self.config = config
        self._access = access_token
        self._expires_monotonic = 0.0
        self._http = http or httpx.Client(timeout=600)

    def supports_privacy(self, privacy: str) -> bool:
        """Pre-flight capability probe (worker calls it before any side effect).

        Unaudited TikTok clients are restricted to SELF_ONLY, so a public
        request is refused up front instead of failing after upload.
        """
        level = PRIVACY_LEVELS.get(privacy)
        if level is None:
            return False
        return level == "SELF_ONLY" or app_audited()

    # ------------------------------------------------------------------ auth

    def ensure_ready(self) -> None:
        self._ensure_token()

    def _ensure_token(self, force: bool = False) -> None:
        if not force and self._access and (self._expires_monotonic - time.monotonic()) > TOKEN_MIN_TTL_S:
            return
        if self.config is None:
            if self._access:
                self._expires_monotonic = time.monotonic() + 3600  # static test token
                return
            raise TokenExpiredError("TikTok credentials missing (TIKTOK_* env not configured)")
        self._force_refresh()

    def _force_refresh(self) -> None:
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={
                    "client_key": self.config.client_key,
                    "client_secret": self.config.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code in (400, 401):
                raise TokenExpiredError(
                    f"refresh rejected ({resp.status_code}) — app/renewal needed"
                )
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data or "access_token" not in data["data"]:
                raise TokenExpiredError(f"refresh returned no token: {data.get('error')}")
        except TokenExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001 — network errors must not loop forever
            raise TokenExpiredError(f"token refresh failed: {exc}") from exc

        self._access = data["data"]["access_token"]
        ttl = int(data["data"].get("expires_in", 86400))
        self._expires_monotonic = time.monotonic() + ttl
        if self.account_id and self.on_refresh:
            self.on_refresh(datetime.now(timezone.utc) + timedelta(seconds=ttl))

    # ---------------------------------------------------------------- upload

    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: str | None = None) -> str:
        self._ensure_token()
        try:
            return self._do_upload(video_path, meta, privacy)
        except TransportUnauthorized:
            # token-expiry recovery: refresh once, retry once (§6)
            self._force_refresh()
            return self._do_upload(video_path, meta, privacy)

    def _do_upload(self, video_path: Path, meta: dict[str, Any], privacy: str) -> str:
        size = Path(video_path).stat().st_size
        if size > MAX_SINGLE_CHUNK_BYTES:
            raise RuntimeError(
                f"video {size}B exceeds single-chunk cap — split before uploading"
            )

        level = PRIVACY_LEVELS.get(privacy, "SELF_ONLY")
        # Read-only and BEFORE init: nothing is published if this refuses.
        creator = self.creator_info()
        options = creator.get("privacy_level_options") or []
        if level not in options:
            raise UnsupportedPrivacyError(
                f"TikTok creator does not currently offer privacy '{level}' "
                f"(offered: {', '.join(options) or 'none'}) — reschedule with an "
                "offered level; public needs an audited app")
        max_duration = creator.get("max_video_post_duration_sec")
        duration = meta.get("duration_s")
        if max_duration and duration and float(duration) > float(max_duration):
            raise UnsupportedPrivacyError(
                f"video is {float(duration):.0f}s but this creator may post at most "
                f"{int(max_duration)}s — export a shorter edit")

        body = {
            "post_info": {
                "title": (meta.get("title") or "MTK RADAR AI")[:88],
                "description": (meta.get("caption") or "")[:2200],
                "privacy_level": level,
                # The creator's own disabled interactions always win.
                "disable_comment": bool(creator.get("comment_disabled")
                                        or meta.get("disable_comment")),
                "disable_duet": bool(creator.get("duet_disabled")
                                     or meta.get("disable_duet")),
                "disable_stitch": bool(creator.get("stitch_disabled")
                                       or meta.get("disable_stitch")),
                # Commercial-content disclosure is the operator's explicit
                # choice per post; never inferred.
                "brand_content_toggle": bool(meta.get("brand_content")),
                "brand_organic_toggle": bool(meta.get("brand_organic")),
                "self_declared": {"is_aigc": bool(meta.get("synthetic_narration"))},
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        }
        init = self._http.post(
            INIT_URL,
            json=body,
            headers={"Authorization": f"Bearer {self._access}"},
        )
        if init.status_code == 401:
            raise TransportUnauthorized("init rejected: token invalid")
        if init.status_code == 429:
            # WP-G: server-shaped retry — TikTok's rate-limit error carries
            # no delay, so honor Retry-After when the gateway provides one.
            raise RateLimited("tiktok init throttled (HTTP 429)",
                              retry_after_from_response(init))
        init.raise_for_status()
        payload = init.json()
        err = payload.get("error") or {}
        if err.get("code") in ("invalid_token", "access_token_invalid", "auth_link_invalid"):
            raise TransportUnauthorized(err.get("message", "tiktok token invalid"))
        if err.get("code") == "rate_limit_exceeded":
            raise RateLimited(err.get("message") or "tiktok rate limit exceeded",
                              retry_after_from_response(init))
        if err.get("code") not in (None, "ok"):
            raise RuntimeError(f"init error {err.get('code')}: {err.get('message')}")

        data = payload.get("data") or {}
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError(f"init returned no publish_id/upload_url: {payload}")

        with open(video_path, "rb") as fh:
            put = self._http.put(
                upload_url,
                content=fh,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{size - 1}/{size}",
                },
            )
        if put.status_code == 401:
            raise TransportUnauthorized("upload rejected: token expired mid-flight")
        put.raise_for_status()
        return str(publish_id)

    def creator_info(self) -> dict:
        """POST creator_info/query — required before every Direct Post.

        Returns the `data` object (privacy_level_options, *_disabled flags,
        max_video_post_duration_sec, creator handle). Token problems surface
        as TransportUnauthorized so the caller's refresh-once path applies.
        """
        resp = self._http.post(
            CREATOR_INFO_URL,
            json={},
            headers={"Authorization": f"Bearer {self._access}",
                     "Content-Type": "application/json; charset=UTF-8"},
        )
        if resp.status_code == 401:
            raise TransportUnauthorized("creator_info rejected: token invalid")
        if resp.status_code == 429:
            raise RateLimited("tiktok creator_info throttled (HTTP 429)",
                              retry_after_from_response(resp))
        resp.raise_for_status()
        payload = resp.json()
        err = payload.get("error") or {}
        code = err.get("code")
        if code in ("invalid_token", "access_token_invalid", "auth_link_invalid"):
            raise TransportUnauthorized(err.get("message", "tiktok token invalid"))
        if code in _CREATOR_THROTTLE_CODES:
            raise RateLimited(f"tiktok creator cannot post now: {code}",
                              retry_after_from_response(resp))
        if code not in (None, "ok"):
            raise RuntimeError(f"creator_info error {code}: {err.get('message')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("creator_info returned no data")
        return data

    def publish_status(self, publish_id: str) -> dict:
        """Optional post-upload status poll; requires the same token."""
        self._ensure_token()
        resp = self._http.post(
            STATUS_URL,
            json={"publish_id": publish_id},
            headers={"Authorization": f"Bearer {self._access}"},
        )
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------- reconciliation

    def confirm_publication(self, publish_id: str, *, expected_privacy: str,
                            timeout_s: int = 300, interval_s: float = 5.0) -> dict:
        """G02: poll the documented status endpoint until TikTok reports the
        post PUBLISHED, FAILED, or the deadline passes — the accepted
        `publish_id` alone is NOT confirmation. Per the evidence-to-video
        plan (G23): TikTok's unaudited visibility restrictions mean even
        `PUBLISH_COMPLETE` cannot be verified as publicly visible from the
        server alone, so confirmation carries the post id from the
        `publicaly_available_post_id` field (sic — TikTok's documented typo)
        when present, and 'unknown visibility' stays an explicit held state
        rather than an assumed one.

        The worker treats `confirmed: false` as a held failure: no retry,
        no duplicate upload, a human looks at the post.
        """
        deadline = time.monotonic() + max(0, int(timeout_s))
        last: dict = {}
        while True:
            payload = self.publish_status(publish_id)
            data = payload.get("data") or {}
            status = str(data.get("status") or "").upper()
            post_ids = (data.get("publicaly_available_post_id")
                        or data.get("publicly_available_post_id") or [])
            remote_url = ("https://www.tiktok.com/@me/video/"
                          + str(post_ids[0])) if post_ids else None
            last = {
                "processing_state": status or "unknown",
                "remote_url": remote_url,
                "fail_reason": data.get("fail_reason"),
            }
            if status in ("PUBLISH_COMPLETE", "PUBLISHED") or post_ids:
                return {**last, "confirmed": True}
            if status in ("PUBLISH_FAILED", "FAILED", "REJECTED") \
                    or last["fail_reason"]:
                return {**last, "confirmed": False,
                        "error": f"tiktok publish failed: {status} "
                                 f"({last['fail_reason'] or 'no detail'})"}
            if time.monotonic() >= deadline:
                return {**last, "confirmed": False,
                        "error": "tiktok publish status never reached a terminal or "
                                 "complete state before the deadline — verify in the "
                                 "TikTok app before retrying (an upload id is not a "
                                 "confirmed post)"}
            time.sleep(max(0.1, interval_s))
