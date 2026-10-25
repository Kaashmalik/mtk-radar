# EP implementation log — evidence-to-video plan

Companion to
[`enhancement-plan-2026-10-24-evidence-to-video.md`](enhancement-plan-2026-10-24-evidence-to-video.md)
and the [traceability EP table](master-plan-traceability.md). One section per
work package: what landed (commit), what was actually run/checked, and what
remains **unproven**. No stale green claims — every entry separates executed
checks from operator/owner actions.

> **2026-10-25 review (`75b03e4`):** the per-EP `COMPLETE` labels below are
> historical. Current status: **EP-00 PARTIAL** (local filename guard passes;
> CI execution is still blocked), **EP-01–EP-03 IMPLEMENTED_UNVERIFIED for
> live providers/LLMs** (the Postgres integration layer now runs locally),
> **EP-04 PARTIAL** (the loaded-extension Chromium E2E now passes; store and
> manual permission-prompt coverage remain). After the M2 runtime-proof batch
> the local suite is **1176 passed / 0 failed** with 158 real-Postgres
> integration tests, **9/9 Playwright** tests (including the unpacked
> extension), and 29 extension Node tests. Open work is tracked in
> [`implementation-roadmap-2026-10-25.md`](implementation-roadmap-2026-10-25.md).

## Baseline checks at EP-00 start (2026-10-24, commit `e5df8ca`)

| Check | Environment | Result |
|---|---|---|
| `pytest -q` (full suite, no DB) | Linux container, system Python | **887 passed, 3 skipped** — the audit's one Windows failure (`test_rate_limits.py` tempfile reopen) does not reproduce on Linux; fixed portably in EP-00 |
| `pnpm typecheck` | pnpm 10 / tsc 5.7 | passed (offer-schema + dashboard) |
| `ruff check --select E9,F63,F7,F82,F821 .` | ruff on system Python | passed |
| GitHub Actions CI | remote | **blocked before execution — account billing lock (run 40077225919)**. Owner action only; contributors must not touch billing or provision paid runners |
| Docker integration layer | this container | docker unavailable — integration/e2e layers **not re-proven here**; latest remote CI result stands until the lock is lifted |

## EP-00 — Restore contribution confidence

**Status: PARTIAL (reviewed 2026-10-25)** — the Windows tempfile fix, lint and
the end-to-end filename guard now pass locally (CODE-05 fixed: the bad path is
added to a throwaway Git index, not the filesystem). Billing remains an owner
action by design, so remote CI is still `UNPROVEN`.

| Plan item | Commit / evidence |
|---|---|
| Windows tempfile test portability (`G28` first bullet) | `workers/publishing/tests/test_rate_limits.py` — `_video_path()` helper writes and *closes* before use; no held-open `NamedTemporaryFile` reopen. 11/11 tests pass on Linux; the Windows PermissionError mode is structurally gone |
| Filename portability lint + narrow rename of the two `:` documents (separate reviewed change) | rename `5357c7f` (git mv, titles/content unchanged, no references broken); lint `scripts/check_filenames.py` + guard tests `scripts/tests/test_check_filenames.py`, wired into `scripts/verify.sh` step 1 and the CI python job |
| Status source-of-truth in traceability docs | [master-plan-traceability.md](master-plan-traceability.md) EP table carries per-EP status; WP table unchanged (historical, re-prove at release); this log records executed vs unproven checks |
| Owner resolves Actions billing lock | **OPEN — owner action.** Contributors explicitly did not change billing settings |

**Checks executed for this EP (historical, 2026-10-24):** full `pytest -q`
green (887/3) on Linux including the new guard tests; lint run clean over the
repo; CI YAML parses. **Re-run on 2026-10-25 after CODE-05 and the M1 batch:**
975 passed, 3 skipped, **0 failed**. **M2 re-run (`75b03e4`):** 1176 passed,
0 failed, including 158 real-Postgres integration tests and 9/9 Playwright
tests. The portable filename test adds the bad path to a throwaway Git index
instead of creating an invalid file. CI execution is still `UNPROVEN`
(billing lock); live provider posting is also unproven.

**Still unproven:** CI execution itself (billing lock) and live-platform
behavior. The real-Postgres integration suite and the browser E2E now run
locally on Windows with portable PostgreSQL 16.15 (`75b03e4`; 1176 passed,
9/9 Playwright). Do not treat this log as a go-live certificate.

## EP-01 — Safety & financial correctness (G01–G05, G12, G21, G27)

**Status: IMPLEMENTED_UNVERIFIED (reviewed 2026-10-25)** — every gap in the EP-01 register has a
landed, reviewed change. The financial core (budget gate + reservations) and
the platform-capability guards are covered by tests; live-provider behavior
remains operator-verified territory.

| Gap | Commit / evidence |
|---|---|
| G01 Instagram privacy | `66b73ea` — `UnsupportedPrivacyError` in `platforms/base.py`; Instagram supports `public` only, refuses BEFORE container creation; worker pre-flight in `_publish` (held+paused, never retried); lying "draft state" docstring removed |
| G02 publication reconciliation | `d889b67` — `confirm_publication` implemented for Facebook (video_status/published match), Instagram (permalink present), TikTok (public: `PUBLISH_COMPLETE` **plus a public post id**; private/unlisted: `SELF_ONLY` completion, `visibility: self_only`, never public); synthetic `confirmed=True` fallback replaced with `confirmed: False` + hold; fakes reconcile like real adapters. TikTok's private-mode exception is `a6138d7` (CODE-02) |
| G03 fail-closed budget gate | `7e636cd` — `budget_ok` permits paid work ONLY on explicit `allowed: true`; unreachable/non-2xx/ambiguous all DENY |
| G12 worker config parity | `7e636cd` — `CostClient` reads `MTK_API_URL`/`MTK_WORKER_TOKEN` first, legacy names as fallbacks. This is **CostClient parity only**; `workers/verification/main.py` and `workers/collectors/main.py` still read `API_URL` directly |
| G04 atomic reservations | `69f8e1f` — `check_budget` runs read-decide-insert in one transaction under a per-kind advisory lock; allowed requests insert a reservation the usage report settles (`settle_reservation`); unsettled reservations stay as recorded liability; extraction predicts tokens (chars/4 + hard `max_tokens` cap) instead of asking with 0 |
| G05 scoped credentials + route/role matrix | `79d4a03` — deny-by-default `NON_HUMAN_ROUTE_GRANTS` (extension = `POST /items` + `GET /whoami`); reviewer-only `/media/gc` + `/jobs/bulk-retry` enforced centrally and in-router; extension options page asks for the dedicated `MTK_EXTENSION_TOKEN` |
| G21 derived-data permission switches | `a0964a7` — shared `MTK_ENABLE_DERIVED_ENGAGEMENT` switch (off by default) now gates best-times' views+2×(likes+comments) blend AND the hashtag measured-performance lift; default outputs use native metrics with explicit editorial-heuristic labels; dashboard renders the API's `ranking_method`. With the gate off, unmeasured hashtag ties now keep source priority (CODE-03 fixed 2026-10-25) |
| G27 media GC | `eee66cb` — reference/hold-aware mark-and-sweep: pins by ref VALUE as well as row; failed/paused/held schedules pin their artifacts (only `cancelled` releases, and only its own cover); apply runs in one advisory-locked transaction shared with schedule creation, with a second pin re-check inside the lock; dry-run default unchanged |

**Checks executed for this EP:** historical 2026-10-24 unit suite 921 passed /
3 skipped. **Re-run 2026-10-25 (`75b03e4`):** full suite **1176 passed / 0
failed**, including **158 API integration tests** against PostgreSQL 16.15 and
the real migration runner; 9/9 Playwright tests; typecheck (offer-schema +
dashboard) clean; `ruff --select E9,F63,F7,F82,F821` clean; extension
`node --check` clean. Live provider endpoints remain mocked-transport tested
only.

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

IMPLEMENTED_UNVERIFIED (reviewed 2026-10-25). Every gap in the EP-02 register
landed as its own reviewed commit. The acceptance fixtures from the plan
(HN 100→160 ⇒ raw 30 points/h with no duplicate story; unchanged fields cannot
fake a rising trend; cached Google Trends parses; every adapter kind creatable
through the API) exist as tests, but the database-backed ones were **not run**
on 2026-10-25 (no Docker/Postgres).

| Gap | Commit / evidence |
|---|---|
| G06 adapter registry | `911069a` — `packages/source_adapters/registry.py` (AdapterSpec: kind/label/collector_polled/required config) is the single source of truth; `schemas.AdapterKind` extended to all ten kinds with import-time + guard-test sync; `SourceIn` rejects kinds whose required config is missing at creation; collector raises on unknown kinds (was silent `[]`); the dashboard now fetches `GET /source-adapters` and renders kinds + config fields from it, so reddit/approval state cannot drift (CODE-09 fixed) |
| G22 Reddit off by default | `9d99665` — registry `APPROVAL_PENDING` gate: API refuses ENABLED reddit sources (disabled recording allowed, `MTK_ENABLE_REDDIT_ADAPTER=1` lifts), collector refuses to poll even pre-gate rows, seed ships `enabled: false` |
| G10 Trends cache byte/JSON mismatch | `ec0a198` — symmetric TEXT cache path (`get_text`/`set_text`/`cached_text`); Google Trends caches `resp.text`; cached parse identical to live parse; `set_text` refuses non-str |
| G11 cache hits 500 | `bbb06a6` — `cache_get_json_with_ttl` returns (value, remaining TTL); `_pg_cache_get` carries `expires_at` distance; every promoted hit keeps its original expiry (bounded 30 s fallback); outage combinations are clean misses |
| G14 GitHub auth/conditionally | `d3e52d3` — `FetchResult.headers` carries final response headers; github_stars actually sends `Authorization: Bearer`, If-None-Match ETags (30 d TTL), fail-closed on `x-ratelimit-remaining: 0`, Retry-After surfaced on 403/429 |
| G07 observed context + observations | `7ce1e3b` — migration 037: items.text/selection/account_handle/extra (bounded 4000/500/30) + APPEND-ONLY `source_observations` (trigger refuses UPDATE/DELETE) with entity_key, typed measurements, payload_hash, provenance; every retrieval appends one observation even when the item dedupes; collector forwards `RawItem.extra`. Radar candidates now also store `signals.evidence` (observation id, retrieval time, payload hash, URL) so a lead is auditable without a join (CODE-14 fixed; DB assertion unrun) |
| G08 engagement momentum | `e6a4d68` — `trend_engine.engagement_rate()` (raw count delta/h; priorities points>upvotes>stars>comments; flat stays flat, missing unknown, cooling negative) + `engagement_bump()` (log-scaled, cap 15); `velocity` demoted to recorded diagnostic, `velocity_bump` deleted; migration 038 `trend_candidates.engagement`; github_stars stable entity id `gh-stars:{repo}` |
| G09 cross-URL story clustering | `2431ca2` — `trend_engine.story_key()` (normalized headline; case/punct/whitespace-insensitive; thin titles never fabricate a cluster); migration 039 `items.story_key` + COALESCE expression index; scan computes corroboration/duplicates over the whole story cluster; items dedup rules untouched |
| G15 queue evidence score | `b0e4c2c` — evidence component: fresh window 14 d (captured_at, robots_allowed, fetch 200/legacy); support 40 official / 25 fresh third-party / 0 stale-only; claims 30 × declared-required-claims coverage; independence 30 × min(1, distinct fresh sources/2); safety is a HARD eligibility gate (`ELIGIBLE_OFFER_STATES`) — expired/corrected/evidence_needed offers never appear ready |
| G16 real cooling duration | `b0e4c2c` — cooling measured from last MEANINGFUL growth (`COALESCE(last_growth_at, first_at)`), so the daily rescan cadence cannot reset the clock; archive when latest velocity ≤ 0 AND cooling since > 7 days |
| G13 compose env matrix | `4481042` — collectors +REDIS_URL; verification +VERIFY_LLM_*; api +VERIFY_LLM_*/TTS_*/COST_*; render +TTS_* incl. _UR overrides; publishing +INSTAGRAM_*/FACEBOOK_APP_*/MTK_PUBLIC_MEDIA_BASE_URL/MTK_TOKEN_REFRESH_*; metrics +INSTAGRAM_*; guard test enforces the matrix BOTH directions (documented var → container receives it; compose var → documented or explicitly internal) and now maps **every** matrix variable to a named reader, including dynamic TTS/Urdu and per-account Instagram forms (CODE-11 fixed) |

**Checks executed for this EP:** historical 2026-10-24 unit suite 951 passed /
3 skipped. **Re-run 2026-10-25 (`75b03e4`):** full suite **1176 passed / 0
failed**, including **158 API integration tests** on PostgreSQL 16.15 (the
claimed 620-test figure was a cumulative historical count, not the current
suite); `ruff --select E9,F63,F7,F82,F821` clean; `docker compose config -q` clean;
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

## EP-03 - Research briefs & content-type gates (G17-G18, 2026-10-24)

**Status: IMPLEMENTED_UNVERIFIED (reviewed 2026-10-25).** The database path is
now locally verified: the research versioning, claim-status and daily-cap
integration tests ran in the 158-test PostgreSQL 16.15 suite (`75b03e4`).
Live research-provider/LLM behavior remains unproven. The contradiction gate
checks the **current** brief only; a superseded contradiction is exposed as
`superseded_conflicts` history and never blocks. The daily cap counts both
`automation:%` and `system:%` actors (CODE-10 fixed). Research tracks suppress
both `promo_code` and `renewal.regularPrice` (CODE-04 fixed).

A promoted topic is now RESEARCH material, not an offer-shaped placeholder.
Migration `040` adds versioned `research_briefs` (viewer question / angle /
audience / sources / counterevidence / limitations, one row per VERSION — a
new version supersedes, never rewrites), the `research_claims` ledger
(class-tagged: `author_reported` / `independently_reproduced` /
`tested_by_mtk` / `editorial_analysis` — a preprint is not peer review; a
claimed sentence resolves to its supporting excerpt, source and scope; status
`supported` / `contradicted` / `unknown` with permitted wording and recheck
policy), and `production_queue.content_type`. The offer container itself is
unchanged: promotion still lands as state `candidate` and "promoted" still
never means "verified".

- G17 (queue detail 500): the DETAIL endpoint was rewritten onto the SAME
  ranked SQL as the list (`_RANKED_SELECT_READY` / `_RANKED_SELECT_ANY`
  compiled from one template) — commit `c8f2893`. Detail rank == list rank;
  archived/demoted rows still answer (`ready_now` computed under the SAME
  eligibility rule as the list).
- G18: `research_api.py` (brief versions with version+1 under one tx; claim
  PATCH is HUMAN-ONLY — automation actors get 403, the reviewer identity is
  recorded on the claim and audited); `promote_trend` creates brief v1 + the
  queue row's track in the promotion transaction; scriptgen runs a fail-closed
  contradiction gate (a standing `contradicted` claim on the **current** brief
  blocks copy in every track until a human resolves it; superseded briefs are
  audit history and are returned as `superseded_conflicts`, never as gate
  content — CODE-10), a content_type→format matrix (a research
  explainer cannot borrow first-person formats), per-class attribution
  blocks (EN + Urdu: "The authors report…" is sourcing, "Our analysis…" is
  labeled analysis, unconfirmed claims say so verbatim), and research tracks
  suppress `promo_code` and `renewal.regularPrice` (CODE-04 fixed). The 'offer'
  track keeps its legacy wording, regression-guarded.
  Automation promotion is bounded by the new `auto_research_max_per_day`
  guardrail (advisory-locked daily count in the promotion tx — the same
  TOCTOU defense as the approval budget; human promotions are never
  capped; automation-marked briefs flag `auto_shortlisted`).

| Gap | Commit / evidence |
|---|---|
| G17 queue detail SQL/readiness | `c8f2893` — shared `_RANKED_SELECT_TEMPLATE`; detail reuses the list's ranked projection (no GROUP BY anywhere in queue reads); `test_queue_detail_matches_list_rank_and_never_500s` |
| G18 research tracks + claim ledger | `995c4ad` — migration 040 + `research_api.py` + promote/brief wiring + scriptgen gates/attribution + guardrail; unit `test_scriptgen_research.py` (**15 tests**, corrected 2026-10-25), integration: `test_promote_creates_research_brief_v1_and_queue_content_type`, `test_research_brief_versioning_and_human_only_claim_status`, `test_paper_explainer_script_is_attributed_and_coupon_free`, `test_automation_promotion_daily_cap` (**all passed** against PostgreSQL 16.15 on 2026-10-25) |

**Checks executed for this EP:** historical 2026-10-24 full suite 1147 passed.
**Re-run 2026-10-25 (`75b03e4`):** full suite **1176 passed / 0 failed**,
including 158 real-Postgres integration tests and the four G18 tests above;
`ruff check .` clean; `docker compose config -q` clean; dashboard `tsc
--noEmit` clean; extension `node --check` clean. The local DB path is verified;
live LLM/research endpoints and CI remain unproven.

**Still unproven:** remote CI execution (owner billing lock — logged, not
touched); the dashboard's queue/offer UIs do not yet surface `content_type`
or the brief/claim editor (API-complete; UI work was not part of this EP's
gate — the API contract is exercised by the integration tests); studio
and offers script generation were verified for the contradiction gate and
attribution via the API, not through a browser session; the recheck_at due
list (attention_api) does not yet include research_claims.recheck_at rows.

## EP-04 — Finish the browser extension (2026-10-24)

**Status: PARTIAL (reviewed 2026-10-25).** The intake, outbox and credential
scoping landed. Saving options no longer wipes a masked token (CODE-01 fixed),
the granted origin is persisted and retired on change/revoke (CODE-06 fixed),
page-context URLs are sanitized before upload (CODE-12 fixed), and the contract
test asserts context persistence in both `items.extra` and observation
provenance (CODE-13 fixed; DB execution passed). Saves now deep-link to the exact
inbox row via `GET /items/{id}` and `/inbox?saved_item=<id>` (CODE-07). 29 Node
tests pass. The loaded-extension Chromium E2E now loads the unpacked MV3
extension in a persistent profile, pairs with the real API, delivers a queued
save, and proves the duplicate path creates no second inbox row. Remaining
open: store packaging/CSP review and the manual permission-prompt/badge/alarm
surfaces.

The extension was a syntax-checked stub with a wrong context-menu target and
a shared token story. It is now a real intake tool: the right-clicked LINK is
the saved target (the page rides along as context — the audit's headline
bug), pairing uses the dedicated revocable intake-only credential with a
masked display, explicit revoke/reset, a `GET /whoami` health probe, https-
validated API base (loopback-only exception), and runtime per-origin host
grants (the manifest no longer asks for all-web access at install; the previous
origin is retired on change and the granted origin is persisted across reloads)
— plan ref [S15]. Saves go through a durable,
bounded offline outbox (50 entries / 14-day TTL, alarm-driven retry,
attempt-capped) whose client idempotency key rides as `external_item_id`, so
an offline save survives worker death and is delivered ONCE logically —
proven on both sides: a fake-fetch unit suite in Node (29 tests over `core.js`,
wired into `verify.sh`) and the server-side contract integration test.
Distinct statuses for saved / duplicate / queued(offline · timeout ·
rate-limited) / auth-expired / rejected, plus restricted-tab (`chrome://`,
store), denylist, missing-host-permission and full-outbox actions. Privacy
fails closed: secret-shaped selections block the save, tracking parameters
are stripped without touching canonical identity, private surfaces (webmail,
DMs, sign-in) are excluded by default, page-context URLs are reduced to
scheme+host+path and omitted entirely on private surfaces (CODE-12), selection
is bounded at 500 chars.
The contract test also caught a real API bug: `create_item` labeled extension
intake as `collector` in the observation provenance because source
resolution aliased the flag (fixed).

| Work | Commit / evidence |
|---|---|
| Targets, pairing, host grants, outbox, statuses, privacy | `42a6f53` — `apps/extension/core.js` (pure logic) + worker/options rewrite + manifest v0.3.0 + `apps/extension/README.md` (tester install steps); 29 unit tests; `test_extension_intake_contract_idempotent_with_context` now asserts context in `items.extra` and observation provenance (CODE-13; DB execution passed 2026-10-25) |
| Loaded-extension E2E | `21b9a85` — `apps/dashboard/e2e/loaded-extension.spec.ts`; 9/9 Playwright tests including real Chromium persistent profile, API health probe, outbox delivery and duplicate dedupe; [evidence](evidence/loaded-extension-e2e.json) |
| Intake provenance bug | `42a6f53` — `services/api/main.py` records `intake: extension` from the pre-resolution flag |

**Checks executed for this EP** (at documentation commit, historical): full suite
1148 passed (incl. **156 integration** on real Postgres, migrations 001→040);
extension `node --test` 25/25; `node --check` on
all three JS files; manifest JSON parses; `ruff check .`, `docker compose
config -q`, dashboard `tsc --noEmit` clean. **Re-run 2026-10-25 (`75b03e4`):**
full suite **1176 passed / 0 failed** including 158 real-Postgres integration
tests; extension 29/29; `pnpm verify` 9/9 Playwright tests including the loaded
extension; `ruff`, `pnpm typecheck`, doc-link and filename guards clean; gitleaks
132 commits/no leaks. The loaded-browser layer is no longer unproven.

**Still unproven:** store packaging/CSP review; Chrome-API surfaces such as the
`chrome.permissions.request` UI, badge painting and alarm cadence are stubbed in
unit tests and not exercised by the E2E; no Firefox claim (Chrome MV3 only);
remote CI execution still blocked by the owner billing lock (logged, not
touched).
