# MTK RADAR AI

> **Trusted offer discovery, real claim walkthroughs, custom video editing, and scheduled multi-platform publishing — built on verified evidence, not hype.**

Created by **Muhammad Kashif** · MTK Codex · October 2026

---

## Overview

**MTK RADAR AI** is a content platform that finds AI and developer offers ("free credits," student perks, domain promotions), verifies them against official sources, and turns them into honest, real-screen claim walkthrough videos — then schedules and publishes them across YouTube, Facebook, Instagram, and TikTok.

Every offer is treated as **time-sensitive data**: eligibility, region, expiry, claim steps, and current terms are rechecked immediately before recording and publishing. The LLM never acts as the evidence source — it only extracts and compares structured data from immutable snapshots of official pages.

## How It Works

| Stage | What the platform does | Human control |
|---|---|---|
| **Discover** | Collect candidate changes from trusted source feeds, APIs, release notes, official pages, and saved links. | Choose source categories and regions. |
| **Verify** | Extract offer fields, preserve evidence, compare sources, and flag conflicts or missing terms. | Approve, reject, or request more evidence. |
| **Prepare** | Create a claim checklist, script, command cards, shot list, and platform copy. | Edit factual claims and narration. |
| **Capture & Edit** | Record the real claim flow; generate captions, voiceover, and 16:9 / 9:16 exports. | Review redactions, edit copy/captions in the Studio, or export the bundle for an external editor. |
| **Schedule** | Create a platform-specific post package, schedule it, and track status. | Final approval per platform; cancel or reschedule. |
| **Learn** | Record results and corrections; refresh or expire stale offer pages. | Correct errors and request takedown/update. |

### Offer lifecycle

```
Candidate → Evidence needed → Verified → Approved for video → Published → Expired/Corrected
```

Video generation is **blocked** from `Candidate` or `Evidence needed` states. If terms change, scheduled posts pause automatically and affected videos are marked stale.

## Automation & Human Control

Every pipeline stage — collect, verify, script, render, approve, schedule — is
controlled by one policy in **Settings → Automation control**. Pick a preset or
mix stages yourself:

| Mode | Mechanical work | Offer & post approval | Scheduling |
|---|---|---|---|
| **Manual** | human-triggered | human only | human only |
| **Assisted** (default) | automatic | **human** | **human** |
| **Autopilot** | automatic | automatic inside guardrails | automatic inside guardrails |

The API re-checks the policy on every gated write, so a stale or forged worker
cannot skip a human stage. Automations are audited as `automation:<stage>`, and
guardrails cap confidence, evidence age, platform/privacy, and unattended
approvals per day. The **Pause all automation** switch stops unattended
progress immediately; **dry-run** reports what would happen without changing
anything. Some guarantees are not configurable: `verified` always needs
official, domain-checked evidence; redaction review is always human; a render
can only publish when its script hash matches the approved hash; and expiry or
corrections auto-pause queued posts.

See [`docs/automation-and-human-control.md`](docs/automation-and-human-control.md)
for the full matrix, guardrails, API, and rollout advice.

## Language & Packaging

Titles, descriptions, hashtags, cover text, CTA and on-screen captions are
**English by default for every video**. Urdu is an **opt-in voiceover only**:
enable it in **Settings → Language policy** when you want an Urdu-spoken
version, while the package stays English and searchable. The renderer skips
disabled languages, and Content Studio/scheduling/render registration reject
them, so no worker can quietly publish an unapproved language.

Captions are generated from the real capture step log, split into readable
chunks, and rendered with a legible font, safe margins and 9:16-aware sizing.
Override the font with `MTK_CAPTION_FONT` if you install another one. The
render worker then measures the output — stream metadata, a full decode,
black/freeze/silence events, loudness/true peak and caption safe area — and only
a `rendered / passed` row may be scheduled or published. See
[`docs/render-qc.md`](docs/render-qc.md) for thresholds, intentional-still
exemptions and the dead-letter workflow.

See [`docs/language-policy.md`](docs/language-policy.md) for defaults,
validation, and the English-first rationale.

## Key Principles

- **Source registry, not scraping.** Each source has an owner, official identifier, collection method, trust tier, and polling cadence. Social posts are discovery signals; official terms pages are the evidence.
- **Immutable evidence snapshots.** Page URL, retrieval timestamp, publisher identity, text excerpt, and content hash — stored and reviewable.
- **Tiered trust:** Tier A (provider-owned) can support verification; Tier B (X, Reddit, HN, Discord) only creates leads; Tier C (coupon aggregators, leaked codes) is excluded until official confirmation exists.
- **Real walkthroughs only.** No staged success screens, no implied universal results, no secrets on camera. Commands come from official docs, are tested in a clean environment, and are shown with expected output.
- **Human approval before publishing by default,** with pause/cancel/edit controls after scheduling. Automation can be enabled per stage in Settings, but never bypasses evidence, redaction, script-hash or measured render-QC guarantees.

## Architecture

```
┌─────────────────────┐   ┌──────────────────────┐   ┌────────────────────────┐
│  Dashboard (Next.js │   │  Browser Extension   │   │  Background Workers    │
│  React + TypeScript)│   │  (Manifest V3        │   │  collectors · batch ·  │
│  inbox · review ·   │   │   save-current-page) │   │  render · publishing · │
│  queue · calendar   │   └──────────────────────┘   │  metrics · monitor     │
│  connections · …    │                              └────────────────────────┘
└─────────┬───────────┘                                          │
┌─────────┴──────────────────────────────────────────────────────┴─────────┐
│  PostgreSQL (offers, evidence, projects, schedules, metrics, audit)      │
│  Object storage (S3-compatible) · Redis (optional cache) · worker locks  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| Dashboard | Next.js / React + TypeScript |
| Extension | Chrome Manifest V3 |
| API & workers | FastAPI (Python) or NestJS (TypeScript) |
| Data & storage | PostgreSQL 16 · Redis (optional cache) · S3-compatible object storage |
| Collectors | RSS/Atom, GitHub releases, official-page watch (all in-house adapters) |
| Capture | Playwright (human-operated claim sessions) |
| Video | FFmpeg (captions, narration, 16:9/9:16) · Kdenlive/CapCut asset handoff |
| Publishing | Official platform APIs (YouTube Data, Meta Graph, Instagram Graph, TikTok Content Posting) |

## Project Layout

```
apps/dashboard/            # Web admin console (Next.js)
apps/extension/            # Save-current-page extension (Manifest V3)
services/api/              # API service (FastAPI + Postgres)
services/api/db/migrations/001_init.sql
workers/collectors/        # Source collection jobs (RSS, GitHub, page watch +
                           # trend signals: HF papers, HN, Reddit, star velocity,
                           # Google Trends — Tier-B leads for the radar)
workers/verification/      # Extraction & evidence jobs
workers/batch/             # Script generation + pipeline readiness
workers/capture/           # Playwright capture session (human-operated)
workers/render/            # FFmpeg renders, captions, narration, handoff
workers/video/             # Alias for workers/render (master plan §12 layout)
workers/publishing/        # Platform upload jobs (+ platform adapters)
workers/metrics/           # Audience metrics (YouTube Analytics, Graph)
workers/monitor/           # Expiry, token and freshness alerts
packages/offer-schema/     # Shared offer life-cycle + validation schemas
packages/source_adapters/  # Per-source collection adapters
packages/object_storage/   # S3-compatible storage driver (httpx + SigV4)
apps/extension/            # Save-current-page extension (Manifest V3)
infra/docker/              # Docker Compose dev environment (api, dashboard, workers)
infra/systemd/             # Backup + restore-drill timers
scripts/verify.sh          # One-command verification (same steps as CI)
docs/                      # Master plan, runbook, go-live checklist, notices
```

## Quick Start

```bash
cp .env.example .env                  # never commit the real .env
docker compose -f infra/docker/docker-compose.yml up -d --build \
  --profile workers --profile storage  # postgres + redis + api + dashboard + workers
docker compose -f infra/docker/docker-compose.yml exec api python db_migrate.py
```

The base compose file builds immutable API/dashboard/worker images and keeps
PostgreSQL, Redis and MinIO off the host network. For host-side hot reload and
published development ports use
`-f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml`.

- Dashboard (operator console): http://localhost:3000 · API health: http://localhost:8000/health
- Choose how much runs unattended in **Settings → Automation control** (default:
  Assisted — approve and schedule stay human)
- The schema is owned by the migration runner (`db_migrate.py`) — run it once
  after the first boot; it records what it applied in `schema_migrations`
- Extension: load `apps/extension/` via `chrome://extensions` → Developer mode → Load unpacked
- Verify the whole system in one command: `pnpm verify`
- Operator procedure (keys, social connections, first real post):
  [`docs/go-live-checklist.md`](docs/go-live-checklist.md)

### Run the collectors (Week 2)

```bash
# 1. Seed the source registry (Tier-A sources from docs/source-registry.md)
pip install -r services/api/requirements.txt
python services/api/scripts/seed_sources.py

# 2. Start the collector worker (RSS, GitHub releases, page watch)
pip install -r workers/requirements.txt
python workers/collectors/main.py
```

New candidates appear once (deduplicated by canonical URL) in the review inbox.

### Local development without Docker

Docker is the supported path, but the stack also runs directly on a host. On
Windows without Docker Desktop, a portable PostgreSQL build works (the
[Zonky embedded binaries](https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-windows-amd64/)
need no admin rights); Docker's Postgres 16 image is the other option.

```bash
# 1. Python environment (3.12 matches CI)
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r services/api/requirements.txt \
    -r workers/requirements.txt -r workers/publishing/requirements.txt \
    -r workers/render/requirements.txt pytest

# 2. Postgres on 5432 with role `mtk` / password `mtk` and database `mtk_radar`
#    (Redis is optional — it only caches the dashboard's aggregate read)

# 3. Schema + source registry
cp .env.example .env
DATABASE_URL=postgresql://mtk:mtk@localhost:5432/mtk_radar .venv/Scripts/python.exe services/api/db_migrate.py
DATABASE_URL=postgresql://mtk:mtk@localhost:5432/mtk_radar .venv/Scripts/python.exe services/api/scripts/seed_sources.py

# 4. API and dashboard
DATABASE_URL=postgresql://mtk:mtk@localhost:5432/mtk_radar \
  .venv/Scripts/python.exe -m uvicorn main:app --app-dir services/api --port 8000
pnpm --filter mtk-radar-dashboard dev          # http://localhost:3000

# 5. Workers (each in its own shell; API_URL points at the API)
API_URL=http://localhost:8000 .venv/Scripts/python.exe workers/collectors/main.py
API_URL=http://localhost:8000 .venv/Scripts/python.exe workers/monitor/main.py
```

The pnpm version is pinned in `package.json` (`packageManager`); run
`corepack enable` so `pnpm` matches it. `pnpm install` needs the `sharp`
build script, already approved via `allowBuilds` in `pnpm-workspace.yaml`.

### Tests & checks

```bash
pnpm install
pnpm verify      # EVERYTHING: lint → compile → unit+integration tests on a
                 # real Postgres → typecheck → dashboard build → compose/CI/
                 # extension checks → browser E2E (Playwright)
```

`pnpm verify` is the same pipeline CI runs (`.github/workflows/ci.yml`), so a
green local run means a green CI run. Use `pnpm verify --fast` to skip the
browser step.

### Operations (Week 12)

- **Analytics** — dashboard `/analytics` page + `GET /api/analytics`: pipeline funnel, verification load, publishing outcomes, source freshness.
- **Migrations** — `pnpm migrate` (or `python services/api/db_migrate.py`); numbered SQL, applied once, recorded in `schema_migrations`.
- **Backup/restore** — `pnpm backup` (`infra/backup.sh`: pg_dump custom format, retention, optional off-host copy to S3); monthly **verified** drill via `infra/drill.sh` (restores into a throwaway DB and compares row counts) driven by `infra/systemd/` timers.
- See [`docs/runbook.md`](docs/runbook.md) for deployment hardening, token-expiry recovery, incident playbooks, and the first production review.

## Documentation

- [`docs/implementation-roadmap-2026-10-25.md`](docs/implementation-roadmap-2026-10-25.md) — **the active execution plan**: status rules, gap register, milestones and proof commands. Start here for current work.
- [`docs/README.md`](docs/README.md) — documentation index (active docs, operations, engineering, history).
- [`docs/archive/wp01/implementation-wp01-2026-10-21.md`](docs/archive/wp01/implementation-wp01-2026-10-21.md) — **historical** first verification-integrity checkpoint; superseded by the roadmap and EP log.
- [`docs/automation-master-plan-2026-10-21.md`](docs/automation-master-plan-2026-10-21.md) — **dated 2026–2027 enhancement roadmap and code audit**: actual test results, implemented/remaining checklist, safety gaps, trend radar, premium video, light editor, local-model controls and ordered work packages. Use this for new enhancement work; historical completion claims below are not production certification.
- [`docs/enhancement-plan-2026-10-24-trends-automation.md`](docs/enhancement-plan-2026-10-24-trends-automation.md) — **Trend Radar v2, research-to-video queue, one-click scheduling, evidence-based hashtags, and the cost engine** — work packages WP-A…WP-H with acceptance criteria (extends the 10-22 audit and this master plan).
- [`docs/archive/coding-model-handoff-2026-10-21.md`](docs/archive/coding-model-handoff-2026-10-21.md) — **historical** compact handoff for GLM, MiniMax or other coding assistants; use the roadmap for current work.
- [`docs/master plan.md`](docs/master%20plan.md) — the complete build plan: product scope, verification design, offer schema, video production guide, publishing operations, and reference links.
- [`docs/implementation-best-practices.md`](docs/implementation-best-practices.md) — working agreements; the Weeks 1–4 checklist is historical, and unimplemented tooling is marked `PLANNED`.
- [`docs/first-offer-recipe.md`](docs/first-offer-recipe.md) — the pilot case-study recipe: pre-flight, script, guided capture, redaction review, hard no's.
- [`docs/open-source-integrations.md`](docs/open-source-integrations.md) — upstream repositories we integrate (and how), license reviews, fork strategy, and integration to-dos.
- [`docs/source-registry.md`](docs/source-registry.md) — registered sources with trust tiers and polling cadence.
- [`docs/automation-and-human-control.md`](docs/automation-and-human-control.md) — **automation policy**: manual/assisted/autopilot modes, per-stage control, server-enforced guardrails, kill switch and dry-run.
- [`docs/language-policy.md`](docs/language-policy.md) — **English-first packaging**: English titles/captions by default, opt-in Urdu voiceover, caption wrapping/fonts, and API validation.
- [`docs/security-and-redaction.md`](docs/security-and-redaction.md) — secrets, capture, and privacy rules that block release if violated.
- [`docs/runbook.md`](docs/runbook.md) — **operational runbook**: deployment, migrations, backup/restore drills, credential & source recovery, incident playbooks, retention policy, first production review.
- [`docs/cost-laptop-vps-2026-10-22.md`](docs/cost-laptop-vps-2026-10-22.md) — **low-cost hosting**: cost scenarios, student/free-resource stack, laptop production setup, Render/MongoDB credits, Supabase/Cloudinary/Drive tradeoffs, and the split-VPS fallback when the laptop is off.
- [`docs/notifications.md`](docs/notifications.md) — **monitor webhook/email alerts**: payload schema, SMTP/Gmail setup, webhook security, test command, troubleshooting, and which parts can (and cannot) run on free Supabase.
- [`docs/third-party-notices.md`](docs/third-party-notices.md) — pinned upstream dependencies, licenses, obligations, and the evaluated-but-not-adopted list.
- [`docs/tool-stack-alignment-2026-10-23.md`](docs/tool-stack-alignment-2026-10-23.md) — **external tool-stack evaluation**: Perkstack, OBS, Descript, CapCut, Opus Clip, Metricool, Loomly, Runway, HeyGen mapped against the in-house pipeline, with adopt/skip decisions and guardrails.
- [`docs/go-live-checklist.md`](docs/go-live-checklist.md) — **the operator procedure**: which keys to add, how to connect each social account, the first real post, and the daily/weekly operations.
- [`docs/master-plan-traceability.md`](docs/master-plan-traceability.md) — every master-plan item mapped to its code and its proof.
- [`docs/upgrade-checklist.md`](docs/upgrade-checklist.md) — how a pinned dependency or image is upgraded safely.

## Delivery Roadmap

| Phase | Focus | Exit criteria | Status |
|---|---|---|---|
| 0. Foundation | Source registry, offer schema, roles, audit trail | Sources can be added/disabled; every offer field explained | ✅ v0.1–v0.5 |
| 1. Offer radar | RSS, GitHub releases, extension save-link, dedup | Candidate appears once with source/time, reviewable | ✅ v0.6–v0.13 |
| 2. Verification desk | Structured extraction, evidence snapshots, staleness rules | No unverified offer enters script generation | ✅ v0.7–v0.9 |
| 3. Script & checklist | Claim guide, command cards, citations | Every factual claim traceable to evidence | ✅ v0.10 |
| 4. Capture & video | Screen recording, redaction, captions, FFmpeg exports | One complete video package reproducible | ✅ v0.11–v0.14, v0.17 |
| 5. Editing & schedule | Editor handoff, calendar, approval gates | Schedule pauses, retries, and exports safely | ✅ v0.15, v0.16, v0.23 (handoff export; no timeline editor — WP10 planned) |
| 6. Publishing integrations | YouTube, Meta, Instagram, TikTok | Each connector passes private/test posting | ⚠️ v0.19 — adapters + mocked tests + fail-closed private smoke harness; live private/test posts unproven (needs keys) |
| 7. Analytics & scale | Views, corrections, source freshness | Data improves packaging without weakening verification | ✅ v0.18, v0.22, v0.24 |
| 8. Automation & control | Manual / assisted / autopilot policy per stage | Every gated write re-checks the policy; human stages cannot be bypassed | ✅ v0.26 |
| 9. Production polish | Trend radar, bilingual studio, covers/motion, English-first packaging, growth analytics | English package + captions for every video; Urdu voiceover opt-in; verified render/schedule path | ✅ v0.27 |

> **Status note (2026-10-28):** the ✅ marks above record the original v0.x
> delivery, not production certification. Current open work — scene-based
> video (EP-05), one-click reviewed scheduling (EP-06) and recovery/robustness
> (EP-07) — is tracked in
> [`docs/enhancement-plan-2026-10-28-gap-audit.md`](docs/enhancement-plan-2026-10-28-gap-audit.md)
> and [`docs/ep-implementation-log.md`](docs/ep-implementation-log.md).
> To prove the latest pass on a fully set-up machine, follow
> [`docs/verify-at-home-2026-10-28.md`](docs/verify-at-home-2026-10-28.md).

Remaining, with reasons: SSO/self-serve logins (single-operator token model is
sufficient — see runbook §9), Postgres HA (single instance at this scale),
TikTok publishing (requires an approved developer app), the WP10 in-app light
editor (handoff export exists; there is no timeline editor), EP-05–EP-07
(evidence-to-video plan, still proposed), live private/test posting (needs
provider keys and an approved clip), and GitHub Actions (currently blocked by
the owner account's billing lock). The Postgres integration suite and the
loaded-extension Chromium E2E now run locally; see the
[evidence log](docs/evidence/verify-pnpm-2026-10-25.log). The ordered
remediation plan is the [implementation roadmap](docs/implementation-roadmap-2026-10-25.md).

For the detailed twelve-week implementation sequence, see the [master plan](docs/master%20plan.md).

## Content Coverage

MTK RADAR catalogs offers as distinct types: free/open-weight models, hosted inference free tiers, API trial credits, first-signup credits, cloud credits, student packs, hackathon prizes, startup programs, software subscriptions, and domain/hosting discounts — tracking whether each is universal, application-based, student-only, time-limited, or a discount that renews at a paid rate.

## Safety & Ethics

- Never call a promotion universal unless the provider says so — region and eligibility requirements are always stated.
- Monetary credits, free model weights, free tiers, trials, and contest prizes are never conflated.
- Offers are rechecked before recording **and** before scheduled publication; expired deals auto-pause queued posts.
- No API keys, tokens, or personal account data ever appear in footage, transcripts, or project bundles.
- Synthetic narration/visuals are labeled where platform policy requires it; correction links and version dates live in every video description.

## License

Project license to be determined before first release. Third-party dependencies (n8n — Sustainable Use License, Postiz — AGPL-3.0, Remotion — commercial terms, etc.) are evaluated individually and recorded in `THIRD_PARTY_NOTICES`.

> ⚠️ Program terms, platform APIs, and repository licenses change. Use this plan as the build blueprint; verify each live offer and integration at implementation time.
