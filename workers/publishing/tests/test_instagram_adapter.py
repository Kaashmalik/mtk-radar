"""Instagram adapter (v0.19, §6): the Graph content-publishing flow is
container → wait for transcoding → publish. The tests pin the parts that
historically break: a missing public media URL must fail loudly (Graph
fetches the file itself), a failed container must not be published, and a
dead token must surface as TokenExpiredError (so the worker pauses the queue
instead of retrying into the ground)."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platforms.base import TokenExpiredError
from platforms.instagram import InstagramAdapter


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_container_publish_flow_returns_media_id(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "container-1"})
        if request.url.path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media-42"})
        if request.url.path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(404, json={})

    video = tmp_path / "reel.mp4"
    video.write_bytes(b"video")
    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    media_id = adapter.upload(video, {"caption": "hello", "public_url": "https://cdn.test/reel.mp4"})

    assert media_id == "media-42"
    paths = [c[1] for c in calls]
    assert any(p.endswith("/media") for p in paths)
    assert any(p.endswith("/container-1") for p in paths), "container status must be polled"
    assert any(p.endswith("/media_publish") for p in paths)
    # the video URL is what Graph fetches — it must reach the create call
    # (form-encoded, so match the host part rather than the raw URL)
    assert b"cdn.test" in calls[0][2]
    assert b"media_type" in calls[0][2] and b"REELS" in calls[0][2]


def test_missing_public_url_fails_loudly(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not call the API without a public URL")

    video = tmp_path / "reel.mp4"
    video.write_bytes(b"video")
    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    with pytest.raises(RuntimeError, match="publicly reachable"):
        adapter.upload(video, {"caption": "hello"})


def test_failed_container_is_never_published(tmp_path):
    published = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "container-1"})
        if request.url.path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": "ERROR", "status": "transcode failed"})
        if request.url.path.endswith("/media_publish"):
            published.append(request)
            return httpx.Response(200, json={"id": "media-42"})
        return httpx.Response(404, json={})

    video = tmp_path / "reel.mp4"
    video.write_bytes(b"video")
    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    with pytest.raises(RuntimeError, match="processing failed"):
        adapter.upload(video, {"caption": "hello", "public_url": "https://cdn.test/reel.mp4"})
    assert published == [], "a failed container must not be published"


def test_dead_token_raises_token_expired(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": 190, "message": "invalid token"}})

    video = tmp_path / "reel.mp4"
    video.write_bytes(b"video")
    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    with pytest.raises(TokenExpiredError):
        adapter.upload(video, {"caption": "hello", "public_url": "https://cdn.test/reel.mp4"})


def test_insights_parses_metric_values():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [
            {"name": "reach", "values": [{"value": 120}]},
            {"name": "plays", "values": [{"value": "80"}]},
            {"name": "likes", "values": [{"value": 5}]},
        ]})

    adapter = InstagramAdapter(user_id="ig-1", access_token="tok", http=_client(handler))
    assert adapter.insights("media-42") == {"reach": 120, "plays": 80, "likes": 5}
