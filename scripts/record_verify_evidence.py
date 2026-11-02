#!/usr/bin/env python3
"""Run `scripts/verify.sh` and record the result as committed evidence.

The interim convention while GitHub Actions is billing-locked
(docs/production-readiness-2026-11-01.md): a claim without a committed
artifact is a proposal, not a proof. This script produces exactly the
artifact the convention asks for, so the proof run is one command:

    docs/evidence/verify-pnpm-YYYY-MM-DD.log   # full stdout+stderr + exit status
    docs/evidence/verify-pnpm-YYYY-MM-DD.json  # commit, date, platform, counts

Usage:
    python scripts/record_verify_evidence.py [verify.sh args...]
    MTK_VERIFY_DATABASE_URL=postgresql://... python scripts/record_verify_evidence.py

It never commits; review the two files and commit them yourself. A failed
run is recorded too (result "fail") — failing evidence is still evidence.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs" / "evidence"


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip()


def _version(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    out = subprocess.run(cmd, capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None


def _redact(url: str) -> str:
    """Never write a database password into a committed file."""
    return re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", url)


def summarize(log: str) -> dict:
    """Pull the counts a reader wants out of the raw verify output."""
    checks: dict = {}
    tests = re.findall(r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) failed)?", log)
    if tests:
        passed, skipped, failed = tests[0]
        checks["python_tests"] = {"passed": int(passed), "skipped": int(skipped or 0),
                                  "failed": int(failed or 0)}
    if len(tests) > 1:  # the Playwright suite reports last
        checks["playwright"] = {"passed": int(tests[-1][0])}
    node = re.search(r"# pass (\d+)", log)
    if node:
        checks["extension_node_tests"] = int(node.group(1))
    checks["steps_ok"] = re.findall(r"✔ (.+)", log)
    failed = re.search(r"✘ (.+)", log)
    if failed:
        checks["failed_step"] = failed.group(1).strip()
    return checks


def main(argv: list[str]) -> int:
    started = datetime.now(timezone.utc)
    bash = shutil.which("bash") or "bash"
    proc = subprocess.run([bash, "scripts/verify.sh", *argv], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)  # strip ANSI colours
    day = started.strftime("%Y-%m-%d")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE / f"verify-pnpm-{day}.log"
    json_path = EVIDENCE / f"verify-pnpm-{day}.json"
    log_path.write_text(output + f"\n[exit status {proc.returncode}]\n", encoding="utf-8")

    db_url = os.environ.get("MTK_VERIFY_DATABASE_URL", "")
    record = {
        "schema": "mtk-verify-evidence/1",
        "recorded_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _git("rev-parse", "HEAD"),
        "commit_subject": _git("log", "-1", "--format=%s"),
        "working_tree_clean": _git("status", "--porcelain", "--untracked-files=no") == "",
        "command": " ".join(["scripts/verify.sh", *argv]),
        "result": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "duration_s": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "environment": {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "python": platform.python_version(),
            "node": _version(["node", "--version"]),
            "pnpm": _version(["pnpm", "--version"]),
            "ffmpeg": _version(["ffmpeg", "-version"]),
            "docker": _version(["docker", "--version"]),
            "database_url_redacted": _redact(db_url) if db_url else "docker throwaway (mtk-verify-pg)",
        },
        "checks": summarize(output),
        "raw_log": f"docs/evidence/{log_path.name}",
        "notes": ["GitHub Actions not executed (billing lock); this file is the substitute."],
    }
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{record['result'].upper()} (exit {proc.returncode}) — wrote "
          f"{log_path.relative_to(REPO)} and {json_path.relative_to(REPO)}")
    print("Review both files, then commit them: git add docs/evidence && git commit")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
