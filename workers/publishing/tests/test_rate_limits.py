"""WP-G rate-limit handling (§5.6.2): the taxonomy, header parsing, adapter
translation, and the retry path honoring the server-provided delay.

Hammering a throttled endpoint only extends the ban — the platform's own
`Retry-After` / `x-ratelimit-*` signal must shape the retry.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # workers/publishing
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root (packages)

import httpx  # noqa: E402
import pytest  # noqa: E402

from platforms.base import RateLimited, raise_on_graph_error, retry_after_from_response  # noqa: E402

import main as pub  # noqa: E402


def _response(status_code=429, headers=None, payload=None):
    resp = httpx.Response(status_code, headers=headers or {},
                          json=payload if payload is not None else {"error": {"message": "x"}})
    return resp


# ------------------------------------------------------------ header parsing

def test_retry_after_seconds_header_is_honored():
    assert retry_after_from_response(_response(headers={"Retry-After": "42"})) == 42


def test_retry_after_http_date_is_converted():
    import email.utils
    import time
    when = email.utils.formatdate(time.time() + 120, usegmt=True)
    value = retry_after_from_response(_response(headers={"Retry-After": when}))
    assert value is not None and 100 <= value <= 140


def test_ratelimit_reset_epoch_is_used():
    import time
    value = retry_after_from_response(_response(headers={"x-ratelimit-reset": str(int(time.time()) + 90)}))
    assert value is not None and 60 <= value <= 120


def test_garbage_headers_yield_none():
    assert retry_after_from_response(_response(headers={"Retry-After": "soon"})) is None
    assert retry_after_from_response(_response()) is None


# -------------------------------------------------------- graph translation

def test_graph_code_4_raises_rate_limited_with_retry_after():
    resp = _response(payload={"error": {"code": 4, "message": "application request limit reached"}},
                     headers={"Retry-After": "77"})
    with pytest.raises(RateLimited) as exc:
        raise_on_graph_error(resp.json(), response=resp)
    assert exc.value.retry_after_s == 77


def test_graph_subcode_2446852_is_rate_limited():
    resp = _response(payload={"error": {"code": 9, "error_subcode": 2446852,
                                        "message": "temporarily blocked for policies"}})
    with pytest.raises(RateLimited):
        raise_on_graph_error(resp.json(), response=resp)


def test_graph_dead_session_still_unauthorized():
    resp = _response(payload={"error": {"code": 190, "message": "dead token"}})
    from platforms.base import TransportUnauthorized
    with pytest.raises(TransportUnauthorized):
        raise_on_graph_error(resp.json(), response=resp)


import tempfile  # noqa: E402


def test_facebook_upload_translates_http_429():
    from platforms.facebook import FacebookAdapter

    class Http:
        def post(self, url, data=None, files=None):
            return httpx.Response(429, headers={"Retry-After": "33"},
                                  json={"error": {"message": "throttled"}},
                                  request=httpx.Request("POST", url))

    with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
        adapter = FacebookAdapter(page_id="pg1", page_access_token="tok", http=Http())
        with pytest.raises(RateLimited) as exc:
            adapter.upload(Path(video.name), {"title": "t"})
    assert exc.value.retry_after_s == 33


def test_tiktok_init_throttle_raises_rate_limited():
    from platforms.tiktok import TikTokAdapter, TikTokConfig

    class Http:
        def post(self, url, json=None, headers=None):
            return httpx.Response(429, headers={"Retry-After": "60"},
                                  json={"error": {"code": "rate_limit_exceeded"}},
                                  request=httpx.Request("POST", url))

    config = TikTokConfig(client_key="k", client_secret="s", refresh_token="r")
    adapter = TikTokAdapter(config=config, http=Http())
    import time as _time
    adapter._access = "tok"
    adapter._expires_monotonic = _time.monotonic() + 9999
    with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
        with pytest.raises(RateLimited) as exc:
            adapter.upload(Path(video.name), {})
    assert exc.value.retry_after_s == 60


# --------------------------------------------------------- retry path (WP-G)

def test_server_retry_after_is_parsed_from_outcome_detail():
    post = {"outcome_detail": json.dumps({"retry_after_s": 123, "detail": "platform rate limit"})}
    assert pub.Publisher._server_retry_after(post) == 123
    assert pub.Publisher._server_retry_after({"outcome_detail": "{}"}) is None
    assert pub.Publisher._server_retry_after({"outcome_detail": json.dumps({"retry_after_s": "x"})}) is None


def test_retry_failed_waits_for_max_backoff_and_server_delay(monkeypatch):
    """A 400s Retry-After must override a shorter exponential backoff; a
    short one never shortens the backoff."""
    posts = [{
        "id": "sch-1", "platform": "youtube", "offer_id": "off-1",
        "retry_count": 0,  # backoff = retry_base * 1 = 300
        "state": "failed",
        "outcome_detail": json.dumps({"retry_after_s": 900}),
        "updated_at": "2026-01-01T00:00:00Z",
    }]
    posted = []

    class FakeAPI:
        def get(self, path, params=None):
            assert path == "/schedules"
            class R:
                status_code = 200
                def json(self):
                    return posts
            return R()

        def post(self, path, json=None):
            posted.append((path, json))
            class R:
                status_code = 200
                def json(self):
                    return {"id": "sch-1", "state": "scheduled"}
            return R()

        def get_json(self, path, params=None):
            return {}

    worker = pub.Publisher.__new__(pub.Publisher)
    worker.api = FakeAPI()
    monkeypatch.setattr(pub, "fetch_all",
                        lambda api, path, params=None, limit=None: posts)
    monkeypatch.setattr(pub.Publisher, "_automation_allowed", lambda self: True)
    monkeypatch.setattr(pub.Publisher, "_limits",
                        lambda self: {"auto_retry": True, "retry_max_attempts": 3,
                                      "retry_base_seconds": 300})
    worker.retry_failed()
    (path, body), = posted
    assert "/transition" in path
    assert "900s" in body["note"], "the server delay must win over the 300s backoff"
