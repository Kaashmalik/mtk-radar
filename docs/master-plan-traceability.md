# Master-plan traceability

> **21 October 2026 audit:** this is historical feature-to-code traceability,
> not proof all documented gates are fully enforced or all integrations work
> live. See the [dated automation master plan](automation-master-plan-2026-10-21.md)
> for code-level gaps, checks actually executed, and the new implementation ledger.

Which master-plan item lives where, and where it is intended to be proven. The proof column records test identifiers/locations as checked at the documentation date — re-prove against the current commit before relying on any row at release time. Use this to audit
the build without reading the whole repository; use
[`go-live-checklist.md`](go-live-checklist.md) for the operator procedure.

Legend: **code** = the implementation, **proof** = the test/behaviour that
demonstrates it works.

## §18 Twelve-week sequence

| Week | Deliverable | Where it lives | Proof |
|---|---|---|---|
| 1 | Repo foundation, compose, schema, source registry, secrets + audit | `infra/docker/docker-compose.yml`, `services/api/db/migrations/001…010`, `services/api/main.py` (sources), `services/api/api_hardening.py`, `audit_log` | 13 integration tests on real Postgres; `pnpm verify` |
| 2 | RSS/Atom, GitHub feeds, page monitoring, extension save-link | `packages/source_adapters/{rss,github_releases,page_watch}.py`, `workers/collectors/`, `apps/extension/` | collector unit tests; extension `node --check` in CI; live `--once` sweep |
| 3–4 | Extraction, domain allowlist, evidence snapshots, conflict/stale, reviewer queue | `services/api/offers_api.py` (evidence/extraction), `services/api/state.py`, `workers/verification/`, dashboard *Review desk* | state-machine tests; integration pipeline test (illegal transitions refused) |
| 5–6 | Claim checklist, browser recording, step log, redaction review | `services/api/scriptgen.py`, `workers/capture/` (Playwright), `services/api/captures_api.py` | scriptgen tests; redaction gate enforced in `renders_api` (integration test) |
| 7–8 | Script + command cards, TTS, captions, FFmpeg templates, 16:9/9:16 | `services/api/scriptgen.py`, `workers/render/{render,captions,narration,presets}.py` | 35 render tests; live render sweep (both presets registered) |
| 9 | Editing handoff, project bundle, calendar, approval/version controls | `workers/render/handoff.py`, `services/api/schedules_api.py`, `services/api/schedules_state.py`, dashboard *Calendar* | schedule state-machine tests; approval-hash binding test |
| 10 | YouTube + one more platform via official APIs, token-expiry recovery | `workers/publishing/platforms/{youtube,facebook,tiktok,instagram}.py`, `workers/publishing/main.py` | adapter tests (mocked transport); expiry → pause path tested |
| 11 | Remaining connectors, expiry monitor, corrections | all four adapters, `workers/monitor/`, `services/api/offers_api.py` (corrections), `workers/publishing/main.py` (`apply_corrections`) | correction write-back tests; monitor alert tests |
| 12 | Analytics, backup/restore, docs, deployment hardening, production review | `services/api/analytics_api.py`, `workers/metrics/`, `infra/backup.sh`, `infra/restore.sh`, `infra/systemd/`, `docs/runbook.md`, `docs/go-live-checklist.md` | metrics worker tests; systemd units; `pnpm verify` (full pipeline) |

## Core rules that must never bend (§3, §4, §5, §11, §17)

| Rule | Implementation | Enforced by |
|---|---|---|
| Unverified records cannot enter script generation | `can_generate_video()` gate in `offers_api.create_script` | integration test (409 for non-verified offer) |
| Every verified field links to evidence | `extraction.supported_fields` + `evidence` rows; script cites evidence URLs | scriptgen tests |
| Official evidence must sit on the provider domain | `evidence.domain_ok` computed server-side | integration test (rejects off-domain URL) |
| No secrets in artifacts | `services/api/redact.py` (server-side scan) + `workers/capture/redact_local.py` (slim local copy); `secret_findings` stores pattern names only | redaction tests; review attestation required before render |
| Synthetic narration must be disclosed | `narration.disclosure_record()` → `renders.disclosure`; narration mix refused unless the track decodes and covers ≥85 % of segments | narration tests (truncation refused) |
| Posts pause when an offer expires or changes | DB trigger `trg_pause_on_offer_change` + worker-side recheck at upload time | integration + publish-gate tests |
| Approval binds to the exact script content | `script_version_hash()` (sha256 of the markdown) on schedule + render + approval | publish-gate test (hash mismatch ⇒ pause) |
| Never publish the same post twice | attempt marker (`POST /schedules/{id}/attempt`) + hold semantics; a held post is skipped by auto-retry and shown on the calendar | duplicate-protection tests (worker + integration) |
| Publishing uses official APIs only | `workers/publishing/platforms/*` (Data API, Graph, TikTok, IG Graph) | adapter tests; no browser automation for posting |
| Corrections link to affected posts | `offer_corrections` + caption permalink (`MTK_PUBLIC_BASE_URL`) + YouTube description write-back | correction write-back tests |
| Reviewed records only | redaction review attestation required for render registration | integration test (unreviewed capture never queues) |
| Manageable publish cadence, never "best hours" | `settings.publish_windows` (validated HH:MM, PKT) | settings tests (invalid window refused) |
| No worker can bypass a human stage | `automation_policy` loaded on every gated write; automation actors must be `automation:<stage>` and the stage must be `auto` | automation unit + integration tests (403 on human stages) |
| Automation stays inside guardrails | confidence/freshness/render/unsafe-command/platform/privacy/budget checks in `offers_api` + `schedules_api` | integration tests (422/409/429) |
| No worker speaks a disabled language | `language_policy.narration_languages` checked in Content Studio, render registration, `/render-candidates`, the renderer and scheduling | language-policy unit tests; renderer skip; API 409 tests |

## Language & packaging coverage (v0.27)

English-first defaults live in `settings.language_policy` (migration
`021_language_policy.sql`) and **Settings → Language policy**. The package
(title, description, hashtags, cover, CTA) and on-screen captions are English
by default; Urdu is opt-in for voiceover only. See
[`language-policy.md`](language-policy.md).

| Behaviour | Implementation | Proof |
|---|---|---|
| English metadata even for Urdu voiceover | `content_studio_api` + `schedules_api` pass `metadata_language` to `seo.py` | SEO unit tests; settings normalizer tests |
| English on-screen captions | `captions.build_cues` wraps step-log text; `to_ass` uses DejaVu Sans/large 9:16 style | caption chunk/wrap/font tests |
| English covers/lower-third | renderer uses `copy_language` for `covers.generate_covers` and `motion.build_motion_filter` | cover/motion tests; render metadata records copy language |
| Urdu only when enabled | policy gate in studio/render/register/schedule/candidates | `test_language_policy.py`; renderer filtering |

## Automation coverage (v0.26)

The mode is set in **Settings → Automation control** and stored as
`settings.automation_policy`; see
[`automation-and-human-control.md`](automation-and-human-control.md).

| Stage | Default (assisted) | Automated by |
|---|---|---|
| Collect | auto | `workers/collectors` (compose service) |
| Verify | auto, with evidence/confidence/freshness gates | `workers/verification` + dashboard *Review desk* |
| Script | auto | `workers/batch` (deterministic generation) |
| Capture | **human** (always) | `workers/capture` (Playwright drives the mechanics) |
| Redaction review | **human** (always) | dashboard offer page |
| Render | auto | `workers/render --sweep` (queue via `GET /render-candidates`) |
| Approve + schedule | **human** (auto in autopilot) | dashboard *Calendar* / *Settings*, or `workers/batch` inside guardrails |
| Publish | approved + scheduled only | `workers/publishing` (+ policy-controlled retry with backoff) |
| Measure | auto | `workers/metrics` (YouTube Analytics / Graph insights) |
| Alert | auto | `workers/monitor` (expiry, token, metrics freshness) |

## Operator surfaces (no curl needed)

| Page | What it does |
|---|---|
| `/` Inbox | collected candidates, dedupe state |
| `/review` Review desk | evidence, extraction, verification decisions |
| `/queue` | what is rendering automatically vs waiting on a person |
| `/sources` | register/disable what the collectors poll, poll health |
| `/calendar` | scheduled posts, approve/pause/resume, outcomes |
| `/analytics` | pipeline health, source freshness, audience reach, content performance |
| `/connections` | register social accounts + where their credentials live |
| `/settings` | automation policy (manual/assisted/autopilot, per-stage control, guardrails, kill switch, dry-run), live automation status/audit, publish windows |
| `/offers/[id]` | script, capture, renders, corrections, scheduling |

## Enhancement plan 2026-10-24 (WP-A…H) — feature-to-code map

Traceability for
[`enhancement-plan-2026-10-24-trends-automation.md`](enhancement-plan-2026-10-24-trends-automation.md)
as of commit `e90a9d3` (2026-10-24, WP-H). Same proof discipline as above:
re-run the named suites against the current commit before relying on a row.
Standing safety rule across ALL rows: trend signals are Tier-B leads (never
evidence), scoring is deterministic/cite-able, cost and release gates fail
closed, and every human gate is untouched.

| WP | Deliverable | Code | Proof |
|---|---|---|---|
| A | Trend sources + adapters (HF Papers, HN Algolia, Reddit new, GitHub stars, Google Trends RSS) | `packages/source_adapters/{hf_papers,hn_algolia,reddit_new,github_stars,google_trends}.py`, collector wiring in `workers/collectors/main.py`, `scripts/seed_sources.py` | adapter fixture tests in `packages/source_adapters/tests/`; egress/permission tests; [`source-registry.md`](source-registry.md) Tier-B table |
| B | Engine v2: topics + observations, velocity/corroboration, incremental scans, durable `trend_scan` job | migrations `031_items_canonical_dedup.sql`, `032_trend_velocity.sql`; `services/api/trends_api.py`, scoring in `packages/trend_*` / trend engine modules; `jobs` arm in 032 | `services/api/tests/test_trend_engine.py`; scan-result re-arm contract in `test_integration.py` |
| C | Production queue + trend→offer bridge | migration `033_production_queue.sql`; `POST /trends/{id}/promote` in `services/api/trends_api.py` (single transaction, audited); `/queue` dashboard | promote tests in `test_integration.py`; queue page `apps/dashboard/src/app/queue/` |
| D | One-click scheduling from queue-ready entities | `services/api/schedules_api.py` (batch endpoints), dashboard calendar adds | `test_schedules.py`; `test_integration.py` batch-transition suite |
| E | Hashtag engine + release gate (traceable tags only; over-max/charset/vanity BLOCK, below-min ADVISORY) | `services/api/hashtags.py`, `services/api/seo.py`, gate checks in `release_gate.py`; `hashtag_performance` (migration 034) | `services/api/tests/test_hashtags.py`, `test_seo.py` |
| F | Cost engine: usage ledger, fail-closed budgets, shared caches (LLM/TTS/analytics), Settings → Costs | `services/api/costs_api.py`, `costs_store.py`, `cache.py`, migration `035_usage_events.sql`; workers meter over HTTP in `workers/verification/extractors.py`, render/narration | `services/api/tests/test_costs.py`, `test_cache.py`; `workers/verification/tests/test_extraction_costs.py` |
| G | Robustness close-outs: token lifecycle, rate-limit taxonomy, LLM hardening, bulk-retry, media GC, lease heartbeat, global trends summary | `workers/publishing/platforms/base.py` (`RateLimited`, `retry_after_from_response`, `exchange_long_lived_token`) + adapters; `workers/publishing/main.py` (`token_maintenance`, `_server_retry_after`); `workers/verification/extractors.py` (`RunBudget`, retries); `services/api/jobs_api.py` (`/jobs/bulk-retry`, `/jobs/{id}/touch`); `services/api/media_api.py` (`/media/gc`); `workers/render/main.py` (`_lease_keeper`); migration `036_extraction_method.sql` | `workers/publishing/tests/test_rate_limits.py`, `test_token_maintenance.py`; `workers/verification/tests/test_llm_hardening.py`; `services/api/tests/test_robustness.py` |
| H | Calendar & analytics polish: conflict flags, measured best-times, week grid | `services/api/schedules_api.py` (`_annotate_conflicts`, `GET /schedules/best-times`, `PUBLISH_CONFLICT_WINDOW_MIN`); `apps/dashboard/src/app/calendar/page.tsx` | `test_robustness.py` (conflict + best-times suites); dashboard `npx tsc --noEmit` |

Full-suite green at the documentation commit: 580 API + 461 workers/packages
pytest, `ruff` (E9/F63/F7/F82), `compileall`, dashboard `tsc`.

## Follow-up plan 2026-10-24 (EP-00…EP-07) — evidence-to-video audit

Traceability for
[`enhancement-plan-2026-10-24-evidence-to-video.md`](enhancement-plan-2026-10-24-evidence-to-video.md),
baselined at commit `75ddff3`. Status: **partially PROPOSED** — EP-00 has
landed (see its row and the log); EP-01…EP-07 have no code yet, so their
Code/Proof columns record the *intended* landing place, not shipped
work. Rows close the gap register G01–G28 in that plan; WP-A–WP-H features above
are the preserved foundation. Ordering: EP-00 → EP-01 → EP-02 → EP-03 →
(EP-04 ∥ EP-05) → EP-06 → EP-07. Rough scope 17–32 developer-days.
Executed-check vs unproven detail per EP lives in
[`ep-implementation-log.md`](ep-implementation-log.md); **status column updated
per EP as it lands.**

| EP | Deliverable (gaps closed) | Intended code | Intended proof |
|---|---|---|---|
| 0 — **COMPLETE (2026-10-24, minus owner billing action)** | Contribution confidence: portable Windows tempfile test, filename-portability lint, CI billing unblock (owner), implemented/partial/unproven status table in traceability docs (G28) | `workers/publishing/tests/test_rate_limits.py`, `scripts/check_filenames.py` + CI/verify wiring, this document, `ep-implementation-log.md` | portable tempfile tests pass; lint run clean + guard tests; rename landed as its own reviewed commit (`5357c7f`); CI execution still blocked by owner billing (logged, not silent) |
| 1 | Safety & financial correctness: Instagram privacy capability model, no synthetic `confirmed=True`, fail-closed atomic budget reservations, role/route matrix + scoped extension credential, derived-metric permission switches (G01–G05, G12, G21, G27) | `workers/publishing/platforms/instagram.py`, `workers/publishing/main.py`, `packages/costing.py`, `services/api/costs_store.py`, `api_hardening.py`, `media_api.py` | unknown budget ⇒ zero paid calls; concurrent reservations cannot oversubscribe; accepted ≠ processing ≠ published; extension denied on jobs/media writes |
| 2 | Discovery & observable momentum: shared adapter registry, persisted excerpts/raw observations, append-only engagement series, cache contract fixes, Google token auth, Compose env matrix, Reddit off-by-default (G06–G11, G13–G16, G22) | `schemas.py`, `workers/collectors/main.py`, `services/api/trends_api.py`, `packages/source_adapters/google_trends.py`, `github_stars.py`, `services/api/cache.py`, `costs_store.py`, `infra/docker/docker-compose.yml` | HN 100→160 fixture ⇒ raw 30 points/h with no duplicate story; unchanged fields can't fake momentum; cached Trends RSS parses; every adapter kind creatable via API |
| 3 | Research briefs & content-type gates: explainer/tutorial/research tracks, versioned claim ledger, reproducible slate snapshot, queue SQL/readiness fixes (G17–G18) | `trends_api.py`, `queue_api.py`, extraction/script templates, migrations | a paper becomes an accurately attributed explainer with no invented coupon/price fields; conflicting evidence blocks unsupported copy |
| 4 | Browser extension finish: link/selection targets, dedicated pairing credential, runtime host grant, durable offline outbox + idempotency, result UX, tests (extension table in plan) | `apps/extension/{background,options}.js`, `options.html`, `verify.sh` | clicked link (not current page) is saved; offline save survives worker restart, delivered once; 401/429/duplicate/timeout are distinct tested states |
| 5 | Scene-based real video production: scene manifest/editor, public-page capture worker, citation/rights overlays, audio normalization, font-aware caption checks, content-addressed TTS cache | `workers/render/`, `workers/capture/`, `workers/render/narration.py`, `packages/costing.py` | one explainer yields reviewable long video + two self-contained vertical edits with traceable claims; claim walkthrough stops for human actions |
| 6 | One-click reviewed scheduling: per-platform preview with disabled targets, idempotent stale-hash commit, account-aware UTC conflicts, hashtag rule relabeling, TikTok export bundle (G19–G20, G23–G24, G26) | `apps/dashboard` ScheduleForm/BatchApprove, `schedules_api.py`, `hashtags.py` | ten repeat submissions ⇒ one logical post per target; stale/changed package refused; unapproved targets never publish |
| 7 | Recovery, learning & cost optimization: lease fencing, telemetry outboxes, circuit breakers, retention, token-rotation persistence, comparable-age outcome snapshots, failure-injection contracts | `services/api/jobs_api.py`, `media_api.py`, `workers/publishing/main.py`, `workers/metrics/` | crash/retry drills show no duplicate publish; budget bounded during outage; restored backup recovers artifact references |
