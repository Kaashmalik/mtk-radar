"""Caption pipeline tests — deterministic cues, valid srt/vtt."""

import pytest

from captions import build_cues, segments_from_step_log, to_ass, to_srt, to_vtt

SEGMENTS = [
    {"text": "One-year .TECH domain free for verified students."},
    {"text": "Open the official benefit page and read the terms."},
    {"text": "Use code STUDENT24 at checkout before January 31, 2027."},
]


class TestBuildCues:
    def test_contiguous_monotonic_timing(self):
        cues = build_cues(SEGMENTS)
        assert len(cues) == 3
        for prev, cur in zip(cues, cues[1:]):
            assert abs(prev["end"] - cur["start"]) < 0.001
            assert cur["start"] > prev["start"]

    def test_duration_clamped(self):
        cues = build_cues([{"text": "word " * 200}])  # way over max
        assert cues[0]["end"] - cues[0]["start"] <= 8.0
        cues = build_cues([{"text": "hi"}])  # under min
        assert cues[0]["end"] - cues[0]["start"] >= 1.2

    def test_html_stripped_and_indexed(self):
        cues = build_cues([{"text": "<b>bold</b> claim  here"}])
        assert cues[0]["text"] == "bold claim here"
        assert cues[0]["index"] == 1

    def test_empty_segments_no_cues(self):
        assert build_cues([]) == []
        assert build_cues([{"text": ""}]) == []

    def test_long_text_is_split_into_readable_chunks(self):
        text = " ".join(["verified student offer"] * 30)
        cues = build_cues([{"text": text}])
        assert len(cues) > 1, "a long step must not become one unreadable cue"
        assert all(len(cue["text"]) <= 84 for cue in cues)
        assert " ".join(cue["text"] for cue in cues) == text
        for prev, cur in zip(cues, cues[1:]):
            assert abs(prev["end"] - cur["start"]) < 0.001

    def test_step_log_download_ordering(self):
        step_log = [
            {"n": 2, "title": "terms page"},
            {"n": 0, "title": "offer page"},
            {"n": 1, "description": "check eligibility"},
        ]
        segments = segments_from_step_log(step_log)
        assert segments[0]["text"] == "offer page"
        assert len(segments) == 3

    def test_real_start_timestamp_is_honoured(self):
        cues = build_cues([
            {"text": "opening", "start": 0},
            {"text": "proof page", "start": 12.5},
        ])
        assert cues[1]["start"] >= 12.5

    def test_start_before_previous_cue_never_overlaps(self):
        cues = build_cues([
            {"text": "a long enough first line", "start": 5},
            {"text": "second", "start": 1},
        ])
        assert cues[1]["start"] >= cues[0]["end"]

    def test_iso_step_log_becomes_relative_seconds(self):
        segments = segments_from_step_log([
            {"n": 0, "title": "opening", "at": "2026-10-22T10:00:00Z"},
            {"n": 1, "title": "proof", "at": "2026-10-22T10:00:14Z"},
        ])
        assert segments[1]["start"] == 14.0
        cues = build_cues(segments)
        assert cues[1]["start"] >= 14.0


class TestSrt:
    def test_format_standard(self):
        srt = to_srt(build_cues(SEGMENTS))
        blocks = [b for b in srt.strip().split("\n\n") if b]
        assert len(blocks) == 3
        assert blocks[0].split("\n")[0] == "1"
        assert "-->" in blocks[1]
        assert "," in blocks[0].split("\n")[1]  # srt uses comma millis

    def test_ends_with_newline(self):
        assert to_srt(build_cues(SEGMENTS)).endswith("\n")


class TestVtt:
    def test_header_and_dot_millis(self):
        vtt = to_vtt(build_cues(SEGMENTS))
        assert vtt.startswith("WEBVTT\n\n")
        blocks = [b for b in vtt.strip().split("\n\n") if b][1:]  # skip header
        assert len(blocks) == 3
        for block in blocks:
            tc_line = block.split("\n")[1]
            assert "." in tc_line
            assert "," not in tc_line  # dot millis in the timecode, srt uses comma

    def test_empty_is_header_only(self):
        assert to_vtt([]) == "WEBVTT\n"


class TestAss:
    def test_styled_header_and_events(self):
        ass = to_ass(build_cues(SEGMENTS), language="en")
        assert ass.startswith("[Script Info]")
        assert "PlayResX: 1920" in ass
        assert "Dialogue: 0,0:00:00.00" in ass
        assert ass.count("Dialogue:") == 3

    def test_urdu_uses_rtl_font_and_escapes_braces(self):
        ass = to_ass([{"text": "سلام {tag}", "start": 0, "end": 2}], language="ur")
        assert "Noto Nastaliq Urdu" in ass
        assert "\\{tag\\}" in ass
        assert "0:00:00.00,0:00:02.00" in ass

    def test_english_uses_readable_font_and_fits_vertical(self, monkeypatch):
        monkeypatch.delenv("MTK_CAPTION_FONT", raising=False)
        ass = to_ass([{"text": "Official terms below", "start": 0, "end": 2}],
                     language="en", width=1080, height=1920)
        assert "DejaVu Sans" in ass
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "WrapStyle: 0" in ass
        # Larger type and safe margins for a 9:16 frame.
        assert "Style: Default,DejaVu Sans,64" in ass
        assert ",120,120,170,1" in ass

    def test_caption_font_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("MTK_CAPTION_FONT", "Inter")
        ass = to_ass([{"text": "Hello", "start": 0, "end": 2}], language="en")
        assert "Style: Default,Inter,52" in ass


def test_measured_speech_duration_is_honoured():
    cues = build_cues([
        {"text": "First spoken line", "start": 0, "duration": 4.25},
        {"text": "Second spoken line", "start": 4.25, "duration": 2.5},
    ])
    assert cues[0]["end"] - cues[0]["start"] == pytest.approx(4.25, abs=0.01)
    assert cues[1]["start"] == pytest.approx(4.25, abs=0.01)
    assert cues[1]["end"] - cues[1]["start"] == pytest.approx(2.5, abs=0.01)
