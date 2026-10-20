"""Render pipeline tests — FFmpeg command assembly, presets, manifest."""

import pytest

from presets import PRESETS, get_preset
from project import build_edit_manifest
from render import build_ffmpeg_cmd, describe


class TestPresets:
    def test_both_platform_presets(self):
        assert set(PRESETS) == {"landscape", "vertical"}
        assert get_preset("landscape").width == 1920
        assert get_preset("vertical").height == 1920

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError):
            get_preset("square")


class TestFfmpegCommand:
    def test_landscape_base(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("landscape"))
        joined = describe(cmd)
        assert " -y -i capture.mp4 " in joined
        assert "scale=1920:1080:flags=lanczos" in joined
        assert "libx264" in joined and "+faststart" in joined
        assert "subtitles" not in joined

    def test_vertical_crop_chain(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("vertical"))
        joined = describe(cmd)
        assert "scale=-2:1920:flags=lanczos,crop=1080:1920" in joined

    def test_captions_burned_with_relative_path(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"), captions="assets/captions.srt"
        )
        joined = describe(cmd)
        assert "subtitles=assets/captions.srt" in joined

    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError):
            build_ffmpeg_cmd(
                "capture.mp4", "out.mp4", get_preset("landscape"), captions="C:/abs/cap.srt"
            )

    def test_narration_maps_second_input(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"), narration="assets/narration.mp3"
        )
        joined = describe(cmd)
        assert "-i assets/narration.mp3" in joined
        assert "-map 1:a" in joined
        assert "-shortest" in joined

    def test_without_narration_uses_capture_audio_if_present(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("landscape"))
        assert cmd[cmd.index("-map") + 1] == "0:v"
        assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "0:a?"
        assert "-shortest" not in cmd


class TestEditManifest:
    def test_full_manifest_shape(self):
        manifest = build_edit_manifest(
            offer={"id": "o1", "title": "One-year .tech", "provider": ".TECH", "state": "verified"},
            script_version=2,
            capture_id="c1",
            capture_video="captures/raw.mp4",
            srt="assets/captions.srt",
            vtt="assets/captions.vtt",
            narration_used=True,
            renders=[{"preset": "landscape", "path": "renders/o1-landscape.mp4", "duration_s": 212.5}],
        )
        assert manifest["product"] == "MTK RADAR AI"
        assert manifest["sources"]["script_version"] == 2
        assert manifest["disclosure"] == {"synthetic_narration": True, "label_required": True}
        assert manifest["renders"][0]["duration_s"] == 212.5

    def test_no_narration_discloses_fallback(self):
        manifest = build_edit_manifest(
            offer={"id": "o1"},
            script_version=None, capture_id=None, capture_video=None,
            srt=None, vtt=None, narration_used=False, renders=[],
        )
        assert manifest["disclosure"] == {"synthetic_narration": False, "label_required": False}
        assert manifest["sources"]["narration"]["fallback"] == "capture audio"

    def test_revision_note_present(self):
        manifest = build_edit_manifest(
            offer={}, script_version=None, capture_id=None, capture_video=None,
            srt=None, vtt=None, narration_used=False, renders=[],
        )
        assert "regenerate" in manifest["revision_note"]
