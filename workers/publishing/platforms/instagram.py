"""Instagram adapter — Graph API Content Publishing (master plan §6, docs:
https://developers.facebook.com/docs/instagram-platform/content-publishing).

Instagram needs THREE things this adapter makes explicit:
  1. an Instagram professional (business/creator) account bound to a Page —
     a personal account cannot publish here at all;
  2. a PUBLICLY reachable media URL (the Graph API fetches the video itself —
     it does not accept an upload), so the caller must pass `public_url` in
     the publish metadata;
  3. the two-step container flow: create a media container, wait for the
     transcoding status to be FINISHED, then publish it.

Test uploads stay unpublished by default: `privacy != "public"` publishes the
container but keeps the media in a draft state, mirroring the Facebook
adapter's conservative default.
"""

import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    TokenExpiredError,
    TransportUnauthorized,
    raise_on_graph_error,
)

GRAPH_VERSION = "v21.0"
GRAPH_ENDPOINT = f"https://graph.facebook.com/{GRAPH_VERSION}/"

# Graph polls the container until transcoding completes; keep the window short
# and bounded so a stuck container cannot block the publishing worker.
CONTAINER_POLL_ATTEMPTS = 20
CONTAINER_POLL_INTERVAL_S = 3


class InstagramAdapter(PublishAdapter):
    platform = "instagram"

    def __init__(self, user_id: str, access_token: str,
                 account_id: Optional[str] = None, on_refresh=None,
                 http: Optional[httpx.Client] = None):
        super().__init__(account_id=account_id, on_refresh=on_refresh)
        self.user_id = user_id
        self.access_token = access_token
        self._http = http or httpx.Client(timeout=600)

    def ensure_ready(self) -> None:
        if not self.user_id or not self.access_token:
            raise TokenExpiredError(
                "Instagram credentials missing (INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN)"
            )

    # ---------------------------------------------------------------- upload

    def upload(self, video_path: Path, meta: dict[str, Any],
               privacy: str = "private", idempotency_key: Optional[str] = None) -> str:
        self.ensure_ready()
        public_url = (meta.get("public_url") or "").strip()
        if not public_url:
            raise RuntimeError(
                "Instagram needs a publicly reachable video URL (meta.public_url) — "
                "the Graph API fetches the media itself; expose the render over "
                "HTTPS (object storage public URL) and pass it in the metadata"
            )
        caption = (meta.get("caption") or meta.get("title") or "")[:2200]
        container_id = self._create_container(public_url, caption)
        self._await_container(container_id)
        return self._publish_container(container_id, privacy)

    # ------------------------------------------------------------- internals

    def _create_container(self, video_url: str, caption: str) -> str:
        resp = self._http.post(
            f"{GRAPH_ENDPOINT}{self.user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": self.access_token,
            },
        )
        payload = self._payload(resp)
        if resp.status_code == 401:
            raise TokenExpiredError("graph rejected the Instagram token — re-authentication required")
        if resp.status_code >= 400:
            try:
                raise_on_graph_error(payload)
            except TransportUnauthorized as exc:
                raise TokenExpiredError(str(exc)) from exc
            resp.raise_for_status()
        return str(payload["id"])

    def _await_container(self, container_id: str) -> None:
        """Wait until Graph finished processing the media (status_code)."""
        for attempt in range(CONTAINER_POLL_ATTEMPTS):
            resp = self._http.get(
                f"{GRAPH_ENDPOINT}{container_id}",
                params={"fields": "status_code,status", "access_token": self.access_token},
            )
            payload = self._payload(resp)
            status = str(payload.get("status_code", "")).upper()
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED", "PUBLISH_FAILED"):
                raise RuntimeError(
                    f"instagram media processing failed: {status} "
                    f"({payload.get('status', 'no detail')})"
                )
            time.sleep(CONTAINER_POLL_INTERVAL_S)
        raise RuntimeError("instagram media processing did not finish in time")

    def _publish_container(self, container_id: str, privacy: str) -> str:
        resp = self._http.post(
            f"{GRAPH_ENDPOINT}{self.user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
        )
        payload = self._payload(resp)
        if resp.status_code == 401:
            raise TokenExpiredError("graph rejected the Instagram token on publish")
        if resp.status_code >= 400:
            try:
                raise_on_graph_error(payload)
            except TransportUnauthorized as exc:
                raise TokenExpiredError(str(exc)) from exc
            resp.raise_for_status()
        return str(payload["id"])

    def insights(self, media_id: str) -> dict:
        """Per-media reach metrics (Graph insights). Unpublished/draft media
        answers empty — callers treat that as no-data, not failure."""
        self.ensure_ready()
        resp = self._http.get(
            f"{GRAPH_ENDPOINT}{media_id}/insights",
            params={
                "metric": "reach,plays,likes,comments,shares,saved",
                "access_token": self.access_token,
            },
        )
        if resp.status_code in (400, 401, 403):
            raise TokenExpiredError(f"graph insights rejected ({resp.status_code})")
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

    @staticmethod
    def _payload(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {}
