# Security & Redaction Policy

Non-negotiable rules from the master plan (§3, §4, §11). Violations block release.

## Secrets & credentials

- No API keys, passwords, recovery codes, tokens, or personal account data in: recordings, transcripts, terminal history, downloadable projects, logs, or repo files.
- Secrets live only in a vault/env manager; `.env` is git-ignored, only `.env.example` is committed.
- Promo codes shown on camera must be public and verified as authorized for redistribution.
- Object storage is never exposed directly: there are no public or presigned URLs. Captures and renders stream only through the authenticated API (byte-range aware), with the dashboard proxy attaching the reviewer's HttpOnly session server-side.

## Capture sessions

- Human-operated, on the operator's own eligible account, from a clean laptop profile.
- Playwright automates repeatable capture mechanics only — never credential entry, never account creation at scale, never bypassing eligibility checks.
- Blur/redact sensitive areas while preserving the real steps; review redactions before media enters the pipeline.

## Commands on camera

- Generated from official documentation, tested in a clean environment first.
- Shown with exact expected output; destructive or billable effects explained before they run.
- OS/shell stated; commands must be relevant to the actual provider flow.

## PRIVACY REDACTION CHECKLIST (before any render)

- [ ] Email addresses, phone numbers, physical addresses masked
- [ ] API keys / tokens / recovery codes absent from frames, audio, and terminals
- [ ] Browser tabs/bookmarks/history not leaking personal info
- [ ] Account identifiers that shouldn't be public blurred
- [ ] Synthetic narration/visuals labeled where platform policy requires
- [ ] Captions and transcripts scanned with the same rules

## Data handling

- Evidence snapshots are immutable (content hashes); store screenshots only when needed and redact personal details first.
- Human approval (user, time, version hash) required before publishing; approvals are auditable (`audit_log`).
- Corrections: keep source correction link + version date in video descriptions; takedown/correction handling is part of the workflow, not an afterthought.

## Dependency hygiene

- Pinned versions; monthly security-advisory check. Secret scanning with
  gitleaks is configured in `.pre-commit-config.yaml` and the CI `secret-scan` job
  (`.gitleaks.toml`). The config was run locally over all 128 commits with no
  leaks on 2026-10-25; CI execution is `UNPROVEN` while the owner billing lock
  remains (PROOF-04), so treat the CI gate as configured, not proven.
- Licenses recorded in `third-party-notices.md` before adoption.

## Incident log

### 2026-11-01 — git history purge (personal-data archive removed)

**What was removed.** A customer contact/location archive
(`docs/marshmallow-contact-location-…json`, ≈370k lines — issue H1 of the
[2026-10-28 gap audit](enhancement-plan-2026-10-28-gap-audit.md)) had been
added by a long-gone commit and remained retrievable from git history even
after its on-branch deletion. The rewrite also removed an unrelated binary
(`docs/Fudge (2).zip`) and a separate, mistakenly committed project
directory (`mtk-codex/`).

**Action taken.** On **2026-11-01** the repository history was rewritten to
the purged lineage and **force-pushed** to GitHub (`main` now rooted at
commit `fa05c1f` — the plain removal commit). Anything referenced by the
removed files should be considered potentially exposed and rotated by the
owner.

**Caveats and follow-ups:**

- A pre-rewrite backup bundle exists at
  `D:\MalikTech\mtk-radar-pre-rewrite.bundle` so the owner can verify the
  rewrite. **Delete it once verified** — the bundle itself still contains the
  removed personal data.
- GitHub may serve cached objects from the old history until its garbage
  collection runs (a cache is not a security boundary); the owner can
  request an accelerated GC through GitHub Support.
- Old clones still carry the pre-rewrite history. Re-clone, or point the
  existing clone at the rewritten remote and hard-reset
  (`git fetch origin && git reset --hard origin/main`); old local refs,
  tags and stashes that still name removed objects must be deleted too.
  Treat any other fork/clone of the old lineage as still containing the
  removed data.
