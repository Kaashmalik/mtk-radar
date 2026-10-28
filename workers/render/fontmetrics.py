"""Caption width measured with the real font (V9, 2026-10-28 plan).

QC used to assume every glyph is 0.60 × font size wide. That is roughly right
for Latin text in DejaVu Sans but wrong in both directions for other faces —
and badly wrong for Urdu Nastaliq — so an overflowing caption could pass or a
fine one fail. This module measures with the font file libass will use.

libass sizing rule: an ASS `Fontsize` of N makes the font's ascender plus
descender exactly N pixels (not the em size). Pillow's `truetype(size=N)` is
em-based, so the measured advance is scaled by N / (ascent + descent).

Resolution order for the font file:
  1. MTK_CAPTION_FONT_FILE (explicit path),
  2. `fc-match` for the family name (Linux/macOS with fontconfig),
  3. a search of the usual font directories by normalised family name.
When Pillow or the font is unavailable the old estimate is used and the
result says so (`method == "estimate"`), so a report never pretends.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

ESTIMATE_FACTOR = 0.60
_FONT_DIRS = (
    "/usr/share/fonts", "/usr/local/share/fonts", "~/.fonts", "~/.local/share/fonts",
    "/Library/Fonts", "/System/Library/Fonts", "~/Library/Fonts",
    "C:/Windows/Fonts", "~/AppData/Local/Microsoft/Windows/Fonts",
)
_FONT_SUFFIXES = (".ttf", ".otf", ".ttc")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@lru_cache(maxsize=32)
def resolve_font_file(family: str) -> Optional[str]:
    explicit = os.environ.get("MTK_CAPTION_FONT_FILE", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    if shutil.which("fc-match"):
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", family],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            # fc-match always answers with SOME font; accept it only when it
            # is the requested family, never a silent substitute.
            if out and Path(out).is_file() and _norm(family) in _norm(Path(out).stem):
                return out
        except (OSError, subprocess.SubprocessError):
            pass
    wanted = _norm(family)
    candidates: list[Path] = []
    for raw in _FONT_DIRS:
        root = Path(raw).expanduser()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() in _FONT_SUFFIXES and _norm(path.stem).startswith(wanted):
                candidates.append(path)
    if not candidates:
        return None
    # Prefer the Regular/Book face over Bold/Italic variants.
    candidates.sort(key=lambda p: (len(_norm(p.stem)) - len(wanted), str(p)))
    return str(candidates[0])


@lru_cache(maxsize=64)
def _load(font_file: str, size: int):
    from PIL import ImageFont  # optional dependency
    try:
        engine = ImageFont.Layout.RAQM  # shapes Arabic-script text (Urdu)
        return ImageFont.truetype(font_file, size, layout_engine=engine)
    except (OSError, ValueError, AttributeError, KeyError):
        return ImageFont.truetype(font_file, size)


@dataclass(frozen=True)
class Measurer:
    family: str
    font_size: float
    font_file: Optional[str]

    @property
    def method(self) -> str:
        return f"font:{Path(self.font_file).name}" if self.font_file else "estimate"

    def width(self, text: str) -> float:
        if not text:
            return 0.0
        if self.font_file:
            try:
                size = max(1, int(round(self.font_size)))
                font = _load(self.font_file, size)
                ascent, descent = font.getmetrics()
                scale = self.font_size / max(1, ascent + descent)  # libass rule
                return float(font.getlength(text)) * scale
            except Exception:  # noqa: BLE001 — fall back, never break QC
                pass
        return len(text) * self.font_size * ESTIMATE_FACTOR


def measurer(family: str, font_size: float) -> Measurer:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return Measurer(family, font_size, None)
    return Measurer(family, font_size, resolve_font_file(family))
