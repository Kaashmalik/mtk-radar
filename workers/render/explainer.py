"""Research explainer track — a reviewable video without a screen capture (M3).

Before this, the renderer stopped with "no capture video", so a research
explainer (EP-03 content_type 'explainer') could not be produced at all. An
explainer needs no hands-on recording: it shows the viewer question, each
claim from the CURRENT research brief with its attribution and source, and
the stated limitations, while the narration explains them.

Honesty rules (mirror scriptgen's research tracks):
- `contradicted` claims are never shown (a standing contradiction already
  blocks script generation; this is defence in depth).
- every claim card carries its class attribution ("The authors report…",
  "Our analysis…") and its cited source; `unknown` claims say so verbatim.
- no "tested"/"we tried" framing: there is no capture behind these cards.

The cards become the BASE video fed into the normal pipeline, so presets,
narration, captions, loudness and measured QC all apply unchanged. The base
is mid-tone (not black) with subtle grain and fades, so black-frame and
freeze QC pass honestly instead of through exemptions.

Every scene is recorded in a scene manifest (claim ids, text, source, in/out)
whose sha256 is logged with the render.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final, Optional
from urllib.parse import urlparse

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
WIDTH, HEIGHT, FPS = 1920, 1080, 30
BACKGROUND: Final[str] = "0x1e2638"   # mid-tone slate: luma ≈ 0.14 (> black threshold)
MIN_SCENE_S, DEFAULT_SCENE_S = 3.0, 6.0
FONT = os.environ.get("MTK_CAPTION_FONT", "DejaVu Sans")

ATTRIBUTION: Final[dict[str, str]] = {
    "author_reported": "The authors report",
    "independently_reproduced": "Independently reproduced",
    "tested_by_mtk": "Tested by MTK",
    "editorial_analysis": "Our analysis",
}


def eligible_brief(research: Any) -> Optional[dict]:
    """The current brief when it is an explainer with something to show."""
    if not isinstance(research, dict):
        return None
    current = research.get("current")
    if not isinstance(current, dict) or current.get("content_type") != "explainer":
        return None
    shown = [c for c in current.get("claims") or [] if c.get("status") != "contradicted"]
    return current if shown or current.get("viewer_question") else None


def _source_label(claim: dict) -> str:
    owner = (claim.get("source_owner") or "").strip()
    url = (claim.get("source_url") or "").strip()
    host = urlparse(url).hostname if url else None
    label = owner or host or ""
    date = claim.get("source_date")
    if label and date:
        label = f"{label} · {date}"
    return f"Source: {label}" if label else "Source: not cited"


def plan_scenes(offer: dict, brief: dict,
                total_s: Optional[float] = None) -> list[dict]:
    """Title → one card per shown claim → limitations/close, with timing.

    With a measured narration length the scenes share it in proportion to
    their text (min MIN_SCENE_S each); otherwise each lasts DEFAULT_SCENE_S.
    """
    scenes: list[dict] = [{
        "id": "title",
        "kind": "title",
        "heading": (brief.get("viewer_question") or offer.get("title") or "").strip()
        or "Research explained",
        "body": (brief.get("angle") or "").strip(),
        "claim_ids": [],
    }]
    for claim in brief.get("claims") or []:
        if claim.get("status") == "contradicted":
            continue
        text = (claim.get("permitted_wording") or claim.get("claim_text") or "").strip()
        if not text:
            continue
        attribution = ATTRIBUTION.get(claim.get("claim_class"), "Reported")
        if claim.get("status") == "unknown":
            attribution += " — not yet independently confirmed"
        scenes.append({
            "id": f"claim-{claim.get('id')}",
            "kind": "claim",
            "heading": attribution,
            "body": text,
            "source": _source_label(claim),
            "scope": (claim.get("scope") or "").strip(),
            "claim_ids": [str(claim.get("id"))],
        })
    closing = (brief.get("limitations") or "").strip()
    scenes.append({
        "id": "close",
        "kind": "close",
        "heading": "Limitations" if closing else "Sources",
        "body": closing or "Every source is linked in the description.",
        "claim_ids": [],
    })

    weights = [max(1, len(s["heading"]) + len(s.get("body", ""))) for s in scenes]
    if total_s and total_s > 0:
        raw = [total_s * w / sum(weights) for w in weights]
        durations = [max(MIN_SCENE_S, d) for d in raw]
        scale = total_s / sum(durations)
        durations = [d * scale for d in durations]
    else:
        durations = [DEFAULT_SCENE_S] * len(scenes)
    cursor = 0.0
    for scene, duration in zip(scenes, durations):
        scene["start"] = round(cursor, 3)
        cursor += duration
        scene["end"] = round(cursor, 3)
    return scenes


def _ass_text(value: str) -> str:
    """Escape for an ASS dialogue line: braces open override blocks and a
    backslash starts a tag, so neither may pass through from claim text."""
    return (str(value).replace("\\", "/").replace("{", "(").replace("}", ")")
            .replace("\r", "").replace("\n", "\\N"))


def _ts(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def cards_ass(scenes: list[dict]) -> str:
    """Styled card text for every scene (libass wraps long claims)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{FONT},76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,2,5,180,180,0,1
Style: Kicker,{FONT},40,&H00FFB37B,&H00FFB37B,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,8,180,180,250,1
Style: Body,{FONT},58,&H00F0EAE8,&H00F0EAE8,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,2,5,200,200,0,1
Style: Source,{FONT},34,&H00C3B4A8,&H00C3B4A8,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,180,180,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for scene in scenes:
        start, end = _ts(scene["start"]), _ts(scene["end"])
        fade = "{\\fad(350,350)}"
        if scene["kind"] == "title":
            lines.append(f"Dialogue: 0,{start},{end},Title,,0,0,0,,{fade}{_ass_text(scene['heading'])}")
            if scene.get("body"):
                lines.append(f"Dialogue: 0,{start},{end},Source,,0,0,0,,{fade}{_ass_text(scene['body'])}")
            continue
        lines.append(f"Dialogue: 0,{start},{end},Kicker,,0,0,0,,{fade}{_ass_text(scene['heading'].upper())}")
        lines.append(f"Dialogue: 0,{start},{end},Body,,0,0,0,,{fade}{_ass_text(scene['body'])}")
        footer = " · ".join(x for x in (scene.get("source"), scene.get("scope")) if x)
        if footer:
            lines.append(f"Dialogue: 0,{start},{end},Source,,0,0,0,,{fade}{_ass_text(footer)}")
    return header + "\n".join(lines) + "\n"


def base_video_cmd(cards_rel: str, out_rel: str, duration_s: float) -> list[str]:
    """Mid-tone background + light temporal grain + cards → silent base MP4.

    Paths are RELATIVE (run with cwd = project dir) like render.py, so the
    subtitles filter never needs OS-specific escaping.
    """
    if Path(cards_rel).is_absolute() or Path(out_rel).is_absolute():
        raise ValueError("use relative paths; run with cwd=project folder")
    return [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration_s:.3f}",
        "-vf", f"noise=alls=4:allf=t,vignette=PI/5,subtitles={cards_rel}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
        out_rel,
    ]


def scene_manifest(offer_id: str, brief: dict, scenes: list[dict]) -> dict:
    body = {
        "version": 1,
        "track": "explainer",
        "offer_id": str(offer_id),
        "brief_id": str(brief.get("id")),
        "brief_version": brief.get("version"),
        "scenes": scenes,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}
