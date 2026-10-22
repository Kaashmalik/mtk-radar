#!/usr/bin/env python3
"""Media backup + manifest verification (v0.27).

The database is not the only irreplaceable asset: captures, renders, covers
and narration are large and expensive to recreate. This script implements the
"laptop pull" side of the 3-2-1 policy:

  server primary → off-site object store → operator laptop

Two modes:

  local copy    --source /srv/mtk/media --dest /mnt/laptop/mtk-media
  rclone pull   --rclone-remote server:mtk-media --dest /mnt/laptop/mtk-media

Every snapshot gets a SHA-256 manifest. `--verify` re-hashes it, so the
operator knows the laptop copy is readable *before* it becomes the only copy.
Secrets are excluded by default (`.env`, tokens, keys); media backups should
never be the reason a credential leaks.

Usage:
  python scripts/media_backup.py --source /srv/mtk/projects --dest /backup/mtk
  python scripts/media_backup.py --rclone-remote server:mtk-media --dest /backup/mtk
  python scripts/verify_media_backup.py /backup/mtk/media/20261022T...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

MANIFEST_NAME = "manifest.json"
SNAPSHOT_FORMAT = "%Y%m%dT%H%M%SZ"
DEFAULT_EXCLUDES = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "token*", "*secret*", "*credential*", ".git", "__pycache__",
)
CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path, patterns: Iterable[str]) -> bool:
    parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern in parts:
            return True
        if Path(name).match(pattern):
            return True
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
    return False


def iter_files(source: Path, excludes: Iterable[str] = DEFAULT_EXCLUDES) -> Iterable[Path]:
    if source.is_file():
        yield source
        return
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if _excluded(relative, excludes):
            continue
        yield path


def copy_local(source: Path, snapshot: Path,
               excludes: Iterable[str] = DEFAULT_EXCLUDES) -> list[dict]:
    """Copy files into a fresh snapshot; return manifest entries."""
    files: list[dict] = []
    for path in iter_files(source, excludes):
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        files.append({
            "path": relative.as_posix(),
            "bytes": target.stat().st_size,
            "sha256": sha256_file(target),
        })
    return files


def pull_rclone(remote: str, snapshot: Path, rclone_bin: str = "rclone") -> None:
    """Pull a remote tree into the snapshot (rclone copy is checksum-aware)."""
    snapshot.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [rclone_bin, "copy", remote, str(snapshot), "--checksum",
         "--exclude", ".env", "--exclude", "*.key", "--exclude", "*.pem"],
        capture_output=True, text=True, timeout=6 * 60 * 60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"rclone pull failed: {proc.stderr[-1200:]}")


def build_manifest(source: str, snapshot: Path, files: list[dict],
                   *, label: str = "") -> dict:
    total = sum(int(entry["bytes"]) for entry in files)
    return {
        "product": "MTK RADAR AI",
        "manifest_version": 1,
        "label": label,
        "snapshot": snapshot.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "files": files,
        "file_count": len(files),
        "total_bytes": total,
        "excluded_patterns": list(DEFAULT_EXCLUDES),
        "restore_note": "copy the snapshot tree back; verify hashes before serving media",
    }


def write_manifest(snapshot: Path, manifest: dict) -> Path:
    path = snapshot / MANIFEST_NAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic on the same filesystem
    return path


def verify_snapshot(snapshot: Path, *, sample: Optional[int] = None) -> dict:
    """Re-hash a snapshot manifest. Returns {ok, checked, failures}."""
    manifest_path = snapshot / MANIFEST_NAME
    if not manifest_path.exists():
        return {"ok": False, "checked": 0, "failures": ["manifest.json missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"ok": False, "checked": 0, "failures": [f"invalid manifest: {exc}"]}
    entries = manifest.get("files") or []
    if sample is not None:
        entries = entries[:sample]
    failures: list[str] = []
    checked = 0
    for entry in entries:
        path = snapshot / entry.get("path", "")
        if not path.is_file():
            failures.append(f"missing: {entry.get('path')}")
            continue
        checked += 1
        if path.stat().st_size != int(entry.get("bytes", -1)):
            failures.append(f"size mismatch: {entry.get('path')}")
            continue
        if sha256_file(path) != entry.get("sha256"):
            failures.append(f"hash mismatch: {entry.get('path')}")
    return {"ok": not failures, "checked": checked, "failures": failures,
            "file_count": manifest.get("file_count", len(entries)),
            "created_at": manifest.get("created_at")}


def prune_snapshots(root: Path, keep: int) -> list[Path]:
    """Keep the newest `keep` snapshot dirs; remove only directories that
    contain our manifest (never delete unrelated files)."""
    if keep < 1:
        raise ValueError("keep must be >= 1")
    candidates = [p for p in root.iterdir()
                  if p.is_dir() and (p / MANIFEST_NAME).exists()]
    candidates.sort(key=lambda p: p.name, reverse=True)
    removed: list[Path] = []
    for path in candidates[keep:]:
        shutil.rmtree(path)
        removed.append(path)
    return removed


def update_settings(api_url: str, token: str, *, status: str, manifest: Path,
                    snapshot: Path) -> bool:
    """Best-effort status update for the dashboard. Never fails a backup."""
    try:
        import urllib.request

        payload = json.dumps({"value": {
            "enabled": True,
            "schedule": os.environ.get("MTK_MEDIA_SCHEDULE", "daily"),
            "retention_days": int(os.environ.get("MTK_MEDIA_RETENTION_DAYS", "14")),
            "destination": str(snapshot.parent),
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": status,
            "last_manifest": str(manifest),
        }}).encode("utf-8")
        request = urllib.request.Request(
            f"{api_url.rstrip('/')}/settings/media_backup",
            data=payload, method="PUT",
            headers={"Content-Type": "application/json",
                     **({"Authorization": f"Bearer {token}"} if token else {})},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300
    except Exception:  # noqa: BLE001 — observability must not break backups
        return False


def run(source: Optional[Path], dest: Path, *, keep: int = 14,
        label: str = "", rclone_remote: Optional[str] = None,
        excludes: Iterable[str] = DEFAULT_EXCLUDES,
        verify: bool = True, dry_run: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).strftime(SNAPSHOT_FORMAT)
    root = dest / "media"
    snapshot = root / stamp
    if dry_run:
        return {"ok": True, "dry_run": True, "snapshot": str(snapshot),
                "file_count": 0, "total_bytes": 0, "removed": []}
    root.mkdir(parents=True, exist_ok=True)
    snapshot.mkdir(parents=True, exist_ok=False)

    if rclone_remote:
        pull_rclone(rclone_remote, snapshot)
        # rclone has already written the files; inventory them locally.
        files = []
        for path in iter_files(snapshot, excludes):
            relative = path.relative_to(snapshot)
            files.append({"path": relative.as_posix(),
                          "bytes": path.stat().st_size,
                          "sha256": sha256_file(path)})
        source_label = rclone_remote
    else:
        if source is None:
            raise ValueError("--source is required unless --rclone-remote is used")
        if not source.exists():
            raise FileNotFoundError(f"media source not found: {source}")
        files = copy_local(source, snapshot, excludes)
        source_label = str(source)

    manifest = build_manifest(source_label, snapshot, files, label=label)
    manifest_path = write_manifest(snapshot, manifest)
    verification = verify_snapshot(snapshot) if verify else {"ok": True, "skipped": True}
    removed = prune_snapshots(root, keep)
    return {
        "ok": bool(verification.get("ok")),
        "snapshot": str(snapshot),
        "manifest": str(manifest_path),
        "file_count": len(files),
        "total_bytes": manifest["total_bytes"],
        "verification": verification,
        "removed": [str(p) for p in removed],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MTK RADAR media backup")
    parser.add_argument("--source", help="local media/project directory")
    parser.add_argument("--dest", required=True, help="backup root (e.g. laptop mount)")
    parser.add_argument("--rclone-remote", help="rclone remote:path to pull instead of local source")
    parser.add_argument("--label", default="", help="operator note stored in the manifest")
    parser.add_argument("--keep", type=int, default=14, help="snapshots to keep (default 14)")
    parser.add_argument("--no-verify", action="store_true", help="skip immediate re-hash")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-url", default=os.environ.get("MTK_API_URL", ""))
    parser.add_argument("--api-token", default=os.environ.get("MTK_API_TOKEN", ""))
    args = parser.parse_args()

    try:
        result = run(
            Path(args.source) if args.source else None,
            Path(args.dest),
            keep=args.keep,
            label=args.label,
            rclone_remote=args.rclone_remote,
            verify=not args.no_verify,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 — CLI must exit non-zero, not traceback-only
        print(f"media backup failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    if result.get("ok") and args.api_url and not args.dry_run:
        update_settings(args.api_url, args.api_token, status="verified",
                        manifest=Path(result["manifest"]),
                        snapshot=Path(result["snapshot"]))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
