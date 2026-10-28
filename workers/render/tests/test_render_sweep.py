"""Render sweep (v0.19): the render worker must pick up the ready queue on
its own — one candidate at a time, through the same code path as a manual
render, and one broken candidate never stops the sweep.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_spec = importlib.util.spec_from_file_location(
    "mtk_render_main", Path(__file__).resolve().parent.parent / "main.py")
render_main = importlib.util.module_from_spec(_spec)
sys.modules["mtk_render_main"] = render_main
_spec.loader.exec_module(render_main)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, candidates, fail=False):
        self.candidates = candidates
        self.fail = fail

    def get(self, path, params=None):
        if self.fail:
            raise httpx.ConnectError("api down")
        return FakeResponse(self.candidates)

    def post(self, path, json=None):
        # No durable queue on this fake: sync/claim fall back (404) and the
        # classic candidate sweep remains the driver.
        return FakeResponse({"detail": "not found"}, 404)


def _patch_client(monkeypatch, candidates, fail=False):
    monkeypatch.setattr(render_main.httpx, "Client",
                        lambda *a, **k: FakeClient(candidates, fail))


def test_sweep_renders_every_candidate(monkeypatch, tmp_path):
    calls = []
    behaviour_candidates = [
        {"offer_id": "off-1", "script_version": 2, "capture_id": "cap-1"},
        {"offer_id": "off-2", "script_version": 1, "capture_id": "cap-2"},
    ]

    class FakeJob:
        def __init__(self, offer_id, api_url, out_root):
            self.offer_id = offer_id

        def run(self, capture_video, preset_keys, skip_narration, capture_id=None):
            calls.append((self.offer_id, capture_id, tuple(preset_keys)))

    monkeypatch.setattr(render_main, "RenderJob", FakeJob)
    _patch_client(monkeypatch, behaviour_candidates)

    rendered = render_main.sweep("http://fake", tmp_path, ["landscape"], True, limit=5)
    assert rendered == 2
    assert [c[0] for c in calls] == ["off-1", "off-2"]
    assert calls[0][1] == "cap-1", "the reviewed capture drives the render"


def test_one_broken_candidate_does_not_stop_the_sweep(monkeypatch, tmp_path):
    rendered_ids = []

    class FakeJob:
        def __init__(self, offer_id, api_url, out_root):
            self.offer_id = offer_id

        def run(self, capture_video, preset_keys, skip_narration, capture_id=None):
            if self.offer_id == "off-bad":
                raise SystemExit("capture video unavailable on this host")
            rendered_ids.append(self.offer_id)

    monkeypatch.setattr(render_main, "RenderJob", FakeJob)
    _patch_client(monkeypatch, [
        {"offer_id": "off-bad", "capture_id": "cap-1"},
        {"offer_id": "off-good", "capture_id": "cap-2"},
    ])

    assert render_main.sweep("http://fake", tmp_path, ["landscape"], True) == 1
    assert rendered_ids == ["off-good"]


def test_api_unreachable_sweep_is_nonfatal(monkeypatch, tmp_path):
    _patch_client(monkeypatch, [], fail=True)
    assert render_main.sweep("http://fake", tmp_path, ["landscape"], True) == 0


def test_render_job_skips_a_disabled_voiceover_language(monkeypatch, tmp_path):
    _patch_client(monkeypatch, [])
    job = render_main.RenderJob("off-1", "http://fake", tmp_path)
    job.language_policy = {"narration_languages": ["en"]}
    calls = []
    monkeypatch.setattr(job, "_run_language",
                        lambda *args: calls.append(args[-1]))

    job.run(None, ["landscape"], True, languages=("en", "ur"))

    assert calls == ["en"], "Urdu must never render while disabled in Settings"


def test_render_job_refuses_when_every_requested_language_is_disabled(monkeypatch, tmp_path):
    _patch_client(monkeypatch, [])
    job = render_main.RenderJob("off-1", "http://fake", tmp_path)
    job.language_policy = {"narration_languages": ["en"]}
    monkeypatch.setattr(job, "_run_language", lambda *args: None)

    with pytest.raises(SystemExit, match="Language policy"):
        job.run(None, ["landscape"], True, languages=("ur",))


def test_render_job_persists_a_qc_rejection_and_raises(monkeypatch, tmp_path):
    """A QC-rejected output is still registered with its report, then the job
    fails so the sweep does not count it as delivered."""
    job = render_main.RenderJob("off-1", "http://fake", tmp_path)
    project = tmp_path / "off-1"
    capture = project / "capture.mp4"
    capture.write_bytes(b"capture")
    job.script_version = 1
    job.script_version_hash = "a" * 64
    job.capture_id = "cap-1"
    job.script_metadata = {}
    job.caption_language = "en"
    job.copy_language = "en"

    monkeypatch.setattr(job, "load_sources", lambda *a, **k: {
        "offer": {"id": "off-1", "title": "Example", "provider": "Acme"},
        "script": {"markdown": "# script"},
        "capture": {"step_log": [], "video_path": str(capture)},
    })
    monkeypatch.setattr(render_main, "materialize", lambda *a, **k: None)
    monkeypatch.setattr(render_main.covers_mod, "generate_covers", lambda *a, **k: {
        "primary": {}, "covers": [],
    })
    monkeypatch.setattr(render_main.covers_mod, "cover_for_preset", lambda *a, **k: {})
    monkeypatch.setattr(render_main.motion_mod, "build_motion_filter", lambda *a, **k: "")
    monkeypatch.setattr(render_main.motion_mod, "motion_metadata", lambda *a, **k: {})
    monkeypatch.setattr(render_main.render_mod, "build_ffmpeg_cmd", lambda *a, **k: ["ffmpeg"])
    monkeypatch.setattr(render_main.render_mod, "describe", lambda cmd: "ffmpeg")

    class Proc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, project_dir):
        output = Path(project_dir) / "renders" / "off-1-landscape.mp4"
        output.write_bytes(b"rendered")
        return Proc()

    monkeypatch.setattr(render_main.render_mod, "run", fake_run)
    monkeypatch.setattr(render_main.render_mod, "probe_duration", lambda *a: 10.0)
    monkeypatch.setattr(render_main, "make_from_env", lambda: None)
    monkeypatch.setattr(render_main.qc_mod, "run", lambda *a, **k: {
        "version": 1, "status": "failed", "errors": ["no audio stream"],
        "warnings": [], "checks": {},
    })

    class FakeApi:
        def __init__(self):
            self.payloads = []

        def post(self, path, json=None):
            self.payloads.append((path, json))

            class Resp:
                status_code = 201

                def json(self):
                    return {"id": "r1"}

            return Resp()

    job.api = FakeApi()
    with pytest.raises(SystemExit, match="failed"):
        job._run_language(str(capture), ["landscape"], True, "cap-1", "en")

    assert len(job.api.payloads) == 1
    payload = job.api.payloads[0][1]
    assert payload["status"] == "qc_failed"
    assert payload["qc_status"] == "failed"
    assert payload["qc_report"]["errors"] == ["no audio stream"]
    assert payload["captions_path"].endswith("assets/captions.srt")


def test_encoder_failure_row_is_a_dead_letter_record(tmp_path):
    row = render_main._render_failure_row(
        preset=render_main.get_preset("landscape"),
        language="en",
        video_path="projects/off-1/renders/off-1-landscape.mp4",
        captions_path="projects/off-1/assets/captions.srt",
        cover_path=None,
        command="ffmpeg -i capture.mp4 out.mp4",
        reason="ffmpeg exited 1 for preset landscape",
        stderr="Invalid data found when processing input",
        expected_duration=10.0,
    )
    assert row["status"] == "render_failed"
    assert row["qc_status"] == "failed"
    assert row["qc_report"]["stage"] == "ffmpeg"
    assert "Invalid data" in row["qc_report"]["details"]["stderr"]
    assert row["video_sha256"] is None
    assert row["duration_s"] is None


def test_missing_ffmpeg_is_reported_with_the_configured_path(monkeypatch):
    """The preflight must honour FFMPEG_PATH (the render/narration modules do)
    and name the binary it looked for — a wrong PATH used to hide the real
    knob."""
    monkeypatch.setattr(render_main, "FFMPEG_PATH", "/nonexistent/ffmpeg-binary")
    monkeypatch.setattr(render_main.shutil, "which", lambda cmd: None)
    with pytest.raises(SystemExit) as exc:
        render_main._require_ffmpeg()
    assert "/nonexistent/ffmpeg-binary" in str(exc.value)


def test_ffmpeg_preflight_passes_when_the_binary_exists(monkeypatch):
    monkeypatch.setattr(render_main, "FFMPEG_PATH", "/usr/bin/ffmpeg")
    monkeypatch.setattr(render_main.shutil, "which", lambda cmd: "/usr/bin/ffmpeg")
    assert render_main._require_ffmpeg() == "/usr/bin/ffmpeg"


# ------------------------------------------------- durable queue drain (v0.33)


class QueueClient:
    """Fake client whose /jobs endpoints speak the real queue contract."""

    def __init__(self, candidates, claims):
        self.candidates = candidates
        self.claims = list(claims)  # claim bodies served in order
        self.results = []
        self.enqueued = []

    def get(self, path, params=None):
        return FakeResponse(self.candidates)

    def post(self, path, json=None):
        if path == "/jobs":
            self.enqueued.append(json)
            return FakeResponse({"id": "job-1", "created": True}, 201)
        if path == "/jobs/claim":
            return FakeResponse(self.claims.pop(0) if self.claims
                                else {"claimed": False})
        if path.startswith("/jobs/") and path.endswith("/result"):
            self.results.append((path.split("/")[2], json))
            return FakeResponse({"id": path.split("/")[2], "status": "done"})
        return FakeResponse({"ok": True})


def _candidate(offer_id="off-1", language="en"):
    return {"offer_id": offer_id, "script_version": 3,
            "script_version_hash": "sh3", "capture_id": "cap-1",
            "missing_presets": ["landscape"], "language": language}


def _claimed_job(offer_id="off-1", language="en"):
    return {"claimed": True, "id": "job-1", "kind": "render_package",
            "entity_id": offer_id,
            "payload": {"offer_id": offer_id, "language": language},
            "lease_expires_at": "2030-01-01T00:00:00Z"}


def test_claimed_render_job_drives_the_render(monkeypatch, tmp_path):
    candidates = [_candidate()]
    client = QueueClient(candidates, [_claimed_job()])
    calls = []

    class FakeJob:
        def __init__(self, offer_id, api_url, out_root):
            self.offer_id = offer_id

        def run(self, capture_video, preset_keys, skip_narration, capture_id=None,
                languages=None):
            calls.append((self.offer_id, capture_id))

    monkeypatch.setattr(render_main, "RenderJob", FakeJob)
    keys = render_main._drain_render_jobs(
        client, "http://fake", tmp_path, ["landscape"], True, "studio", candidates)
    assert keys == {("off-1", "en")}
    job_id, payload = client.results[-1]
    assert payload["ok"] is True and payload["detail"] == "rendered"
    assert calls == [("off-1", "cap-1")], "the claimed job drives the same render path"


def test_stale_render_job_resolves_without_rendering(monkeypatch, tmp_path):
    client = QueueClient([_candidate()], [_claimed_job(offer_id="off-gone")])
    class NeverJob:
        def __init__(self, *a, **k):
            raise AssertionError("no render may start for a stale job")
    monkeypatch.setattr(render_main, "RenderJob", NeverJob)
    keys = render_main._drain_render_jobs(
        client, "http://fake", tmp_path, ["landscape"], True, "studio",
        [_candidate()])
    assert keys == set()
    _, payload = client.results[-1]
    assert payload["ok"] is True and "no longer" in payload["detail"]


def test_failed_render_requeues_the_job(monkeypatch, tmp_path):
    client = QueueClient([_candidate()], [_claimed_job()])

    class BoomJob:
        def __init__(self, offer_id, api_url, out_root):
            pass

        def run(self, **kwargs):
            raise RuntimeError("encoder crashed")

    monkeypatch.setattr(render_main, "RenderJob", BoomJob)
    keys = render_main._drain_render_jobs(
        client, "http://fake", tmp_path, ["landscape"], True, "studio",
        [_candidate()])
    assert keys == set()
    _, payload = client.results[-1]
    assert payload["ok"] is False and payload["retry_after_s"] == 300


def test_queue_unavailable_degrades_to_sweep_only(monkeypatch, tmp_path):
    candidates = [_candidate()]
    client = QueueClient(candidates, [])
    client.post = lambda path, json=None: FakeResponse({"detail": "not found"}, 404)
    calls = []

    class FakeJob:
        def __init__(self, offer_id, api_url, out_root):
            self.offer_id = offer_id

        def run(self, capture_video, preset_keys, skip_narration, capture_id=None,
                languages=None):
            calls.append(self.offer_id)

    monkeypatch.setattr(render_main, "RenderJob", FakeJob)
    _patch_client(monkeypatch, candidates)
    assert render_main._ensure_render_jobs(client, candidates) == 0
    assert render_main._drain_render_jobs(
        client, "http://fake", tmp_path, ["landscape"], True, "studio",
        candidates) == set()
    # the classic sweep still renders the candidate
    rendered = render_main.sweep("http://fake", tmp_path, ["landscape"], True, limit=5)
    assert rendered == 1


def test_kill_knob_disables_the_render_queue(monkeypatch, tmp_path):
    monkeypatch.setenv("MTK_RENDER_JOB_QUEUE", "0")
    client = QueueClient([_candidate()], [_claimed_job()])
    assert render_main._ensure_render_jobs(client, [_candidate()]) == 0
    assert render_main._drain_render_jobs(
        client, "http://fake", tmp_path, ["landscape"], True, "studio",
        [_candidate()]) == set()


def test_lease_keeper_flags_a_lost_lease_and_stops(monkeypatch):
    """A 409 on renewal means another holder owns the job now: the keeper
    sets `lost` (so no outcome is reported) and stops touching."""
    import threading

    monkeypatch.setattr(render_main, "RENDER_LEASE_TOUCH_S", 0)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(409, json={"detail": "held by another worker"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")
    stop, lost = threading.Event(), threading.Event()
    render_main._lease_keeper(client, "job-1", stop, "render-a-1", lost)
    assert lost.is_set()
    assert len(calls) == 1
    assert b'"worker":"render-a-1"' in calls[0].content.replace(b" ", b"")

