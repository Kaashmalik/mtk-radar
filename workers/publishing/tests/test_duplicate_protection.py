"""Duplicate-publish protection (v0.23): a platform upload that succeeds but
is never reported (worker died mid-flight) leaves an OPEN attempt marker.
The next sweep must NOT upload again — a duplicate public post is worse than
a delayed one — it must hold the post for a human to verify.
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_publishing_main", Path(__file__).resolve().parent.parent / "main.py")
pub = importlib.util.module_from_spec(_spec)
sys.modules["mtk_publishing_main"] = pub
_spec.loader.exec_module(pub)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, outcome_detail=None):
        self.outcome_detail = outcome_detail
        self.posts = []
        self.uploads = []

    def get(self, path, params=None):
        if path == "/renders":
            return FakeResponse([{"id": "r1", "video_path": "projects/x/r.mp4",
                                  "script_version_hash": "hash-1"}])
        if path.startswith("/offers/"):
            return FakeResponse({"id": "off-1", "state": "approved_for_video",
                                 "expires_at": None, "recheck_at": None})
        if path == "/schedules":
            return FakeResponse([])
        return FakeResponse({})

    def post(self, path, json=None):
        self.posts.append((path, json))
        if path == "/schedules/sch-1/attempt":
            return FakeResponse({"ok": True})
        if path.endswith("/result"):
            return FakeResponse({"ok": True})
        return FakeResponse({"ok": True})


class FakeAdapter:
    def __init__(self):
        self.uploads = 0

    def upload(self, path, meta, privacy=None, idempotency_key=None):
        self.uploads += 1
        return "remote-1"


def _post(outcome_detail=None):
    return {
        "id": "sch-1", "platform": "youtube", "offer_id": "off-1",
        "local_time": "2020-01-01T00:00:00+00:00", "privacy": "private",
        "version_hash": "hash-1", "metadata": {}, "idempotency_key": "k-1",
        "outcome_detail": outcome_detail,
    }


def test_open_attempt_marker_is_detected():
    marker = {"attempt": {"started_at": "2026-10-21T10:00:00+00:00", "worker": "publishing-worker"}}
    assert pub.Publisher._open_attempt(_post(marker)) is not None
    assert pub.Publisher._open_attempt(_post(json.dumps(marker))) is not None


def test_a_closed_attempt_is_not_a_blocker():
    # a definite result clears the marker (attempt: null)
    assert pub.Publisher._open_attempt(_post({"attempt": None, "detail": "ok"})) is None
    assert pub.Publisher._open_attempt(_post({})) is None
    assert pub.Publisher._open_attempt(_post(None)) is None


def test_an_interrupted_upload_is_not_retried(tmp_path):
    api = FakeAPI({"attempt": {"started_at": "2026-10-21T10:00:00+00:00"}})
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    video = tmp_path / "render.mp4"
    video.write_bytes(b"video")
    worker._latest_render = lambda offer_id: {"id": "r1", "video_path": str(video),
                                              "script_version_hash": "hash-1"}

    worker._publish(_post({"attempt": {"started_at": "2026-10-21T10:00:00+00:00"}}),
                    {"youtube": adapter})

    assert adapter.uploads == 0, "the post may already be live — never upload twice"
    results = [c for c in api.posts if c[0].endswith("/result")]
    assert results and results[0][1]["ok"] is False
    assert "may already be live" in results[0][1]["detail"]


def test_the_attempt_is_announced_before_the_upload(tmp_path):
    api = FakeAPI()
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    video = tmp_path / "render.mp4"
    video.write_bytes(b"video")
    worker._latest_render = lambda offer_id: {"id": "r1", "video_path": str(video),
                                              "script_version_hash": "hash-1"}

    worker._publish(_post(), {"youtube": adapter})

    paths = [c[0] for c in api.posts]
    assert "/schedules/sch-1/attempt" in paths, "the attempt must be announced"
    assert paths.index("/schedules/sch-1/attempt") < paths.index(
        [p for p in paths if p.endswith("/result")][0]), "and before the outcome is reported"


def test_a_held_post_is_not_auto_retried():
    """The hold must survive the auto-retry sweep: a post waiting for a human
    (unknown upload outcome) must not be requeued automatically."""
    held = {
        "id": "sch-hold", "platform": "youtube", "retry_count": 1,
        "updated_at": "2020-01-01T00:00:00+00:00",
        "outcome_detail": {"hold": True, "detail": "unknown outcome"},
    }
    api = FakeAPI()
    api.posts = []
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker.RETRY_BASE_S = 0  # backoff elapsed — only the hold may stop it

    assert worker.retry_failed() == 0
    assert not [c for c in api.posts if c[0].endswith("/transition")], \
        "a held post must not be auto-requeued"


def test_hold_detection_handles_string_payloads():
    assert pub.Publisher._is_held({"outcome_detail": '{"hold": true}'}) is True
    assert pub.Publisher._is_held({"outcome_detail": '{"hold": false}'}) is False
    assert pub.Publisher._is_held({"outcome_detail": None}) is False
    assert pub.Publisher._is_held({}) is False


def test_the_hold_is_reported_with_the_hold_flag():
    api = FakeAPI()
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker._latest_render = lambda offer_id: {"id": "r1", "video_path": "projects/x/r.mp4",
                                              "script_version_hash": "hash-1"}
    worker._publish(_post({"attempt": {"started_at": "2026-10-21T10:00:00+00:00"}}),
                    {"youtube": adapter})
    results = [c for c in api.posts if c[0].endswith("/result")]
    assert results[0][1]["hold"] is True, "the API must know this post needs a human"
