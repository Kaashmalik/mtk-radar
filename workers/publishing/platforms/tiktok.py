"""TikTok adapter — Content Posting API v2 (§6, docs:
https://developers.tiktok.com/doc/content-posting-api-get-started).

URGENT permission note: TikTok requires an approved developer app with
video.publish scopes. This adapter is implemented "as permissions allow"
(§18 week 11) — it stays unconfigured until TIKTOK_* env credentials exist.

Flow: refresh-token auth (tokens in memory only) -> video/init (FILE_UPLOAD,
single chunk for clips under our size cap) -> PUT bytes to the returned
upload_url -> publish_id. Test uploads default to SELF_ONLY (private).
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    TokenExpiredError,
    TransportUnauthorized,
)

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TOKEN_MIN_TTL_S = 120
MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024  # API allows 128MB/chunk; stay under

PRIVACY_LEVELS = {
    "public": "PUBLIC_TO_EVERYONE",
    "unlisted": "SELF_ONLY",   # TikTok has no unlisted tier; closest is SELF_ONLY
    "private": "SELF_ONLY",
}


@dataclass
class TikTokConfig:
    client_key: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls) -> Optional["TikTokConfig"]:
        import os

        cfg = cls(
            client_key=os.environ.get("TIKTOK_CLIENT_KEY", ""),
            client_secret=os.environ.get("TIKTOK_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("TIKTOK_REFRESH_TOKEN", ""),
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

        body = {
            "post_info": {
                "title": (meta.get("title") or "MTK RADAR AI")[:88],
                "description": (meta.get("caption") or "")[:2200],
                "privacy_level": PRIVACY_LEVELS.get(privacy, "SELF_ONLY"),
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
        init.raise_for_status()
        payload = init.json()
        err = payload.get("error") or {}
        if err.get("code") in ("invalid_token", "access_token_invalid", "auth_link_invalid"):
            raise TransportUnauthorized(err.get("message", "tiktok token invalid"))
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
