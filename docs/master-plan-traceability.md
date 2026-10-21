# Master-plan traceability

> **21 October 2026 audit:** this is historical feature-to-code traceability,
> not proof all documented gates are fully enforced or all integrations work
> live. See the [dated automation master plan](automation-master-plan-2026-10-21.md)
> for code-level gaps, checks actually executed, and the new implementation ledger.

Which master-plan item lives where, and how it is proven. Use this to audit
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

## Automation coverage (v0.19–v0.21)

| Stage | Human gate? | Automated by |
|---|---|---|
| Collect | no | `workers/collectors` (compose service) |
| Verify | **yes** (human decision) | dashboard *Review desk* |
| Script | no | `workers/batch` (deterministic generation) |
| Capture | **yes** (human-operated recording) | `workers/capture` (Playwright drives the mechanics) |
| Redaction review | **yes** (attestation) | dashboard offer page |
| Render | no | `workers/render --sweep` (queue via `GET /render-candidates`) |
| Approve + schedule | **yes** (named reviewer) | dashboard *Calendar* / *Settings* |
| Publish | no | `workers/publishing` (+ auto-retry with backoff) |
| Measure | no | `workers/metrics` (YouTube Analytics / Graph insights) |
| Alert | no | `workers/monitor` (expiry, token, metrics freshness) |

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
| `/settings` | publish windows, pipeline status |
| `/offers/[id]` | script, capture, renders, corrections, scheduling |
