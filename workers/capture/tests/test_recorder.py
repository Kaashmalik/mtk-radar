"""FFmpeg screen recorder (M2) — argv per OS and clean stop, no FFmpeg needed."""

import subprocess

import recorder
from recorder import CaptureConfig, ScreenRecorder, build_capture_cmd


def _arg(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_playwright_stays_the_default_backend(monkeypatch):
    monkeypatch.delenv("MTK_CAPTURE_BACKEND", raising=False)
    assert recorder.backend() == "playwright"
    monkeypatch.setenv("MTK_CAPTURE_BACKEND", "FFmpeg")
    assert recorder.backend() == "ffmpeg"
    monkeypatch.setenv("MTK_CAPTURE_BACKEND", "something-else")
    assert recorder.backend() == "playwright"


def test_windows_grabs_exactly_the_1080p_region(tmp_path):
    cmd = build_capture_cmd(tmp_path / "c.mkv", CaptureConfig(offset_x=10, offset_y=20), "win32")
    assert _arg(cmd, "-f") == "gdigrab" and _arg(cmd, "-i") == "desktop"
    assert _arg(cmd, "-video_size") == "1920x1080"
    assert _arg(cmd, "-offset_x") == "10" and _arg(cmd, "-offset_y") == "20"
    assert int(_arg(cmd, "-crf")) <= 14 and _arg(cmd, "-pix_fmt") == "yuv420p"
    assert cmd[-1].endswith(".mkv")
    assert "dshow" not in cmd, "no audio device unless configured"


def test_linux_and_mac_backends(tmp_path):
    linux = build_capture_cmd(tmp_path / "c.mkv", CaptureConfig(display=":1"), "linux")
    assert _arg(linux, "-f") == "x11grab" and _arg(linux, "-i") == ":1+0,0"
    mac = build_capture_cmd(tmp_path / "c.mkv", CaptureConfig(screen_index="2"), "darwin")
    assert _arg(mac, "-f") == "avfoundation" and _arg(mac, "-i") == "2:none"
    assert _arg(mac, "-vf").startswith("crop=1920:1080")


def test_optional_audio_is_encoded_as_aac(tmp_path):
    cmd = build_capture_cmd(tmp_path / "c.mkv", CaptureConfig(audio_device="Mic"), "win32")
    assert "audio=Mic" in cmd and _arg(cmd, "-c:a") == "aac"


def test_kiosk_launch_covers_the_recorded_region():
    args = recorder.browser_launch_args(CaptureConfig(offset_x=5, offset_y=7))
    assert "--kiosk" in args and "--window-size=1920,1080" in args
    assert "--window-position=5,7" in args


class FakeProc:
    def __init__(self, out):
        self.out, self.stdin_data, self.terminated = out, b"", False

        class In:
            def write(inner, data):
                self.stdin_data += data

            def flush(inner):
                pass

            def close(inner):
                out.write_bytes(b"matroska")

        self.stdin, self.stderr = In(), None

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self.terminated = True


def test_stop_sends_q_and_returns_the_finalized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder.time, "sleep", lambda s: None)
    made = {}

    def popen(cmd, **kw):
        made["proc"] = FakeProc(tmp_path / "capture.mkv")
        made["cmd"] = cmd
        return made["proc"]

    rec = ScreenRecorder(tmp_path / "capture", CaptureConfig(), popen=popen, platform="linux")
    rec.start()
    out = rec.stop()
    assert made["proc"].stdin_data == b"q"
    assert out == tmp_path / "capture.mkv" and out.read_bytes() == b"matroska"
    assert rec.stop() is None, "idempotent"


def test_hung_recorder_is_terminated(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder.time, "sleep", lambda s: None)

    class Hung(FakeProc):
        def wait(self, timeout=None):
            if not self.terminated:
                raise subprocess.TimeoutExpired("ffmpeg", timeout)
            return 0

    proc = Hung(tmp_path / "capture.mkv")
    rec = ScreenRecorder(tmp_path / "capture", CaptureConfig(),
                         popen=lambda cmd, **kw: proc, platform="linux")
    rec.start()
    rec.stop(timeout_s=0.01)
    assert proc.terminated
