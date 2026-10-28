"""Storyboard: the reviewable scene list of a research explainer (V7).

One pure module shared by the API (validation of a reviewer's edits) and the
render worker (timing + manifest), so the honesty rules cannot drift between
what the editor accepts and what the renderer draws.

Scene kinds
- ``title``  — the viewer question; heading/body editable (bounded).
- ``claim``  — one claim of the CURRENT research brief. Its wording, class
  attribution and source are DERIVED from the claim ledger and can never be
  rewritten in the editor; contradicted claims are refused; "unknown" claims
  always carry "not yet independently confirmed".
- ``page``   — a captured public page (screenshot) with its source line;
  the caption is editable, the source is derived from the capture.
- ``close``  — limitations / sources; editable (bounded).

Editable by the reviewer: order, include/exclude, relative duration
(``weight``), and the free text of title/page/close scenes. Everything is
size-bounded and control-character free, and every saved storyboard is
hashed so the render manifest proves which version was drawn.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

ATTRIBUTION: dict[str, str] = {
    "author_reported": "The authors report",
    "independently_reproduced": "Independently reproduced",
    "tested_by_mtk": "Tested by MTK",
    "editorial_analysis": "Our analysis",
}
UNCONFIRMED = " — not yet independently confirmed"
KINDS = ("title", "claim", "page", "close")
MAX_SCENES = 30
MAX_HEADING, MAX_BODY = 140, 400
MIN_WEIGHT, MAX_WEIGHT = 0.5, 5.0
MIN_SCENE_S, DEFAULT_SCENE_S = 3.0, 6.0
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(value: Any, limit: int) -> str:
    text = _CONTROL.sub("", str(value or "")).replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit]


def claim_source(claim: dict) -> str:
    owner = (claim.get("source_owner") or "").strip()
    url = (claim.get("source_url") or "").strip()
    host = urlparse(url).hostname if url else None
    label = owner or host or ""
    date = claim.get("source_date")
    if label and date:
        label = f"{label} · {date}"
    return f"Source: {label}" if label else "Source: not cited"


def page_source(capture: dict) -> str:
    host = urlparse(str(capture.get("final_url") or capture.get("url") or "")).hostname or ""
    when = str(capture.get("captured_at") or "")[:10]
    return f"Source: {host}" + (f" · captured {when}" if when else "")


def claim_scene(claim: dict) -> dict:
    attribution = ATTRIBUTION.get(claim.get("claim_class"), "Reported")
    if claim.get("status") == "unknown":
        attribution += UNCONFIRMED
    return {
        "id": f"claim-{claim.get('id')}",
        "kind": "claim",
        "heading": attribution,
        "body": clean_text(claim.get("permitted_wording") or claim.get("claim_text"), MAX_BODY),
        "source": claim_source(claim),
        "scope": clean_text(claim.get("scope"), 120),
        "claim_ids": [str(claim.get("id"))],
    }


def page_scene(capture: dict, caption: str = "") -> dict:
    return {
        "id": f"page-{capture.get('id')}",
        "kind": "page",
        "heading": clean_text(capture.get("title") or "Source page", MAX_HEADING),
        "body": clean_text(caption, MAX_BODY),
        "source": page_source(capture),
        "page_capture_id": str(capture.get("id")),
        "claim_ids": [],
    }


def suggest(offer: dict, brief: dict, page_captures: Iterable[dict] = ()) -> list[dict]:
    """Default storyboard: question → pages → shown claims → close."""
    scenes: list[dict] = [{
        "id": "title", "kind": "title",
        "heading": clean_text(brief.get("viewer_question") or offer.get("title")
                              or "Research explained", MAX_HEADING),
        "body": clean_text(brief.get("angle"), MAX_BODY),
        "claim_ids": [],
    }]
    for capture in page_captures:
        if capture.get("status", "ok") == "ok":
            scenes.append(page_scene(capture))
    for claim in brief.get("claims") or []:
        if claim.get("status") == "contradicted":
            continue
        scene = claim_scene(claim)
        if scene["body"]:
            scenes.append(scene)
    closing = clean_text(brief.get("limitations"), MAX_BODY)
    scenes.append({
        "id": "close", "kind": "close",
        "heading": "Limitations" if closing else "Sources",
        "body": closing or "Every source is linked in the description.",
        "claim_ids": [],
    })
    for scene in scenes:
        scene.setdefault("weight", 1.0)
        scene.setdefault("include", True)
    return scenes


def validate(edits: list[dict], brief: dict,
             page_captures: Iterable[dict] = ()) -> tuple[list[dict], list[str]]:
    """Rebuild a reviewer's storyboard from trusted data.

    Returns (scenes, problems). Problems are blocking: the API refuses to
    save, and the renderer drops the offending scenes (never draws them).
    """
    problems: list[str] = []
    claims = {str(c.get("id")): c for c in brief.get("claims") or []}
    pages = {str(p.get("id")): p for p in page_captures}
    if not isinstance(edits, list) or not edits:
        return [], ["a storyboard needs at least one scene"]
    if len(edits) > MAX_SCENES:
        problems.append(f"at most {MAX_SCENES} scenes")
        edits = edits[:MAX_SCENES]
    scenes: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(edits, start=1):
        raw = raw if isinstance(raw, dict) else {}
        kind = raw.get("kind")
        try:
            weight = float(raw.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        weight = min(MAX_WEIGHT, max(MIN_WEIGHT, weight))
        include = raw.get("include", True) is not False
        if kind == "claim":
            claim_id = str((raw.get("claim_ids") or [raw.get("claim_id")])[0] or "")
            claim = claims.get(claim_id)
            if claim is None:
                problems.append(f"scene {index}: claim is not in the current research brief")
                continue
            if claim.get("status") == "contradicted":
                problems.append(f"scene {index}: a contradicted claim cannot be shown")
                continue
            scene = claim_scene(claim)  # wording/attribution/source are derived
        elif kind == "page":
            capture = pages.get(str(raw.get("page_capture_id") or ""))
            if capture is None or capture.get("status", "ok") != "ok":
                problems.append(f"scene {index}: page capture missing or failed")
                continue
            scene = page_scene(capture, raw.get("body", ""))
            if raw.get("heading"):
                scene["heading"] = clean_text(raw["heading"], MAX_HEADING)
        elif kind in ("title", "close"):
            heading = clean_text(raw.get("heading"), MAX_HEADING)
            if not heading:
                problems.append(f"scene {index}: {kind} needs a heading")
                continue
            scene = {"id": kind, "kind": kind, "heading": heading,
                     "body": clean_text(raw.get("body"), MAX_BODY), "claim_ids": []}
        else:
            problems.append(f"scene {index}: unknown kind {kind!r}")
            continue
        if scene["id"] in seen:
            problems.append(f"scene {index}: duplicate scene {scene['id']}")
            continue
        seen.add(scene["id"])
        scene["weight"] = round(weight, 2)
        scene["include"] = include
        scenes.append(scene)
    if not any(s["include"] for s in scenes):
        problems.append("at least one scene must be included")
    return scenes, problems


def apply_timing(scenes: list[dict], total_s: Optional[float] = None) -> list[dict]:
    """Start/end for the INCLUDED scenes, shared by weight (≥ MIN_SCENE_S)."""
    shown = [dict(s) for s in scenes if s.get("include", True)]
    if not shown:
        return []
    weights = [float(s.get("weight", 1.0)) for s in shown]
    if total_s and total_s > 0:
        raw = [total_s * w / sum(weights) for w in weights]
        durations = [max(MIN_SCENE_S, d) for d in raw]
        scale = total_s / sum(durations)
        durations = [d * scale for d in durations]
    else:
        durations = [DEFAULT_SCENE_S * w for w in weights]
    cursor = 0.0
    for scene, duration in zip(shown, durations):
        scene["start"] = round(cursor, 3)
        cursor += duration
        scene["end"] = round(cursor, 3)
    return shown


def digest(scenes: list[dict]) -> str:
    return hashlib.sha256(json.dumps(scenes, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()
