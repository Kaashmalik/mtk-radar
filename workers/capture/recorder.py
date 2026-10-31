"""High-quality screen recorder for guided captures (M2, 2026-10-28 plan).

Playwright's built-in `record_video` writes low-bitrate VP8 WebM: small UI and
code text arrives soft before the render worker ever sees it, and no 1080p
export can restore that detail. This backend records the screen region the
browser occupies with FFmpeg at near-lossless quality instead.

Privacy: a screen recorder captures whatever is in that region — including
notifications or windows dragged over it. It is therefore OPT-IN
(`MTK_CAPTURE_BACKEND=ffmpeg`), the browser is launched in kiosk mode exactly
over the recorded region, and the human redaction review stays mandatory.

Output is Matroska (.mkv): if the recorder is killed mid-session the file is
still readable, where an MP4 without its index would be lost.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
WIDTH, HEIGHT = 1920, 1080


@dataclass(frozen=True)
class CaptureConfig:
    fps: int = 30
    # CRF 12 + ultrafast keeps up in real time on a laptop CPU and is visually
    # lossless for screen content; the delivery encode happens later.
    crf: int = 12
    offset_x: int = 0
    offset_y: int = 0
    display: str = ":0.0"            # X11 display (Linux)
    screen_index: str = "1"          # avfoundation screen device (macOS)
    audio_device: Optional[str] = None  # dshow name / pulse source / avfoundation index

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, default))
            except ValueError:
                return default
        return cls(
            fps=_int("MTK_CAPTURE_FPS", 30),
            crf=_int("MTK_CAPTURE_CRF", 12),
            offset_x=_int("MTK_CAPTURE_OFFSET_X", 0),
            offset_y=_int("MTK_CAPTURE_OFFSET_Y", 0),
            display=os.environ.get("DISPLAY") or ":0.0",
            screen_index=os.environ.get("MTK_CAPTURE_SCREEN_INDEX", "1"),
            audio_device=(os.environ.get("MTK_CAPTURE_AUDIO_DEVICE") or None),
        )


def backend() -> str:
    """'ffmpeg' only when explicitly requested; Playwright stays the default."""
    choice = os.environ.get("MTK_CAPTURE_BACKEND", "playwright").strip().lower()
    return "ffmpeg" if choice == "ffmpeg" else "playwright"


def browser_launch_args(config: CaptureConfig) -> list[str]:
    """Chromium flags that place the page exactly over the recorded region,
    without browser chrome (address bar, tabs) in the frame."""
    return [
        "--kiosk",
        f"--window-position={config.offset_x},{config.offset_y}",
        f"--window-size={WIDTH},{HEIGHT}",
        "--disable-notifications",
        "--hide-crash-restore-bubble",
    ]


def build_capture_cmd(out_path: Path, config: CaptureConfig,
                      platform: str = sys.platform) -> list[str]:
    """FFmpeg argv for this OS. Pure: unit-testable without FFmpeg."""
    size = f"{WIDTH}x{HEIGHT}"
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "warning", "-y"]
    if platform == "win32":
        cmd += ["-f", "gdigrab", "-framerate", str(config.fps), "-draw_mouse", "1",
                "-offset_x", str(config.offset_x), "-offset_y", str(config.offset_y),
                "-video_size", size, "-i", "desktop"]
        if config.audio_device:
            cmd += ["-f", "dshow", "-i", f"audio={config.audio_device}"]
    elif platform == "darwin":
        audio = config.audio_device or "none"
        cmd += ["-f", "avfoundation", "-framerate", str(config.fps),
                "-capture_cursor", "1", "-i", f"{config.screen_index}:{audio}",
                "-vf", f"crop={WIDTH}:{HEIGHT}:{config.offset_x}:{config.offset_y}"]
    else:
        cmd += ["-f", "x11grab", "-framerate", str(config.fps), "-draw_mouse", "1",
                "-video_size", size,
                "-i", f"{config.display}+{config.offset_x},{config.offset_y}"]
        if config.audio_device:
            cmd += ["-f", "pulse", "-i", config.audio_device]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", str(config.crf),
            "-pix_fmt", "yuv420p", "-g", str(config.fps * 2)]
    if config.audio_device:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += [str(out_path)]
    return cmd


class ScreenRecorder:
    """Start/stop an FFmpeg screen recording. Stop sends 'q' so FFmpeg
    finalizes the file cleanly; a hung process is terminated, never left."""

    def __init__(self, out_path: Path, config: CaptureConfig | None = None,
                 popen=subprocess.Popen, platform: str = sys.platform):
        self.out_path = Path(out_path).with_suffix(".mkv")
        self.config = config or CaptureConfig.from_env()
        self._popen = popen
        self._platform = platform
        self._proc = None

    def start(self) -> None:
        if self._popen is subprocess.Popen and shutil.which(FFMPEG) is None:
            raise RuntimeError("ffmpeg not found — install it, set FFMPEG_PATH, "
                               "or use MTK_CAPTURE_BACKEND=playwright")
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = self._popen(
            build_capture_cmd(self.out_path, self.config, self._platform),
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        time.sleep(0.5)  # let the grabber open before the first navigation
        if self._proc.poll() is not None:
            err = (self._proc.stderr.read() if self._proc.stderr else b"") or b""
            raise RuntimeError(f"screen recorder exited at start: {err.decode(errors='replace')[-400:]}")

    def stop(self, timeout_s: float = 20.0) -> Optional[Path]:
        proc, self._proc = self._proc, None
        if proc is None:
            return None
        try:
            if proc.stdin:
                proc.stdin.write(b"q")
                proc.stdin.flush()
                proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self.out_path.exists() and self.out_path.stat().st_size > 0:
            return self.out_path
        return None
