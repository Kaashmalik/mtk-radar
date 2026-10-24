"""G02 (evidence-to-video plan): an accepted upload id is NOT confirmed
publication. Every adapter must reconcile remote status/visibility before the
worker reports success; anything unconfirmed is a HELD failure, never a
phantom post."""

import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platforms.facebook import FacebookAdapter
from platforms.instagram import InstagramAdapter
from platforms.tiktok import TikTokAdapter, TikTokConfig


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------- facebook

def test_facebook_confirms_published_video_for_public_schedule():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["fields"] == "status,published,permalink_url"
        return httpx.Response(200, json={
            "status": {"video_status": "ready"},
            "published": True,
            "permalink_url": "https://facebook.com/pg1/videos/42",
        })

    adapter = FacebookAdapter(page_id="pg1", page_access_token="tok", http=_client(handler))
    out = adapter.confirm_publication("42", expected_privacy="public", timeout_s=1)
    assert out["confirmed"] is True
    assert out["remote_url"].endswith("/videos/42")


def test_facebook_unpublished_draft_counts_for_private_not_public():
    """'private' on Facebook means the honest published=false draft; that same
    state must NOT count as a confirmed public post."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "status": {"video_status": "ready"},
            "published": False,
            "permalink_url": None,
        })

    adapter = FacebookAdapter(page_id="pg1", page_access_token="tok", http=_client(handler))
    assert adapter.confirm_publication("42", expected_privacy="private", timeout_s=0)["confirmed"] is True
    out = adapter.confirm_publication("42", expected_privacy="public", timeout_s=0)
    assert out["confirmed"] is False
    assert "verify on the Page" in out["error"]


def test_facebook_error_video_status_is_terminal_unconfirmed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": {"video_status": "error"},
                                         "published": False})

    adapter = FacebookAdapter(page_id="pg1", page_access_token="tok", http=_client(handler))
    out = adapter.confirm_publication("42", expected_privacy="public", timeout_s=0)
    assert out["confirmed"] is False
    assert "terminal" in out["error"]


# ------------------------------------------------------------------ instagram

def test_instagram_confirms_only_when_media_object_has_permalink():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={
            "permalink": "https://instagram.com/reel/abc/",
            "timestamp": "2026-10-24T00:00:00+0000",
            "media_type": "REELS",
        })

    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    out = adapter.confirm_publication("media-42", expected_privacy="public", timeout_s=1)
    assert out["confirmed"] is True
    assert out["remote_url"] == "https://instagram.com/reel/abc/"
    assert calls and calls[0].endswith("/media-42")


def test_instagram_permalink_absent_stays_unconfirmed():
    """A 200 with no permalink (or a 404 while processing) is NOT a
    confirmation — the post id was accepted but nobody has seen it live."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "not found"}})

    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    out = adapter.confirm_publication("media-42", expected_privacy="public", timeout_s=0)
    assert out["confirmed"] is False
    assert "not confirmed live" in out["error"]


# --------------------------------------------------------------------- tiktok

def _tiktok(handler) -> TikTokAdapter:
    adapter = TikTokAdapter(
        config=TikTokConfig(client_key="k", client_secret="s", refresh_token="r"),
        http=_client(handler))
    adapter._access = "tok"
    adapter._expires_monotonic = time.monotonic() + 9999
    return adapter


def test_tiktok_confirms_complete_status_with_available_post_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {
            "status": "PUBLISH_COMPLETE",
            "publicaly_available_post_id": ["7301"],  # documented typo, kept
        }})

    adapter = _tiktok(handler)
    out = adapter.confirm_publication("pub-1", expected_privacy="public", timeout_s=1)
    assert out["confirmed"] is True
    assert out["remote_url"].endswith("/7301")


def test_tiktok_failure_is_terminal_unconfirmed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {
            "status": "PUBLISH_FAILED", "fail_reason": "audience mismatch",
        }})

    adapter = _tiktok(handler)
    out = adapter.confirm_publication("pub-1", expected_privacy="public", timeout_s=0)
    assert out["confirmed"] is False
    assert "audience mismatch" in out["error"]


def test_tiktok_unknown_status_stays_unconfirmed_never_assumed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"status": "SEND_TO_USER_TASK"}})

    adapter = _tiktok(handler)
    out = adapter.confirm_publication("pub-1", expected_privacy="public", timeout_s=0)
    assert out["confirmed"] is False
    assert "not a confirmed post" in out["error"]
