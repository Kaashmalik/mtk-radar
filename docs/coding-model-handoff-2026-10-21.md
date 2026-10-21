# Coding-model handoff — MTK RADAR AI

**Date:** 21 October 2026 (UTC)

**For:** GLM, MiniMax, other local models, or any coding assistant.

**Authoritative roadmap:** [Automation Master Plan 2026–2027](automation-master-plan-2026-10-21.md).

## 1. What this repository actually is

Existing monorepo, version `0.25.0` at audit time: Next.js/React/TypeScript dashboard, FastAPI/Python API and workers, PostgreSQL, S3-compatible storage, FFmpeg video pipeline. Extend existing modules and tests. **Do not rebuild the project, replace it with a demo, or install a second stack.**

Current code includes discovery, evidence/extraction, scripts, human-operated capture, simple rendering, scheduling, four publishing adapters, metrics and monitoring. It is not yet proven premium native-Full-HD, all-source trend radar or fully unattended production. Existing completion claims are not acceptance evidence.

Audit results: 239 Python tests passed, one database integration module skipped, TypeScript typecheck and narrow Python lint passed. Real database, browser, media and platform release verification still need proof. Do not copy these counts as your own new test results.

**Implementation update:** the first WP01 integrity slice is implemented; its latest local result is 325 passing tests including isolated PostgreSQL integration. Read [the checkpoint](implementation-wp01-2026-10-21.md) and the master-plan ledger before choosing a task. The preceding counts are the original audit baseline, not the current test total.

## 2. Copy/paste prompt for one implementation session

```text
Work in the existing MTK RADAR repository.

Read docs/coding-model-handoff-2026-10-21.md and the requested work package
in docs/automation-master-plan-2026-10-21.md.

Task: implement ONLY [WPxx, specific unchecked subtask].
Acceptance case: [one precise input -> expected result].
Allowed scope: [specific modules/tests/migration if authorized].

First inspect git status, applicable repository instructions, current relevant
code and tests. Preserve all changes you did not make. State the current
behavior and smallest change. Add a failing regression test, implement the
minimal fix, then run targeted tests. Use official current documentation
for external API contracts. Do not invent APIs or assume mocks prove live
behavior.

Do not read real .env/secrets, claim offers, purchase services, publish posts,
apply live migrations, reset databases, upgrade unrelated dependencies,
rewrite architecture, remove tests or disable safety gates.

If blocked, report BLOCKED with the exact missing input; do not fabricate
results. Update only the relevant master-plan ledger entry with dated proof.
Finish with files changed, tests actually run/results, remaining risks and
the next smallest task. Stop after the agreed slice.
```

Fill the brackets before execution. If the model has a small context window, provide the relevant work-package section and current files/tests—not the entire old master plan. Never omit the no-publish/no-secret/no-bypass rules from a compressed prompt.

## 3. Recommended first task

**Next WP01 slice:** type-specific semantic completeness, critical unknowns and applicability. The first snapshot-binding/server-derived core-completeness slice is already implemented; do not rebuild it.

Read:

- `services/api/schemas.py::ExtractionIn`
- `services/api/offers_api.py::add_extraction`, `_gate_verified`, `transition`
- `services/api/tests/test_integration.py` (destructive disposable DB warning)
- `workers/verification/extractors.py` and its tests

Next slice: agree the offer-type terms contract and add fixtures where literal price/eligibility words occur but do not establish a claimable benefit (negation, renewal price, excluded country, ambiguous deadline). Missing critical facts must remain unknown and block automatic verification. Retained extraction text is implemented; original HTTP/HTML bytes and trusted fetch provenance remain separate work. Do not mark full WP01 complete from one slice.

## 4. Non-negotiable acceptance rules

1. Discovery popularity is not evidence. Official identity, applicability, exact stored snapshot and quote support are required for factual verification.
2. Unknown eligibility/cost/expiry stays unknown; never market it as universal, free or forever.
3. Local model output is untrusted input. Strict schema plus semantic validators; bounded retries; no direct shell/SQL/publish credentials.
4. A complete-looking JSON object is not a verified offer; the server derives verification and checks unresolved conflicts.
5. Keep Python, TypeScript, SQL state enums and API contracts consistent. Inspect the latest migration number before adding one; never rewrite applied migrations.
6. Native Full HD is not 720p upscaled to a 1080p container. Actual media must be decoded/probed/previewed and pass measured QC.
7. Approvals pin immutable complete packages, including media bytes, metadata, evidence, account, revisions and policy—not just script text.
8. No upload without an atomic owned durable attempt/lease; unknown remote outcome means reconcile/hold, not blind retry.
9. Worker/service identity cannot pretend to be a human reviewer. Autopilot approvals are separate, explicitly scoped and operator-authorized.
10. Platform policies win. TikTok private internal uploader is not an assumed eligible Direct Post use; use compliant export/handoff when blocked.
11. Optional manual edits are revisions, not overwrites; invalidate approval and handle in-flight upload honestly.
12. Failed tests, unavailable tools, missing account consent, model incompatibility and broken links must be visible—not silently skipped and called “100% working.”

## 5. Test guidance

Existing PowerShell-safe, non-live checks:

```powershell
# Run from repository root. Clearing this variable prevents the integration
# module from touching any accidentally inherited database URL.
$env:MTK_TEST_DATABASE_URL = ''
& '.\.venv\Scripts\python.exe' -m pytest packages/object_storage/tests services/api/tests workers/verification/tests workers/render/tests workers/publishing/tests workers/metrics/tests workers/batch/tests workers/monitor/tests -q
pnpm typecheck
& '.\.venv\Scripts\python.exe' -m ruff check --select E9,F63,F7,F82,F821 services workers packages
```

Use a smaller relevant test suite during iteration. Preserve the separate skipped/integration status in reports. Do not print secrets from shell environment, auth headers, browser state or `.env`.

`pnpm verify` currently calls Bash, expects Docker and starts a disposable Postgres. Docker/Bash/FFmpeg/ffprobe were not on audit PATH. A proposed `scripts/verify.ps1` and new model-evaluation commands **do not exist until WP03/WP07 implements them**. Never report running a planned command.

**Important:** integration tests explicitly drop/recreate `public` schema. Only run against a newly created disposable test database, after confirming its identity. Never reuse a production/development database URL. Do not run migrations remotely without explicit authorization.

For media tasks: include actual FFmpeg/ffprobe versions, source/output measurements, artifact locations, full decode result and human-readable sample/QC findings. For platform tasks: unit mocks are necessary but do not replace an approved live test with confirmed remote processing/visibility.

## 6. Required completion report

```text
Date/time UTC:
Task/subtask ID:
Status: TODO | IN_PROGRESS | BLOCKED | IMPLEMENTED_UNVERIFIED | VERIFIED

Behavior before:
Behavior after:
Files changed:
Tests actually executed (command, exit status, pass/fail/skip):
Artifacts / evidence:
External services touched: none, unless specifically authorized
Safety / migration / compatibility impact:
Unresolved issues and unavailable checks:
Next smallest task:
```

`VERIFIED` applies only to the defined acceptance scope, not the entire roadmap. Do not mark a work package complete while any mandatory subtask remains unchecked. Append proof to the master-plan ledger; do not delete earlier blockers to make the report look better.

## 7. Stop conditions

Stop and request a decision when the task needs real credentials, a paid API, app review, unapproved scraping, unsafe code execution, a destructive migration, unsupported model artifact/runtime, contradictory official terms or a material architecture change. Return a precise blocker and safe alternative. Do not invent new requirements, use placeholder successes or hide exceptions to satisfy a “fully automated” request.
