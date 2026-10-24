#!/usr/bin/env python3
"""Filename-portability lint (evidence-to-video plan G28 / EP-00).

Windows reserved characters (and a few reserved names) make a checkout
unreadable for contributors on Windows and can break CI archives that the
audit found were already blocking remote runs. Names containing ':'
historically slip through on Linux — CI never sees the problem, so the
guard has to run where the file is created.

Checks every git-tracked path segment for:
- Windows-invalid characters: < > : " / \\ | ? * and control chars (0x00-0x1f)
- trailing dots or spaces (silently stripped by Windows and some tools)
- reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9, ...)

Exit 0 = portable; exit 1 = list of offending paths. Run bare:
    python scripts/check_filenames.py            # repo
    python scripts/check_filenames.py DIR...     # specific trees
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PureWindowsPath

# Characters Windows refuses in any path segment (plus control characters).
INVALID_CHARS = set('<>:"|?*')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _tracked_paths(roots: list[str]) -> list[str]:
    if not roots:
        out = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, check=True)
        return [p for p in out.stdout.decode().split("\0") if p]
    paths: list[str] = []
    for root in roots:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", root], capture_output=True, check=True)
        paths += [p for p in out.stdout.decode().split("\0") if p]
    return paths


def check_segment(segment: str) -> str | None:
    """Return the reason a single path segment is not Windows-portable."""
    lowered = segment.rstrip(". ").upper()
    stem = lowered.split(".")[0]
    if any(ch in INVALID_CHARS for ch in segment):
        return "contains a Windows-invalid character (<>:\"|?*)"
    if any(ord(ch) < 0x20 for ch in segment):
        return "contains a control character"
    if segment != segment.rstrip(". "):
        return "ends with a dot or space (stripped on Windows)"
    if stem in RESERVED_NAMES:
        return "uses a Windows reserved device name"
    return None


def main(argv: list[str]) -> int:
    problems: list[str] = []
    for path in _tracked_paths(argv[1:]):
        # PureWindowsPath treats every segment the way Windows would.
        for segment in PureWindowsPath(path).parts:
            reason = check_segment(segment)
            if reason:
                problems.append(f"{path}: {reason}")
                break
    if problems:
        print("non-portable filenames found (breaks Windows checkouts/CI):\n"
              + "\n".join(f"  - {p}" for p in problems), file=sys.stderr)
        print("\nfix: rename with `git mv` in a reviewed change so history "
              "and links are preserved.", file=sys.stderr)
        return 1
    print(f"all tracked filenames portable ({sys.argv[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
