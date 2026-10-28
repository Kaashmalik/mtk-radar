"""FFmpeg render command assembly — deterministic, reproducible exports (§5).

"Use FFmpeg for deterministic exports; render reproducibly; maintain source
assets and per-platform presets." Every command is returned so it can be
logged in the edit manifest — the render must be re-derivable from assets.
"""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Final, Optional

from presets import Preset

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE: Final[str] = os.environ.get("FFPROBE_PATH", "ffprobe")
# Encoder speed/quality trade-off. "slow" buys ~5-10% smaller files at the
# same CRF; keep "medium" as the default for a single CPU render worker.
X264_PRESET: Final[str] = os.environ.get("MTK_RENDER_X264_PRESET", "medium")
AUDIO_SAMPLE_RATE: Final[int] = 48_000
TRUE_PEAK_HEADROOM_DB: Final[float] = 0.5


@dataclass(frozen=True)
class Loudness:
    """Delivery loudness target — mirrors qc.QCConfig so render and QC agree."""

    target_lufs: float = -16.0
    max_true_peak: float = -1.0
    lra: float = 11.0


DEFAULT_LOUDNESS: Final = Loudness()


def resolve_timeline(
    capture_s: Optional[float],
    narration_s: Optional[float],
    *,
    narration_used: bool = False,
    tolerance_s: float = 0.5,
) -> tuple[Optional[float], Optional[str]]:
    """Resolve the render duration from the measured speech timeline.

    `-shortest` silently chose whichever stream ended first: a short capture
    could cut narration, and a short narration could cut footage. The narration
    is now authoritative. A capture that cannot cover it fails closed instead
    of producing a quietly truncated video.
    """
    if not narration_used:
        return (capture_s if capture_s and capture_s > 0 else None), None
    if narration_s is None or narration_s <= 0:
        return (capture_s if capture_s and capture_s > 0 else None), (
            "narration track exists but its duration is unreadable; cannot "
            "verify speech/action alignment"
        )
    if capture_s is None or capture_s <= 0:
        return narration_s, (
            "capture duration is unavailable; cannot verify speech/action alignment"
        )
    if capture_s + tolerance_s < narration_s:
        return narration_s, (
            f"speech track is {narration_s:.2f}s but the capture is only "
            f"{capture_s:.2f}s; re-record coverage or shorten the script "
            "(refusing to truncate narration)"
        )
    return narration_s, None


def build_ffmpeg_cmd(
    video: str,
    output: str,
    preset: Preset,
    captions: Optional[str] = None,
    narration: Optional[str] = None,
    motion: Optional[str] = None,
    duration: Optional[float] = None,
    loudness: Optional[Loudness] = DEFAULT_LOUDNESS,
) -> list[str]:
    """Build the full ffmpeg invocation for one preset.

    - video/narration/captions are RELATIVE paths (run with cwd=project dir)
      so subtitles filters never need OS-specific escaping.
    - `motion` is a filter fragment from motion.py (push/crop/lower-third).
    - `duration` is the measured speech timeline. It is required with
      narration so no stream can be truncated implicitly by `-shortest`.
    - `loudness` normalizes the delivered audio to the same target QC
      measures. QC used to fail renders it never corrected; None opts out.
    """
    for asset in (video, output, captions, narration):
        if asset and (Path(asset).is_absolute() or PureWindowsPath(asset).is_absolute()):
            raise ValueError("use relative asset paths; run with cwd=project folder")
    if narration and (duration is None or duration <= 0):
        raise ValueError("narration renders require a positive measured duration")

    cmd = [FFMPEG, "-y", "-i", video]
    audio_map = "0:a?"
    if narration:
        cmd += ["-i", narration]
        audio_map = "1:a"  # narration replaces capture audio

    if preset.complex_filter:
        # A multi-chain composition (e.g. vertical blurred background + full
        # frame). Motion/captions become the final chain after the labelled
        # composite output, so the graph still produces exactly one video.
        post = []
        if motion:
            post.append(motion)
        if captions:
            post.append(f"subtitles={captions}")
        graph = preset.filter_chain + f";[vbase]{','.join(post) or 'null'}[vout]"
        cmd += ["-filter_complex", graph, "-map", "[vout]", "-map", audio_map]
        if narration:
            cmd += ["-t", f"{duration:.3f}"]
        return cmd + delivery_args(preset, loudness) + [output]

    vf = preset.filter_chain
    if motion:
        vf += f",{motion}"
    if captions:
        vf += f",subtitles={captions}"
    cmd += ["-map", "0:v", "-map", audio_map]
    if narration:
        cmd += ["-t", f"{duration:.3f}"]

    cmd += ["-vf", vf]
    return cmd + delivery_args(preset, loudness) + [output]


def loudnorm_filter(loudness: Loudness) -> str:
    """Single-pass EBU R128 normalization toward the QC target.

    The true-peak ceiling sits a little below QC's limit so the encoder's
    AAC overshoot cannot push a normalized track over it. loudnorm resamples
    internally to 192 kHz, so the output is pinned back to 48 kHz.
    """
    return (
        f"loudnorm=I={loudness.target_lufs:g}:"
        f"TP={loudness.max_true_peak - TRUE_PEAK_HEADROOM_DB:g}:"
        f"LRA={loudness.lra:g},aresample={AUDIO_SAMPLE_RATE}"
    )


def delivery_args(preset: Preset, loudness: Optional[Loudness]) -> list[str]:
    """Platform-safe H.264/AAC delivery flags shared by every preset.

    Everything a player or platform would otherwise guess is explicit:
    8-bit 4:2:0 High profile (universal decode), BT.709 tags (no washed-out
    colour on re-encode), a fixed 2-second GOP (clean seeking and the
    keyframe cadence YouTube recommends), 48 kHz stereo AAC.
    """
    args = [
        "-c:v", "libx264",
        "-preset", X264_PRESET,
        "-crf", str(preset.crf),
        "-maxrate", preset.video_bitrate,
        "-bufsize", preset.bufsize,
        "-r", str(preset.fps),
        "-g", str(preset.fps * 2),
        "-keyint_min", str(preset.fps),
        "-bf", "2",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level:v", "4.2",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
    ]
    if loudness is not None:
        args += ["-af", loudnorm_filter(loudness)]
    args += [
        "-c:a", "aac",
        "-b:a", preset.audio_bitrate,
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-ac", "2",
        "-movflags", "+faststart",
    ]
    return args


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
