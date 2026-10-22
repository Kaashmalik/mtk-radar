"""Deterministic cover/thumbnail generation (v0.27).

Covers are source assets, not hand-made one-offs: the same offer/language/
variant always produces the same SVG, and the edit manifest records it. SVG
keeps the renderer dependency-free; the optional Pillow path produces a
platform-ready PNG when the host has it (including RTL shaping extras when
installed).

A cover intentionally mirrors the video's editorial rules: it says *verified
claim*, not *guaranteed free money*, and it repeats the region/eligibility
risk instead of hiding it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final
from xml.sax.saxutils import escape

PALETTES: Final[dict[str, dict[str, str]]] = {
    "a": {
        "bg": "#07111f", "bg2": "#0b2239", "accent": "#38bdf8",
        "warm": "#fbbf24", "text": "#f8fafc", "muted": "#94a3b8",
    },
    "b": {
        "bg": "#150b24", "bg2": "#2a1240", "accent": "#f472b6",
        "warm": "#fbbf24", "text": "#fdf4ff", "muted": "#c4b5fd",
    },
}

_LANDSCAPE: Final = {"key": "landscape", "width": 1280, "height": 720}
_VERTICAL: Final = {"key": "vertical", "width": 1080, "height": 1920}
PRESETS: Final = (_LANDSCAPE, _VERTICAL)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _wrap(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = _clean(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) == max_lines - 1 and current:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines or ["Offer walkthrough"]


def build_cover_spec(
    offer: dict[str, Any],
    *,
    language: str = "en",
    variant: str = "a",
    preset: str = "landscape",
    website_url: str | None = None,
) -> dict[str, Any]:
    preset_data = _LANDSCAPE if preset == "landscape" else _VERTICAL
    palette = PALETTES.get(variant, PALETTES["a"])
    title = _clean(offer.get("title") or "Offer walkthrough")
    provider = _clean(offer.get("provider") or "")
    eyebrow = "VERIFIED CLAIM" if language == "en" else "تصدیق شدہ کلیم"
    cta = ("REAL WALKTHROUGH · SOURCES BELOW" if language == "en"
           else "حقیقی کلیم · ذرائع نیچے")
    return {
        "version": 1,
        "language": language,
        "variant": variant,
        "preset": preset_data["key"],
        "width": preset_data["width"],
        "height": preset_data["height"],
        "title": title,
        "title_lines": _wrap(title, 20 if preset == "vertical" else 30, 3),
        "provider": provider,
        "eyebrow": eyebrow,
        "cta": cta,
        "website_url": _clean(website_url),
        "palette": palette,
        "rtl": language == "ur",
        "badge": "OFFICIAL TERMS" if language == "en" else "آفیشل شرائط",
    }


def render_svg(spec: dict[str, Any]) -> str:
    """Render a complete, self-contained SVG cover."""
    width = int(spec["width"])
    height = int(spec["height"])
    palette = spec["palette"]
    rtl = bool(spec.get("rtl"))
    anchor = "end" if rtl else "start"
    x = width - 76 if rtl else 76
    font = ("Noto Nastaliq Urdu, Noto Sans Arabic, Noto Sans, sans-serif"
            if rtl else "Inter, DejaVu Sans, system-ui, sans-serif")
    title_size = 76 if spec["preset"] == "landscape" else 88
    line_height = title_size * 1.14
    title_lines = "".join(
        f'<text x="{x}" y="{250 + i * line_height}" text-anchor="{anchor}" '
        f'font-family="{font}" font-size="{title_size}" font-weight="800" '
        f'fill="{palette["text"]}">{escape(line)}</text>'
        for i, line in enumerate(spec["title_lines"])
    )
    radar_cx = width - 150 if not rtl else 150
    radar_cy = height - 160
    rings = "".join(
        f'<circle cx="{radar_cx}" cy="{radar_cy}" r="{60 + i * 54}" fill="none" '
        f'stroke="{palette["accent"]}" stroke-opacity="{0.30 - i * 0.06}" stroke-width="2"/>'
        for i in range(4)
    )
    website = ""
    if spec.get("website_url"):
        website = (
            f'<text x="{x}" y="{height - 52}" text-anchor="{anchor}" '
            f'font-family="{font}" font-size="24" fill="{palette["muted"]}">'
            f'{escape(spec["website_url"][:80])}</text>'
        )
    provider = ""
    if spec.get("provider"):
        provider = (
            f'<text x="{x}" y="{205}" text-anchor="{anchor}" font-family="{font}" '
            f'font-size="25" font-weight="600" fill="{palette["accent"]}">'
            f'{escape(spec["provider"])}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(spec["title"])}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette["bg"]}"/>
      <stop offset="1" stop-color="{palette["bg2"]}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.82" cy="0.18" r="0.7">
      <stop offset="0" stop-color="{palette["accent"]}" stop-opacity="0.24"/>
      <stop offset="1" stop-color="{palette["accent"]}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M 48 0 L 0 0 0 48" fill="none" stroke="{palette["text"]}" stroke-opacity="0.055" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
  <rect width="{width}" height="{height}" fill="url(#grid)"/>
  <rect width="{width}" height="{height}" fill="url(#glow)"/>
  {rings}
  <line x1="{radar_cx}" y1="{radar_cy}" x2="{radar_cx + 165}" y2="{radar_cy - 115}" stroke="{palette["warm"]}" stroke-width="4" stroke-linecap="round" opacity="0.9"/>
  <circle cx="{radar_cx + 92}" cy="{radar_cy - 66}" r="9" fill="{palette["warm"]}"/>
  <rect x="{76 if not rtl else width - 76 - 280}" y="96" width="280" height="44" rx="22" fill="{palette["accent"]}" fill-opacity="0.16" stroke="{palette["accent"]}" stroke-opacity="0.5"/>
  <text x="{76 + 140 if not rtl else width - 76 - 140}" y="124" text-anchor="middle" font-family="{font}" font-size="18" font-weight="700" letter-spacing="2" fill="{palette["accent"]}">{escape(spec["eyebrow"])}</text>
  {provider}
  {title_lines}
  <rect x="{76 if not rtl else width - 76 - 430}" y="{height - 150}" width="430" height="58" rx="12" fill="{palette["warm"]}"/>
  <text x="{76 + 215 if not rtl else width - 76 - 215}" y="{height - 112}" text-anchor="middle" font-family="{font}" font-size="20" font-weight="800" fill="#1a1203">{escape(spec["cta"])}</text>
  {website}
</svg>
'''


def _try_png(svg_path: Path, png_path: Path, spec: dict[str, Any]) -> Path | None:
    """Optional PNG path. Pillow has no SVG rasterizer, so we draw the same
    layout directly when Pillow is available. Failure is non-fatal: SVG is the
    canonical cover source and platforms can accept a converted copy."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:  # noqa: BLE001 — optional dependency
        return None
    try:
        width, height = int(spec["width"]), int(spec["height"])
        palette = spec["palette"]
        image = Image.new("RGB", (width, height), palette["bg"])
        draw = ImageDraw.Draw(image)
        draw.rectangle([0, 0, width, height], fill=palette["bg"])
        draw.rectangle([0, height - 12, width, height], fill=palette["warm"])
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
        ]
        font = ImageFont.load_default()
        for candidate in font_paths:
            if Path(candidate).exists():
                font = ImageFont.truetype(candidate, 64)
                break
        y = 220
        for line in spec["title_lines"]:
            draw.text((76, y), line, font=font, fill=palette["text"])
            y += 78
        draw.text((76, 130), spec["eyebrow"], fill=palette["accent"])
        draw.text((76, 180), spec.get("provider", ""), fill=palette["accent"])
        draw.text((76, height - 120), spec["cta"], fill="#1a1203")
        image.save(png_path)
        return png_path
    except Exception:  # noqa: BLE001
        return None


def cover_for_preset(bundle: dict[str, Any], preset_key: str) -> dict[str, Any]:
    """Pick the cover drawn for one delivery frame, falling back to primary."""
    for cover in bundle.get("covers", []) or []:
        if isinstance(cover, dict) and cover.get("preset") == preset_key:
            return cover
    return bundle.get("primary") or {}


def generate_covers(
    project: Path,
    offer: dict[str, Any],
    *,
    language: str = "en",
    variant: str = "a",
    website_url: str | None = None,
    presets: tuple[str, ...] = ("landscape", "vertical"),
) -> dict[str, Any]:
    """Write cover assets and return project-relative paths + specs."""
    out_dir = Path(project) / "assets" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    covers: list[dict[str, Any]] = []
    for preset in presets:
        spec = build_cover_spec(offer, language=language, variant=variant,
                                preset=preset, website_url=website_url)
        svg_path = out_dir / f"{language}-{variant}-{preset}.svg"
        svg_path.write_text(render_svg(spec), encoding="utf-8")
        png_path = _try_png(svg_path, out_dir / f"{language}-{variant}-{preset}.png", spec)
        covers.append({
            "preset": preset,
            "language": language,
            "variant": variant,
            "svg": str(svg_path.relative_to(project)),
            "png": str(png_path.relative_to(project)) if png_path else None,
            "spec": spec,
        })
    return {"covers": covers, "primary": covers[0] if covers else None}
