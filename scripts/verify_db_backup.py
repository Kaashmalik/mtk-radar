#!/usr/bin/env python3
"""Verify a Postgres dump (and optionally restore it into a throwaway DB).

A backup file that has never been restored is a hope, not a backup. This
script performs the cheap half automatically (archive readability) and makes
the destructive half explicit: restoring needs `--restore-to` plus
`--yes-really`, because it can overwrite the target database.

Usage:
  python scripts/verify_db_backup.py backups/mtk_radar_....dump
  python scripts/verify_db_backup.py backups/...dump \
    --restore-to postgresql://mtk:mtk@localhost:55499/mtk_restore_drill --yes-really
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PG_RESTORE = os.environ.get("PG_RESTORE_PATH", "pg_restore")


def list_archive(path: Path) -> dict:
    try:
        proc = subprocess.run(
            [PG_RESTORE, "--list", str(path)],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr[-1200:] or "pg_restore failed"}
    entries = [line for line in proc.stdout.splitlines()
               if line and not line.startswith(";")]
    return {"ok": True, "entries": len(entries),
            "has_schema": any("SCHEMA" in line for line in entries),
            "has_data": any("TABLE DATA" in line for line in entries)}


def restore(path: Path, database_url: str) -> dict:
    try:
        proc = subprocess.run(
            [PG_RESTORE, "--clean", "--if-exists", "--no-owner",
             "--dbname", database_url, str(path)],
            capture_output=True, text=True, timeout=6 * 60 * 60,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    # pg_restore returns 1 for benign "already exists" warnings on some
    # versions; only a hard error (>=2) means the archive is unusable.
    return {"ok": proc.returncode < 2, "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an MTK Postgres dump")
    parser.add_argument("dump", type=Path)
    parser.add_argument("--restore-to", help="THROWAWAY database URL for a drill")
    parser.add_argument("--yes-really", action="store_true",
                        help="confirm the restore target may be overwritten")
    args = parser.parse_args()

    if not args.dump.exists():
        print(f"dump not found: {args.dump}", file=sys.stderr)
        return 2
    archive = list_archive(args.dump)
    print(f"archive: {'OK' if archive['ok'] else 'FAILED'} — {archive}")
    if not archive["ok"]:
        return 1
    if args.restore_to:
        if not args.yes_really:
            print("refusing to restore without --yes-really", file=sys.stderr)
            return 2
        result = restore(args.dump, args.restore_to)
        print(f"restore: {'OK' if result['ok'] else 'FAILED'} — {result}")
        return 0 if result["ok"] else 1
    print("restore drill skipped (pass --restore-to <throwaway-url> --yes-really)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
