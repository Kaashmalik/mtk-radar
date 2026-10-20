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


def write_script(project: Path, markdown: str, version: int) -> Path:
    path = project / "script.md"
    path.write_text(markdown, encoding="utf-8")
    _touch_version_file(project, version)
    return path


def write_evidence_json(project: Path, evidence: list[dict[str, Any]]) -> Path:
    path = project / "evidence.json"
    path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return path


def write_captions(project: Path, srt: str, vtt: str) -> tuple[Path, Path]:
    srt_path = project / "assets" / "captions.srt"
    vtt_path = project / "assets" / "captions.vtt"
    srt_path.write_text(srt, encoding="utf-8", newline="\n")
    vtt_path.write_text(vtt, encoding="utf-8", newline="\n")
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
) -> dict[str, Any]:
    return {
        "product": "MTK RADAR AI",
        "manifest_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
        },
        "renders": renders,
        "disclosure": {
            "synthetic_narration": narration_used,
            "label_required": narration_used,
        },
        "revision_note": "regenerate from these source assets; never hand-edit exported files",
    }


def write_edit_manifest(project: Path, manifest: dict[str, Any]) -> Path:
    path = project / "edit_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path


def _touch_version_file(project: Path, version: int) -> None:
    (project / ".script_version").write_text(str(version), encoding="utf-8")
