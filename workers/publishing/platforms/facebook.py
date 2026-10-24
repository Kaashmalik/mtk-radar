"""Facebook Pages adapter — Meta Graph API video upload (§6, docs:
https://developers.facebook.com/docs/video-api/guides/publishing/).

Page token flow: a long-lived Page access token from the env; error code 190
means a dead session → TokenExpiredError. Test uploads post UNPUBLISHED
(published=false) unless privacy=public.
"""

from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    RateLimited,
    TokenExpiredError,
    TransportUnauthorized,
    exchange_long_lived_token as _base_exchange,
    raise_on_graph_error,
    retry_after_from_response,
)

GRAPH_VERSION = "v21.0"
OAUTH_ENDPOINT = f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token"
VIDEO_ENDPOINT = f"https://graph.facebook.com/{GRAPH_VERSION}/"


def exchange_long_lived_token(page_token: str, app_id: str, app_secret: str,
                              http: Optional[httpx.Client] = None) -> dict:
    """Meta long-lived token exchange for a Facebook Page token (WP-G §5.6.1).

    Thin wrapper over the shared Graph helper in platforms/base.py: the
    documented `fb_exchange_token` grant renews a long-lived Page token
    WITHOUT re-auth. Raises TokenExpiredError on any refusal so the account
    is marked expired and the operator sees it — never a silent stall.
    """
    return _base_exchange(VIDEO_ENDPOINT, page_token, app_id, app_secret, http)


class FacebookAdapter(PublishAdapter):
    platform = "facebook"

    def __init__(self, page_id: str, page_access_token: str,
                 account_id: Optional[str] = None, on_refresh=None,
                 http: Optional[httpx.Client] = None):
        super().__init__(account_id=account_id, on_refresh=on_refresh)
        self.page_id = page_id
        self.page_access_token = page_access_token
        self._http = http or httpx.Client(timeout=600)

    def ensure_ready(self) -> None:
        if not self.page_id or not self.page_access_token:
            raise TokenExpiredError("Facebook Page credentials missing (FACEBOOK_* env)")

    def refresh_long_lived_token(self, http: Optional[httpx.Client] = None) -> dict:
        """Renew the long-lived Page token without re-auth (WP-G §5.6.1).

        Meta's `fb_exchange_token` grant renews a long-lived Page token while
        the app id + secret are configured. On success the in-memory token is
        replaced AND `on_refresh` fires (the publisher reports the new expiry
        to /platform-accounts). On refusal TokenExpiredError surfaces so the
        account is marked expired — never a silent stall.
        """
        import os
        result = exchange_long_lived_token(
            self.page_access_token,
            os.environ.get("FACEBOOK_APP_ID") or "",
            os.environ.get("FACEBOOK_APP_SECRET") or "",
            http=http,
        )
        self.page_access_token = result["access_token"]
        if result.get("expires_at") and self.on_refresh is not None:
            self.on_refresh(result["expires_at"])
        return result

    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: str | None = None) -> str:
        self.ensure_ready()
        data = {
            "title": (meta.get("title") or meta.get("platform") or "MTK RADAR AI")[:120],
            "description": meta.get("caption", ""),
            "access_token": self.page_access_token,
            # test uploads stay unpublished until the operator flips them live
            "published": "true" if privacy == "public" else "false",
        }
        if idempotency_key:
            data["workflow"] = "mtk-radar"  # documented marker; FB has no request-id dedupe

        with open(video_path, "rb") as fh:
            resp = self._http.post(
                f"{VIDEO_ENDPOINT}{self.page_id}/videos",
                data=data,
                files={"source": (Path(video_path).name, fh, "video/mp4")},
            )

        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = {}

        if resp.status_code == 401:
            raise TokenExpiredError("graph rejected the page token — re-authentication required")
        if resp.status_code == 429:
            raise RateLimited(
                "graph upload throttled (HTTP 429)",
                retry_after_from_response(resp))
        if resp.status_code >= 400:
            try:
                raise_on_graph_error(payload, response=resp)
            except TransportUnauthorized as exc:
                # FB has no in-flight refresh: a dead session needs re-auth (§6)
                raise TokenExpiredError(str(exc)) from exc
            resp.raise_for_status()
        return str(payload["id"])

    # ------------------------------------------------------------- analytics

    def insights(self, video_id: str) -> dict:
        """Per-video audience metrics via Graph video_insights (v0.18, docs:
        https://developers.facebook.com/docs/video-api/guides/insights/).
        Requires the video to be published; unpublished test uploads answer
        empty/404 — callers treat that as no-data, not failure."""
        self.ensure_ready()
        resp = self._http.get(
            f"{VIDEO_ENDPOINT}{video_id}/video_insights",
            params={
                "metric": "total_video_views,total_video_reactions,total_comments",
                "access_token": self.page_access_token,
            },
        )
        if resp.status_code in (400, 401, 403):
            raise TokenExpiredError(f"graph insights rejected ({resp.status_code}) — re-auth required")
        resp.raise_for_status()
        out: dict[str, int] = {}
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("Graph insights returned a non-object payload")
        for entry in payload.get("data", []):
            values = entry.get("values") or [{}]
            try:
                out[entry["name"]] = int(values[0].get("value", 0))
            except (TypeError, ValueError):
                out[entry["name"]] = 0
        return out
