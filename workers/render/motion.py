"""Branded motion layer for FFmpeg exports (v0.27).

The old export was a scale/crop plus burned captions: truthful but visibly
flat. This module adds a *reproducible* motion preset without introducing a
second renderer:

  * a gentle 4% push + drifting crop (keeps the frame alive)
  * light colour polish
  * fade-in / fade-out
  * a branded lower-third with the provider + "verified claim"
  * optional Urdu/latin font file via env

Everything is an FFmpeg filter string, recorded in the edit manifest, so the
same source assets regenerate the same motion. No opaque design tool, no
per-video hand editing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Final

from presets import Preset

TEMPLATES: Final[tuple[str, ...]] = ("studio", "minimal", "none")

_DEFAULT_FONT_EN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_DEFAULT_FONT_UR = "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"


def _escape_drawtext(value: str) -> str:
    """Escape a string for FFmpeg's drawtext option parser."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _font_option(language: str) -> str:
    env_key = "MTK_URDU_FONT" if language == "ur" else "MTK_LATIN_FONT"
    candidates = [os.environ.get(env_key, ""),
                  _DEFAULT_FONT_UR if language == "ur" else _DEFAULT_FONT_EN]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return f":fontfile='{candidate.replace(':', '\\:')}'"
    return ""


def build_motion_filter(
    preset: Preset,
    *,
    title: str,
    provider: str = "",
    language: str = "en",
    duration_s: float | None = None,
    template: str = "studio",
) -> str:
    """Return an FFmpeg video-filter fragment (comma-separated)."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown motion template '{template}' — known: {', '.join(TEMPLATES)}")
    if template == "none":
        return ""

    width, height = preset.width, preset.height
    # Scale slightly larger than the delivery frame, then move the crop window
    # with time. This is a real, continuous motion (not a static crop) and is
    # deterministic for any input length.
    filters = [
        f"scale={int(width * 1.04)}:{int(height * 1.04)}:flags=lanczos",
        f"crop={width}:{height}:"
        f"x='(iw-ow)/2+sin(t*0.32)*8':y='(ih-oh)/2+cos(t*0.24)*6'",
        "eq=saturation=1.04:contrast=1.03",
    ]
    if duration_s and duration_s > 0:
        filters.append("fade=t=in:st=0:d=0.35")
        filters.append(f"fade=t=out:st={max(0.0, duration_s - 0.55):.2f}:d=0.5")

    if template == "studio":
        label = "VERIFIED CLAIM" if language == "en" else "تصدیق شدہ کلیم"
        # Trim before escaping: a trailing backslash/quote must not be cut in
        # half and produce an invalid filter.
        name = _escape_drawtext((provider or title)[:46])
        label_text = _escape_drawtext(label)
        box_y = 72 if preset.key == "landscape" else 150
        bar_w = 430 if preset.key == "landscape" else 620
        filters.extend([
            f"drawbox=x=48:y={box_y}:w={bar_w}:h=86:color=0x07111f@0.82:t=fill:"
            f"enable='between(t,0.9,6.2)'",
            f"drawbox=x=48:y={box_y}:w=8:h=86:color=0x38bdf8@0.95:t=fill:"
            f"enable='between(t,0.9,6.2)'",
            f"drawtext=text='{name}'{_font_option(language)}:fontcolor=0xf8fafc:"
            f"fontsize={30 if preset.key == 'landscape' else 38}:x=76:y={box_y + 12}:"
            f"enable='between(t,0.9,6.2)'",
            f"drawtext=text='{label_text}'{_font_option(language)}:fontcolor=0x38bdf8:"
            f"fontsize={17 if preset.key == 'landscape' else 22}:x=76:"
            f"y={box_y + (54 if preset.key == 'landscape' else 58)}:"
            f"enable='between(t,0.9,6.2)'",
        ])
    return ",".join(filters)


def describe(template: str) -> str:
    return {
        "studio": "gentle push + drifting crop + brand lower-third + fades",
        "minimal": "gentle push + colour polish + fades",
        "none": "no motion layer (legacy export)",
    }.get(template, template)


def motion_metadata(template: str, language: str, **extra: Any) -> dict[str, Any]:
    return {
        "motion_template": template,
        "motion_description": describe(template),
        "language": language,
        **extra,
    }
