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
import sys
from pathlib import Path
from typing import Any, Final, Optional

_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
if str(_PACKAGES) not in sys.path:  # shared with the API (storyboard rules)
    sys.path.insert(0, str(_PACKAGES))

import storyboard  # noqa: E402

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
WIDTH, HEIGHT, FPS = 1920, 1080, 30
BACKGROUND: Final[str] = "0x1e2638"   # mid-tone slate: luma ≈ 0.14 (> black threshold)
MIN_SCENE_S, DEFAULT_SCENE_S = storyboard.MIN_SCENE_S, storyboard.DEFAULT_SCENE_S
FONT = os.environ.get("MTK_CAPTION_FONT", "DejaVu Sans")

# Scene planning, honesty rules and timing live in packages/storyboard so the
# Studio storyboard editor (API) and this renderer apply the SAME rules.
ATTRIBUTION: Final[dict[str, str]] = storyboard.ATTRIBUTION


def eligible_brief(research: Any) -> Optional[dict]:
    """The current brief when it is an explainer with something to show."""
    if not isinstance(research, dict):
        return None
    current = research.get("current")
    if not isinstance(current, dict) or current.get("content_type") != "explainer":
        return None
    shown = [c for c in current.get("claims") or [] if c.get("status") != "contradicted"]
    return current if shown or current.get("viewer_question") else None


def plan_scenes(offer: dict, brief: dict,
                total_s: Optional[float] = None,
                page_captures: tuple = ()) -> list[dict]:
    """The suggested storyboard (title → pages → claims → close), timed.

    With a measured narration length the scenes share it by weight (≥3 s
    each); otherwise each lasts DEFAULT_SCENE_S × weight.
    """
    return storyboard.apply_timing(
        storyboard.suggest(offer, brief, page_captures), total_s)


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


#: Frame sizes per delivery orientation. The vertical base is composed
#: natively for 9:16 (larger type, narrower margins) instead of shrinking the
#: 16:9 cards into a strip on the Shorts/Reels/TikTok export.
FRAMES: Final[dict[str, tuple[int, int]]] = {
    "landscape": (WIDTH, HEIGHT),
    "vertical": (HEIGHT, WIDTH),
}


def cards_ass(scenes: list[dict], orientation: str = "landscape") -> str:
    """Styled card text for every scene (libass wraps long claims)."""
    width, height = FRAMES[orientation]
    vertical = orientation == "vertical"
    title, kicker, body, source = (84, 44, 66, 36) if vertical else (76, 40, 58, 34)
    side = 90 if vertical else 180
    kicker_v, source_v = (560, 520) if vertical else (250, 230)
    page_top, page_bottom = (520, 500) if vertical else (24, 20)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{FONT},{title},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,2,5,{side},{side},0,1
Style: Kicker,{FONT},{kicker},&H00FFB37B,&H00FFB37B,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,8,{side},{side},{kicker_v},1
Style: Body,{FONT},{body},&H00F0EAE8,&H00F0EAE8,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,2,5,{side + 20},{side + 20},0,1
Style: Source,{FONT},{source},&H00C3B4A8,&H00C3B4A8,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,{side},{side},{source_v},1
Style: PageTitle,{FONT},{kicker},&H00FFFFFF,&H00FFFFFF,&H00101825,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,8,{side},{side},{page_top},1
Style: PageSource,{FONT},{source},&H00F0EAE8,&H00F0EAE8,&H00101825,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,{side},{side},{page_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for scene in scenes:
        start, end = _ts(scene["start"]), _ts(scene["end"])
        fade = "{\\fad(350,350)}"
        if scene["kind"] == "page":
            # The screenshot itself is overlaid by base_video_cmd; the card
            # adds only its title and the derived source line.
            lines.append(f"Dialogue: 0,{start},{end},PageTitle,,0,0,0,,{fade}{_ass_text(scene['heading'])}")
            footer = " · ".join(x for x in (scene.get("body"), scene.get("source")) if x)
            lines.append(f"Dialogue: 0,{start},{end},PageSource,,0,0,0,,{fade}{_ass_text(footer)}")
            continue
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


def base_video_cmd(cards_rel: str, out_rel: str, duration_s: float,
                   orientation: str = "landscape",
                   pages: list[tuple[str, float, float]] | None = None) -> list[str]:
    """Mid-tone background + light temporal grain (+ page screenshots) + cards.

    `pages` = [(image_rel, start_s, end_s)]: each captured page is overlaid
    for its scene with a slow 5 % push-in and alpha fades, so the frame keeps
    moving (freeze QC passes on merit). Paths are RELATIVE (cwd = project
    dir) like render.py, so the subtitles filter never needs OS escaping.
    """
    pages = pages or []
    rels = [cards_rel, out_rel, *(p[0] for p in pages)]
    if any(Path(r).is_absolute() for r in rels):
        raise ValueError("use relative paths; run with cwd=project folder")
    width, height = FRAMES[orientation]
    target_w = int(width * (0.9 if orientation == "vertical" else 0.84)) // 2 * 2
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi",
           "-i", f"color=c={BACKGROUND}:s={width}x{height}:r={FPS}:d={duration_s:.3f}"]
    target_h = int(target_w * 9 / 16) // 2 * 2  # screenshots are 16:9 viewports
    for image, start, end in pages:
        # Loop each screenshot ONLY for its own scene: frames outside the
        # scene are never decoded or scaled.
        span = max(0.5, end - start)
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{span:.3f}", "-i", image]
    graph = ["[0:v]noise=alls=4:allf=t,vignette=PI/5[bg0]"]
    for index, (_image, start, end) in enumerate(pages):
        span = max(0.5, end - start)
        frames = max(1, int(round(span * FPS)))
        fade = min(0.35, span / 4)
        # zoompan (long-standing filter, no `t` in scale) gives a 5 % push-in
        # on the scene's own timeline; setpts then places it at the scene
        # start, and overlay shows the main video alone until then.
        graph.append(
            f"[{index + 1}:v]scale={target_w}:{target_h}:flags=lanczos,"
            f"zoompan=z='min(1.05,1+0.05*on/{frames})':x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':d=1:s={target_w}x{target_h}:fps={FPS},"
            f"format=yuva420p,"
            f"fade=t=in:st=0:d={fade:.3f}:alpha=1,"
            f"fade=t=out:st={span - fade:.3f}:d={fade:.3f}:alpha=1,"
            f"setpts=PTS-STARTPTS+{start:.3f}/TB[p{index}]")
        graph.append(
            f"[bg{index}][p{index}]overlay=x=(W-w)/2:y=(H-h)/2:"
            f"enable='between(t,{start:.3f},{end:.3f})'[bg{index + 1}]")
    graph.append(f"[bg{len(pages)}]subtitles={cards_rel}[vout]")
    return cmd + [
        "-filter_complex", ";".join(graph), "-map", "[vout]",
        "-t", f"{duration_s:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
        out_rel,
    ]


def scene_manifest(offer_id: str, brief: dict, scenes: list[dict],
                   storyboard_version: Optional[int] = None,
                   dropped: Optional[list[str]] = None) -> dict:
    body = {
        "version": 1,
        "track": "explainer",
        "offer_id": str(offer_id),
        "brief_id": str(brief.get("id")),
        "brief_version": brief.get("version"),
        # None = the suggested storyboard; N = the reviewer-saved version N.
        "storyboard_version": storyboard_version,
        "dropped": dropped or [],
        "scenes": scenes,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}
