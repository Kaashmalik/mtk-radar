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

## EP-02 — Discovery & observable momentum (G06–G11, G13–G16, G22)

COMPLETE 2026-10-24. Every gap in the EP-02 register landed as its own
reviewed commit; the acceptance fixtures from the plan (HN 100→160 ⇒ raw
30 points/h with no duplicate story; unchanged fields cannot fake a rising
trend; cached Google Trends parses; every adapter kind creatable through the
API) are integration-tested against the real Postgres.

| Gap | Commit / evidence |
|---|---|
| G06 adapter registry | `911069a` — `packages/source_adapters/registry.py` (AdapterSpec: kind/label/collector_polled/required config) is the single source of truth; `schemas.AdapterKind` extended to all ten kinds with import-time + guard-test sync; `SourceIn` rejects kinds whose required config is missing at creation; collector raises on unknown kinds (was silent `[]`); dashboard form + seeds validate through the same rules |
| G22 Reddit off by default | `9d99665` — registry `APPROVAL_PENDING` gate: API refuses ENABLED reddit sources (disabled recording allowed, `MTK_ENABLE_REDDIT_ADAPTER=1` lifts), collector refuses to poll even pre-gate rows, seed ships `enabled: false` |
| G10 Trends cache byte/JSON mismatch | `ec0a198` — symmetric TEXT cache path (`get_text`/`set_text`/`cached_text`); Google Trends caches `resp.text`; cached parse identical to live parse; `set_text` refuses non-str |
| G11 cache hits 500 | `bbb06a6` — `cache_get_json_with_ttl` returns (value, remaining TTL); `_pg_cache_get` carries `expires_at` distance; every promoted hit keeps its original expiry (bounded 30 s fallback); outage combinations are clean misses |
| G14 GitHub auth/conditionally | `d3e52d3` — `FetchResult.headers` carries final response headers; github_stars actually sends `Authorization: Bearer`, If-None-Match ETags (30 d TTL), fail-closed on `x-ratelimit-remaining: 0`, Retry-After surfaced on 403/429 |
| G07 observed context + observations | `7ce1e3b` — migration 037: items.text/selection/account_handle/extra (bounded 4000/500/30) + APPEND-ONLY `source_observations` (trigger refuses UPDATE/DELETE) with entity_key, typed measurements, payload_hash, provenance; every retrieval appends one observation even when the item dedupes; collector forwards `RawItem.extra` |
| G08 engagement momentum | `e6a4d68` — `trend_engine.engagement_rate()` (raw count delta/h; priorities points>upvotes>stars>comments; flat stays flat, missing unknown, cooling negative) + `engagement_bump()` (log-scaled, cap 15); `velocity` demoted to recorded diagnostic, `velocity_bump` deleted; migration 038 `trend_candidates.engagement`; github_stars stable entity id `gh-stars:{repo}` |
| G09 cross-URL story clustering | `2431ca2` — `trend_engine.story_key()` (normalized headline; case/punct/whitespace-insensitive; thin titles never fabricate a cluster); migration 039 `items.story_key` + COALESCE expression index; scan computes corroboration/duplicates over the whole story cluster; items dedup rules untouched |
| G15 queue evidence score | `b0e4c2c` — evidence component: fresh window 14 d (captured_at, robots_allowed, fetch 200/legacy); support 40 official / 25 fresh third-party / 0 stale-only; claims 30 × declared-required-claims coverage; independence 30 × min(1, distinct fresh sources/2); safety is a HARD eligibility gate (`ELIGIBLE_OFFER_STATES`) — expired/corrected/evidence_needed offers never appear ready |
| G16 real cooling duration | `b0e4c2c` — cooling measured from last MEANINGFUL growth (`COALESCE(last_growth_at, first_at)`), so the daily rescan cadence cannot reset the clock; archive when latest velocity ≤ 0 AND cooling since > 7 days |
| G13 compose env matrix | `4481042` — collectors +REDIS_URL; verification +VERIFY_LLM_*; api +VERIFY_LLM_*/TTS_*/COST_*; render +TTS_* incl. _UR overrides; publishing +INSTAGRAM_*/FACEBOOK_APP_*/MTK_PUBLIC_MEDIA_BASE_URL/MTK_TOKEN_REFRESH_*; metrics +INSTAGRAM_*; guard test enforces the matrix BOTH directions (documented var → container receives it; compose var → documented or explicitly internal) and re-checks itself against the code that reads each var |

**Checks executed for this EP** (at documentation commit): unit suite
951 passed, 3 skipped; **620 API integration tests green** against local
Postgres 16 with migrations 001→039 applied by the real migration runner;
`ruff --select E9,F63,F7,F82,F821` clean; `docker compose config -q` clean;
dashboard `tsc --noEmit` clean (offer-schema + dashboard); extension
`node --check` clean. New failure-path tests: identical payload hashes cannot
fake new information, append-only trigger refuses rewrites, zero-evidence
queue rows rank at exactly 0.35·trend+0.20·freshness+0.15·fit, 8-day cooling
with daily fresh observations archives while 3-day cooling stays ready,
expired offers stay off the ready list despite fresh evidence.

**Still unproven:** remote CI execution (owner billing lock — run 40077225919
blocked, logged not touched); live adapter behavior against the real HF/HN/
Reddit/Google/GitHub endpoints and live rate-limit refusals (fixture-tested
only — including whether GitHub's real 304/ETag flows match the fake); Redis
path of the new text cache (memory layer covered; REDIS_URL-dependent tests
need a live Redis); production collector runs under Docker where the matrix
now applies (config asserted statically + `compose config`, not started here);
story_key clustering quality on real-world headline corpora (conservative by
design — distinct stories must not merge, but recall on real syndication
title variants beyond the tested patterns is operator-observed territory).
