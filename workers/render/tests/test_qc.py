"""Render QC tests (v0.29).

All FFmpeg/FFprobe calls are faked through qc._run_command; the real binaries
are not required in CI. The report shape, gating thresholds, exempt ranges and
caption geometry are the contract the render worker persists.
"""

from pathlib import Path

import pytest

import qc
from captions import to_ass


class Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _probe(*, width=1920, height=1080, audio=True, duration="10.0"):
    streams = [{
        "codec_type": "video", "codec_name": "h264", "width": width,
        "height": height, "avg_frame_rate": "30/1", "duration": duration,
        "pix_fmt": "yuv420p", "bit_rate": "4000000",
        "sample_aspect_ratio": "1:1", "display_aspect_ratio": f"{width}:{height}",
    }]
    if audio:
        streams.append({
            "codec_type": "audio", "codec_name": "aac", "sample_rate": "48000",
            "channels": 2, "bit_rate": "192000",
        })
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": duration, "size": "1000000", "bit_rate": "4200000",
        },
        "streams": streams,
    }


class FakeRunner:
    def __init__(self, *, probe=None, decode=None, video_events="",
                 silence="", loudness=None):
        self.probe = probe if probe is not None else _probe()
        self.decode = decode or Proc()
        self.video_events = video_events
        self.silence = silence
        self.loudness = loudness or '{"input_i":"-16.0","input_tp":"-1.5","input_lra":"5.0"}'
        self.calls = []

    def __call__(self, cmd, *, timeout):
        self.calls.append((list(cmd), timeout))
        if cmd[-1] == "-version":
            return Proc(stdout="ffmpeg version 7-test\n")
        if "-print_format" in cmd:
            if isinstance(self.probe, Exception):
                raise self.probe
            import json
            return Proc(stdout=json.dumps(self.probe))
        if "-vf" in cmd:
            return Proc(stderr=self.video_events)
        if "-af" in cmd:
            filt = cmd[cmd.index("-af") + 1]
            if "loudnorm" in filt:
                return Proc(stderr=f"measurement follows\n{self.loudness}\n")
            if "silencedetect" in filt:
                return Proc(stderr=self.silence)
        if "-map" in cmd:
            return self.decode
        return Proc()


@pytest.fixture()
def media(tmp_path):
    path = tmp_path / "render.mp4"
    path.write_bytes(b"not-a-real-video")
    return path


@pytest.fixture()
def captions(tmp_path):
    path = tmp_path / "captions.ass"
    path.write_text(to_ass([
        {"text": "Official terms below", "start": 0, "end": 2},
    ], language="en", width=1080, height=1920), encoding="utf-8")
    return path


def _run(monkeypatch, media, runner, captions_path=None, **overrides):
    monkeypatch.setattr(qc, "_run_command", runner)
    kwargs = {
        "width": 1920, "height": 1080, "fps": 30, "preset": "landscape",
        "expected_duration": 10.0, "captions_path": captions_path,
    }
    kwargs.update(overrides)
    return qc.run(media, **kwargs)


def test_clean_render_passes_and_records_measurements(monkeypatch, media, captions):
    runner = FakeRunner(probe=_probe(width=1080, height=1920))
    report = _run(monkeypatch, media, runner, captions_path=captions,
                  width=1080, height=1920)
    assert report["status"] == "passed", report["errors"]
    assert report["checks"]["streams"]["details"]["video"]["width"] == 1080
    assert report["checks"]["streams"]["details"]["video"]["height"] == 1920
    assert report["checks"]["streams"]["details"]["audio"]["sample_rate"] == 48000
    assert report["checks"]["loudness"]["details"]["integrated_lufs"] == -16.0
    assert report["checks"]["captions"]["status"] == "passed"
    assert report["tool_versions"]["ffmpeg"].startswith("ffmpeg version")


def test_wrong_resolution_and_missing_audio_fail(monkeypatch, media):
    runner = FakeRunner(probe=_probe(width=1280, height=720, audio=False))
    report = _run(monkeypatch, media, runner)
    assert report["status"] == "failed"
    assert any("1280x720" in error for error in report["errors"])
    assert any("no audio stream" in error for error in report["errors"])
    assert report["checks"]["silence"]["status"] == "skipped"
    assert report["checks"]["loudness"]["status"] == "skipped"


def test_full_decode_error_blocks(monkeypatch, media):
    runner = FakeRunner(decode=Proc(returncode=1, stderr="Invalid data found"))
    report = _run(monkeypatch, media, runner)
    assert report["status"] == "failed"
    assert any("decode:" in error and "Invalid data" in error
               for error in report["errors"])


def test_black_freeze_and_silence_events_block(monkeypatch, media):
    runner = FakeRunner(
        video_events=(
            "[blackdetect @ 0x1] black_start:1 black_end:3 black_duration:2\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 4\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 8\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 12\n"
        ),
        silence="[silencedetect @ 0x1] silence_start: 2\n"
                "[silencedetect @ 0x1] silence_end: 6 | silence_duration: 4\n",
    )
    report = _run(monkeypatch, media, runner)
    assert report["status"] == "failed"
    assert any("uncovered black" in error for error in report["errors"])
    assert any("uncovered freeze" in error for error in report["errors"])
    assert any("uncovered silent" in error for error in report["errors"])


def test_annotated_exempt_ranges_allow_intentional_stills(monkeypatch, media):
    runner = FakeRunner(
        video_events=(
            "[blackdetect @ 0x1] black_start:1 black_end:3 black_duration:2\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 4\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 8\n"
            "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 12\n"
        ),
        silence="[silencedetect @ 0x1] silence_start: 2\n"
                "[silencedetect @ 0x1] silence_end: 6 | silence_duration: 4\n",
    )
    report = _run(
        monkeypatch, media, runner,
        exempt_ranges=[
            {"start": 0, "end": 3.1, "reason": "static official page"},
            {"start": 3.9, "end": 12.1, "reason": "static official page"},
            {"start": 1.9, "end": 6.1, "reason": "intentional silent demo"},
        ],
    )
    assert report["status"] == "passed", report["errors"]


def test_loudness_outside_target_and_clipping_fail(monkeypatch, media):
    runner = FakeRunner(
        loudness='{"input_i":"-22.0","input_tp":"0.5","input_lra":"5.0"}'
    )
    report = _run(monkeypatch, media, runner)
    assert report["status"] == "failed"
    assert any("outside" in error for error in report["errors"])
    assert any("true peak" in error for error in report["errors"])


def test_duration_mismatch_blocks(monkeypatch, media):
    runner = FakeRunner(probe=_probe(duration="6.0"))
    report = _run(monkeypatch, media, runner, expected_duration=10.0)
    assert report["status"] == "failed"
    assert any("duration 6.00s" in error for error in report["errors"])


def test_caption_safe_area_passes(monkeypatch, media, captions):
    monkeypatch.setattr(qc, "_run_command", FakeRunner())
    result = qc.check_captions(captions, width=1080, height=1920,
                               config=qc.QCConfig())
    assert result["status"] == "passed", result["errors"]
    assert result["details"]["cue_count"] == 1


def test_caption_overflow_and_unbreakable_word_fail(monkeypatch, media, tmp_path):
    long_text = " ".join(["verified student benefit"] * 80)
    path = tmp_path / "long.ass"
    path.write_text(to_ass([
        {"text": long_text, "start": 0, "end": 8},
    ], language="en", width=1080, height=1920), encoding="utf-8")
    monkeypatch.setattr(qc, "_run_command", FakeRunner())
    result = qc.check_captions(path, width=1080, height=1920,
                               config=qc.QCConfig())
    assert result["status"] == "failed"
    assert any("safe area" in error or "wide" in error for error in result["errors"])

    unbreakable = tmp_path / "word.ass"
    unbreakable.write_text(to_ass([
        {"text": "X" * 200, "start": 0, "end": 8},
    ], language="en", width=1080, height=1920), encoding="utf-8")
    result = qc.check_captions(unbreakable, width=1080, height=1920,
                               config=qc.QCConfig())
    assert result["status"] == "failed"
    assert any("unbreakable word" in error for error in result["errors"])


def test_missing_media_returns_a_report_not_an_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(qc, "_run_command", FakeRunner())
    report = qc.run(tmp_path / "missing.mp4", width=1920, height=1080, fps=30,
                    preset="landscape")
    assert report["status"] == "failed"
    assert "not found" in report["errors"][0]


def test_failure_report_is_json_safe():
    report = qc.failure_report(
        stage="ffmpeg", errors=["ffmpeg exited 1"], preset="vertical",
        expected_duration=10.0,
    )
    assert report["status"] == "failed" and report["stage"] == "ffmpeg"
    assert report["errors"] == ["ffmpeg exited 1"]
    assert report["preset"] == "vertical"


def test_blank_env_values_keep_code_defaults(monkeypatch):
    monkeypatch.setenv("MTK_RENDER_QC_REQUIRE_AUDIO", "")
    monkeypatch.setenv("MTK_RENDER_QC_TARGET_LUFS", "")
    config = qc.QCConfig.from_env()
    assert config.require_audio is True
    assert config.target_lufs == -16.0


def test_exempt_range_parser_normalizes_and_ignores_bad_values():
    ranges = qc.parse_exempt_ranges(
        '[{"start": 5, "end": 8}, {"start": 9, "end": 9}, {"start": -2, "end": 1}]'
    )
    assert ranges == [
        {"start": 0.0, "end": 1.0, "reason": "annotated still/official page"},
        {"start": 5.0, "end": 8.0, "reason": "annotated still/official page"},
    ]