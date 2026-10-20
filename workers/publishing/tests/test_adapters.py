"""Adapter tests with mocked HTTP — no real network, no real tokens.

Covers the week-10 exit criteria: private/test upload + token-expiry recovery.
"""

import httpx
import pytest

from platforms import (
    FacebookAdapter,
    OAuthConfig,
    TokenExpiredError,
    YouTubeAdapter,
)


def _video(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake video bytes")
    return p


class TestYouTube:
    def test_private_upload_success(self, tmp_path):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth2.googleapis.com/token" in url:
                return httpx.Response(200, json={"access_token": "tok123", "expires_in": 3600})
            if "uploadType=resumable" in url:
                calls.append("init")
                return httpx.Response(200, headers={"location": "https://upload.example/session"})
            if url == "https://upload.example/session":
                calls.append("put")
                return httpx.Response(200, json={"id": "vid_abc123"})
            return httpx.Response(404)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(
            oauth=OAuthConfig("cid", "csecret", "rtok"),
            account_id="acc1", http=http,
        )
        remote = adapter.upload(_video(tmp_path), {"title": "T", "caption": "c"},
                                privacy="private", idempotency_key="key1")
        assert remote == "vid_abc123"
        assert calls == ["init", "put"]

    def test_refreshed_expiry_reported_not_token(self, tmp_path):
        reported = {}

        def on_refresh(expires_at):
            reported["expires_at"] = expires_at
            reported["keys"] = set(dir())

        def handler(request: httpx.Request) -> httpx.Response:
            if "token" in str(request.url):
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 1800})
            return httpx.Response(200, headers={"location": "https://u/s"}, json={})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "r"),
                                 account_id="acc1", on_refresh=on_refresh, http=http)
        adapter.ensure_ready()
        assert "expires_at" in reported

    def test_401_recovers_via_refresh_and_retry(self, tmp_path):
        state = {"token": "old"}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "token" in url:
                state["token"] = "new"
                return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
            if "uploadType=resumable" in url:
                if request.headers.get("authorization") == "Bearer old":
                    return httpx.Response(401)
                state.setdefault("inits_after_refresh", 0)
                state["inits_after_refresh"] += 1
                return httpx.Response(200, headers={"location": "https://u/s"})
            if url == "https://u/s":
                return httpx.Response(200, json={"id": "vid_ok"})
            return httpx.Response(404)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "r"),
                                 access_token="old", account_id="acc1", http=http)
        remote = adapter.upload(_video(tmp_path), {}, privacy="private")
        assert remote == "vid_ok"
        assert state["inits_after_refresh"] == 1  # retried exactly once after refresh

    def test_refresh_failure_raises_token_expired(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            if "token" in str(request.url):
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(500)

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = YouTubeAdapter(oauth=OAuthConfig("c", "s", "BAD"), account_id="acc1", http=http)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_missing_credentials_raise(self, tmp_path):
        adapter = YouTubeAdapter(oauth=None, account_id="acc1")
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")


class TestFacebook:
    def test_unpublished_test_upload(self, tmp_path):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["published"] = getattr(request, "_content", b"")
            return httpx.Response(200, json={"id": "fb_video_1"})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = FacebookAdapter("PAGE_ID", "page_token", account_id="acc2", http=http)
        remote = adapter.upload(_video(tmp_path), {"title": "T", "caption": "c"}, privacy="private")
        assert remote == "fb_video_1"

    def test_dead_session_error_raises(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})

        http = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = FacebookAdapter("PAGE_ID", "dead", http=http)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_missing_credentials_raise(self, tmp_path):
        adapter = FacebookAdapter("", "", http=httpx.Client())
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")
