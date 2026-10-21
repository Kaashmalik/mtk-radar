#!/usr/bin/env python3
"""Off-host backup copy (v0.24) — keep a copy of every dump somewhere other
than the deploy box.

A backup that only lives on the same disk as the database protects against
logical mistakes, not against a disk failure. This helper uploads the dump
to any S3-compatible store using the repository's own zero-dependency client
(SigV4 over httpx — no boto3), and prunes old copies with the same
retention policy as the local files.

Usage:
    python scripts/upload_backup.py <dumpfile> [--keep-days 14]

Environment (same names as the workers):
    MTK_S3_ENDPOINT, MTK_S3_BUCKET, MTK_S3_ACCESS_KEY, MTK_S3_SECRET_KEY,
    MTK_S3_REGION (optional, default us-east-1)

Exit code 0 = copied (or nothing to do), non-zero = the copy failed — the
backup script treats that as a failed backup, because an unverified
off-site copy is not a backup.
"""

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))

from object_storage import make_s3_from_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy a Postgres dump to the object store")
    parser.add_argument("dump", help="path to the .dump file")
    parser.add_argument("--keep-days", type=int,
                        default=int(os.environ.get("MTK_BACKUP_KEEP_DAYS", "14")))
    parser.add_argument("--prefix", default="backups")
    args = parser.parse_args()

    dump = Path(args.dump)
    if not dump.is_file():
        print(f"dump not found: {dump}", file=sys.stderr)
        return 1

    storage = make_s3_from_env()
    if storage is None:
        print("MTK_S3_* is not configured — skipping the off-host copy", file=sys.stderr)
        return 0

    key = f"{args.prefix}/{dump.name}"
    try:
        ref = storage.put(dump, key)
    except Exception as exc:  # noqa: BLE001 — the copy failed; that is fatal here
        print(f"off-host copy FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"copied {dump} -> {ref}")

    # prune old copies (retention mirrors the local policy)
    cutoff = time.time() - args.keep_days * 86400
    try:
        for existing in storage.list(prefix=args.prefix):
            name = existing.rsplit("/", 1)[-1]
            if not name.startswith("mtk_radar_") or not name.endswith(".dump"):
                continue
            if not name.startswith("mtk_radar_20"):  # only dated dumps
                continue
            stamp = name[len("mtk_radar_"):-len(".dump")]
            try:
                when = time.strptime(stamp, "%Y%m%dT%H%M%SZ")
            except ValueError:
                continue
            if time.mktime(when) < cutoff:
                storage.delete(existing)
                print(f"pruned old copy {existing}")
    except Exception as exc:  # noqa: BLE001 — pruning problems must not fail the copy
        print(f"prune step skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
