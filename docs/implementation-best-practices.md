# Implementation Guide — Best Practices & To-Do Checklist

How to work on MTK RADAR AI, per the [master plan](master%20plan.md). This guide
started as the Weeks 1–4 start-up checklist; the repository is now at v0.30, so
the checklist in §3 is historical. The working agreements still apply, and the
current execution order lives in the
[implementation roadmap](implementation-roadmap-2026-10-25.md).

---

## 1. Golden rules (read before writing any code)

1. **Verification-first.** No unverified offer may enter script generation, video capture, or publishing. Build the verification gate before any shiny feature.
2. **Dashboard is the single source of truth** for offers, evidence, projects, edits, and schedules. Workers and the extension only read/write through the API.
3. **Pilot before pipeline.** Build ONE complete case-study offer end-to-end (collect → verify → script → record → edit → private test post) before adding more source adapters or platforms.
4. **Every factual claim traces to evidence.** Each extracted field stores its supporting source URL, quote, hash, and confidence.
5. **Human approval gates.** Publishing requires an explicit approval recorded with user, time, and the exact version hash approved.
6. **Secrets never leave the vault.** No API keys, tokens, or credentials in code, footage, transcripts, terminal history, or DB rows outside the secrets manager.

---

## 2. Engineering best practices

### Repository & Git
- Monorepo with the layout from the master plan (`apps/`, `services/`, `workers/`, `packages/`, `infra/`, `docs/`).
- Trunk-based development: short-lived feature branches → PR into `main` → squash merge.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) are the team
  convention. `commitlint` is **not configured and no longer claimed**; adopt
  it only if a real multi-author workflow needs the enforcement.
- PRs require: green CI, at least one review, and no failing type checks. Small PRs (< ~400 lines) preferred.

### Environment & configuration
- Local development runs via Docker Compose (`infra/docker/`): Postgres, Redis, workers, dashboard.
- Configuration via `.env`; a single schema validator at boot is **planned, not
  implemented** (CLAIM-01). Today each service validates the variables it reads
  and fails closed where a missing value is unsafe, and the Compose env matrix
  is guard-tested against every reader.
- Secrets in a vault/env manager (never in the repo); object storage uses
  server-side SigV4 and media streams through the authenticated API — there are
  no public or presigned URLs (see `security-and-redaction.md`).

### Database
- Versioned migrations from day 1 (no schema drift); migrations are
  **forward-only** and every change relies on the tested backup/restore path
  rather than down-migrations.
- Every table gets `created_at`/`updated_at`; offers, evidence, and approvals are append-friendly with explicit state columns.
- Idempotency keys for all job outcomes (collections, publishes) so retries never duplicate work.

### Quality gates
- TypeScript everywhere strict mode; Python uses `ruff` (enforced) and type
  hints. `mypy` is **not configured and no longer claimed** (CLAIM-01); add it
  only with a scoped baseline that can stay green.
- Pre-commit hooks are configured in `.pre-commit-config.yaml`: gitleaks secret
  scanning (put the pinned `gitleaks` binary on `PATH`), `ruff`, the Windows
  filename guard and the doc-link check. Install with
  `pip install pre-commit && pre-commit install`; the config passes
  `pre-commit run --all-files` on 2026-10-25.
- CI on every PR: secret scan → lint → typecheck → unit tests → build. The
  gitleaks scan also runs over full history in the `secret-scan` job; the config is
  verified locally (128 commits, no leaks). CI execution still fails before
  starting because the owner account is billing-locked; record that as
  `UNPROVEN`, not green (PROOF-04).
- Structured logs with job/trace IDs; dead-letter queue watched from week 1; source health dashboard before scaling sources.

### Data & content safety
- Verify offer state at **two moments**: before recording and again before publish; auto-pause on expiry/change.
- Pin exact upstream versions of every dependency (see [open-source-integrations.md](open-source-integrations.md)).
- Keep evidence snapshots immutable (content hashes); personal data redacted at capture time.

---

## 3. Historical start checklist (Weeks 1–4) — superseded

> The checkboxes below record the original start-up sequence. They are not a
> current status report; use the [implementation roadmap](implementation-roadmap-2026-10-25.md)
> for open work.

### Week 1 — Foundation
- [ ] Create monorepo skeleton: `apps/dashboard`, `apps/extension`, `services/api`, `workers/*`, `packages/*`, `infra/docker` (per master plan §12).
- [ ] Docker Compose dev environment: dashboard + API + Postgres + Redis boots with one command.
- [ ] Implement database schema: `sources`, `items`, `offers`, `evidence`, `projects`, `approvals`, `schedules` (master plan §10) + migrations.
- [ ] User roles + audit trail table (who did what, when, on which version).
- [ ] Source registry table seeded with initial Tier-A sources (Hugging Face docs, GitHub releases, MLH, registrar partner pages).
- [ ] Secrets/audit model: `.env.example`, vault handling, gitleaks in pre-commit & CI.
- ✅ *Done when: local system starts; source and offer records can be created and reviewed.*

### Week 2 — Offer radar (first collector)
- [ ] RSS/Atom collector + GitHub release feeds collector (rate-limited, robots-aware, deduplicated).
- [ ] Browser extension: Manifest V3 "save current page" → API with URL/title/selected text/account handle + user confirmation.
- [ ] Deduplication key + canonical URL resolution; items land in the review inbox exactly once.
- ✅ *Done when: a candidate appears once with URL, timestamp, and dedup key, and is reviewable.*

### Weeks 3–4 — Verification desk
- [ ] Structured extraction of offer fields (LLM as extractor, never as source).
- [ ] Provider-domain allowlist check (domain + account handle belong to provider).
- [ ] Immutable evidence snapshots: URL, timestamp, excerpt, content hash; screenshots only when needed.
- [ ] Conflict & staleness detection (offer expiry, terms change → recheck required).
- [ ] Reviewer queue with Approve / Reject / Request-evidence actions; state machine per master plan §3.
- ✅ *Done when: every verified field links to evidence and unverified records cannot enter script generation.*

### First-pilot checklist (parallel to Weeks 1–4, but manual where needed)
- [ ] Pick ONE current, officially documented developer/student offer (e.g., a .TECH domain via a student benefit program).
- [ ] Verify: live partner page, program listing, eligibility, promo code + steps, deadline, renewal price/auto-renew.
- [ ] Write script + claim checklist + command cards (commands tested in a clean env, expected output documented).
- [ ] Record a real walkthrough on a clean laptop profile (or clearly labeled demo if not eligible).
- [ ] Produce 16:9 + 9:16 exports with captions; schedule a private/unlisted test post.
- [ ] Measure: time spent, missed details, corrections, rendering reliability — this drives what to automate next.

---

## 4. Definition of Done (for any feature)

- [ ] Migrations included; schema changes backward-compatible.
- [ ] Tests: unit for logic, integration for API endpoints; job idempotency covered.
- [ ] Observability: structured logs, error surface, alert if the feature fails silently.
- [ ] Security review: no secrets, inputs validated, auth/roles enforced, redaction respected.
- [ ] Docs updated (`docs/`, inline where needed); `THIRD_PARTY_NOTICES` updated if new upstreams introduced.
- [ ] Works end-to-end in Docker Compose from a clean clone.

## 5. Operating cadence

- **Daily:** triage the review inbox; check source-health and dead-letter alerts.
- **Weekly:** recheck all Tier-A sources for stale data; run dependency/advisory check; review pending corrections.
- **Before each release:** backup/restore drill, rollback plan (compose images tagged, DB migration rollback), release checklist in PR.
