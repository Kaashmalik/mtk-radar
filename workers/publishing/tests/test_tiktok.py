"""TikTok adapter tests — mocked HTTP, no network, no real credentials.

TikTok needs an approved developer app; until then the adapter must degrade
cleanly (TokenExpiredError) and behave correctly once permissions arrive.
"""

import time

import httpx
import pytest

from platforms import TikTokAdapter, TikTokConfig, TokenExpiredError


def _video(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"fake tiktok video bytes")
    return p


def _adapter(tmp_path, config=None, access_token=None, handler=None, on_refresh=None):
    http = httpx.Client(transport=httpx.MockTransport(handler)) if handler else httpx.Client()
    return TikTokAdapter(
        config=config, access_token=access_token,
        account_id="acc3", on_refresh=on_refresh, http=http,
    )


class TestTikTok:
    def test_self_only_test_upload_success(self, tmp_path):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth/token" in url:
                return httpx.Response(200, json={"data": {"access_token": "tok", "expires_in": 86400}})
            if url.endswith("/post/publish/video/init/"):
                try:
                    seen["body"] = request.read()
                except Exception:  # noqa: BLE001
                    pass
                return httpx.Response(200, json={
                    "error": {"code": "ok", "message": ""},
                    "data": {"publish_id": "pub123",
                             "upload_url": "https://upload.tiktok.example/chunk"},
                })
            if url == "https://upload.tiktok.example/chunk":
                seen["range"] = request.headers.get("Content-Range")
                return httpx.Response(201)
            return httpx.Response(404)

        adapter = _adapter(
            tmp_path, config=TikTokConfig("key", "secret", "rtok"), handler=handler,
        )
        remote = adapter.upload(_video(tmp_path), {"title": "T"}, privacy="private")
        assert remote == "pub123"
        assert seen["body"] and b"SELF_ONLY" in seen["body"]  # test = private

    def test_upload_respects_public_privacy(self, tmp_path):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth/token" in url:
                return httpx.Response(200, json={"data": {"access_token": "tok", "expires_in": 86400}})
            if url.endswith("/post/publish/video/init/"):
                seen["body"] = request.read()
                return httpx.Response(200, json={
                    "error": {"code": "ok"},
                    "data": {"publish_id": "pub1", "upload_url": "https://u/c"},
                })
            if url == "https://u/c":
                return httpx.Response(201)
            return httpx.Response(404)

        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"), handler=handler)
        adapter.upload(_video(tmp_path), {}, privacy="public")
        assert b"PUBLIC_TO_EVERYONE" in seen["body"]

    def test_invalid_token_recovers_via_refresh(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "oauth/token" in url:
                return httpx.Response(200, json={"data": {"access_token": "new", "expires_in": 86400}})
            if url.endswith("/post/publish/video/init/"):
                if request.headers.get("authorization") == "Bearer old":
                    return httpx.Response(200, json={
                        "error": {"code": "invalid_token", "message": "expired"},
                    })
                return httpx.Response(200, json={
                    "error": {"code": "ok"},
                    "data": {"publish_id": "pub2", "upload_url": "https://u/c"},
                })
            if url == "https://u/c":
                return httpx.Response(201)
            return httpx.Response(404)

        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           access_token="old", handler=handler)
        # simulate a still-valid cached token so the 401 path fires mid-flight
        adapter._expires_monotonic = time.monotonic() + 3600
        remote = adapter.upload(_video(tmp_path), {}, privacy="private")
        assert remote == "pub2"

    def test_refresh_failure_raises_token_expired(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            if "oauth/token" in str(request.url):
                return httpx.Response(400, json={"error": "invalid_refresh_token"})
            return httpx.Response(500)

        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "BAD"), handler=handler)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_missing_credentials_raise(self, tmp_path):
        adapter = _adapter(tmp_path, config=None)
        with pytest.raises(TokenExpiredError):
            adapter.upload(_video(tmp_path), {}, privacy="private")
