"""Publish-time approval integrity + expiry gates (v0.16, master plan §11/§17).

The worker must refuse to upload unless:
- the offer is in a publishable state AND not expired / recheck-overdue, and
- the render's script_version_hash equals the schedule's approved version_hash.

Fakes replace HTTP + platform adapters; the video file is real on disk so the
storage materialize step runs for plain legacy paths.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # workers/publishing

import main as pub


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeAPI:
    def __init__(self, offer, renders):
        self.offer = offer
        self.renders = renders
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        if path.startswith("/offers/"):
            return FakeResponse(self.offer)
        if path == "/renders":
            return FakeResponse(self.renders)
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return FakeResponse({"ok": True})


class FakeAdapter:
    def __init__(self):
        self.uploads = []

    def upload(self, path, meta, privacy=None, idempotency_key=None):
        self.uploads.append((str(path), privacy, idempotency_key))
        return "remote-1"


def _iso(offset: timedelta) -> str:
    return (datetime.now(timezone.utc) + offset).isoformat()


def _publisher(offer, renders):
    p = pub.Publisher(api_url="http://fake-api")
    p.api = FakeAPI(offer, renders)
    return p


def _post(version_hash="APPROVED"):
    return {
        "id": "sch-1",
        "offer_id": "off-1",
        "platform": "youtube",
        "privacy": "private",
        "version_hash": version_hash,
        "metadata": None,
    }


def _render(hash_value):
    path = Path(tempfile.mkdtemp()) / "r.mp4"
    path.write_bytes(b"VIDEO")
    return {"video_path": str(path), "script_version_hash": hash_value}


def _healthy_offer():
    return {"state": "verified", "expires_at": _iso(timedelta(days=1)),
            "recheck_at": _iso(timedelta(days=1))}


def _result_calls(api):
    return [c for c in api.calls if c[0] == "POST" and "/result" in c[1]]


def _pause_calls(api):
    return [c for c in api.calls if c[0] == "POST" and "/pause" in c[1]]


# ---------------------------------------------------------------- gates


def test_happy_path_publishes_when_hash_pins_and_offer_valid():
    p = _publisher(_healthy_offer(), [_render("APPROVED")])
    adapter = FakeAdapter()
    p._publish(_post(), {"youtube": adapter})

    assert len(adapter.uploads) == 1, "upload must happen when every gate passes"
    assert _result_calls(p.api)[0][2]["ok"] is True


def test_hash_mismatch_blocks_and_pauses():
    p = _publisher(_healthy_offer(), [_render("DIFFERENT-SCRIPT")])
    adapter = FakeAdapter()
    p._publish(_post(), {"youtube": adapter})

    assert adapter.uploads == [], "must never upload a render from another script version"
    assert _pause_calls(p.api), "schedule must be paused for re-approval"
    detail = _result_calls(p.api)[0][2]
    assert detail["ok"] is False and "approval integrity" in detail["detail"]


def test_render_without_bound_hash_fails_closed():
    p = _publisher(_healthy_offer(), [_render(None)])
    adapter = FakeAdapter()
    p._publish(_post(), {"youtube": adapter})

    assert adapter.uploads == []
    assert "approval integrity" in _result_calls(p.api)[0][2]["detail"]


def test_offer_expiry_blocks_upload_even_when_state_is_publishable():
    offer = {"state": "verified", "expires_at": _iso(timedelta(hours=-1)),
             "recheck_at": _iso(timedelta(days=1))}
    p = _publisher(offer, [_render("APPROVED")])
    adapter = FakeAdapter()
    p._publish(_post(), {"youtube": adapter})

    assert adapter.uploads == []
    assert _pause_calls(p.api), "§11: expired deals pause queued posts automatically"
    assert "offer expired" in _result_calls(p.api)[0][2]["detail"]


def test_overdue_recheck_blocks_upload():
    offer = {"state": "verified", "expires_at": _iso(timedelta(days=1)),
             "recheck_at": _iso(timedelta(hours=-2))}
    p = _publisher(offer, [_render("APPROVED")])
    adapter = FakeAdapter()
    p._publish(_post(), {"youtube": adapter})

    assert adapter.uploads == []
    assert "recheck overdue" in _result_calls(p.api)[0][2]["detail"]
