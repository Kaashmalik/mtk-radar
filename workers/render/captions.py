"""Caption generation — .srt and .vtt from source segments.

Captions are first-class source assets (master plan §5): regenerated from the
step log / narration segments, never hand-patched after export.
"""

import re
from typing import Any

_WORDS_PER_MINUTE = 150
_MIN_CUE_S = 1.2
_MAX_CUE_S = 8.0

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", text or "")).strip()


def build_cues(
    segments: list[dict[str, Any]],
    wpm: int = _WORDS_PER_MINUTE,
    min_cue_s: float = _MIN_CUE_S,
    max_cue_s: float = _MAX_CUE_S,
) -> list[dict[str, Any]]:
    """Contiguous cues from ordered segments [{text, start?, title?, description?}].

    Duration derives from word count at `wpm`; timings are monotonically
    increasing and never overlap.
    """
    cues: list[dict[str, Any]] = []
    t = 0.0
    for seg in segments:
        text = _clean(seg.get("text") or seg.get("title") or seg.get("description") or "")
        if not text:
            continue
        words = len(text.split())
        duration = min(max(words * 60.0 / wpm, min_cue_s), max_cue_s)
        cues.append({
            "index": len(cues) + 1,
            "start": round(t, 3),
            "end": round(t + duration, 3),
            "text": text,
        })
        t += duration
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


def segments_from_step_log(step_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordered narration segments derived from the capture step log."""
    segments = []
    for entry in sorted(step_log or [], key=lambda e: e.get("n", 0)):
        text = entry.get("description") or entry.get("title") or ""
        if text:
            segments.append({"text": text, "start": entry.get("at")})
    return segments
