"""Optional TTS narration (master plan §7 video layer, §5 authenticity rules).

Synthetic narration must be labeled: when TTS is used, the render's
disclosure metadata records it so platform policy labels can be applied (§5:
"Label synthetic narration/visuals where platform policy requires it").

Configured via env:
    TTS_BASE_URL   e.g. https://api.openai.com/v1 (OpenAI-compatible)
    TTS_API_KEY
    TTS_MODEL      default "tts-1"
    TTS_VOICE      default "onyx"

When not configured (or on any failure) narration is skipped and the capture's
own audio is used — verification must never depend on TTS being available.
"""

import os
from pathlib import Path
from typing import Final, Optional

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE: Final[str] = os.environ.get("FFPROBE_PATH", "ffprobe")

_MARKDOWN_NOISE = ("```", "---", "> ", "# ", "- ", "  -")


def tts_configured() -> bool:
    return bool(os.environ.get("TTS_BASE_URL") and os.environ.get("TTS_API_KEY"))


def narration_segments(markdown: str) -> list[str]:
    """Spoken segments derived from the script: headings become plain lines,
    code blocks are SKIPPED (commands are shown on screen, not spoken), block
    quotes and list bullets are flattened."""
    segments: list[str] = []
    in_code = False
    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        text = line
        for noise in _MARKDOWN_NOISE:
            if text.startswith(noise):
                text = text[len(noise):]
                break
        text = text.replace("**", "").replace("_", "").strip()
        if text:
            segments.append(text)
    return segments


def synthesize(text: str, out_path: Path, *,
               base_url: Optional[str] = None,
               api_key: Optional[str] = None,
               model: Optional[str] = None,
               voice: Optional[str] = None) -> Optional[Path]:
    """One narration line → MP3 via an OpenAI-compatible /audio/speech endpoint.
    Returns None on any failure (never raises into the pipeline)."""
    import httpx

    base = (base_url or os.environ.get("TTS_BASE_URL", "")).rstrip("/")
    key = api_key or os.environ.get("TTS_API_KEY", "")
    if not base or not key:
        return None
    body = {
        "model": model or os.environ.get("TTS_MODEL", "tts-1"),
        "voice": voice or os.environ.get("TTS_VOICE", "onyx"),
        "input": text,
        "response_format": "mp3",
    }
    try:
        resp = httpx.post(
            f"{base}/audio/speech",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        return out_path
    except Exception:  # noqa: BLE001
        return None


def synthesize_all(segments: list[str], out_dir: Path) -> dict:
    """Render all segments; returns {"paths": [...], "used": bool}.

    Partial success is treated as failure (a narration with holes is worse
    than no narration) so the capture audio remains the fallback.
    """
    if not tts_configured() or not segments:
        return {"paths": [], "used": False}
    paths: list[str] = []
    for i, seg in enumerate(segments):
        out = synthesize(seg, out_dir / f"narration-{i:03d}.mp3")
        if out is None:
            return {"paths": [], "used": False}
        paths.append(str(out))
    return {"paths": paths, "used": True}


def concat_paths(paths: list[str], out_path: Path) -> Optional[Path]:
    if not paths:
        return None
    list_file = out_path.with_suffix(".txt")
    list_file.write_text("\n".join(f"file '{p}'" for p in paths), encoding="utf-8")
    return list_file


def ffmpeg_concat_cmd(list_file: Path, out_path: Path) -> list[str]:
    """Concat-demuxer command that RE-ENCODES to a canonical audio format
    (libmp3lame, 44.1 kHz stereo, v0.17). The v0.14 stream-copy (-c copy)
    silently produced corrupt output whenever segments differed in codec
    parameters (sample rate/channels/bitrate — e.g. a TTS provider or model
    change between retry batches). Re-encoding makes the concat codec-agnostic
    at the cost of one TTS-track encode (~seconds).
    -safe 0 because segment paths are absolute; -t tolerance via later probe.
    """
    return [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        str(out_path),
    ]


def probe_duration_seconds(path: Path) -> float | None:
    """ffprobe duration in seconds, or None when unreadable/undecodable."""
    import subprocess

    try:
        proc = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(proc.stdout.strip()) if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001 — probe failure = treat as unverifiable
        return None


def mix_segments(paths: list[str], out_dir: Path) -> Optional[Path]:
    """Per-segment TTS files → ONE narration track (v0.14, hardened v0.17).

    Returns the mixed track path, or None on any failure — callers must treat
    None as "no narration" so the disclosure metadata never claims synthetic
    narration that isn't in the render (§5 authenticity). A duration check
    (output must decode and cover ≥85% of the summed segment length) converts
    the old silent-at-boundaries corruption into an explicit refusal.
    """
    if not paths:
        return None
    out = out_dir / "narration.mp3"
    list_file = concat_paths(paths, out)
    if list_file is None:
        return None
    import subprocess

    try:
        proc = subprocess.run(
            ffmpeg_concat_cmd(list_file, out), capture_output=True, text=True, timeout=300
        )
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        return None

    expected = sum(_seg_duration(p) for p in paths)
    actual = probe_duration_seconds(out)
    if actual is None or actual <= 0:
        return None
    if expected and actual < expected * 0.85:
        return None  # truncated/corrupt track — prefer capture-audio fallback
    return out


def _seg_duration(path: str) -> float:
    return probe_duration_seconds(Path(path)) or 0.0


def disclosure_record(used: bool, model: str | None = None) -> dict:
    if not used:
        return {"synthetic_narration": False}
    return {
        "synthetic_narration": True,
        "tts_model": model or os.environ.get("TTS_MODEL", "tts-1"),
        "label_required": True,
        "note": "synthetic voice narration — label per platform policy (master plan §5)",
    }
