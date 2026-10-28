"""Activity-following vertical reframing for screen captures (V5).

The 9:16 export used to fit the whole 16:9 recording into 1080 px of width,
so UI and code text shrank to ~56 % and became hard to read on a phone.
Blind centre-cropping is no better: the action is rarely in the centre.

This module finds WHERE the screen changes over time (typing, scrolling,
clicks, new pages), smooths that into a calm camera path, and crops a
narrower window that follows it — text ends up about twice the size of the
full-frame composition. Where the activity signal is weak (static slides,
whole-page transitions) it refuses and the caller keeps the full frame.

Opt-in: MTK_VERTICAL_REFRAME=auto (default `full` = previous behaviour)
until it is validated on real captures; the human playback review still
signs off every export. MTK_VERTICAL_REFRAME_WIDTH sets the crop width as a
fraction of the source (default 0.5 → 960 of 1920 px).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Final, Optional, Sequence

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
SAMPLE_W, SAMPLE_H, SAMPLE_FPS = 192, 108, 2
NOISE: Final[int] = 12            # per-pixel luma change ignored as noise
MIN_ACTIVE_FRACTION: Final[float] = 0.002   # of pixels, to call a frame "active"
WHOLE_FRAME_FRACTION: Final[float] = 0.45   # page switch: no single focus
DEAD_ZONE: Final[float] = 0.06    # ignore focus moves smaller than this
EASE: Final[float] = 0.35         # how fast the window follows (0..1)
KEYFRAME_EVERY_S: Final[float] = 2.0
MAX_KEYFRAMES: Final[int] = 90
MIN_CONFIDENCE: Final[float] = 0.3  # share of frames with a usable focus


def enabled() -> bool:
    return os.environ.get("MTK_VERTICAL_REFRAME", "full").strip().lower() == "auto"


def crop_fraction() -> float:
    try:
        value = float(os.environ.get("MTK_VERTICAL_REFRAME_WIDTH", "0.5"))
    except ValueError:
        value = 0.5
    return min(0.9, max(0.35, value))


# ------------------------------------------------------------------ analysis

def sample_cmd(video: str) -> list[str]:
    return [FFMPEG, "-v", "error", "-i", video,
            "-vf", f"fps={SAMPLE_FPS},scale={SAMPLE_W}:{SAMPLE_H},format=gray",
            "-f", "rawvideo", "-"]


def focus_samples(frames: Sequence[bytes], width: int = SAMPLE_W,
                  height: int = SAMPLE_H) -> list[Optional[float]]:
    """Per frame: the horizontal centre (0..1) of what changed since the
    previous frame, or None when nothing (or everything) changed."""
    out: list[Optional[float]] = [None]
    total = width * height
    for prev, cur in zip(frames, frames[1:]):
        column_mass = [0] * width
        changed = 0
        for i in range(total):
            if abs(cur[i] - prev[i]) > NOISE:
                column_mass[i % width] += 1
                changed += 1
        fraction = changed / total
        if fraction < MIN_ACTIVE_FRACTION or fraction > WHOLE_FRAME_FRACTION:
            out.append(None)
            continue
        weighted = sum(x * m for x, m in enumerate(column_mass))
        out.append((weighted / changed + 0.5) / width)
    return out


def split_frames(raw: bytes, width: int = SAMPLE_W, height: int = SAMPLE_H) -> list[bytes]:
    size = width * height
    return [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]


# ------------------------------------------------------------------- camera

@dataclass(frozen=True)
class Keyframe:
    t: float
    center: float  # 0..1 of the source width


def camera_path(samples: Sequence[Optional[float]], crop_frac: float,
                fps: float = SAMPLE_FPS) -> Optional[list[Keyframe]]:
    """Smoothed, clamped window centres; None when the signal is too weak."""
    if not samples:
        return None
    usable = sum(1 for s in samples if s is not None)
    if usable / len(samples) < MIN_CONFIDENCE:
        return None
    half = crop_frac / 2
    first = next(s for s in samples if s is not None)
    position = min(1 - half, max(half, first))
    path: list[tuple[float, float]] = []
    for index, sample in enumerate(samples):
        if sample is not None and abs(sample - position) > DEAD_ZONE:
            position += (sample - position) * EASE
        position = min(1 - half, max(half, position))
        path.append((index / fps, position))
    step = max(1, int(round(KEYFRAME_EVERY_S * fps)))
    keys = [Keyframe(round(t, 3), round(c, 4)) for t, c in path[::step]]
    if path and keys[-1].t != round(path[-1][0], 3):
        keys.append(Keyframe(round(path[-1][0], 3), round(path[-1][1], 4)))
    if len(keys) > MAX_KEYFRAMES:  # keep the expression bounded
        stride = -(-len(keys) // MAX_KEYFRAMES)
        keys = keys[::stride] + ([keys[-1]] if keys[-1] not in keys[::stride] else [])
    # Collapse runs where the camera holds still.
    compact = [keys[0]]
    for key in keys[1:-1]:
        if key.center != compact[-1].center:
            compact.append(key)
    if len(keys) > 1:
        compact.append(keys[-1])
    return compact


def crop_x_expr(keys: Sequence[Keyframe], src_w: int, crop_w: int) -> str:
    """Piecewise-linear x(t) for FFmpeg's crop filter (pixels, clamped)."""
    def px(center: float) -> int:
        return int(round(min(src_w - crop_w, max(0, center * src_w - crop_w / 2))))

    if len(keys) == 1:
        return str(px(keys[0].center))
    expr = str(px(keys[-1].center))
    for a, b in reversed(list(zip(keys, keys[1:]))):
        xa, xb = px(a.center), px(b.center)
        span = max(1e-3, b.t - a.t)
        segment = f"{xa}+({xb - xa})*(t-{a.t:g})/{span:g}" if xa != xb else str(xa)
        expr = f"if(lt(t,{b.t:g}),{segment},{expr})"
    return expr


def vertical_focus_chain(keys: Sequence[Keyframe], crop_frac: float,
                         src_w: int = 1920, src_h: int = 1080) -> str:
    """Filter graph producing [vbase] like presets.VERTICAL, but the
    foreground is the activity-following crop instead of the whole frame."""
    crop_w = int(round(src_w * crop_frac / 2)) * 2
    x = crop_x_expr(keys, src_w, crop_w)
    return (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=24:2[bg2];"
        f"[fg]crop=w={crop_w}:h={src_h}:x='{x}':y=0,"
        "scale=1080:-2:flags=lanczos[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[vbase]"
    )


def analyse(video: str, crop_frac: float, timeout_s: float = 600.0,
            run=subprocess.run) -> Optional[list[Keyframe]]:
    """Run the low-res sampling pass and return a camera path, or None."""
    try:
        proc = run(sample_cmd(video), capture_output=True, timeout=timeout_s)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return camera_path(focus_samples(split_frames(proc.stdout)), crop_frac)
