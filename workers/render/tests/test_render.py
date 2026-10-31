"""Render pipeline tests — FFmpeg command assembly, presets, manifest."""

import pytest

from presets import PRESETS, get_preset
from project import build_edit_manifest, write_preset_captions
from render import Loudness, build_ffmpeg_cmd, describe, resolve_timeline


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

    def test_vertical_full_frame_composition(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("vertical"))
        joined = describe(cmd)
        assert "-filter_complex" in joined
        assert "force_original_aspect_ratio=decrease" in joined, \
            "the full 16:9 frame must be preserved"
        assert "overlay=(W-w)/2:(H-h)/2" in joined
        assert "boxblur=" in joined, "the 9:16 background must be a blurred fill"
        assert "-map '[vout]'" in joined

    def test_captions_burned_with_relative_path(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"), captions="assets/captions.srt"
        )
        joined = describe(cmd)
        assert "subtitles=assets/captions.srt" in joined

    def test_each_preset_gets_frame_specific_captions(self, tmp_path):
        cues = [{"text": "Readable on every frame", "start": 0, "end": 2}]
        landscape = write_preset_captions(
            tmp_path, cues, "landscape", 1920, 1080,
            language="en", caption_language="en",
        )
        vertical = write_preset_captions(
            tmp_path, cues, "vertical", 1080, 1920,
            language="en", caption_language="en",
        )
        assert landscape == "assets/captions-landscape.ass"
        assert vertical == "assets/captions-vertical.ass"
        landscape_text = (tmp_path / landscape).read_text()
        vertical_text = (tmp_path / vertical).read_text()
        assert "PlayResX: 1920" in landscape_text and "PlayResY: 1080" in landscape_text
        assert "PlayResX: 1080" in vertical_text and "PlayResY: 1920" in vertical_text
        assert "Style: Default,DejaVu Sans,64" in vertical_text, \
            "vertical captions need larger type and vertical margins"

    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError):
            build_ffmpeg_cmd(
                "capture.mp4", "out.mp4", get_preset("landscape"), captions="C:/abs/cap.srt"
            )

    def test_narration_maps_second_input_and_measured_duration(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"),
            narration="assets/narration.mp3", duration=12.0,
        )
        joined = describe(cmd)
        assert "-i assets/narration.mp3" in joined
        assert "-map 1:a" in joined
        assert "-t 12.000" in joined
        assert "-shortest" not in cmd, "the shorter stream must not decide the timeline"

    def test_narration_requires_a_measured_duration(self):
        with pytest.raises(ValueError, match="measured duration"):
            build_ffmpeg_cmd(
                "capture.mp4", "out.mp4", get_preset("landscape"),
                narration="assets/narration.mp3",
            )

    def test_without_narration_uses_capture_audio_if_present(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("landscape"))
        assert cmd[cmd.index("-map") + 1] == "0:v"
        assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "0:a?"
        assert "-shortest" not in cmd
        assert "-t" not in cmd


class TestDeliveryFlags:
    @pytest.mark.parametrize("key", ["landscape", "vertical"])
    def test_full_hd_delivery_is_explicit(self, key):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset(key))

        def arg(flag):
            return cmd[cmd.index(flag) + 1]

        assert arg("-pix_fmt") == "yuv420p"
        assert arg("-profile:v") == "high"
        assert arg("-g") == "60", "2-second GOP at 30 fps"
        assert arg("-colorspace") == "bt709"
        assert arg("-ar") == "48000" and arg("-ac") == "2"
        assert int(arg("-crf")) <= 18
        assert int(arg("-maxrate").rstrip("k")) >= 8000, "≥ YouTube 1080p SDR guidance"
        assert cmd[-1] == "out.mp4", "output stays the final argument"

    def test_audio_is_normalized_to_the_qc_target(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"),
            narration="assets/narration.mp3", duration=10.0,
            loudness=Loudness(target_lufs=-14.0, max_true_peak=-1.0),
        )
        af = cmd[cmd.index("-af") + 1]
        assert af.startswith("loudnorm=I=-14:TP=-1.5:LRA=11")
        assert af.endswith("aresample=48000"), "loudnorm upsamples to 192 kHz"

    def test_vertical_normalizes_audio_outside_the_video_graph(self):
        cmd = build_ffmpeg_cmd("capture.mp4", "out.mp4", get_preset("vertical"))
        assert "loudnorm" not in cmd[cmd.index("-filter_complex") + 1]
        assert "loudnorm" in cmd[cmd.index("-af") + 1]

    def test_loudness_can_be_disabled(self):
        cmd = build_ffmpeg_cmd(
            "capture.mp4", "out.mp4", get_preset("landscape"), loudness=None
        )
        assert "-af" not in cmd


class TestTimeline:
    def test_speech_is_authoritative_and_capture_overshoot_is_trimmed(self):
        expected, error = resolve_timeline(15.0, 12.0, narration_used=True)
        assert expected == 12.0
        assert error is None

    def test_capture_that_cannot_cover_speech_fails_closed(self):
        expected, error = resolve_timeline(8.0, 12.0, narration_used=True)
        assert expected == 12.0
        assert error and "refusing to truncate narration" in error

    def test_missing_capture_probe_fails_closed(self):
        expected, error = resolve_timeline(None, 12.0, narration_used=True)
        assert expected == 12.0
        assert error and "unavailable" in error

    def test_unreadable_narration_probe_fails_closed(self):
        expected, error = resolve_timeline(12.0, None, narration_used=True)
        assert expected == 12.0
        assert error and "unreadable" in error

    def test_without_narration_the_capture_is_the_timeline(self):
        expected, error = resolve_timeline(9.5, None)
        assert expected == 9.5
        assert error is None


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
