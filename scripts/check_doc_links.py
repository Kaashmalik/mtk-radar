#!/usr/bin/env python3
"""Check relative Markdown links in README and docs (DOC-16).

External URLs, mail links and pure anchors are ignored. A link to a missing
file (or directory) fails with exit 1 and a `file:line` list. Run from the
repository root:

    python scripts/check_doc_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
ROOTS = [Path("README.md"), Path("docs"), Path("apps/extension/README.md")]
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "#")


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def iter_links(path: Path):
    """Yield (line_number, target) for relative Markdown links."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for match in LINK_RE.finditer(line):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if not target or target.startswith(SKIP_PREFIXES):
                continue
            yield number, target


def resolve(path: Path, target: str) -> Path:
    clean = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not clean:
        return path  # anchor-only after stripping
    return (path.parent / clean).resolve()


def broken_links() -> list[str]:
    problems: list[str] = []
    for path in markdown_files():
        for number, target in iter_links(path):
            if not resolve(path, target).exists():
                problems.append(f"{path}:{number}: {target}")
    return problems


def main() -> int:
    problems = broken_links()
    if problems:
        print("broken relative documentation links:\n"
              + "\n".join(f"  - {p}" for p in problems), file=sys.stderr)
        return 1
    print(f"documentation links resolve ({len(markdown_files())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
