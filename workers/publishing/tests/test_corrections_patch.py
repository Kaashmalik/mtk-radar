"""§11 description patching (v0.18): when an offer is corrected after its
video is live, the worker pushes a correction notice into the published
YouTube description — exactly once (idempotency marker), only on YouTube,
only with a non-empty note, and only while the offer is still 'corrected'.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # workers/publishing

import main as pub


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeAPI:
    """route-aware: /schedules (published list), /offers/{id}, mark-patched."""

    def __init__(self, posts, offer):
        self.posts = posts
        self.offer = offer
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        if path == "/schedules":
            return FakeResponse(self.posts)
        if path.startswith("/offers/"):
            return FakeResponse(self.offer)
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return FakeResponse({"ok": True}, status_code=200)


class FakeYouTube:
    def __init__(self, fail=False):
        self.notices = []
        self.fail = fail

    def apply_correction_notice(self, video_id, notice):
        if self.fail:
            raise RuntimeError("update refused")
        self.notices.append((video_id, notice))


def _published(schedule_id="sch-1", platform="youtube", remote="vid-1", patched_at=None):
    return {"id": schedule_id, "platform": platform, "offer_id": "off-1",
            "remote_post_id": remote, "description_patched_at": patched_at}


def _corrected_offer(note="renewal is now $49/yr, not $29"):
    return {"state": "corrected", "correction_note": note}


def _worker(posts, offer):
    p = pub.Publisher(api_url="http://fake")
    p.api = FakeAPI(posts, offer)
    return p


def test_corrected_offer_patches_published_description_once():
    yt = FakeYouTube()
    p = _worker([_published()], _corrected_offer())
    assert p.apply_corrections({"youtube": yt}) == 1
    video_id, notice = yt.notices[0]
    assert video_id == "vid-1"
    assert notice.startswith("⚠ CORRECTION (") and "$49/yr" in notice
    assert ("POST", "/schedules/sch-1/mark-description-patched") in [
        (c[0], c[1]) for c in p.api.calls if c[0] == "POST"
    ]


def test_already_patched_posts_are_skipped():
    yt = FakeYouTube()
    p = _worker([_published(patched_at="2026-10-20T10:00:00Z")], _corrected_offer())
    assert p.apply_corrections({"youtube": yt}) == 0
    assert yt.notices == []


def test_non_corrected_or_empty_note_never_touches_the_platform():
    yt = FakeYouTube()
    p = _worker([_published()], {"state": "verified", "correction_note": None})
    assert p.apply_corrections({"youtube": yt}) == 0
    p = _worker([_published()], {"state": "corrected", "correction_note": "   "})
    assert p.apply_corrections({"youtube": yt}) == 0
    assert yt.notices == []


def test_non_youtube_platforms_are_a_documented_skip():
    yt = FakeYouTube()
    p = _worker([_published(platform="facebook", remote="fb-1")], _corrected_offer())
    assert p.apply_corrections({"youtube": yt}) == 0
    assert yt.notices == []


def test_platform_failure_leaves_post_unmarked_for_next_sweep():
    yt = FakeYouTube(fail=True)
    p = _worker([_published()], _corrected_offer())
    assert p.apply_corrections({"youtube": yt}) == 0
    posts = [c for c in p.api.calls if c[0] == "POST"]
    assert posts == [], "a failed patch must NOT be marked as applied"


def test_missing_youtube_adapter_is_a_noop():
    p = _worker([_published()], _corrected_offer())
    assert p.apply_corrections({}) == 0
