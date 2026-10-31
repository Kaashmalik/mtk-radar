"""Measured render QC for MTK RADAR (v0.29).

A render is not publishable merely because FFmpeg exited zero. This module
runs the deterministic checks the publishing gate relies on:

  * ffprobe stream/container measurements (resolution, fps, duration, audio)
  * a full FFmpeg decode pass
  * black/freeze/silence event detection, with annotated exempt ranges
  * EBU R128 loudness / true-peak analysis
  * caption safe-area and overflow validation on the burn-in ASS file
  * tool versions and an immutable JSON report

The module deliberately uses only the FFmpeg/FFprobe binaries already in the
render image. It does not add Chromium, a vision model or a second renderer.
Media/QC failures are returned as reports, not exceptions, so the render worker
can persist the failure and the dead-letter view can show it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Final, Iterable, Optional

import fontmetrics

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE: Final[str] = os.environ.get("FFPROBE_PATH", "ffprobe")

REPORT_VERSION: Final[int] = 1


@dataclass(frozen=True)
class QCConfig:
    """QC thresholds. Defaults are conservative starting points, not platform
    law; operators can tune them from the environment without editing code."""

    target_lufs: float = -16.0
    lufs_tolerance: float = 1.0
    max_true_peak: float = -1.0
    min_video_bps: int = 250_000
    min_audio_bps: int = 64_000
    require_audio: bool = True
    duration_tolerance_s: float = 0.5
    duration_tolerance_ratio: float = 0.01
    max_black_s: float = 1.0
    max_freeze_s: float = 5.0
    max_silence_s: float = 2.0
    black_pixel_threshold: float = 0.10
    freeze_noise: float = 0.003
    silence_noise_db: float = -50.0
    probe_timeout_s: float = 30.0
    decode_timeout_s: float = 300.0
    caption_safe_fraction: float = 0.03
    caption_max_lines_warning: int = 3
    exempt_ranges: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> "QCConfig":
        defaults = cls()
        ranges = parse_exempt_ranges(
            os.environ.get("MTK_RENDER_QC_EXEMPT_RANGES", "")
        )
        return cls(
            target_lufs=_env_float("MTK_RENDER_QC_TARGET_LUFS", defaults.target_lufs),
            lufs_tolerance=_env_float(
                "MTK_RENDER_QC_LUFS_TOLERANCE", defaults.lufs_tolerance
            ),
            max_true_peak=_env_float(
                "MTK_RENDER_QC_MAX_TRUE_PEAK", defaults.max_true_peak
            ),
            min_video_bps=_env_int(
                "MTK_RENDER_QC_MIN_VIDEO_BPS", defaults.min_video_bps
            ),
            min_audio_bps=_env_int(
                "MTK_RENDER_QC_MIN_AUDIO_BPS", defaults.min_audio_bps
            ),
            require_audio=_env_bool(
                "MTK_RENDER_QC_REQUIRE_AUDIO", defaults.require_audio
            ),
            duration_tolerance_s=_env_float(
                "MTK_RENDER_QC_DURATION_TOLERANCE_S",
                defaults.duration_tolerance_s,
            ),
            duration_tolerance_ratio=_env_float(
                "MTK_RENDER_QC_DURATION_TOLERANCE_RATIO",
                defaults.duration_tolerance_ratio,
            ),
            max_black_s=_env_float(
                "MTK_RENDER_QC_MAX_BLACK_S", defaults.max_black_s
            ),
            max_freeze_s=_env_float(
                "MTK_RENDER_QC_MAX_FREEZE_S", defaults.max_freeze_s
            ),
            max_silence_s=_env_float(
                "MTK_RENDER_QC_MAX_SILENCE_S", defaults.max_silence_s
            ),
            black_pixel_threshold=_env_float(
                "MTK_RENDER_QC_BLACK_PIXEL_THRESHOLD",
                defaults.black_pixel_threshold,
            ),
            freeze_noise=_env_float(
                "MTK_RENDER_QC_FREEZE_NOISE", defaults.freeze_noise
            ),
            silence_noise_db=_env_float(
                "MTK_RENDER_QC_SILENCE_NOISE_DB",
                defaults.silence_noise_db,
            ),
            probe_timeout_s=_env_float(
                "MTK_RENDER_QC_PROBE_TIMEOUT_S", defaults.probe_timeout_s
            ),
            decode_timeout_s=_env_float(
                "MTK_RENDER_QC_DECODE_TIMEOUT_S", defaults.decode_timeout_s
            ),
            caption_safe_fraction=_env_float(
                "MTK_RENDER_QC_CAPTION_SAFE_FRACTION",
                defaults.caption_safe_fraction,
            ),
            caption_max_lines_warning=_env_int(
                "MTK_RENDER_QC_CAPTION_MAX_LINES",
                defaults.caption_max_lines_warning,
            ),
            exempt_ranges=tuple(ranges),
        )

    def public(self) -> dict[str, Any]:
        return {
            "target_lufs": self.target_lufs,
            "lufs_tolerance": self.lufs_tolerance,
            "max_true_peak": self.max_true_peak,
            "min_video_bps": self.min_video_bps,
            "min_audio_bps": self.min_audio_bps,
            "require_audio": self.require_audio,
            "duration_tolerance_s": self.duration_tolerance_s,
            "duration_tolerance_ratio": self.duration_tolerance_ratio,
            "max_black_s": self.max_black_s,
            "max_freeze_s": self.max_freeze_s,
            "max_silence_s": self.max_silence_s,
            "black_pixel_threshold": self.black_pixel_threshold,
            "freeze_noise": self.freeze_noise,
            "silence_noise_db": self.silence_noise_db,
            "probe_timeout_s": self.probe_timeout_s,
            "decode_timeout_s": self.decode_timeout_s,
            "caption_safe_fraction": self.caption_safe_fraction,
            "caption_max_lines_warning": self.caption_max_lines_warning,
            "exempt_ranges": list(self.exempt_ranges),
        }


# --------------------------------------------------------------- env helpers


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


# -------------------------------------------------------------- check shape


def _check() -> dict[str, Any]:
    return {"status": "passed", "errors": [], "warnings": [], "details": {}}


def _fail(check: dict[str, Any], message: str) -> None:
    check["status"] = "failed"
    check["errors"].append(message)


def _warn(check: dict[str, Any], message: str) -> None:
    check["warnings"].append(message)


def _skipped(reason: str) -> dict[str, Any]:
    check = _check()
    check["status"] = "skipped"
    check["details"]["reason"] = reason
    return check


def _run_command(cmd: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    """One seam for tests and for the worker's configured binaries."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=max(1.0, float(timeout))
    )


def _tail(value: str, limit: int = 1600) -> str:
    text = (value or "").strip()
    return text[-limit:]


def _float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _tool_version(binary: str) -> str:
    try:
        proc = _run_command([binary, "-version"], timeout=10)
        line = (proc.stdout or "").splitlines()[0].strip()
        return line or "unknown"
    except Exception:  # noqa: BLE001 — version metadata must never break QC
        return "unknown"


# ------------------------------------------------------------- probe/decode


def probe_media(path: str | Path, *, timeout: float = 30.0) -> tuple[dict[str, Any] | None, str | None]:
    try:
        proc = _run_command(
            [
                FFPROBE,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — report, never crash the render worker
        return None, f"ffprobe failed: {exc}"
    if proc.returncode != 0:
        return None, f"ffprobe failed: {_tail(proc.stderr)}"
    try:
        payload = json.loads(proc.stdout or "{}")
    except (TypeError, ValueError) as exc:
        return None, f"ffprobe returned invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "ffprobe returned an unexpected payload"
    return payload, None


def _fps(value: Any) -> Optional[float]:
    try:
        frac = Fraction(str(value))
        if frac.denominator == 0:
            return None
        result = float(frac)
        return result if result > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def check_streams(
    probe: dict[str, Any],
    *,
    width: int,
    height: int,
    fps: int,
    expected_duration: float | None,
    config: QCConfig,
) -> dict[str, Any]:
    check = _check()
    fmt = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    video_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"]

    check["details"] = {
        "format": {
            "format_name": fmt.get("format_name"),
            "duration_s": _float(fmt.get("duration")),
            "size_bytes": _int_or_none(fmt.get("size")),
            "bit_rate": _int_or_none(fmt.get("bit_rate")),
        },
        "video_streams": video_streams,
        "audio_streams": audio_streams,
    }

    if not video_streams:
        _fail(check, "streams: no video stream")
        measured_duration = None
    else:
        video = video_streams[0]
        stream_width = _int_or_none(video.get("width"))
        stream_height = _int_or_none(video.get("height"))
        measured_fps = _fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
        measured_duration = _float(video.get("duration")) or _float(fmt.get("duration"))
        bit_rate = _int_or_none(video.get("bit_rate")) or _int_or_none(fmt.get("bit_rate"))
        check["details"]["video"] = {
            "codec_name": video.get("codec_name"),
            "width": stream_width,
            "height": stream_height,
            "fps": measured_fps,
            "pix_fmt": video.get("pix_fmt"),
            "bit_rate": bit_rate,
            "duration_s": measured_duration,
            "sample_aspect_ratio": video.get("sample_aspect_ratio"),
            "display_aspect_ratio": video.get("display_aspect_ratio"),
        }
        if stream_width != width or stream_height != height:
            _fail(
                check,
                f"streams: measured {stream_width}x{stream_height}, expected {width}x{height}",
            )
        if measured_fps is None:
            _fail(check, "streams: frame rate is missing/unreadable")
        elif abs(measured_fps - float(fps)) > 0.5:
            _fail(check, f"streams: measured {measured_fps:.2f} fps, expected {fps}")
        if video.get("codec_name") != "h264":
            _warn(check, f"streams: video codec is {video.get('codec_name')!r}, expected h264")
        if video.get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
            _warn(check, f"streams: pixel format is {video.get('pix_fmt')!r}, expected yuv420p")
        if bit_rate is not None and bit_rate < config.min_video_bps:
            _fail(
                check,
                f"streams: video bitrate {bit_rate} bps is below the {config.min_video_bps} bps floor",
            )
        if measured_duration is None or measured_duration <= 0:
            _fail(check, "streams: duration is missing/unreadable")
        elif expected_duration is not None:
            tolerance = max(
                config.duration_tolerance_s,
                float(expected_duration) * config.duration_tolerance_ratio,
            )
            if abs(measured_duration - float(expected_duration)) > tolerance:
                _fail(
                    check,
                    f"streams: duration {measured_duration:.2f}s differs from expected "
                    f"{float(expected_duration):.2f}s by more than {tolerance:.2f}s",
                )

    if not audio_streams:
        if config.require_audio:
            _fail(check, "streams: no audio stream (narration-required format)")
    else:
        audio = audio_streams[0]
        sample_rate = _int_or_none(audio.get("sample_rate"))
        channels = _int_or_none(audio.get("channels"))
        audio_rate = _int_or_none(audio.get("bit_rate"))
        check["details"]["audio"] = {
            "codec_name": audio.get("codec_name"),
            "sample_rate": sample_rate,
            "channels": channels,
            "bit_rate": audio_rate,
        }
        if audio.get("codec_name") != "aac":
            _warn(check, f"streams: audio codec is {audio.get('codec_name')!r}, expected aac")
        if sample_rate not in (44_100, 48_000):
            _warn(check, f"streams: audio sample rate is {sample_rate}, expected 44100 or 48000")
        if channels is None or channels < 1:
            _fail(check, "streams: audio channel layout is unreadable")
        if audio_rate is not None and audio_rate < config.min_audio_bps:
            _fail(
                check,
                f"streams: audio bitrate {audio_rate} bps is below the {config.min_audio_bps} bps floor",
            )

    if fmt.get("format_name") and "mp4" not in str(fmt.get("format_name")):
        _warn(check, f"streams: container is {fmt.get('format_name')!r}, expected mp4")
    return check


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def full_decode(path: str | Path, *, timeout: float = 300.0) -> dict[str, Any]:
    check = _check()
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _fail(check, f"decode: {exc}")
        return check
    check["details"]["returncode"] = proc.returncode
    if proc.returncode != 0:
        _fail(check, f"decode: ffmpeg exited {proc.returncode}: {_tail(proc.stderr)}")
    elif (proc.stderr or "").strip():
        _fail(check, f"decode: errors reported: {_tail(proc.stderr)}")
    return check


# -------------------------------------------------------- event detection


def _parse_black(stderr: str) -> list[dict[str, float]]:
    events: list[dict[str, float]] = []
    for line in (stderr or "").splitlines():
        if "black_start:" not in line:
            continue
        start = _re_value(line, r"black_start:\s*([0-9.]+)")
        end = _re_value(line, r"black_end:\s*([0-9.]+)")
        duration = _re_value(line, r"black_duration:\s*([0-9.]+)")
        if start is not None and end is not None:
            events.append({"start": start, "end": end, "duration": end - start})
        elif start is not None and duration is not None:
            events.append({"start": start, "end": start + duration, "duration": duration})
    return events


def _parse_freeze(stderr: str) -> list[dict[str, float]]:
    events: list[dict[str, float]] = []
    start: float | None = None
    for line in (stderr or "").splitlines():
        if "freeze_start" in line:
            start = _re_value(line, r"freeze_start:\s*([0-9.]+)")
        elif "freeze_duration" in line and start is not None:
            duration = _re_value(line, r"freeze_duration:\s*([0-9.]+)")
            if duration is not None:
                events.append({"start": start, "end": start + duration, "duration": duration})
                start = None
        elif "freeze_end" in line and start is not None:
            end = _re_value(line, r"freeze_end:\s*([0-9.]+)")
            if end is not None:
                events.append({"start": start, "end": end, "duration": end - start})
                start = None
    return events


def _parse_silence(stderr: str) -> list[dict[str, float]]:
    events: list[dict[str, float]] = []
    start: float | None = None
    for line in (stderr or "").splitlines():
        if "silence_start" in line:
            start = _re_value(line, r"silence_start:\s*(-?[0-9.]+)")
        if "silence_end" in line:
            end = _re_value(line, r"silence_end:\s*(-?[0-9.]+)")
            duration = _re_value(line, r"silence_duration:\s*([0-9.]+)")
            if start is not None and end is not None:
                events.append({"start": start, "end": end,
                               "duration": duration if duration is not None else end - start})
                start = None
    return events


def _re_value(line: str, pattern: str) -> float | None:
    match = re.search(pattern, line)
    if not match:
        return None
    return _float(match.group(1))


def detect_black_freeze(
    path: str | Path,
    *,
    exempt_ranges: Iterable[dict[str, Any]],
    config: QCConfig,
) -> dict[str, Any]:
    check = _check()
    d_black = max(0.1, min(0.5, config.max_black_s))
    d_freeze = max(0.2, min(1.0, config.max_freeze_s))
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-v",
        "info",
        "-i",
        str(path),
        "-vf",
        (
            f"blackdetect=d={d_black}:pix_th={config.black_pixel_threshold}:pic_th=0.98,"
            f"freezedetect=n={config.freeze_noise}:d={d_freeze}"
        ),
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=config.decode_timeout_s)
    except Exception as exc:  # noqa: BLE001
        _fail(check, f"video events: {exc}")
        return check
    if proc.returncode != 0:
        _fail(check, f"video events: detection pass failed: {_tail(proc.stderr)}")
        return check
    black = _parse_black(proc.stderr)
    freeze = _parse_freeze(proc.stderr)
    ranges = normalize_ranges(exempt_ranges)
    black_long = _longest_uncovered(black, ranges)
    freeze_long = _longest_uncovered(freeze, ranges)
    check["details"] = {
        "black_events": black,
        "freeze_events": freeze,
        "exempt_ranges": ranges,
        "longest_uncovered_black_s": black_long,
        "longest_uncovered_freeze_s": freeze_long,
    }
    if black_long > config.max_black_s:
        _fail(
            check,
            f"video events: uncovered black segment {black_long:.2f}s exceeds "
            f"{config.max_black_s:.2f}s",
        )
    if freeze_long > config.max_freeze_s:
        _fail(
            check,
            f"video events: uncovered freeze segment {freeze_long:.2f}s exceeds "
            f"{config.max_freeze_s:.2f}s",
        )
    return check


def detect_silence(
    path: str | Path,
    *,
    exempt_ranges: Iterable[dict[str, Any]],
    config: QCConfig,
) -> dict[str, Any]:
    check = _check()
    d_silence = max(0.1, min(0.5, config.max_silence_s))
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-v",
        "info",
        "-i",
        str(path),
        "-vn",
        "-af",
        f"silencedetect=n={config.silence_noise_db}dB:d={d_silence}",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=config.decode_timeout_s)
    except Exception as exc:  # noqa: BLE001
        _fail(check, f"silence: {exc}")
        return check
    if proc.returncode != 0:
        _fail(check, f"silence: detection pass failed: {_tail(proc.stderr)}")
        return check
    events = _parse_silence(proc.stderr)
    ranges = normalize_ranges(exempt_ranges)
    longest = _longest_uncovered(events, ranges)
    check["details"] = {
        "silence_events": events,
        "exempt_ranges": ranges,
        "longest_uncovered_silence_s": longest,
    }
    if longest > config.max_silence_s:
        _fail(
            check,
            f"silence: uncovered silent segment {longest:.2f}s exceeds "
            f"{config.max_silence_s:.2f}s",
        )
    return check


# --------------------------------------------------------------- loudness


def measure_loudness(path: str | Path, *, config: QCConfig) -> dict[str, Any]:
    check = _check()
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-nostats",
        "-v",
        "info",
        "-i",
        str(path),
        "-vn",
        "-af",
        (
            f"loudnorm=I={config.target_lufs}:TP={config.max_true_peak}:"
            "LRA=11:print_format=json"
        ),
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=config.decode_timeout_s)
    except Exception as exc:  # noqa: BLE001
        _fail(check, f"loudness: {exc}")
        return check
    if proc.returncode != 0:
        _fail(check, f"loudness: measurement failed: {_tail(proc.stderr)}")
        return check
    payload = _last_json_object(proc.stderr)
    if payload is None:
        _fail(check, "loudness: loudnorm produced no JSON measurement")
        return check
    integrated = _float(payload.get("input_i"))
    true_peak = _float(payload.get("input_tp"))
    lra = _float(payload.get("input_lra"))
    check["details"] = {
        "integrated_lufs": integrated,
        "true_peak_dbtp": true_peak,
        "loudness_range_lu": lra,
        "target_lufs": config.target_lufs,
        "target_tolerance_lu": config.lufs_tolerance,
        "max_true_peak_dbtp": config.max_true_peak,
    }
    if integrated is None:
        _fail(check, "loudness: integrated loudness is unreadable (silent audio?)")
    elif abs(integrated - config.target_lufs) > config.lufs_tolerance:
        _fail(
            check,
            f"loudness: integrated {integrated:.1f} LUFS is outside "
            f"{config.target_lufs:.1f} ± {config.lufs_tolerance:.1f} LUFS",
        )
    if true_peak is None:
        _fail(check, "loudness: true peak is unreadable")
    elif true_peak > config.max_true_peak:
        _fail(
            check,
            f"loudness: true peak {true_peak:.1f} dBTP exceeds "
            f"{config.max_true_peak:.1f} dBTP",
        )
    return check


def _last_json_object(value: str) -> dict[str, Any] | None:
    text = value or ""
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


# ---------------------------------------------------------------- captions


def check_captions(
    path: str | Path,
    *,
    width: int,
    height: int,
    config: QCConfig,
) -> dict[str, Any]:
    check = _check()
    caption_path = Path(path)
    if not caption_path.is_file():
        _fail(check, f"captions: file not found: {caption_path}")
        return check
    text = caption_path.read_text(encoding="utf-8", errors="replace")
    play_width = _int_or_none(_ass_value(text, r"PlayResX:\s*(\d+)")) or width
    play_height = _int_or_none(_ass_value(text, r"PlayResY:\s*(\d+)")) or height
    style = _parse_default_style(text)
    if style is None:
        _fail(check, "captions: no Default ASS style found")
        return check
    font_size = style["font_size"]
    # V9: measure with the real font file libass will use (estimate only as
    # a labelled fallback when the font or Pillow is unavailable).
    measure = fontmetrics.measurer(style.get("font_name") or "", font_size)
    width_of = measure.width
    margin_l = style["margin_l"]
    margin_r = style["margin_r"]
    margin_v = style["margin_v"]
    safe_x = max(1.0, width * config.caption_safe_fraction)
    safe_y = max(1.0, height * config.caption_safe_fraction)
    available_width = max(1.0, play_width - margin_l - margin_r)
    cues = _ass_events(text)
    check["details"] = {
        "play_res": [play_width, play_height],
        "font_size": font_size,
        "margins": {"left": margin_l, "right": margin_r, "vertical": margin_v},
        "safe_area": {"left": safe_x, "right": width - safe_x,
                      "top": safe_y, "bottom": height - safe_y},
        "cue_count": len(cues),
        "max_lines": 0,
        "max_line_width_px": 0.0,
        "width_method": measure.method,
    }
    if play_width != width or play_height != height:
        _warn(
            check,
            f"captions: PlayRes {play_width}x{play_height} differs from render "
            f"{width}x{height}",
        )
    if margin_l < safe_x - 1 or margin_r < safe_x - 1:
        _fail(
            check,
            f"captions: side margins {margin_l}/{margin_r}px violate the "
            f"{safe_x:.0f}px safe area",
        )
    if not cues:
        _warn(check, "captions: no Dialogue events found")
    for index, cue in enumerate(cues, start=1):
        lines = _wrap_ass_text(cue, available_width, font_size, width_of)
        if isinstance(lines, str):
            _fail(check, f"captions: cue {index} has an unbreakable word wider "
                         f"than {available_width:.0f}px ({lines})")
            continue
        line_count = len(lines)
        max_width = max((width_of(line) for line in lines), default=0.0)
        bottom = height - margin_v
        top = bottom - (line_count * font_size * 1.2)
        check["details"]["max_lines"] = max(check["details"]["max_lines"], line_count)
        check["details"]["max_line_width_px"] = max(
            check["details"]["max_line_width_px"], round(max_width, 1)
        )
        if max_width > available_width + 1:
            _fail(
                check,
                f"captions: cue {index} line is {max_width:.0f}px wide, "
                f"available {available_width:.0f}px",
            )
        if top < safe_y or bottom > height - safe_y:
            _fail(
                check,
                f"captions: cue {index} occupies y={top:.0f}..{bottom:.0f}, "
                f"outside the {safe_y:.0f}px safe area",
            )
        if line_count > config.caption_max_lines_warning:
            _warn(
                check,
                f"captions: cue {index} wraps to {line_count} lines "
                f"(warning threshold {config.caption_max_lines_warning})",
            )
    return check


def _ass_value(text: str, pattern: str) -> Any:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _parse_default_style(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        if not line.startswith("Style:"):
            continue
        parts = [part.strip() for part in line[len("Style:"):].split(",")]
        if len(parts) < 22 or parts[0] != "Default":
            continue
        try:
            return {
                "font_name": parts[1],
                "font_size": float(parts[2]),
                "margin_l": float(parts[19]),
                "margin_r": float(parts[20]),
                "margin_v": float(parts[21]),
            }
        except (TypeError, ValueError):
            return None
    return None


def _ass_events(text: str) -> list[str]:
    events = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        value = re.sub(r"\{[^}]*\}", "", parts[9])
        value = value.replace("\\N", "\n").replace("\\n", "\n").strip()
        if value:
            events.append(value)
    return events


def _text_width(value: str, font_size: float) -> float:
    """Fallback width estimate (fontmetrics.ESTIMATE_FACTOR × size per char).

    ASS/libass wraps with the real font. This estimate is deliberately a little
    wide for the bundled DejaVu Sans/Nastaliq faces, so it catches overflow
    before a cue reaches the frame while remaining deterministic across hosts.
    """
    return len(value) * font_size * 0.60


def _wrap_ass_text(value: str, available_width: float, font_size: float,
                   width_of: Optional[Callable[[str], float]] = None) -> list[str] | str:
    """Return wrapped lines, or the offending word when it cannot fit."""
    measure = width_of or (lambda text: _text_width(text, font_size))
    lines: list[str] = []
    for explicit in value.split("\n"):
        current = ""
        for word in explicit.split():
            if measure(word) > available_width + 1:
                return word
            candidate = f"{current} {word}".strip()
            if current and measure(candidate) > available_width + 1:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines or [""]


# --------------------------------------------------------------- ranges


def parse_exempt_ranges(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    payload = value
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            start = _float(item.get("start"))
            end = _float(item.get("end"))
            reason = str(item.get("reason") or "annotated still/official page")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            start = _float(item[0])
            end = _float(item[1])
            reason = "annotated still/official page"
        else:
            continue
        if start is None or end is None or end <= start:
            continue
        out.append({"start": max(0.0, start), "end": end, "reason": reason})
    return normalize_ranges(out)


def normalize_ranges(value: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        start = _float(item.get("start"))
        end = _float(item.get("end"))
        if start is None or end is None or end <= start:
            continue
        out.append({"start": max(0.0, start), "end": end,
                    "reason": str(item.get("reason") or "exempt")})
    return sorted(out, key=lambda item: (item["start"], item["end"]))


def _subtract_ranges(start: float, end: float,
                     ranges: Iterable[dict[str, Any]]) -> list[tuple[float, float]]:
    remaining = [(max(0.0, start), max(0.0, end))]
    for item in normalize_ranges(ranges):
        next_remaining: list[tuple[float, float]] = []
        for left, right in remaining:
            if item["end"] <= left or item["start"] >= right:
                next_remaining.append((left, right))
                continue
            if item["start"] > left:
                next_remaining.append((left, item["start"]))
            if item["end"] < right:
                next_remaining.append((item["end"], right))
        remaining = next_remaining
    return [(left, right) for left, right in remaining if right > left]


def _longest_uncovered(events: Iterable[dict[str, Any]],
                       ranges: Iterable[dict[str, Any]]) -> float:
    longest = 0.0
    for event in events:
        start = _float(event.get("start"))
        end = _float(event.get("end"))
        if start is None or end is None:
            continue
        for left, right in _subtract_ranges(start, end, ranges):
            longest = max(longest, right - left)
    return round(longest, 3)


# ------------------------------------------------------------------ report


def run(
    path: str | Path,
    *,
    width: int,
    height: int,
    fps: int,
    preset: str,
    expected_duration: float | None = None,
    captions_path: str | Path | None = None,
    exempt_ranges: Iterable[dict[str, Any]] | None = None,
    config: QCConfig | None = None,
) -> dict[str, Any]:
    """Run every deterministic QC check and return a JSON-safe report.

    Media failures become report errors; only programmer errors propagate.
    """
    config = config or QCConfig.from_env()
    ranges = normalize_ranges([*(config.exempt_ranges or ()), *(exempt_ranges or ())])
    checked_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "version": REPORT_VERSION,
        "checked_at": checked_at,
        "status": "failed",
        "preset": preset,
        "expected_duration_s": expected_duration,
        "checks": {},
        "errors": [],
        "warnings": [],
        "tool_versions": {
            "ffmpeg": _tool_version(FFMPEG),
            "ffprobe": _tool_version(FFPROBE),
        },
        "config": config.public(),
    }
    media_path = Path(path)
    if not media_path.is_file():
        report["errors"] = [f"media file not found: {media_path}"]
        report["checks"] = {"streams": _missing_check("media file not found")}
        return report

    probe, probe_error = probe_media(media_path, timeout=config.probe_timeout_s)
    if probe is None:
        report["errors"] = [probe_error or "ffprobe failed"]
        report["checks"] = {"streams": _missing_check(probe_error or "ffprobe failed")}
        return report

    checks: dict[str, Any] = {}
    checks["streams"] = check_streams(
        probe, width=width, height=height, fps=fps,
        expected_duration=expected_duration, config=config,
    )
    has_audio = bool(checks["streams"]["details"].get("audio_streams"))
    checks["decode"] = full_decode(media_path, timeout=config.decode_timeout_s)
    checks["video_events"] = detect_black_freeze(
        media_path, exempt_ranges=ranges, config=config
    )
    if has_audio:
        checks["silence"] = detect_silence(
            media_path, exempt_ranges=ranges, config=config
        )
        checks["loudness"] = measure_loudness(media_path, config=config)
    else:
        checks["silence"] = _skipped("no audio stream")
        checks["loudness"] = _skipped("no audio stream")
    if captions_path is not None:
        checks["captions"] = check_captions(
            captions_path, width=width, height=height, config=config
        )
    else:
        checks["captions"] = _skipped("no burn-in caption file supplied")

    report["checks"] = checks
    for name, check in checks.items():
        for message in check.get("errors", []):
            report["errors"].append(f"{name}: {message}" if not str(message).startswith(f"{name}:") else message)
        for message in check.get("warnings", []):
            report["warnings"].append(f"{name}: {message}" if not str(message).startswith(f"{name}:") else message)
    report["status"] = "failed" if report["errors"] else "passed"
    return report


def _missing_check(reason: str) -> dict[str, Any]:
    check = _check()
    _fail(check, reason)
    return check


def failure_report(
    *,
    stage: str,
    errors: Iterable[str],
    details: dict[str, Any] | None = None,
    preset: str | None = None,
    expected_duration: float | None = None,
    config: QCConfig | None = None,
) -> dict[str, Any]:
    """A persisted failure record for an encoder/staging failure before QC can
    inspect a real file (for example, FFmpeg exited non-zero)."""
    config = config or QCConfig.from_env()
    return {
        "version": REPORT_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "stage": stage,
        "preset": preset,
        "expected_duration_s": expected_duration,
        "checks": {},
        "details": details or {},
        "errors": [str(error) for error in errors if str(error).strip()],
        "warnings": [],
        "tool_versions": {
            "ffmpeg": _tool_version(FFMPEG),
            "ffprobe": _tool_version(FFPROBE),
        },
        "config": config.public(),
    }
