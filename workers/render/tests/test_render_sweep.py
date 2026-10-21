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
