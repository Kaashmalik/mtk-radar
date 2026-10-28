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


ALL_LEVELS = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]


def _creator_ok(options=None, **extra):
    return httpx.Response(200, json={
        "error": {"code": "ok"},
        "data": {"creator_username": "mtk", "privacy_level_options": options or ALL_LEVELS,
                 "comment_disabled": False, "duet_disabled": False,
                 "stitch_disabled": False, "max_video_post_duration_sec": 600, **extra},
    })


def _with_creator_info(handler):
    """Answer the mandatory creator_info query unless the test handles it."""
    def wrapped(request: httpx.Request) -> httpx.Response:
        resp = handler(request)
        if resp.status_code == 404 and str(request.url).endswith("/creator_info/query/"):
            return _creator_ok()
        return resp
    return wrapped


def _adapter(tmp_path, config=None, access_token=None, handler=None, on_refresh=None):
    http = (httpx.Client(transport=httpx.MockTransport(_with_creator_info(handler)))
            if handler else httpx.Client())
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


class TestDirectPostRules:
    """G23: creator_info first, offered privacy only, creator settings win."""

    def _handler(self, seen, creator):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen.setdefault("calls", []).append(url.rsplit("/v2/", 1)[-1])
            if "oauth/token" in url:
                return httpx.Response(200, json={"data": {"access_token": "tok", "expires_in": 86400}})
            if url.endswith("/creator_info/query/"):
                return creator
            if url.endswith("/post/publish/video/init/"):
                seen["body"] = request.read()
                return httpx.Response(200, json={
                    "error": {"code": "ok"},
                    "data": {"publish_id": "p", "upload_url": "https://u/c"}})
            if url == "https://u/c":
                return httpx.Response(201)
            return httpx.Response(404)
        return handler

    def test_creator_info_is_queried_before_init(self, tmp_path):
        seen = {}
        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           handler=self._handler(seen, _creator_ok()))
        adapter.upload(_video(tmp_path), {}, privacy="private")
        calls = seen["calls"]
        assert calls.index("post/publish/creator_info/query/") <             calls.index("post/publish/video/init/")

    def test_unoffered_privacy_is_refused_before_any_upload(self, tmp_path):
        from platforms.base import UnsupportedPrivacyError

        seen = {}
        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           handler=self._handler(seen, _creator_ok(["SELF_ONLY"])))
        with pytest.raises(UnsupportedPrivacyError, match="PUBLIC_TO_EVERYONE"):
            adapter.upload(_video(tmp_path), {}, privacy="public")
        assert "body" not in seen, "init must never be called"

    def test_creator_disabled_interactions_win(self, tmp_path):
        import json

        seen = {}
        creator = _creator_ok(comment_disabled=True, stitch_disabled=True)
        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           handler=self._handler(seen, creator))
        adapter.upload(_video(tmp_path), {"disable_comment": False}, privacy="private")
        info = json.loads(seen["body"])["post_info"]
        assert info["disable_comment"] is True and info["disable_stitch"] is True
        assert info["disable_duet"] is False
        assert info["brand_content_toggle"] is False

    def test_over_long_video_is_refused(self, tmp_path):
        from platforms.base import UnsupportedPrivacyError

        seen = {}
        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           handler=self._handler(seen, _creator_ok(max_video_post_duration_sec=60)))
        with pytest.raises(UnsupportedPrivacyError, match="at most 60s"):
            adapter.upload(_video(tmp_path), {"duration_s": 95}, privacy="private")
        assert "body" not in seen

    def test_creator_throttle_is_a_retryable_rate_limit(self, tmp_path):
        from platforms.base import RateLimited

        throttled = httpx.Response(200, json={"error": {"code": "spam_risk_too_many_posts"}})
        adapter = _adapter(tmp_path, config=TikTokConfig("k", "s", "r"),
                           handler=self._handler({}, throttled))
        with pytest.raises(RateLimited):
            adapter.upload(_video(tmp_path), {}, privacy="private")

    def test_public_needs_operator_audit_attestation(self, monkeypatch):
        adapter = TikTokAdapter(access_token="t")
        monkeypatch.delenv("TIKTOK_APP_AUDITED", raising=False)
        assert adapter.supports_privacy("private") is True
        assert adapter.supports_privacy("public") is False
        assert adapter.supports_privacy("bogus") is False
        monkeypatch.setenv("TIKTOK_APP_AUDITED", "1")
        assert adapter.supports_privacy("public") is True

