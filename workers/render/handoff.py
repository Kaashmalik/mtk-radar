"""Editing handoff bundle — Kdenlive/CapCut asset export (week 9, master plan §5).

Plan rule: "Provide 'Open in CapCut' via clean exports and project assets;
CapCut project format/integration may be limited, so do not promise
round-trip editable timelines without testing. Also provide Kdenlive-friendly
media and a project file where feasible." → We ship a clean ASSET bundle +
import notes, never a proprietary project file.

Usage:
    python workers/render/handoff.py --project projects/<offer-id> [--out handoff]
"""

import argparse
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

README = """# Editing handoff bundle — {title}

Generated {now} by MTK RADAR AI.

## What's inside
- `script.md` — approved script (version {script_version}); facts are pinned to evidence.json
- `evidence.json` — source links + content hashes (keep source links in your video description)
- `assets/` — captions (.srt + .vtt), step log, narration segments (if any)
- `renders/` — rendered exports (16:9 / 9:16) as reference cuts
- `edit_manifest.json` — the authoritative asset/version list

## Import notes (Kdenlive / CapCut / Resolve)
1. Import the whole `assets/` folder plus your own capture recording.
2. Captions: prefer importing `assets/captions.srt` as a subtitle track —
   do NOT retype captions (risk of factual drift from approved copy).
3. Keep the wrap-up summary card text verbatim from `script.md` (expiry,
   renewal warning, source links) — these are compliance items, not style items.
4. This bundle does NOT contain a native project file: import assets manually.
   (Round-trip project compatibility is deliberately not promised — plan §5.)
5. After editing, re-run redaction review BEFORE export/publish (plan §4).
"""

ASSET_EXTENSIONS = {".srt", ".vtt", ".json", ".md", ".mp3", ".wav", ".png", ".jpg"}


def build_bundle(project_dir: Path, out_dir: Path) -> Path:
    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise SystemExit(f"project folder not found: {project_dir}")

    manifest_path = project_dir / "edit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    offer_id = project_dir.name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bundle_name = f"handoff-{offer_id}-{stamp}"
    bundle_root = out_dir / bundle_name
    bundle_root.mkdir(parents=True, exist_ok=True)

    # 1. human notes
    script_version = manifest.get("sources", {}).get("script_version") or "?"
    title = manifest.get("offer", {}).get("title", offer_id)
    (bundle_root / "README.txt").write_text(
        README.format(title=title, now=manifest.get("generated_at", ""),
                      script_version=script_version),
        encoding="utf-8",
    )

    # 2. copy selected source assets (never the rendered reference cuts' intent:
    #    they're included as reference only)
    copied = []
    for item in sorted(project_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(project_dir)
        if rel.parts and rel.parts[0] in ("assets", "renders") or item.name in (
            "script.md", "evidence.json", "edit_manifest.json"
        ):
            dest = bundle_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied.append(str(rel))

    # 3. asset list CSV for hand-off checklists
    (bundle_root / "asset_list.csv").write_text(
        "path\n" + "\n".join(copied) + "\n", encoding="utf-8"
    )

    # 4. zip
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(bundle_root.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(bundle_root))
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="MTK RADAR editing handoff bundle")
    parser.add_argument("--project", required=True, help="project folder (projects/<offer-id>)")
    parser.add_argument("--out", default="handoff")
    args = parser.parse_args()
    zip_path = build_bundle(Path(args.project), Path(args.out))
    print(f"handoff bundle ready: {zip_path}")
    print("import notes are inside README.txt — captions/subtitles must be reused, not retyped")


if __name__ == "__main__":
    main()
