# Security & Redaction Policy

Non-negotiable rules from the master plan (§3, §4, §11). Violations block release.

## Secrets & credentials

- No API keys, passwords, recovery codes, tokens, or personal account data in: recordings, transcripts, terminal history, downloadable projects, logs, or repo files.
- Secrets live only in a vault/env manager; `.env` is git-ignored, only `.env.example` is committed.
- Promo codes shown on camera must be public and verified as authorized for redistribution.
- Object storage (captures, renders) is served via short-lived signed URLs.

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

- Pinned versions; monthly security-advisory check; gitleaks in pre-commit and CI.
- Licenses recorded in `third-party-notices.md` before adoption.
