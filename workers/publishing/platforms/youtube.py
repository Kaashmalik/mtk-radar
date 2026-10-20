"""YouTube adapter — official Data API resumable upload (§6, docs:
https://developers.google.com/youtube/v3/docs/videos/insert).

Auth: OAuth2 refresh-token flow. Access tokens are held IN MEMORY ONLY and
refreshed when near expiry or on a 401; refresh expiry is reported back via
the on_refresh hook (never the token). Privacy status comes from the schedule
(private by default for test uploads).
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

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_INIT_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
TOKEN_MIN_TTL_S = 120  # refresh before expiry with margin
CATEGORY_DEVELOPER = "28"  # Science & Technology


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls) -> Optional["OAuthConfig"]:
        import os

        cfg = cls(
            client_id=os.environ.get("YOUTUBE_CLIENT_ID", ""),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN", ""),
        )
        return cfg if all([cfg.client_id, cfg.client_secret, cfg.refresh_token]) else None


class YouTubeAdapter(PublishAdapter):
    platform = "youtube"

    def __init__(self, oauth: Optional[OAuthConfig] = None,
                 access_token: Optional[str] = None,
                 account_id: Optional[str] = None,
                 on_refresh=None,
                 http: Optional[httpx.Client] = None):
        super().__init__(account_id=account_id, on_refresh=on_refresh)
        self.oauth = oauth
        self._access = access_token
        self._expires_monotonic = 0.0
        self._http = http or httpx.Client(timeout=600)

    # ------------------------------------------------------------------ auth

    def ensure_ready(self) -> None:
        self._ensure_token()

    def _ensure_token(self, force: bool = False) -> None:
        if not force and self._access and (self._expires_monotonic - time.monotonic()) > TOKEN_MIN_TTL_S:
            return
        if self.oauth is None:
            if self._access:
                self._expires_monotonic = time.monotonic() + 3600  # static test token
                return
            raise TokenExpiredError("YouTube credentials missing (YOUTUBE_* env not configured)")
        self._force_refresh()

    def _force_refresh(self) -> None:
        try:
            resp = self._http.post(
                TOKEN_URL,
                data={
                    "client_id": self.oauth.client_id,
                    "client_secret": self.oauth.client_secret,
                    "refresh_token": self.oauth.refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code in (400, 401):
                raise TokenExpiredError(
                    f"refresh rejected ({resp.status_code}) — operator must re-consent"
                )
            resp.raise_for_status()
            data = resp.json()
        except TokenExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001 — network errors must not loop forever
            raise TokenExpiredError(f"token refresh failed: {exc}") from exc

        self._access = data["access_token"]
        ttl = int(data.get("expires_in", 3600))
        self._expires_monotonic = time.monotonic() + ttl
        if self.account_id and self.on_refresh:
            self.on_refresh(datetime.now(timezone.utc) + timedelta(seconds=ttl))

    # ---------------------------------------------------------------- upload

    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: str | None = None) -> str:
        self._ensure_token()
        try:
            return self._do_upload(video_path, meta, privacy, idempotency_key)
        except TransportUnauthorized:
            # token-expiry recovery: refresh once, retry once (§6)
            self._force_refresh()
            return self._do_upload(video_path, meta, privacy, idempotency_key)

    def _do_upload(self, video_path: Path, meta: dict[str, Any],
                   privacy: str, idempotency_key: str | None) -> str:
        body = {
            "snippet": {
                "title": (meta.get("title") or "MTK RADAR AI")[:100],
                "description": meta.get("caption", ""),
                "tags": meta.get("tags", [])[:30],
                "categoryId": CATEGORY_DEVELOPER,
            },
            "status": {
                "privacyStatus": privacy if privacy in ("public", "unlisted", "private") else "private",
                "selfDeclaredMadeForKids": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._access}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(Path(video_path).stat().st_size),
        }
        if idempotency_key:
            headers["X-Request-Id"] = idempotency_key  # resumable session dedupe

        init = self._http.post(UPLOAD_INIT_URL, json=body, headers=headers)
        if init.status_code == 401:
            raise TransportUnauthorized("upload init rejected: token invalid")
        init.raise_for_status()

        location = init.headers.get("location")
        if not location:
            raise RuntimeError("YouTube did not return a resumable session location")

        with open(video_path, "rb") as fh:
            upload = self._http.put(
                location, content=fh,
                headers={"Content-Type": "video/mp4"},
            )
        if upload.status_code == 401:
            raise TransportUnauthorized("upload rejected: token expired mid-flight")
        upload.raise_for_status()
        return str(upload.json()["id"])
