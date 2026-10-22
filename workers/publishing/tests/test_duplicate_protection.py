"""Duplicate-publish protection (v0.23/v0.28): a platform upload that succeeds
but is never reported (worker died mid-flight) leaves an OPEN attempt marker.
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
        self.text = ""

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, outcome_detail=None, video_path=None):
        self.outcome_detail = outcome_detail
        self.video_path = video_path
        self.posts = []
        self.uploads = []

    def get(self, path, params=None):
        if path == "/renders":
            return FakeResponse([{"id": "r1", "video_path": self.video_path,
                                  "script_version_hash": "hash-1",
                                  "cover_path": None, "captions_path": None}])
        if path.startswith("/offers/"):
            return FakeResponse({"id": "off-1", "state": "approved_for_video",
                                 "expires_at": None, "recheck_at": None})
        if path == "/schedules":
            return FakeResponse([])
        return FakeResponse({})

    def post(self, path, json=None):
        self.posts.append((path, json))
        if path == "/schedules/sch-1/attempt":
            return FakeResponse({"acquired": True, "attempt_token": "token-1"})
        if path.endswith("/result"):
            return FakeResponse({"ok": True})
        return FakeResponse({"ok": True})


class FakeAdapter:
    def __init__(self):
        self.uploads = 0

    def upload(self, path, meta, privacy=None, idempotency_key=None):
        self.uploads += 1
        return "remote-1"


def _post(video_path=None, outcome_detail=None):
    metadata = {
        "title": "Approved title",
        "caption": "Approved caption with the reviewed CTA.",
        "captions_language": "en",
    }
    metadata_hash = pub._canonical_hash(metadata)
    sha = pub._sha256_file(Path(video_path)) if video_path else "sha"
    post = {
        "id": "sch-1", "platform": "youtube", "offer_id": "off-1",
        "local_time": "2020-01-01T00:00:00+00:00", "privacy": "private",
        "version_hash": "hash-1", "metadata": metadata, "idempotency_key": "k-1",
        "outcome_detail": outcome_detail, "language": "en",
        "caption_variant": "default", "metadata_variant": "default",
        "render_id": "r1", "render_sha256": sha, "metadata_hash": metadata_hash,
        "cover_sha256": None, "captions_sha256": None, "pinned_comment": None,
        "youtube_playlist_id": None, "platform_account_id": None, "cover_path": None,
    }
    post["package_hash"] = pub._canonical_hash({
        "offer_id": "off-1", "platform": "youtube", "account_id": None,
        "render_id": "r1", "render_sha256": sha, "metadata_hash": metadata_hash,
        "cover_sha256": None, "captions_sha256": None,
        "script_version_hash": "hash-1", "language": "en", "privacy": "private",
        "caption_variant": "default", "metadata_variant": "default",
        "pinned_comment": None, "youtube_playlist_id": None,
    })
    return post


def test_open_attempt_marker_is_detected():
    marker = {"attempt": {"started_at": "2026-10-21T10:00:00+00:00", "worker": "publishing-worker"}}
    assert pub.Publisher._open_attempt(_post(outcome_detail=marker)) is not None
    assert pub.Publisher._open_attempt(_post(outcome_detail=json.dumps(marker))) is not None


def test_a_closed_attempt_is_not_a_blocker():
    assert pub.Publisher._open_attempt(_post(outcome_detail={"attempt": None, "detail": "ok"})) is None
    assert pub.Publisher._open_attempt(_post(outcome_detail={})) is None
    assert pub.Publisher._open_attempt(_post(outcome_detail=None)) is None


def test_an_interrupted_upload_is_not_retried():
    api = FakeAPI()
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    marker = {"attempt": {"started_at": "2026-10-21T10:00:00+00:00"}}
    worker._publish(_post(outcome_detail=marker), {"youtube": adapter})

    assert adapter.uploads == 0, "the post may already be live — never upload twice"
    results = [c for c in api.posts if c[0].endswith("/result")]
    assert results and results[0][1]["ok"] is False
    assert "may already be live" in results[0][1]["detail"]


def test_the_attempt_is_announced_before_the_upload(tmp_path):
    video = tmp_path / "render.mp4"
    video.write_bytes(b"video")
    api = FakeAPI(video_path=str(video))
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker._publish(_post(str(video)), {"youtube": adapter})

    paths = [c[0] for c in api.posts]
    assert "/schedules/sch-1/attempt" in paths, "the attempt must be announced"
    assert paths.index("/schedules/sch-1/attempt") < paths.index(
        [p for p in paths if p.endswith("/result")][0]), "and before the outcome is reported"


def test_upload_does_not_start_when_attempt_claim_fails(tmp_path):
    video = tmp_path / "render.mp4"
    video.write_bytes(b"video")

    class NoClaimAPI(FakeAPI):
        def post(self, path, json=None):
            self.posts.append((path, json))
            if path.endswith("/attempt"):
                return FakeResponse({"detail": "open attempt"}, status_code=409)
            return FakeResponse({"ok": True})

    api = NoClaimAPI(video_path=str(video))
    adapter = FakeAdapter()
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    assert worker._publish(_post(str(video)), {"youtube": adapter}) is False
    assert adapter.uploads == 0


def test_a_held_post_is_not_auto_retried():
    held = {
        "id": "sch-hold", "platform": "youtube", "retry_count": 1,
        "updated_at": "2020-01-01T00:00:00+00:00",
        "outcome_detail": {"hold": True, "detail": "unknown outcome"},
    }
    api = FakeAPI()
    api.posts = []
    worker = pub.Publisher(api_url="http://fake")
    worker.api = api
    worker.RETRY_BASE_S = 0

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
    marker = {"attempt": {"started_at": "2026-10-21T10:00:00+00:00"}}
    worker._publish(_post(outcome_detail=marker), {"youtube": adapter})
    results = [c for c in api.posts if c[0].endswith("/result")]
    assert results[0][1]["hold"] is True, "the API must know this post needs a human"
