"""v0.14: mixed narration track — per-segment TTS files become ONE audio file
that the render actually maps in. The v0.12 flow disclosed synthetic narration
(satisfying §5 labeling) while the video still carried capture audio — a
silent mismatch between disclosure metadata and the deliverable."""

from pathlib import Path

import narration


class TestFfmpegConcatCmd:
    def test_stream_copy_command_shape(self):
        cmd = narration.ffmpeg_concat_cmd(Path("/p/narration.txt"), Path("/p/narration.mp3"))
        assert cmd[0] == narration.FFMPEG
        assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "concat"
        assert cmd[cmd.index("-safe") + 1] == "0", "absolute segment paths need -safe 0"
        assert cmd[cmd.index("-c") + 1] == "copy", "identical-codec segments need no re-encode"
        assert cmd[-1] == "/p/narration.mp3"


class TestConcatList:
    def test_every_segment_listed_in_order(self, tmp_path: Path):
        segs = [str(tmp_path / f"narration-{i:03d}.mp3") for i in range(3)]
        for s in segs:
            Path(s).write_bytes(b"x")
        list_file = narration.concat_paths(segs, tmp_path / "narration.mp3")
        lines = list_file.read_text().splitlines()
        assert lines == [f"file '{s}'" for s in segs]

    def test_no_paths_no_list(self, tmp_path: Path):
        assert narration.concat_paths([], tmp_path / "narration.mp3") is None


class TestMixSegments:
    def test_failure_yields_none_never_a_broken_track(self, tmp_path: Path, monkeypatch):
        import subprocess

        def boom(*a, **k):
            raise RuntimeError("ffmpeg missing")

        monkeypatch.setattr(subprocess, "run", boom)
        segs = [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")]
        for s in segs:
            Path(s).write_bytes(b"x")
        assert narration.mix_segments(segs, tmp_path) is None

    def test_failed_exit_yields_none(self, tmp_path: Path, monkeypatch):
        import subprocess

        class Proc:
            returncode = 1
            stderr = "boom"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: Proc())
        segs = [str(tmp_path / "a.mp3")]
        Path(segs[0]).write_bytes(b"x")
        assert narration.mix_segments(segs, tmp_path) is None

    def test_success_returns_track(self, tmp_path: Path, monkeypatch):
        import subprocess

        out = tmp_path / "narration.mp3"

        class Proc:
            returncode = 0

        def fake_run(cmd, **k):
            out.write_bytes(b"mixed-audio")  # simulate ffmpeg output
            return Proc()

        monkeypatch.setattr(subprocess, "run", fake_run)
        segs = [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")]
        for s in segs:
            Path(s).write_bytes(b"x")
        result = narration.mix_segments(segs, tmp_path)
        assert result == out and out.stat().st_size > 0

    def test_zero_byte_output_treated_as_failure(self, tmp_path: Path, monkeypatch):
        import subprocess

        out = tmp_path / "narration.mp3"
        out.write_bytes(b"")  # ffmpeg "succeeded" but produced nothing

        class Proc:
            returncode = 0

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: Proc())
        segs = [str(tmp_path / "a.mp3")]
        Path(segs[0]).write_bytes(b"x")
        assert narration.mix_segments(segs, tmp_path) is None

    def test_disclosure_stays_false_without_track(self):
        """The contract main.py relies on: no track → used=False → no label."""
        assert narration.disclosure_record(used=False) == {"synthetic_narration": False}
