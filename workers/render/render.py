"""FFmpeg render command assembly — deterministic, reproducible exports (§5).

"Use FFmpeg for deterministic exports; render reproducibly; maintain source
assets and per-platform presets." Every command is returned so it can be
logged in the edit manifest — the render must be re-derivable from assets.
"""

import os
import shlex
import shutil
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Final, Optional

from presets import Preset

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE: Final[str] = os.environ.get("FFPROBE_PATH", "ffprobe")


def build_ffmpeg_cmd(
    video: str,
    output: str,
    preset: Preset,
    captions: Optional[str] = None,
    narration: Optional[str] = None,
) -> list[str]:
    """Build the full ffmpeg invocation for one preset.

    - video/narration/captions are RELATIVE paths (run with cwd=project dir)
      so subtitles filters never need OS-specific escaping.
    """
    for asset in (video, output, captions, narration):
        if asset and (Path(asset).is_absolute() or PureWindowsPath(asset).is_absolute()):
            raise ValueError("use relative asset paths; run with cwd=project folder")

    cmd = [FFMPEG, "-y", "-i", video]
    audio_map = "0:a?"
    if narration:
        cmd += ["-i", narration]
        audio_map = "1:a"  # narration replaces capture audio

    vf = preset.filter_chain
    if captions:
        vf += f",subtitles={captions}"
    cmd += ["-map", "0:v", "-map", audio_map]
    if narration:
        cmd += ["-shortest"]

    cmd += [
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(preset.crf),
        "-maxrate", preset.video_bitrate,
        "-bufsize", preset.bufsize,
        "-r", str(preset.fps),
        "-c:a", "aac",
        "-b:a", preset.audio_bitrate,
        "-movflags", "+faststart",
        output,
    ]
    return cmd


def probe_duration(path: str) -> Optional[float]:
    """ffprobe duration in seconds; None when ffprobe/format unavailable."""
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:  # noqa: BLE001 — duration is metadata, never fatal
        return None


def describe(cmd: list[str]) -> str:
    """Loggable one-line command (edit-manifest record)."""
    return " ".join(shlex.quote(part) for part in cmd)


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError("ffmpeg binary not found — install FFmpeg or set FFMPEG_PATH")
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
