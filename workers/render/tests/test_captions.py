"""Caption pipeline tests — deterministic cues, valid srt/vtt."""

from captions import build_cues, segments_from_step_log, to_srt, to_vtt

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

    def test_step_log_download_ordering(self):
        step_log = [
            {"n": 2, "title": "terms page"},
            {"n": 0, "title": "offer page"},
            {"n": 1, "description": "check eligibility"},
        ]
        segments = segments_from_step_log(step_log)
        assert segments[0]["text"] == "offer page"
        assert len(segments) == 3


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
