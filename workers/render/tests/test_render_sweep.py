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
