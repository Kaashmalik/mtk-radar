"""Capture-lab quality checks (v0.27).

Recorded footage is the source of truth for a claim walkthrough. A capture can
be technically valid (a file exists) and still be unusable: no audio, wrong
resolution, too short for the checklist, or a step log that skipped the
proof page. These checks are advisory to the human operator, then the API's
redaction gate remains the hard block.

`ffprobe` is injected so the rules can be tested without a media binary.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")
MIN_DURATION_S = 20.0
MIN_WIDTH = 720
MIN_HEIGHT = 480


def probe_streams(path: str) -> dict[str, Any] | None:
    """Return {duration_s, width, height, has_audio} or None if unreadable."""
    try:
        proc = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001 — checking must never kill capture
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout or "{}")
    except ValueError:
        return None
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = (payload.get("format") or {}).get("duration")
    try:
        duration_s = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_s = None
    return {
        "duration_s": duration_s,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": audio is not None,
    }


def run_checks(
    video_path: str | None,
    step_log: list[dict[str, Any]],
    *,
    expected_steps: int = 0,
    probe: Callable[[str], dict[str, Any] | None] = probe_streams,
) -> dict[str, Any]:
    """Return {ok, checks, warnings, blocking} for the operator.

    Blocking checks are things a reviewer cannot fix by simply approving:
    missing footage or missing evidence steps. Warnings are fixable (audio,
    short clip, resolution) and stay visible in the capture notes.
    """
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocking: list[str] = []

    def add(name: str, ok: bool, detail: str, *, hard: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "blocking": hard})
        if not ok:
            (blocking if hard else warnings).append(f"{name}: {detail}")

    add("video_present", bool(video_path), "recording file exists" if video_path
        else "no recording file was produced", hard=True)

    media = probe(video_path) if video_path else None
    if video_path and media is None:
        add("media_readable", False, "ffprobe could not read the recording", hard=True)
    elif media:
        duration = media.get("duration_s") or 0
        add("duration", duration >= MIN_DURATION_S,
            f"{duration:.1f}s (minimum {MIN_DURATION_S:.0f}s)")
        add("resolution", media.get("width", 0) >= MIN_WIDTH
            and media.get("height", 0) >= MIN_HEIGHT,
            f"{media.get('width')}×{media.get('height')}")
        add("audio", bool(media.get("has_audio")), "audio track present"
            if media.get("has_audio") else "no audio track — add narration or re-record")

    steps = [entry for entry in (step_log or []) if isinstance(entry, dict)]
    add("step_log", bool(steps), f"{len(steps)} step(s) logged", hard=True)
    if expected_steps:
        add("step_coverage", len(steps) >= expected_steps,
            f"{len(steps)}/{expected_steps} scripted steps logged")
    evidence_hits = [
        entry for entry in steps
        if entry.get("url") or entry.get("kind") in ("verification", "proof", "result")
    ]
    add("proof_step", bool(evidence_hits),
        f"{len(evidence_hits)} page/proof step(s) logged")

    return {
        "ok": not blocking,
        "ready_for_review": not blocking and not warnings,
        "checks": checks,
        "warnings": warnings,
        "blocking": blocking,
    }
