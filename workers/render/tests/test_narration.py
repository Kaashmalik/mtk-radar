"""v0.14: mixed narration track — per-segment TTS files become ONE audio file
that the render actually maps in. The v0.12 flow disclosed synthetic narration
(satisfying §5 labeling) while the video still carried capture audio — a
silent mismatch between disclosure metadata and the deliverable."""

from pathlib import Path

import narration


class TestFfmpegConcatCmd:
    def test_reencode_command_shape(self):
        """v0.17: stream-copy only worked when every TTS segment shared codec
        params — a provider/model change between retries silently corrupted
        boundaries. Re-encode makes the concat codec-agnostic."""
        cmd = narration.ffmpeg_concat_cmd(Path("/p/narration.txt"), Path("/p/narration.mp3"))
        assert cmd[0] == narration.FFMPEG
        assert "-f" in cmd and cmd[cmd.index("-f") + 1] == "concat"
        assert cmd[cmd.index("-safe") + 1] == "0", "absolute segment paths need -safe 0"
        assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "libmp3lame"
        assert cmd[cmd.index("-ar") + 1] == "44100"
        assert ("-c", "copy") not in list(zip(cmd, cmd[1:])), "no blind stream-copy"
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
            stderr = ""
            stdout = "5.0\n"

        def fake_run(cmd, **k):
            if "ffprobe" in str(cmd[0]):
                p = Proc()
                if str(out) in str(cmd[-1]):
                    p.stdout = "10.0\n"  # mixed track covers both 5s segments
                return p
            out.write_bytes(b"mixed-audio")  # simulate ffmpeg output
            return Proc()

        monkeypatch.setattr(subprocess, "run", fake_run)
        segs = [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")]
        for s in segs:
            Path(s).write_bytes(b"x")
        result = narration.mix_segments(segs, tmp_path)
        assert result == out and out.stat().st_size > 0

    def test_truncated_track_refused(self, tmp_path: Path, monkeypatch):
        """Output that decodes but covers <85% of the summed segment duration
        is corruption (old silent boundary-loss) — refuse, don't ship."""
        import subprocess

        out = tmp_path / "narration.mp3"
        durations = {str(tmp_path / "narration.mp3"): "2.0"}  # 2s out of 10s expected

        class Proc:
            returncode = 0
            stderr = ""

            @property
            def stdout(self):
                pass

        def fake_run(cmd, **k):
            p = Proc()
            p.stdout = durations.get(cmd[-1], "5.0") + "\n"
            if "ffmpeg" in str(cmd[0]):
                out.write_bytes(b"partial")
            return p

        monkeypatch.setattr(subprocess, "run", fake_run)
        segs = [str(tmp_path / "a.mp3"), str(tmp_path / "b.mp3")]
        for s in segs:
            Path(s).write_bytes(b"x")
        assert narration.mix_segments(segs, tmp_path) is None

    def test_undecodable_output_refused(self, tmp_path: Path, monkeypatch):
        """A file that exists but cannot be probed must not enter the render."""
        import subprocess

        out = tmp_path / "narration.mp3"

        class Proc:
            returncode = 0
            stderr = ""
            stdout = ""  # ffprobe yields nothing → duration unreadable

        def fake_run(cmd, **k):
            if "ffmpeg" in str(cmd[0]):
                out.write_bytes(b"garbage-that-is-not-audio")
            return Proc()

        monkeypatch.setattr(subprocess, "run", fake_run)
        segs = [str(tmp_path / "a.mp3")]
        Path(segs[0]).write_bytes(b"x")
        assert narration.mix_segments(segs, tmp_path) is None

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
