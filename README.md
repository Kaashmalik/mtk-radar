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
| **Capture & Edit** | Record the real claim flow; generate captions, voiceover, and 16:9 / 9:16 exports. | Review redactions and edit in-app or in an external editor. |
| **Schedule** | Create a platform-specific post package, schedule it, and track status. | Final approval per platform; cancel or reschedule. |
| **Learn** | Record results and corrections; refresh or expire stale offer pages. | Correct errors and request takedown/update. |

### Offer lifecycle

```
Candidate → Evidence needed → Verified → Approved for video → Published → Expired/Corrected
```

Video generation is **blocked** from `Candidate` or `Evidence needed` states. If terms change, scheduled posts pause automatically and affected videos are marked stale.

## Key Principles

- **Source registry, not scraping.** Each source has an owner, official identifier, collection method, trust tier, and polling cadence. Social posts are discovery signals; official terms pages are the evidence.
- **Immutable evidence snapshots.** Page URL, retrieval timestamp, publisher identity, text excerpt, and content hash — stored and reviewable.
- **Tiered trust:** Tier A (provider-owned) can support verification; Tier B (X, Reddit, HN, Discord) only creates leads; Tier C (coupon aggregators, leaked codes) is excluded until official confirmation exists.
- **Real walkthroughs only.** No staged success screens, no implied universal results, no secrets on camera. Commands come from official docs, are tested in a clean environment, and are shown with expected output.
- **Human approval before publishing,** with pause/cancel/edit controls after scheduling.

## Architecture

```
┌─────────────────────┐   ┌──────────────────────┐   ┌────────────────────────┐
│  Dashboard (Next.js │   │  Browser Extension   │   │  Background Workers    │
│  React + TypeScript)│   │  (Manifest V3        │   │  collectors · verify · │
│  offers · evidence  │   │   save-current-page) │   │  video · publishing    │
│  editor · calendar  │   └──────────────────────┘   └────────────────────────┘
└─────────┬───────────┘                                          │
┌─────────┴──────────────────────────────────────────────────────┴─────────┐
│  PostgreSQL (offers, evidence, projects, schedules) · Object storage      │
│  Redis + BullMQ job queue · Structured logs · Dead-letter queue           │
└──────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| Dashboard | Next.js / React + TypeScript |
| Extension | Chrome Manifest V3 |
| API & workers | FastAPI (Python) or NestJS (TypeScript) |
| Data & storage | PostgreSQL · Redis · BullMQ · object storage |
| Collectors | RSS/Atom, official APIs, GitHub releases, changedetection.io |
| Capture | Playwright (human-operated claim sessions) |
| Video | FFmpeg · optional Remotion templates · Kdenlive/CapCut handoff |
| Publishing | Official platform APIs (YouTube Data, Meta Graph, TikTok Content Posting) · optional Postiz |

## Planned Repository Layout

```
apps/dashboard/            # Web admin console
apps/extension/            # Save-current-page extension
services/api/              # API service
workers/collectors/        # Source collection jobs
workers/verification/      # Extraction & evidence jobs
workers/video/             # Rendering jobs
workers/publishing/        # Platform upload jobs
packages/source-adapters/  # Per-source collection adapters
packages/offer-schema/     # Shared offer data model
packages/video-templates/  # Templated video configs
infra/docker/              # Deployment configs
docs/                      # Source registry, security, third-party notices
```

## Delivery Roadmap

| Phase | Focus | Exit criteria |
|---|---|---|
| 0. Foundation | Source registry, offer schema, roles, audit trail | Sources can be added/disabled; every offer field explained |
| 1. Offer radar | RSS, GitHub releases, extension save-link, dedup | Candidate appears once with source/time, reviewable |
| 2. Verification desk | Structured extraction, evidence snapshots, staleness rules | No unverified offer enters script generation |
| 3. Script & checklist | Claim guide, command cards, citations | Every factual claim traceable to evidence |
| 4. Capture & video | Screen recording, redaction, captions, FFmpeg exports | One complete video package reproducible |
| 5. Editing & schedule | Editor handoff, calendar, approval gates | Schedule pauses, retries, and exports safely |
| 6. Publishing integrations | YouTube, Meta, TikTok, optional Postiz | Each connector passes private/test posting |
| 7. Analytics & scale | Views, retention, corrections, source freshness | Data improves packaging without weakening verification |

For the detailed twelve-week implementation sequence, see the [master plan](docs/master%20plan.md).

## Content Coverage

MTK RADAR catalogs offers as distinct types: free/open-weight models, hosted inference free tiers, API trial credits, first-signup credits, cloud credits, student packs, hackathon prizes, startup programs, software subscriptions, and domain/hosting discounts — tracking whether each is universal, application-based, student-only, time-limited, or a discount that renews at a paid rate.

## Safety & Ethics

- Never call a promotion universal unless the provider says so — region and eligibility requirements are always stated.
- Monetary credits, free model weights, free tiers, trials, and contest prizes are never conflated.
- Offers are rechecked before recording **and** before scheduled publication; expired deals auto-pause queued posts.
- No API keys, tokens, or personal account data ever appear in footage, transcripts, or project bundles.
- Synthetic narration/visuals are labeled where platform policy requires it; correction links and version dates live in every video description.

## Documentation

- [`docs/master plan.md`](docs/master%20plan.md) — the complete build plan: product scope, verification design, offer schema, video production guide, publishing operations, and reference links.

## License

Project license to be determined before first release. Third-party dependencies (n8n — Sustainable Use License, Postiz — AGPL-3.0, Remotion — commercial terms, etc.) are evaluated individually and recorded in `THIRD_PARTY_NOTICES`.

> ⚠️ Program terms, platform APIs, and repository licenses change. Use this plan as the build blueprint; verify each live offer and integration at implementation time.
