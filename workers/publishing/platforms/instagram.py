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

G01 (evidence-to-video plan): there is NO private/draft publish on this
platform — an earlier docstring claimed test uploads "stay unpublished by
default", which was false. `media_publish` puts the media live in front of
the account's default audience, full stop. Schedules requesting `private`
or `unlisted` are rejected with UnsupportedPrivacyError BEFORE the container
is created: correct the schedule to `public` or connect a platform that
supports the requested mode. Facebook keeps the `published=false` draft
capability; that is a Facebook feature, not an Instagram one.
"""

import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .base import (
    PublishAdapter,
    RateLimited,
    TokenExpiredError,
    TransportUnauthorized,
    UnsupportedPrivacyError,
    exchange_long_lived_token as _base_exchange,
    raise_on_graph_error,
    retry_after_from_response,
)

GRAPH_VERSION = "v21.0"
GRAPH_ENDPOINT = f"https://graph.facebook.com/{GRAPH_VERSION}/"

# G01 (evidence-to-video plan): Instagram's Content Publishing API has NO
# per-post privacy control. A container is published to the account's default
# audience the moment `media_publish` succeeds — there is no draft/private
# state to fall back on. Advertising one is how a "private test" becomes a
# public live post. Only `public` is supported; anything else is rejected
# before any API call is made. (`unlisted` is not an Instagram concept.)
SUPPORTED_PRIVACY = frozenset({"public"})

# Graph polls the container until transcoding completes; keep the window short
# and bounded so a stuck container cannot block the publishing worker.
CONTAINER_POLL_ATTEMPTS = 20
CONTAINER_POLL_INTERVAL_S = 3


class InstagramAdapter(PublishAdapter):
    platform = "instagram"

    @classmethod
    def supports_privacy(cls, privacy: str) -> bool:
        """Capability probe used as a pre-flight check publishing-side."""
        return privacy in SUPPORTED_PRIVACY

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
               privacy: str = "public", idempotency_key: Optional[str] = None) -> str:
        self.ensure_ready()
        # G01: reject unsupported privacy BEFORE any publishing side effect —
        # no container may exist for a request Graph cannot honor anyway.
        if privacy not in SUPPORTED_PRIVACY:
            raise UnsupportedPrivacyError(
                f"instagram cannot publish with privacy='{privacy}': the Content "
                f"Publishing API has no per-post private/unpublished mode; supported "
                f"modes are {sorted(SUPPORTED_PRIVACY)} — fix the schedule, do not retry"
            )
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
        return self._publish_container(container_id)

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
        if resp.status_code == 429:
            raise RateLimited("graph creation throttled (HTTP 429)",
                              retry_after_from_response(resp))
        if resp.status_code >= 400:
            try:
                raise_on_graph_error(payload, response=resp)
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

    def _publish_container(self, container_id: str) -> str:
        # No privacy parameter exists on media_publish — if one appears here
        # again, that is the G01 lie returning.
        resp = self._http.post(
            f"{GRAPH_ENDPOINT}{self.user_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
        )
        payload = self._payload(resp)
        if resp.status_code == 401:
            raise TokenExpiredError("graph rejected the Instagram token on publish")
        if resp.status_code == 429:
            raise RateLimited("graph publish throttled (HTTP 429)",
                              retry_after_from_response(resp))
        if resp.status_code >= 400:
            try:
                raise_on_graph_error(payload, response=resp)
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

    def exchange_long_lived_token(self, http: Optional[httpx.Client] = None) -> dict:
        """Renew the long-lived token without re-auth (WP-G §5.6.1).

        Meta's `fb_exchange_token` grant also covers Instagram professional
        accounts bound to a Page. On success the in-memory token is replaced
        AND `on_refresh` fires (the publisher then reports the new expiry to
        /platform-accounts). On refusal TokenExpiredError surfaces so the
        account is marked expired — never a silent stall.
        """
        import os
        result = _base_exchange(
            GRAPH_ENDPOINT, self.access_token,
            os.environ.get("INSTAGRAM_APP_ID") or os.environ.get("FACEBOOK_APP_ID") or "",
            os.environ.get("INSTAGRAM_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET") or "",
            http=http,
        )
        self.access_token = result["access_token"]
        if result.get("expires_at") and self.on_refresh is not None:
            self.on_refresh(result["expires_at"])
        return result

    @staticmethod
    def _payload(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {}
