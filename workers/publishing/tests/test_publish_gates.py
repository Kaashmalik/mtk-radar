"""Publish-time approval integrity + expiry gates (v0.16/v0.28, §11/§17).

The worker must refuse to upload unless:
- the offer is in a publishable state AND not expired / recheck-overdue,
- the render's script_version_hash equals the schedule's approved version_hash,
- the exact pinned render/metadata/package hashes are unchanged.

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
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

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
        if path.startswith("/renders/"):
            wanted = path.rsplit("/", 1)[-1]
            match = next((r for r in self.renders
                          if str(r.get("id")) == wanted), None)
            if match is None:
                return FakeResponse({"detail": "render not found"}, status_code=404)
            # The list fixtures predate offer_id on the row; bind the fixture
            # post's offer id so the worker's ownership check behaves like the
            # real endpoint.
            return FakeResponse({"offer_id": "off-1", **match})
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if path.endswith("/attempt"):
            return FakeResponse({"acquired": True, "attempt_token": "token-1"})
        return FakeResponse({"ok": True})


class FakeAdapter:
    def __init__(self):
        self.uploads = []

    def upload(self, path, meta, privacy=None, idempotency_key=None):
        self.uploads.append((str(path), privacy, idempotency_key, meta))
        return "remote-1"


class ConfirmingAdapter(FakeAdapter):
    def __init__(self, confirmed=True):
        super().__init__()
        self.confirmed = confirmed
        self.confirmations = []

    def confirm_publication(self, remote_id, *, expected_privacy,
                            timeout_s, interval_s):
        self.confirmations.append((remote_id, expected_privacy))
        if not self.confirmed:
            return {"confirmed": False, "error": "still processing"}
        return {"confirmed": True, "processing_state": "succeeded",
                "privacy": expected_privacy,
                "remote_url": f"https://youtu.be/{remote_id}"}


class IncompletePackageAdapter(ConfirmingAdapter):
    def finalize_package(self, remote_id, meta, *, thumbnail_path=None,
                         captions_path=None, playlist_id=None,
                         pinned_comment=None, captions_language=None):
        return {
            "complete": False,
            "failures": {"thumbnail": "unsupported image"},
            "thumbnail": {"ok": False, "error": "unsupported image"},
        }


def _iso(offset: timedelta) -> str:
    return (datetime.now(timezone.utc) + offset).isoformat()


def _publisher(offer, renders):
    p = pub.Publisher(api_url="http://fake-api")
    p.api = FakeAPI(offer, renders)
    return p


def _post(render, version_hash="APPROVED", metadata=None):
    metadata = metadata if metadata is not None else {
        "title": "Approved title",
        "caption": "Approved caption with the reviewed CTA.",
        "captions_language": "en",
    }
    metadata_hash = pub._canonical_hash(metadata)
    post = {
        "id": "sch-1",
        "offer_id": "off-1",
        "platform": "youtube",
        "privacy": "private",
        "version_hash": version_hash,
        "metadata": metadata,
        "language": "en",
        "caption_variant": "default",
        "metadata_variant": "default",
        "render_id": "r1",
        "render_sha256": pub._sha256_file(Path(render["video_path"])),
        "metadata_hash": metadata_hash,
        "cover_sha256": None,
        "captions_sha256": None,
        "pinned_comment": None,
        "youtube_playlist_id": None,
        "platform_account_id": None,
        "cover_path": None,
    }
    post["package_hash"] = pub._canonical_hash({
        "offer_id": "off-1",
        "platform": "youtube",
        "account_id": None,
        "render_id": "r1",
        "render_sha256": post["render_sha256"],
        "metadata_hash": metadata_hash,
        "cover_sha256": None,
        "captions_sha256": None,
        "script_version_hash": version_hash,
        "language": "en",
        "privacy": "private",
        "caption_variant": "default",
        "metadata_variant": "default",
        "pinned_comment": None,
        "youtube_playlist_id": None,
    })
    return post


def _render(hash_value):
    path = Path(tempfile.mkdtemp()) / "r.mp4"
    path.write_bytes(b"VIDEO")
    return {"id": "r1", "video_path": str(path), "script_version_hash": hash_value,
            "cover_path": None, "captions_path": None,
            "status": "rendered", "qc_status": "passed"}


def _healthy_offer():
    return {"state": "verified", "expires_at": _iso(timedelta(days=1)),
            "recheck_at": _iso(timedelta(days=1))}


def _result_calls(api):
    return [c for c in api.calls if c[0] == "POST" and "/result" in c[1]]


def _pause_calls(api):
    return [c for c in api.calls if c[0] == "POST" and "/pause" in c[1]]


# ---------------------------------------------------------------- gates


def test_happy_path_publishes_when_hash_pins_and_offer_valid():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    post = _post(render)
    assert p._publish(post, {"youtube": adapter}) is True

    assert len(adapter.uploads) == 1, "upload must happen when every gate passes"
    assert adapter.uploads[0][3] == post["metadata"], \
        "the adapter must receive the approved metadata verbatim (no injected copy)"
    result = _result_calls(p.api)[0][2]
    assert result["ok"] is True and result["confirmed"] is True
    assert result["attempt_token"] == "token-1"


def test_incomplete_youtube_package_is_held_not_reported_published():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = IncompletePackageAdapter(confirmed=True)
    post = _post(render)

    assert p._publish(post, {"youtube": adapter}) is False
    result = _result_calls(p.api)[0][2]
    assert result["ok"] is False
    assert result["hold"] is True
    assert "package incomplete" in result["detail"]
    assert "thumbnail" in result["detail"]
    assert result["remote_post_id"] == "remote-1", \
        "the uploaded video must remain recorded so it is reconciled, not duplicated"


def test_existing_remote_upload_is_reconfirmed_not_reuploaded():
    """An upload that succeeded but timed out before confirmation may already
    be live. Resuming must confirm that video, never create a duplicate."""
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = ConfirmingAdapter(confirmed=True)
    post = _post(render)
    post["remote_post_id"] = "remote-1"
    post["remote_metadata"] = {"thumbnail": {"ok": True}}

    assert p._publish(post, {"youtube": adapter}) is True
    assert adapter.uploads == [], "a known remote id must never be uploaded again"
    assert adapter.confirmations == [("remote-1", "private")]

    result = _result_calls(p.api)[0][2]
    assert result["ok"] is True and result["confirmed"] is True
    assert result["remote_metadata"]["reconfirmed"] is True
    assert result["remote_metadata"]["thumbnail"] == {"ok": True}


def test_existing_remote_upload_that_is_still_unconfirmed_stays_held():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = ConfirmingAdapter(confirmed=False)
    post = _post(render)
    post["remote_post_id"] = "remote-1"

    assert p._publish(post, {"youtube": adapter}) is False
    assert adapter.uploads == []
    result = _result_calls(p.api)[0][2]
    assert result["ok"] is False and result["hold"] is True
    assert "still unconfirmed" in result["detail"]


def test_remote_post_without_a_confirmation_api_is_never_reuploaded():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    post = _post(render)
    post["remote_post_id"] = "remote-1"

    assert p._publish(post, {"youtube": adapter}) is False
    assert adapter.uploads == []
    assert "will not upload again" in _result_calls(p.api)[0][2]["detail"]


def test_empty_approved_caption_blocks_upload():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render, metadata={"title": "Approved title"}), {"youtube": adapter})

    assert adapter.uploads == [], "the worker must never invent a caption"
    assert "no caption" in _result_calls(p.api)[0][2]["detail"]


def test_youtube_package_must_have_a_title():
    render = _render("APPROVED")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render, metadata={"caption": "Approved caption"}), {"youtube": adapter})

    assert adapter.uploads == []
    assert "no title" in _result_calls(p.api)[0][2]["detail"]


def test_hash_mismatch_blocks_and_pauses():
    render = _render("DIFFERENT-SCRIPT")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == [], "must never upload a render from another script version"
    assert _pause_calls(p.api), "schedule must be paused for re-approval"
    detail = _result_calls(p.api)[0][2]
    assert detail["ok"] is False and detail["hold"] is True
    assert "approval integrity" in detail["detail"]
    # The reason must be recorded while the post is still reportable; pausing
    # first would make the result endpoint refuse the detail.
    calls = [c for c in p.api.calls if c[0] == "POST" and ("/result" in c[1] or "/pause" in c[1])]
    assert calls[0][1].endswith("/result"), "report the held reason before pausing"


def test_qc_failed_render_blocks_upload():
    render = _render("APPROVED")
    render["status"] = "qc_failed"
    render["qc_status"] = "failed"
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == [], "a QC-rejected render must never upload"
    assert _pause_calls(p.api)
    assert "QC" in _result_calls(p.api)[0][2]["detail"]


def test_legacy_render_without_qc_fails_closed():
    render = _render("APPROVED")
    render.pop("qc_status")
    render.pop("status")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == []
    assert "QC" in _result_calls(p.api)[0][2]["detail"]


def test_render_without_bound_hash_fails_closed():
    render = _render(None)
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == []
    assert "approval integrity" in _result_calls(p.api)[0][2]["detail"]


def test_offer_expiry_blocks_upload_even_when_state_is_publishable():
    offer = {"state": "verified", "expires_at": _iso(timedelta(hours=-1)),
             "recheck_at": _iso(timedelta(days=1))}
    render = _render("APPROVED")
    p = _publisher(offer, [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == []
    assert _pause_calls(p.api), "§11: expired deals pause queued posts automatically"
    assert "offer expired" in _result_calls(p.api)[0][2]["detail"]


def test_overdue_recheck_blocks_upload():
    offer = {"state": "verified", "expires_at": _iso(timedelta(days=1)),
             "recheck_at": _iso(timedelta(hours=-2))}
    render = _render("APPROVED")
    p = _publisher(offer, [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == []
    assert "recheck overdue" in _result_calls(p.api)[0][2]["detail"]


def test_missing_recheck_deadline_blocks_upload():
    """NULL is not proof of freshness: the API fails closed and so must the
    worker (previously it skipped the check and published)."""
    offer = {"state": "verified", "expires_at": None, "recheck_at": None}
    render = _render("APPROVED")
    p = _publisher(offer, [render])
    adapter = FakeAdapter()
    p._publish(_post(render), {"youtube": adapter})

    assert adapter.uploads == []
    assert "no recheck deadline" in _result_calls(p.api)[0][2]["detail"]


def test_changed_render_bytes_block_upload():
    render = _render("APPROVED")
    post = _post(render)
    Path(render["video_path"]).write_bytes(b"TAMPERED")
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(post, {"youtube": adapter})

    assert adapter.uploads == []
    assert "pinned sha256" in _result_calls(p.api)[0][2]["detail"]


def test_metadata_edit_after_scheduling_blocks_upload():
    render = _render("APPROVED")
    post = _post(render)
    post["metadata"] = {"title": "changed after review"}
    p = _publisher(_healthy_offer(), [render])
    adapter = FakeAdapter()
    p._publish(post, {"youtube": adapter})

    assert adapter.uploads == []
    assert "metadata changed" in _result_calls(p.api)[0][2]["detail"]


def test_pinned_account_never_falls_back_to_another_account():
    worker = pub.Publisher(api_url="http://fake-api")
    account_a = object()
    account_b = object()
    adapters = {"youtube": account_b, "youtube:acct-a": account_a}

    assert worker._adapter_for(
        {"platform": "youtube", "platform_account_id": "acct-a"}, adapters) is account_a
    assert worker._adapter_for(
        {"platform": "youtube", "platform_account_id": "acct-missing"}, adapters) is None, \
        "a pinned account must never silently upload to the default channel"
    assert worker._adapter_for({"platform": "youtube"}, adapters) is account_b, \
        "legacy schedules without a pin may use the platform default"
