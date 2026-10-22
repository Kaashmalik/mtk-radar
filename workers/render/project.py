"""Project bundle + edit manifest (master plan §5).

"A project folder per offer: evidence.json, script.md, source links, capture
video, narration audio, captions (.srt/.vtt), thumbnail, rendered 16:9 and
9:16 files, and an edit manifest." Preserved so a project can be revised when
the offer changes — regeneration always rebuilds from versioned source assets.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def project_dir(root: Path, offer_id: str) -> Path:
    path = Path(root) / str(offer_id)
    for sub in ("assets", "renders"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path


def write_script(project: Path, markdown: str, version: int,
                 language: str = "en") -> Path:
    path = project / ("script.md" if language == "en" else f"script.{language}.md")
    path.write_text(markdown, encoding="utf-8")
    _touch_version_file(project, version, language)
    return path


def write_evidence_json(project: Path, evidence: list[dict[str, Any]]) -> Path:
    path = project / "evidence.json"
    path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return path


def write_captions(project: Path, srt: str, vtt: str,
                   language: str = "en", ass: Optional[str] = None) -> tuple[Path, Path]:
    suffix = "" if language == "en" else f".{language}"
    srt_path = project / "assets" / f"captions{suffix}.srt"
    vtt_path = project / "assets" / f"captions{suffix}.vtt"
    srt_path.write_text(srt, encoding="utf-8", newline="\n")
    vtt_path.write_text(vtt, encoding="utf-8", newline="\n")
    if ass is not None:
        (project / "assets" / f"captions{suffix}.ass").write_text(
            ass, encoding="utf-8", newline="\n"
        )
    return srt_path, vtt_path


def write_step_log(project: Path, step_log: list[dict[str, Any]]) -> Path:
    path = project / "assets" / "step_log.json"
    path.write_text(json.dumps(step_log, indent=2, default=str), encoding="utf-8")
    return path


def build_edit_manifest(
    *,
    offer: dict[str, Any],
    script_version: Optional[int],
    capture_id: Optional[str],
    capture_video: Optional[str],
    srt: Optional[str],
    vtt: Optional[str],
    narration_used: bool,
    renders: list[dict[str, Any]],
    language: str = "en",
    covers: Optional[list[dict[str, Any]]] = None,
    motion: Optional[dict[str, Any]] = None,
    captions_language: str = "en",
) -> dict[str, Any]:
    return {
        "product": "MTK RADAR AI",
        "manifest_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": language,
        "voiceover_language": language,
        "captions_language": captions_language,
        "offer": {
            "id": offer.get("id"),
            "title": offer.get("title"),
            "provider": offer.get("provider"),
            "state": offer.get("state"),
        },
        "sources": {
            "script_version": script_version,
            "capture_id": capture_id,
            "capture_video": capture_video,
            "captions": {"srt": srt, "vtt": vtt},
            "narration": {
                "synthetic": narration_used,
                "fallback": "capture audio" if not narration_used else None,
            },
            "covers": covers or [],
            "motion": motion or {},
        },
        "renders": renders,
        "disclosure": {
            "synthetic_narration": narration_used,
            "label_required": narration_used,
        },
        "revision_note": "regenerate from these source assets; never hand-edit exported files",
    }


def write_edit_manifest(project: Path, manifest: dict[str, Any],
                        language: str = "en") -> Path:
    name = "edit_manifest.json" if language == "en" else f"edit_manifest.{language}.json"
    path = project / name
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path


def _touch_version_file(project: Path, version: int, language: str = "en") -> None:
    name = ".script_version" if language == "en" else f".script_version.{language}"
    (project / name).write_text(str(version), encoding="utf-8")
