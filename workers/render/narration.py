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

import hashlib
import ipaddress
import logging
import os
from pathlib import Path
from typing import Final, Optional
from urllib.parse import urlparse

log = logging.getLogger("render.narration")

FFMPEG: Final[str] = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE: Final[str] = os.environ.get("FFPROBE_PATH", "ffprobe")

_MARKDOWN_NOISE = ("```", "---", "> ", "# ", "- ", "  -")


def _is_local_endpoint(base_url: str) -> bool:
    """Loopback, private-range IP, or a single-label host (a Docker/compose
    service name such as `kokoro:8880`). Public hostnames never qualify."""
    host = (urlparse(base_url).hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or "." not in host and ":" not in host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def tts_local(base_url: str) -> bool:
    """TTS_LOCAL=1 declares a self-hosted, keyless, free TTS server (e.g. a
    Kokoro/Piper OpenAI-compatible server on the same machine or network).

    Fail-closed: the flag is honoured ONLY when the endpoint really is local.
    Pointing TTS_LOCAL at a public (paid) API keeps normal paid accounting
    and the budget gate, so a misconfiguration can never spend unbudgeted.
    """
    if os.environ.get("TTS_LOCAL", "").strip().lower() not in ("1", "true", "yes"):
        return False
    return _is_local_endpoint(base_url)


def tts_configured(language: str = "en") -> bool:
    base = (os.environ.get(f"TTS_BASE_URL_{language.upper()}")
            or os.environ.get("TTS_BASE_URL"))
    key = (os.environ.get(f"TTS_API_KEY_{language.upper()}")
           or os.environ.get("TTS_API_KEY"))
    return bool(base and (key or tts_local(base)))


def voice_for(language: str = "en") -> str:
    if language == "ur":
        return (os.environ.get("TTS_VOICE_UR")
                or os.environ.get("TTS_VOICE")
                or "ur-PK-AsadNeural")
    return os.environ.get("TTS_VOICE", "onyx")


def model_for(language: str = "en") -> str:
    return (os.environ.get(f"TTS_MODEL_{language.upper()}")
            or os.environ.get("TTS_MODEL", "tts-1"))


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


def _costing():
    """Shared cost module (WP-F), imported lazily so tests without the
    packages path on sys.path keep importing this module."""
    try:
        import costing
    except ImportError:  # pragma: no cover — fallback for direct imports
        import sys as _sys
        _sys.path.insert(0, os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "packages")))
        import costing
    return costing


def synthesize(text: str, out_path: Path, *,
               base_url: Optional[str] = None,
               api_key: Optional[str] = None,
               model: Optional[str] = None,
               voice: Optional[str] = None,
               language: str = "en",
               cost=None) -> Optional[Path]:
    """One narration line → MP3 via an OpenAI-compatible /audio/speech endpoint.
    Returns None on any failure (never raises into the pipeline).

    Cost engine (WP-F): with a `cost` client attached, an unchanged
    narration line is served from the shared
    `tts:{sha256(text+voice+model)}` cache (0 characters spent on a
    re-render), and the DAILY TTS CHAR BUDGET is checked BEFORE the call —
    denied → None (the capture's own audio stays the fallback) and the
    block is recorded so Needs-You shows it.

    Urdu uses language-specific env overrides first:
      TTS_BASE_URL_UR / TTS_API_KEY_UR / TTS_MODEL_UR / TTS_VOICE_UR
    Providers differ in language support; a deployment can point Urdu at a
    regional voice without changing the English pipeline.
    """
    import httpx

    base = (base_url
            or os.environ.get(f"TTS_BASE_URL_{language.upper()}")
            or os.environ.get("TTS_BASE_URL", "")).rstrip("/")
    key = (api_key
           or os.environ.get(f"TTS_API_KEY_{language.upper()}")
           or os.environ.get("TTS_API_KEY", ""))
    local = tts_local(base)
    if not base or not (key or local):
        return None
    provider = "local" if local else "openai-compatible"
    model_id = model or model_for(language)
    voice_id = voice or voice_for(language)
    endpoint = urlparse(base)
    cache_key = _costing().tts_cache_key(
        text, voice=voice_id, model=model_id,
        provider=f"{endpoint.netloc}{endpoint.path}".rstrip("/"))
    reservation_id = None

    if cost is not None:
        cached_path = _cached_audio(cost.cache_lookup("tts", cache_key), out_path)
        if cached_path is not None:
            cost.report("tts", units=0, provider=provider,
                        model=model_id, unit_type="chars",
                        meta={"cache_hit": True, "local": local})
            return cached_path
        if not local:
            # G04: reserve the predicted char count atomically before the
            # call; the usage report after success settles this reservation.
            # A verified-local server costs nothing, so it needs no reservation.
            gate = cost.budget_check("tts", units=len(text or ""),
                                     provider=provider, model=model_id)
            if not gate.get("allowed"):
                return None
            reservation_id = gate.get("reservation_id")
    body = {
        "model": model_id,
        "voice": voice_id,
        "input": text,
        "response_format": "mp3",
    }
    try:
        resp = httpx.post(
            f"{base}/audio/speech",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {key}"} if key else {})},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        if cost is not None:
            cost.cache_store("tts", cache_key, _shareable_entry(out_path))
            cost.report("tts", units=len(text or ""), provider=provider,
                        model=model_id, unit_type="chars",
                        settle_reservation=reservation_id,
                        meta={"local": local})
        return out_path
    except Exception:  # noqa: BLE001
        # G04: a failed/sent TTS request leaves its reservation standing —
        # the provider may still bill for it; unknown usage is not free.
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _storage():
    """Configured object storage (None when MTK_STORAGE_BACKEND is unset)."""
    from object_storage import make_from_env
    return make_from_env()


def _shareable_entry(audio: Path) -> dict:
    """Cache value for a fresh synthesis (G25).

    With object storage configured the audio is uploaded content-addressed
    and the entry carries its ref + sha256, so ANY render host can reuse it.
    The local path stays as a same-host fast path (and for setups without
    storage, which keep the previous single-host behaviour).
    """
    entry: dict = {"path": str(audio), "sha256": _sha256_file(audio)}
    try:
        storage = _storage()
        if storage is not None:
            from object_storage import tts_key
            entry["ref"] = storage.put(audio, tts_key(entry["sha256"]))
    except Exception as exc:  # noqa: BLE001 — sharing is an optimisation
        log.warning("narration audio not shared to storage: %s", exc)
    return entry


def _cached_audio(entry, out_path: Path) -> Optional[Path]:
    """A verified local copy of cached narration, or None (= cache miss).

    Order: the original file on this host; else download the shared ref next
    to `out_path`. Either way the bytes must match the recorded sha256 — a
    truncated or replaced file is a miss, never silently reused.
    """
    if not isinstance(entry, dict):
        return None
    expected = entry.get("sha256")
    local = Path(entry["path"]) if entry.get("path") else None
    if local is not None and local.is_file() and local.stat().st_size > 0:
        if not expected or _sha256_file(local) == expected:
            return local
    ref = entry.get("ref")
    if not ref or not expected:
        return None
    try:
        from object_storage import materialize
        fetched = materialize(str(ref), out_path.parent / "shared-cache")
    except Exception as exc:  # noqa: BLE001 — a miss, not a failure
        log.warning("shared narration audio unavailable: %s", exc)
        return None
    if fetched is None or not Path(fetched).is_file():
        return None
    if _sha256_file(Path(fetched)) != expected:
        log.warning("shared narration audio failed its sha256 check — re-synthesizing")
        return None
    return Path(fetched)


def synthesize_all(segments: list[str], out_dir: Path,
                   language: str = "en", cost=None) -> dict:
    """Render all segments; returns {"paths": [...], "used": bool}.

    Partial success is treated as failure (a narration with holes is worse
    than no narration) so the capture audio remains the fallback.
    """
    if not tts_configured(language) or not segments:
        return {"paths": [], "used": False}
    paths: list[str] = []
    for i, seg in enumerate(segments):
        out = synthesize(seg, out_dir / f"narration-{i:03d}.mp3",
                         language=language, cost=cost)
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


def disclosure_record(used: bool, model: str | None = None,
                      language: str = "en") -> dict:
    if not used:
        # Keep this exact legacy shape: downstream approval/render tests and
        # adapters treat a missing track as "no synthetic disclosure required".
        return {"synthetic_narration": False}
    return {
        "synthetic_narration": True,
        "tts_model": model or model_for(language),
        "language": language,
        "label_required": True,
        "note": "synthetic voice narration — label per platform policy (master plan §5)",
    }
