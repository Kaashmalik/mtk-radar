# Implementation Roadmap — 2026-10-25

**Status:** ACTIVE. This is the single execution plan for closing the gap between
what the documentation claims and what the repository proves.

**Baseline:** `main` @ `0d3b043` (synced with `origin/main` on 2026-10-25).

**Audit basis:** full local audit on 2026-10-25 — `ruff check .` clean,
`pnpm typecheck` clean, extension syntax clean, extension Node tests 25/25,
Python suite **964 passed, 3 skipped, 1 failed**. Docker/Postgres was
unavailable, so all database integration tests were skipped. CI on `0d3b043`
did not run: GitHub reports the owner account is locked for billing.

**Current local state (2026-10-25, working tree):** **975 passed / 3 skipped /
0 failed**; extension 29/29; `ruff`, `pnpm typecheck`, dashboard production
build, doc-link, filename and gitleaks checks clean. Postgres integration,
Playwright and CI execution remain `UNPROVEN`.

**Companions:**
[master plan](master%20plan.md) (product intent),
[automation master plan](automation-master-plan-2026-10-21.md) (automation design),
[EP implementation log](ep-implementation-log.md) (evidence ledger),
[traceability](master-plan-traceability.md) (feature-to-code map).
Proposal documents remain proposals; this roadmap does not turn them into shipped scope.

---

## 1. Goal

Every claim in an active document must be one of:

1. **true and proven** by a named command/artifact, or
2. **explicitly labelled** `PLANNED`, `PARTIAL`, or `UNPROVEN` with the missing proof.

The second goal is to close the real implementation gaps found by the audit, in
an order that keeps the system shippable at every step. This is a remediation
and completion plan, not a rewrite and not a feature expansion beyond what the
documents already promise.

### Non-goals

- No new SaaS becomes a source of truth (see `tool-stack-alignment-2026-10-23.md`).
- No silent scope expansion into EP-05–EP-07 while EP-00–EP-04 evidence is incomplete.
- No mass deletion of history. Superseded documents are archived, not rewritten.

---

## 2. Status vocabulary (binding)

Use these words in every status table and commit message. Do not use ✅ for
anything below `VERIFIED`.

| Status | Meaning | Required evidence |
|---|---|---|
| `VERIFIED` | Behaviour exists and was executed successfully in the stated environment | command + date + commit + environment |
| `IMPLEMENTED_UNVERIFIED` | Code exists, unit-tested, but the end-to-end/database path was not executed | unit test name + missing environment |
| `PARTIAL` | Some acceptance criteria are met; list the unmet ones | per-criterion note |
| `PLANNED` | Agreed work, not built | plan reference |
| `REJECTED` | Deliberately not doing it | reason |
| `STALE` | A previously true statement is no longer true | replacement fact |

**Rules**

1. A test count is valid only with date, commit, platform and command.
2. "Complete" means every acceptance criterion in this roadmap is `VERIFIED`;
   otherwise use `PARTIAL` plus the open IDs.
3. A document that describes future work must open with `Status: PROPOSED`.
4. A claim removed from code must be removed from docs in the same change.
5. Every fixed defect gets a regression test, or a written reason why a test is impossible.

---

## 3. Baseline evidence (2026-10-25)

| Check | Result | Notes |
|---|---|---|
| `git rev-parse HEAD` | `0d3b0432d8fcd234bd9ada3d28b47b5a7df60b1d` | equals `origin/main` |
| `ruff check .` | pass | |
| `pnpm typecheck` | pass | dashboard + offer schema |
| `node --check apps/extension/*.js` | pass | |
| `node --test apps/extension/tests` | 25/25 pass | only `core.js`; `background.js`/`options.js` untested |
| `python -m pytest -q` | 964 pass, 3 skip, 1 fail | failure: `test_check_filenames.py::test_detects_bad_name_in_a_temp_tree` |
| Postgres integration suite | not run | Docker daemon unavailable; `MTK_TEST_DATABASE_URL` unset |
| Dashboard Playwright | not run | requires full stack |
| CI `0d3b043` | not started | GitHub: account locked due to billing issue |
| Live publishing | not run | provider keys required |

### Current local result (after M0 + first M1 batch)

| Check | Result | Notes |
|---|---|---|
| `.\\.venv\\Scripts\\python.exe -m pytest -q` | **975 passed, 3 skipped, 0 failed** | Windows, 2026-10-25; +11 vs baseline |
| `node --test apps/extension/tests/core.test.js` | **29/29 pass** | was 25; settings/probe + context-privacy regressions |
| `ruff check .` | pass | via `.venv` |
| `python scripts/check_doc_links.py` | pass | 48 files |
| `python scripts/check_filenames.py` | pass | Windows-portable |

**Known false/stale claims:** recorded in the 2026-10-25 audit and folded into
the gap register below. The audit is the source for every `DOC-*` item.

---

## 4. Operating principles

1. **Truth before features.** Fix a false claim before adding a feature that
   makes the docs longer.
2. **One source of truth per topic.** Operational facts live in the runbook or
   checklist, not duplicated in three files. Historical detail lives in `archive/`.
3. **Fail closed.** Unknown publish state, missing proof, missing token and
   unreachable budget service must deny or hold, never assume success.
4. **Test at the lowest layer that can fail**, then prove the integration path
   once. A mock is not a live proof.
5. **Small reversible changes.** One work package per commit; no drive-by refactors.
6. **No secrets in fixtures, logs, screenshots or errors.** Pattern names only.
7. **Docs are code.** Every status line carries a date and a commit; link checks
   run in CI.
8. **Archive, do not fork.** Superseded documents move to `docs/archive/` with a
   banner and a pointer to the replacement.
9. **Definition of done:** code + tests + docs + verification command + ledger entry.
10. **No status by assertion.** If it was not run, say `UNPROVEN`.

---

## 5. Milestones

| Milestone | Outcome | Exit criteria |
|---|---|---|
| **M0 — Truth & stabilization** | No active doc contains a known false/stale claim; the suite is green on Windows and Linux | All `DOC-*` closed; `CODE-01`, `CODE-02`, `CODE-05` closed; suite 0 failed |
| **M1 — Correctness defects** | Publish/selection behaviour matches the documented safety rules | `CODE-03`, `CODE-04`, `CODE-06`–`CODE-14` implemented with regression tests; DB execution is `M2` |
| **M2 — Runtime proof** | Every "green integration" claim has a reproducible run | `PROOF-01`–`PROOF-05` recorded with date/commit/command |
| **M3 — Claim decisions** | Each remaining claim is either implemented or relabelled | `CLAIM-01`–`CLAIM-04` closed |
| **M4 — Documentation consolidation** | Active docs are canonical; history is archived; links pass | `DOC-15`, `DOC-16` closed; link check green |
| **M5 — Release verification** | One dated release-evidence report | Full suite, integration, E2E, CI and doc audit all green or explicitly waived |

M0 is intentionally first. It removes the misleading surface before more code
is added on top of it.

---

## 6. Gap register

Severity: **P0** blocks trust/release; **P1** user-visible or safety-relevant;
**P2** maintenance/accuracy.

### 6.1 Documentation truth (`DOC-*`)

| ID | Sev | Gap | Acceptance |
|---|---|---|---|
| DOC-01 | P0 | `README.md` says "edit in-app", marks every phase ✅, and its "Remaining" list omits WP10/EP-05–07/CI block | Roadmap links this plan; "edit in-app" becomes "export for external editing / edit copy in Studio"; remaining list names WP10, EP-05–07, CI billing, unproven live publishing |
| DOC-02 | P0 | `production-queue.md` documents the retired G15 formula | Replace with 40/30/30 evidence score, 14-day freshness and `last_growth_at` cooling; cite `queue_api.py` |
| DOC-03 | P0 | `go-live-checklist.md` says v0.29.0 and migrations 001→023 | v0.30.0; migrations 001→040; env knobs actually present in `.env.example` |
| DOC-04 | P0 | `runbook.md` says no off-host backup and describes the extension as v0.17 | Match `infra/backup.sh`; describe EP-04 extension and the loaded-browser E2E gap; fix token-revocation timing (≤60 s) and monitor log text |
| DOC-05 | P0 | `security-and-redaction.md` and `implementation-best-practices.md` claim gitleaks, commitlint, mypy, env schema | Either implement (see CLAIM-01) or remove; no mixed state |
| DOC-06 | P1 | `third-party-notices.md` / `open-source-integrations.md` have stale pins, wrong NOTICE path, wrong FFmpeg integration, false moto claim | Every pin matches requirements/lock/compose; remove moto; correct FFmpeg and path |
| DOC-07 | P1 | `notifications.md` says `/attention` is always full and omits `attention.*` events | State the 50-per-kind cap (or implement paging, CODE-08); list `attention.*` |
| DOC-08 | P1 | `master-plan-traceability.md` / `system-review` have stale counts, wrong paths, stale lease note, fake commit | Correct counts/paths; mark the review historical; no invented commits |
| DOC-09 | P0 | `youtube-playbook-2026-10-23.md` marks non-existent editing/audio/QC features "Generated" | Relabel beat cuts, J-cut, music mix, welcome-back guard, capture loudness QC and channel-name tags as `PLANNED`/`OPERATOR` |
| DOC-10 | P1 | `first-offer-recipe.md` says capture records 1280×720 | 1920×1080; same correction in the tool-stack doc |
| DOC-11 | P1 | `tool-stack-alignment-2026-10-23.md` reads as implemented and describes non-existent intake/zoom/reconciliation | Add `Status: PROPOSED`; correct present-tense capability statements; keep decisions as proposals |
| DOC-12 | P1 | `ep-implementation-log.md` overstates hashtag order, worker parity, "591 integration green" (TikTok confirmation now fixed) | Correct to the actual code and mark unrun integration `UNPROVEN` |
| DOC-13 | P2 | Enhancement/traceability test counts are wrong (580/461, 12 vs 14) | Use dated, reproducible counts or `UNPROVEN` |
| DOC-14 | P2 | `coding-model-handoff` and `system-review` cite obsolete test totals | Archive (DOC-15) or update to this plan |
| DOC-15 | P1 | 16 WP01 slice docs plus two dated audits clutter the active docs | Move to `docs/archive/` with banner and link rewrite; keep one active ledger |
| DOC-16 | P2 | No docs index; links are not checked automatically | Add `docs/README.md`; add a link-check command to `scripts/verify.sh` or CI |

**Status:** DOC-01–DOC-16 were applied in the 2026-10-25 truth pass.
`docs/README.md` is the active index, `docs/archive/` holds the superseded
history, and `scripts/check_doc_links.py` resolves all 48 markdown files.

### 6.2 Code and test defects (`CODE-*`)

| ID | Sev | Gap | Acceptance |
|---|---|---|---|
| CODE-01 | P0 | Extension save wipes a masked token (`options.js:91`) | Saving without retyping keeps the stored token; regression test covers masked and changed token |
| CODE-02 | P0 | TikTok returns `confirmed: True` on `PUBLISH_COMPLETE` with no public post id (`tiktok.py:240-241`) | Confirmation requires a public post id; otherwise `confirmed: False` + hold; tests for both |
| CODE-03 | P1 | Gate-off hashtags are alphabetical and can drop trend tags (`hashtags.py:214-224`) | Source-priority order preserved; cap never drops a higher-priority tag; test asserts order |
| CODE-04 | P1 | `renewal.regularPrice` leaks into research scripts (`scriptgen.py:445-450`) | Research/explainer paths suppress renewal price unless the claim type allows it; EN + UR tests |
| CODE-05 | P0 | Filename guard test cannot run on Windows (`test_check_filenames.py:53-57`) | End-to-end test works on Windows and Linux without creating an invalid file |
| CODE-06 | P2 | Granted-origin revocation is session-local (`options.js:18`) | Store the granted origin in `chrome.storage.local`; revoke on change across reloads |
| CODE-07 | P2 | `?saved_item=` deep link is ignored by the dashboard | Dashboard selects/highlights the item, or the extension stops emitting the parameter |
| CODE-08 | P2 | `/attention` silently truncates at 50 per kind | Response exposes `truncated`/totals and the UI shows it, or pagination is added |
| CODE-09 | P2 | Dashboard source form hardcodes 9 kinds and omits reddit | Form derives kinds from the API/registry; test covers every registered kind |
| CODE-10 | P2 | G18 daily cap counts only `automation:%`; superseded brief claims stop blocking | Count all non-human automation actors; define and test superseded-brief behaviour |
| CODE-11 | P3 | Compose env matrix re-checks only 7 of 22 vars | Every matrix var is asserted against its reader, or the test states the subset |
| CODE-12 | P1 | Page-context URL is uploaded raw and can leak webmail/chat URLs | Apply denylist/tracking rules to context URLs or omit them when restricted; test |
| CODE-13 | P2 | `with_context` contract test does not assert context persistence | Assert `context_type`/`context_url`, or rename the test |
| CODE-14 | P2 | WP-A evidence lacks retrieval timestamp/raw-payload hash | Add fields and assertions, or mark the claim `PLANNED` |

### 6.3 Claim decisions (`CLAIM-*`)

| ID | Sev | Claim | Decision required |
|---|---|---|---|
| CLAIM-01 | P1 | gitleaks in pre-commit/CI, commitlint, mypy, env schema | Implement or remove; recommended: gitleaks CI job + pre-commit config; drop commitlint unless adopted; add mypy config or remove the claim; add settings validation or remove |
| CLAIM-02 | P2 | OBS external-capture intake; Perkstack/Find AI Credits Tier-C | Implement intake + seed, or mark `PLANNED` and keep the decision table |
| CLAIM-03 | P1 | YouTube beat cuts, J-cut, music mix, brand tag, capture loudness QC | Implement or relabel as `PLANNED`/`OPERATOR` in the playbook |
| CLAIM-04 | P1 | "Each connector passes private/test posting" | Run one private/test post per provider and record it, or label `UNPROVEN (needs keys)` |

Decisions for all four are recorded in [§6.6](#66-claim-decisions-2026-10-25).

### 6.4 Runtime proof (`PROOF-*`)
| ID | Sev | Proof needed | Command / environment |
|---|---|---|---|
| PROOF-01 | P0 | Postgres integration suite and migration runner | `MTK_TEST_DATABASE_URL=... python -m pytest services/api/tests/test_integration.py -q` against Postgres 16 |
| PROOF-02 | P1 | Full `pnpm verify` including Playwright | Docker stack + `pnpm verify` |
| PROOF-03 | P1 | Loaded-extension Chromium E2E | unpacked extension against local API |
| PROOF-04 | P0 | CI actually executes | unblock billing, push a no-op commit, record run URL |
| PROOF-05 | P1 | One private/test publish per provider | provider keys; record post id/privacy/URL |
| PROOF-06 | P1 | Render QC on a real output | ffprobe/QC report attached to the ledger |

---

### 6.5 Closed in this pass (2026-10-25)

| ID | Status | Evidence |
|---|---|---|
| CODE-01 | `IMPLEMENTED_UNVERIFIED` | `settingsPatch`/`probeToken` in `core.js`; options save omits a masked token; 29 Node tests; `node --check options.js`; loaded-browser E2E still unproven |
| CODE-02 | `IMPLEMENTED_UNVERIFIED` | TikTok confirmation now requires a public post id; `PUBLISH_COMPLETE` alone returns `confirmed: False` + hold; 8 TikTok/confirmation tests; live TikTok still unproven |
| CODE-05 | `VERIFIED` (Windows) | 5/5 filename tests, including the temp-git-tree case; Linux CI run still `PROOF-04` |
| DOC-15 | `VERIFIED` | 19 historical files moved under `docs/archive/`; banners added; links resolve |
| DOC-16 | `VERIFIED` | `docs/README.md`, `scripts/check_doc_links.py`, 3 checker tests, verify/CI wiring; 48 files checked |
| CODE-03 | `VERIFIED` (unit) | unmeasured hashtags keep source-priority order; new order/cap test; 15 hashtag tests |
| CODE-04 | `VERIFIED` (unit) | research tracks suppress `renewal.regularPrice` in EN + UR; offer track regression-tested |
| CODE-06 | `IMPLEMENTED_UNVERIFIED` | granted origin persisted in `chrome.storage.local` and retired on change/revoke; loaded-browser proof still pending |
| CODE-12 | `VERIFIED` (unit) | `pageContextUrl` omits private surfaces and strips query/hash; 29 Node tests |
| CODE-07 | `IMPLEMENTED_UNVERIFIED` | `GET /items/{item_id}` exact lookup; extension opens `/inbox?saved_item=<id>`; inbox highlights the row and the home page redirects old links; dashboard typecheck clean; new DB deep-link test written but not run |
| CODE-08 | `VERIFIED` (unit) | `/attention` exposes per-kind `returned`/`truncated` + top-level flags; UI discloses caps; `test_attention_summary.py` (2 tests); DB assertions still unrun |
| CODE-09 | `VERIFIED` | `GET /source-adapters` returns the whole Python registry with required/optional config and approval state; `SourceForm` renders kinds + config fields from it; registry API test passes |
| CODE-10 | `IMPLEMENTED_UNVERIFIED` | cap counts both `automation:%` and `system:%`; superseded contradicted claims are exposed as `superseded_conflicts` and never gate; integration tests written but not run |
| CODE-11 | `VERIFIED` | env-matrix reader map covers every matrix var and fails if a new var lacks a reader; TTS/Urdu and dynamic Instagram prefix reads handled |
| CODE-13 | `IMPLEMENTED_UNVERIFIED` | provenance now stores `context_type`/`context_url`; contract test asserts both observation provenance and `items.extra`; DB test not run |
| CODE-14 | `IMPLEMENTED_UNVERIFIED` | radar candidates store `signals.evidence` (`observation_id`, `retrieved_at`, `payload_hash`, `url`); scan evidence assertion written but not run |

`DOC-01`–`DOC-14` were corrected in the same pass; they remain listed above
until the final audit re-reads each file.

### 6.6 Claim decisions (2026-10-25)

| ID | Decision | Status | Evidence |
|---|---|---|---|
| CLAIM-01 | Implement gitleaks; explicitly drop commitlint and mypy; keep env-schema validation `PLANNED` | `PARTIAL` | `.gitleaks.toml`, `.pre-commit-config.yaml`, CI `secret-scan` job; local gitleaks run over 128 commits found no leaks; CI job unrun (billing); docs no longer claim commitlint/mypy |
| CLAIM-02 | OBS external-capture intake and Perkstack/Find AI Credits Tier-C sources remain proposals, not shipped | `PLANNED` | `tool-stack-alignment-2026-10-23.md` marks both “Proposed”/“not implemented”; no code or seed exists |
| CLAIM-03 | Beat cuts, J-cut/L-cut, music mix, brand tag and loudness QC stay editing-plan/operator work | `PLANNED` | `youtube-playbook-2026-10-23.md` labels each row `PLANNED`/`Operator`; renderer is a continuous pass |
| CLAIM-04 | “Every connector passes private/test posting” is not demonstrated | `UNPROVEN (needs keys)` | no provider keys in this environment; `PROOF-05` owns the dated per-provider evidence |

A decision is closed when the document no longer claims more than the code
does. `PLANNED` is an honest terminal state for a proposal; it is not a promise
of implementation in this roadmap.

## 7. Execution order

1. **M0.1** — Archive/clean docs (DOC-15), add `docs/README.md` (DOC-16).
2. **M0.2** — Documentation truth pass (DOC-01–DOC-14).
3. **M0.3** — CODE-01 (token wipe), CODE-02 (TikTok), CODE-05 (portable test).
4. **M0.4** — Run the full suite; commit only when 0 failed.
5. **M1** — CODE-03, CODE-04, CODE-06–CODE-14 in severity order.
6. **M2** — PROOF-01–PROOF-06; update the ledger with dated evidence.
7. **M3** — CLAIM-01–CLAIM-04 decisions.
8. **M4** — Link check, doc index, remove remaining duplication.
9. **M5** — Release-evidence report and final audit.

Do not start EP-05–EP-07 implementation until M0–M2 are closed. The evidence
ledger must be honest before the next feature layer is added.

---

## 8. Verification matrix

| What | Command | Proves |
|---|---|---|
| Python lint | `ruff check .` | style/static errors |
| Python suite | `python -m pytest -q` | units + non-DB tests |
| Integration | `MTK_TEST_DATABASE_URL=... python -m pytest services/api/tests/test_integration.py -q` | DB/atomicity/rank behaviour |
| Dashboard types | `pnpm typecheck` | TS contracts |
| Extension syntax | `node --check apps/extension/background.js` (and `options.js`) | parse-only |
| Extension logic | `node --test apps/extension/tests` | pure logic/outbox |
| Full verify | `pnpm verify` | lint + types + tests + build + Playwright |
| Filename guard | `python scripts/check_filenames.py` | Windows-portable paths |
| Docs links | `python scripts/check_doc_links.py` | no dead links |
| Secret scan | `gitleaks detect --source . --config .gitleaks.toml --redact` | no committed credentials (CI `secret-scan` job) |

Every ledger entry must name the command, date, commit and environment. A
skipped test is not evidence; write `UNPROVEN` instead.

---

## 9. Documentation governance

### Active vs archive

- `docs/` root contains only current operational, product and plan documents.
- `docs/archive/` contains historical checkpoints and superseded audits.
- Archived files keep a banner:
  `> **Historical.** Superseded by [implementation roadmap](...). Kept for audit trail.`
- Moving a file requires updating every link; the link check is the gate.

### Document header template

```markdown
**Status:** ACTIVE | PROPOSED | HISTORICAL
**Date:** YYYY-MM-DD
**Baseline:** <commit>
**Proof:** <command> — <result> on <date>
```

### One source of truth

| Topic | Canonical document |
|---|---|
| Product intent | `master plan.md` |
| Execution/status | this roadmap |
| Feature-to-code evidence | `master-plan-traceability.md` |
| EP evidence | `ep-implementation-log.md` |
| Operations | `runbook.md` |
| Go-live | `go-live-checklist.md` |
| Queue algorithm | `production-queue.md` + `queue_api.py` |
| Dependencies | `third-party-notices.md` |
| Doc history | `docs/archive/` |

Do not duplicate a formula or version number in more than one active doc; link
to the canonical source instead.

---

## 10. Risks and rollback

| Risk | Mitigation |
|---|---|
| Doc edits accidentally weaken safety rules | Review every `must`/`never` sentence; code remains authoritative |
| Archive move breaks links | Move with `git mv`-equivalent, rewrite links, run link check before commit |
| Code fix changes publish behaviour | Fail closed; add regression tests; never auto-retry a held publish |
| Integration proof unavailable | Leave `UNPROVEN`; do not mark green |
| User's uncommitted work is overwritten | Keep `README.md`, `opencode.json` and the untracked tool-stack doc intact; review diffs before commit |
| Scope creep | New work needs an ID in this register; no ID, no code |

Rollback is per work package: revert the commit, keep the ledger entry, and
restore the previous verified status.

---

## 11. Immediate task list

- [x] Archive WP01 slices + dated audits; add archive index (DOC-15)
- [x] Add `docs/README.md` and link check (DOC-16)
- [x] Correct README roadmap/status (DOC-01)
- [x] Correct queue/checklist/runbook/security docs (DOC-02–DOC-05)
- [x] Correct dependency/notification/traceability docs (DOC-06–DOC-08)
- [x] Correct playbook/recipe/tool-stack/EP log (DOC-09–DOC-12)
- [x] Fix extension token wipe (CODE-01)
- [x] Fix TikTok confirmation (CODE-02)
- [x] Fix portable filename test (CODE-05)
- [x] Fix hashtag source order (CODE-03)
- [x] Suppress renewal price on research tracks (CODE-04)
- [x] Persist the granted extension origin (CODE-06)
- [x] Sanitize page-context URLs (CODE-12)
- [x] Add exact saved-item deep link (CODE-07)
- [x] Expose attention truncation (CODE-08)
- [x] Derive source adapters from the registry (CODE-09)
- [x] Count `system:` promotions and expose superseded conflicts (CODE-10)
- [x] Cover every compose env-matrix reader (CODE-11)
- [x] Assert context persistence in the intake contract (CODE-13)
- [x] Record radar retrieval evidence (CODE-14)
- [x] Run full suite and record the dated result (975 pass / 3 skip / 0 fail)
- [x] Add gitleaks config, pre-commit hooks and CI secret job (CLAIM-01)
- [x] Record CLAIM-01–CLAIM-04 decisions without overclaiming (CLAIM-02–04 `PLANNED`/`UNPROVEN`)
- [ ] M2 runtime proof: Postgres integration, loaded-browser E2E, CI, live publish

---

## 12. Execution log (append-only)

| Date | Commit | Change | Evidence |
|---|---|---|---|
| 2026-10-25 | `0d3b043` | Audit completed; roadmap created | 964 pass / 3 skip / 1 fail; see §3 |
| 2026-10-25 | working tree | Docs archived, truth pass applied, link checker added | 48 files resolve; 19 files archived |
| 2026-10-25 | working tree | CODE-01/02/05 fixed; suite green | 970 pass / 3 skip / 0 fail; 28/28 Node tests; ruff clean |
| 2026-10-25 | working tree | CODE-03/04/06/12 fixed | 972 pass / 3 skip / 0 fail; 29/29 Node tests; ruff clean |
| 2026-10-25 | working tree | CODE-07–CODE-14 fixed/implemented | 975 pass / 3 skip / 0 fail; 29/29 Node tests; ruff + `pnpm typecheck` + doc links + filename guard clean; new DB tests unrun |
| 2026-10-25 | working tree | CLAIM decisions recorded; gitleaks + pre-commit + CI secret job added | gitleaks 8.24.2 full-history scan: 128 commits, no leaks; CI job configured but unrun (billing lock); commitlint/mypy claims removed |
| 2026-10-25 | working tree | Edit-tool CRLF drift normalized back to LF; verification re-run | `git diff --check` clean; 975 pass / 3 skip / 0 fail; 29/29 Node tests; ruff + typecheck + dashboard build + doc/filename guards clean; `pre-commit run --all-files` passed |
