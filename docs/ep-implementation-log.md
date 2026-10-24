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

## EP-01 — Safety & financial correctness (G01–G05, G12, G21, G27)

**Status: COMPLETE (2026-10-24)** — every gap in the EP-01 register has a
landed, reviewed change. The financial core (budget gate + reservations) and
the platform-capability guards are covered by tests; live-provider behavior
remains operator-verified territory.

| Gap | Commit / evidence |
|---|---|
| G01 Instagram privacy | `66b73ea` — `UnsupportedPrivacyError` in `platforms/base.py`; Instagram supports `public` only, refuses BEFORE container creation; worker pre-flight in `_publish` (held+paused, never retried); lying "draft state" docstring removed |
| G02 publication reconciliation | `d889b67` — `confirm_publication` implemented for Facebook (video_status/published match), Instagram (permalink present), TikTok (`PUBLISH_COMPLETE`/available post id); synthetic `confirmed=True` fallback replaced with `confirmed: False` + hold; fakes reconcile like real adapters |
| G03 fail-closed budget gate | `7e636cd` — `budget_ok` permits paid work ONLY on explicit `allowed: true`; unreachable/non-2xx/ambiguous all DENY |
| G12 worker config parity | `7e636cd` — `CostClient` reads `MTK_API_URL`/`MTK_WORKER_TOKEN` first, legacy names as fallbacks |
| G04 atomic reservations | `69f8e1f` — `check_budget` runs read-decide-insert in one transaction under a per-kind advisory lock; allowed requests insert a reservation the usage report settles (`settle_reservation`); unsettled reservations stay as recorded liability; extraction predicts tokens (chars/4 + hard `max_tokens` cap) instead of asking with 0 |
| G05 scoped credentials + route/role matrix | `79d4a03` — deny-by-default `NON_HUMAN_ROUTE_GRANTS` (extension = `POST /items` + `GET /whoami`); reviewer-only `/media/gc` + `/jobs/bulk-retry` enforced centrally and in-router; extension options page asks for the dedicated `MTK_EXTENSION_TOKEN` |
| G21 derived-data permission switches | `a0964a7` — shared `MTK_ENABLE_DERIVED_ENGAGEMENT` switch (off by default) now gates best-times' views+2×(likes+comments) blend AND the hashtag measured-performance lift; default outputs use native metrics (avg views; source-priority order) with explicit editorial-heuristic labels; dashboard renders the API's `ranking_method` |
| G27 media GC | `eee66cb` — reference/hold-aware mark-and-sweep: pins by ref VALUE as well as row; failed/paused/held schedules pin their artifacts (only `cancelled` releases, and only its own cover); apply runs in one advisory-locked transaction shared with schedule creation, with a second pin re-check inside the lock; dry-run default unchanged |

**Checks executed for this EP:** full unit suite green (921 passed, 3 skipped);
**591 API integration tests green against a REAL local Postgres 16** (migrations
applied by the real migration runner; includes the new G04 reservation
lifecycle, G05 matrix, G21 permission gates and G27 sweep tests); typecheck
(offer-schema + dashboard) clean; `ruff --select E9,F63,F7,F82,F821` clean;
extension `node --check` clean.

**Still unproven:** remote CI execution (owner billing lock), live publishing
against real Graph/TikTok endpoints (adapters are mocked-transport tested),
advisory-lock serialization under real multi-process contention (integration
tests exercise the lock sequentially), and GC deletion against a real S3
bucket (local/S3 both wired; S3 path untested here). One repo note: the owner
deliberately committed a production data export (`f079d84`,
`docs/marshmallow-contact-location-…json`) as an intentional archive — kept on
main per the owner's decision; it contains customer contact rows, so repo
visibility choices should account for it.
