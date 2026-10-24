# EP implementation log — evidence-to-video plan

Companion to
[`enhancement-plan-2026-10-24-evidence-to-video.md`](enhancement-plan-2026-10-24-evidence-to-video.md)
and the [traceability EP table](master-plan-traceability.md). One section per
work package: what landed (commit), what was actually run/checked, and what
remains **unproven**. No stale green claims — every entry separates executed
checks from operator/owner actions.

## Baseline checks at EP-00 start (2026-10-24, commit `e5df8ca`)

| Check | Environment | Result |
|---|---|---|
| `pytest -q` (full suite, no DB) | Linux container, system Python | **887 passed, 3 skipped** — the audit's one Windows failure (`test_rate_limits.py` tempfile reopen) does not reproduce on Linux; fixed portably in EP-00 |
| `pnpm typecheck` | pnpm 10 / tsc 5.7 | passed (offer-schema + dashboard) |
| `ruff check --select E9,F63,F7,F82,F821 .` | ruff on system Python | passed |
| GitHub Actions CI | remote | **blocked before execution — account billing lock (run 40077225919)**. Owner action only; contributors must not touch billing or provision paid runners |
| Docker integration layer | this container | docker unavailable — integration/e2e layers **not re-proven here**; latest remote CI result stands until the lock is lifted |

## EP-00 — Restore contribution confidence

**Status: COMPLETE (2026-10-24)** — the Windows-specific, CI, and hygiene items
the plan lists; billing remains an owner action by design.

| Plan item | Commit / evidence |
|---|---|
| Windows tempfile test portability (`G28` first bullet) | `workers/publishing/tests/test_rate_limits.py` — `_video_path()` helper writes and *closes* before use; no held-open `NamedTemporaryFile` reopen. 11/11 tests pass on Linux; the Windows PermissionError mode is structurally gone |
| Filename portability lint + narrow rename of the two `:` documents (separate reviewed change) | rename `5357c7f` (git mv, titles/content unchanged, no references broken); lint `scripts/check_filenames.py` + guard tests `scripts/tests/test_check_filenames.py`, wired into `scripts/verify.sh` step 1 and the CI python job |
| Status source-of-truth in traceability docs | [master-plan-traceability.md](master-plan-traceability.md) EP table carries per-EP status; WP table unchanged (historical, re-prove at release); this log records executed vs unproven checks |
| Owner resolves Actions billing lock | **OPEN — owner action.** Contributors explicitly did not change billing settings |

**Checks executed for this EP:** full `pytest -q` green (887/3) including the
new guard tests; lint run clean over the repo; CI YAML parses.

**Still unproven:** CI execution itself (billing lock), real-Postgres
integration and browser e2e on this machine (no docker), and live-platform
behavior. Do not treat this log as a go-live certificate.
