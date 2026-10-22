"""Caption generation — .srt and .vtt from source segments.

Captions are first-class source assets (master plan §5): regenerated from the
step log / narration segments, never hand-patched after export.
"""

import os
import re
from typing import Any

_WORDS_PER_MINUTE = 150
_MIN_CUE_S = 1.2
_MAX_CUE_S = 8.0

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", text or "")).strip()


def _start_seconds(value: Any) -> float | None:
    """Parse a step-log timestamp without ever letting bad data kill export."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            return max(0.0, float(value))
        except ValueError:
            return None
    return None


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """Split a caption into screen-fitting chunks without cutting words.

    ~84 characters is two comfortable lines at the default ASS size. Without
    this, a long step description burns a single unreadable cue for 8 seconds.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            while len(word) > max_chars:
                chunks.append(word[:max_chars])
                word = word[max_chars:]
            current = word
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks or [text]


def build_cues(
    segments: list[dict[str, Any]],
    wpm: int = _WORDS_PER_MINUTE,
    min_cue_s: float = _MIN_CUE_S,
    max_cue_s: float = _MAX_CUE_S,
    max_chars: int = 84,
) -> list[dict[str, Any]]:
    """Cues from ordered segments [{text, start?, title?, description?}].

    v0.27 fix: a real `start` timestamp is honoured, so captions follow the
    actual claim walkthrough instead of starting at zero and drifting. If a
    start is missing (or earlier than the previous cue), timing stays
    contiguous. Duration still derives from word count at `wpm`; cues are
    monotonic and never overlap.
    """
    cues: list[dict[str, Any]] = []
    t = 0.0
    for seg in segments:
        text = _clean(seg.get("text") or seg.get("title") or seg.get("description") or "")
        if not text:
            continue
        requested_start = _start_seconds(seg.get("start"))
        start = max(t, requested_start) if requested_start is not None else t
        for chunk_index, chunk in enumerate(_chunk_text(text, max_chars)):
            words = len(chunk.split())
            duration = min(max(words * 60.0 / wpm, min_cue_s), max_cue_s)
            cue_start = start if chunk_index == 0 else t
            cues.append({
                "index": len(cues) + 1,
                "start": round(cue_start, 3),
                "end": round(cue_start + duration, 3),
                "text": chunk,
            })
            t = cue_start + duration
    return cues


def _fmt(seconds: float, decimal: str) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{ms:03d}"


def to_srt(cues: list[dict[str, Any]]) -> str:
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue['index']}\n"
            f"{_fmt(cue['start'], ',')} --> {_fmt(cue['end'], ',')}\n"
            f"{cue['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(cues: list[dict[str, Any]]) -> str:
    if not cues:
        return "WEBVTT\n"
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue['index']}\n"
            f"{_fmt(cue['start'], '.')} --> {_fmt(cue['end'], '.')}\n"
            f"{cue['text']}"
        )
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def _ass_time(seconds: float) -> str:
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def to_ass(cues: list[dict[str, Any]], language: str = "en",
           *, width: int = 1920, height: int = 1080,
           font: str | None = None) -> str:
    """Styled captions for burning (libass) with an RTL-safe Urdu style.

    SRT is still written for platform-native caption upload; ASS is the
    burned-in version because it supports a readable stroke, safe margins and
    a proper Urdu font/alignment. Font must be installed on the render host.
    """
    vertical = height > width
    if language == "ur":
        font_name = font or "Noto Nastaliq Urdu"
        alignment = 2
        font_size = 62 if vertical else 54
        margin_v = 180 if vertical else 86
    else:
        # DejaVu Sans is installed on the render host and has excellent
        # legibility for English captions; operators can override with
        # MTK_CAPTION_FONT (e.g. Inter or Montserrat).
        font_name = font or os.environ.get("MTK_CAPTION_FONT", "DejaVu Sans")
        alignment = 2
        font_size = 64 if vertical else 52
        margin_v = 170 if vertical else 64
    margin_lr = 120 if vertical else 90
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00101825,&H80000000,"
        f"1,0,0,0,100,100,0,0,1,4,2,{alignment},{margin_lr},{margin_lr},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for cue in cues:
        text = str(cue["text"]).replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")
        events.append(
            f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},"
            f"Default,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + ("\n" if events else "")


def _relative_start(value: Any, origin: Any) -> float | None:
    """Capture step logs store ISO timestamps; captions need seconds from the
    first observed step. Numeric values are already seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    if not isinstance(value, str) or not isinstance(origin, str):
        return None
    try:
        from datetime import datetime

        start = datetime.fromisoformat(value.replace("Z", "+00:00"))
        base = datetime.fromisoformat(origin.replace("Z", "+00:00"))
        return max(0.0, (start - base).total_seconds())
    except ValueError:
        return None


def segments_from_step_log(step_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordered narration segments derived from the capture step log.

    Real timestamps are converted to seconds relative to the first step so
    captions follow the walkthrough instead of drifting from T=0.
    """
    ordered = sorted(step_log or [], key=lambda e: e.get("n", 0))
    origin = next((e.get("at") for e in ordered if isinstance(e.get("at"), str)), None)
    segments = []
    for entry in ordered:
        text = entry.get("description") or entry.get("title") or ""
        if text:
            segments.append({"text": text,
                             "start": _relative_start(entry.get("at"), origin)})
    return segments
