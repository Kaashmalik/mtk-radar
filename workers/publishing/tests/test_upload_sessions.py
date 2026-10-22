"""The worker-side session store must never put a capability URI in a URL."""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from upload_sessions import APIUploadSessionStore


def test_session_store_round_trip_keeps_uri_in_json_only():
    calls = []
    session = {
        "session_uri": "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=secret",
        "content_length": 100,
        "bytes_sent": 40,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(200, json=session)
        if request.method in ("PUT", "PATCH"):
            return httpx.Response(200, json=session)
        return httpx.Response(404)

    api = httpx.Client(
        base_url="http://api.test",
        transport=httpx.MockTransport(handler),
    )
    store = APIUploadSessionStore(api, "sch-1")

    assert store.load()["session_uri"].endswith("secret")
    store.save(session["session_uri"], 100)
    store.progress(40)
    store.clear()

    assert [r.method for r in calls] == ["GET", "PUT", "PATCH", "DELETE"]
    assert all(r.url.path == "/schedules/sch-1/upload-session" for r in calls)
    assert all("secret" not in str(r.url) for r in calls), \
        "the session capability must not leak into access logs via a query string"
    assert b"upload_id=secret" in calls[1].read()
