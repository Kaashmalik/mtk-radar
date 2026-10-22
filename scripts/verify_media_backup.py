#!/usr/bin/env python3
"""Verify a media backup snapshot without touching the source.

Exit codes:
  0  all hashes/sizes match and the manifest is valid
  1  verification failed (missing/truncated/modified files)
  2  usage error

Usage:
  python scripts/verify_media_backup.py /backup/mtk/media/20261022T...
  python scripts/verify_media_backup.py /backup/mtk/media/20261022T... --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from media_backup import verify_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an MTK media backup snapshot")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--sample", type=int, default=None,
                        help="verify only the first N files (quick smoke check)")
    args = parser.parse_args()

    if not args.snapshot.exists():
        print(f"snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    result = verify_snapshot(args.snapshot, sample=args.sample)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"{status}: checked {result['checked']} file(s) "
              f"of {result.get('file_count', '?')}")
        for failure in result.get("failures", [])[:20]:
            print(f"  - {failure}")
        if len(result.get("failures", [])) > 20:
            print(f"  ... and {len(result['failures']) - 20} more")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
