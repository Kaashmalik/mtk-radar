# Enhancement plan — full-project audit and two-month YouTube-first roadmap (22 October 2026)

**Plan date:** 22 October 2026 (UTC)

**Baseline commit:** `448dced` — *feat: add laptop-first automation and Needs You inbox (v0.30)*

**Status:** audit and recommendation, followed by implementation work. This is
still not a production-readiness certificate, and not a promise of views,
subscribers or revenue.

**Implementation status (22 October 2026, after the audit and the P1
completion pass, plus the follow-up hardening pass):** the plan is **not
completely implemented**. The earlier P0/P1 pass closed several code-scoped
findings (dashboard login gate, immutable revision/attempt media keys,
persisted resumable upload sessions, per-preset render-queue coverage,
authenticated byte-range playback, growth-score zero/unavailable handling, and
keyset cursors on the core list endpoints). This follow-up pass then closed
additional correctness and safety gaps:

- **Analytics provenance/degradation:** YouTube metric groups are requested
  separately; a provider-rejected group is recorded as unsupported instead of
  discarding the whole report. Metrics snapshots now store the report period,
  metric definition, degraded flag/detail, and whether 3-second retention is a
  nearest-bucket estimate. The dashboard labels estimates (`~X%*`) and partial
  data; aggregates preserve missing-vs-zero instead of forcing `0`.
- **Human-only controls:** `require=True` now rejects service, worker,
  extension **and** `automation:*` identities. Automation policy writes
  (including the generic `/settings/automation_policy` route), variant
  approval, experiment decisions, redaction/claim attestations, corrections
  and ToS reviews require a human reviewer credential.
- **Backlog draining:** `/trends/scan` now marks scored items processed, so the
  inbox tail is reachable instead of rescanning the same newest rows forever.
  `/items` and `/trends` gained keyset cursors; `/trends` keeps exact numeric
  cursor values (float round-tripping repeated a page). CORS exposes
  `X-Next-Cursor` to the browser.
- **Per-operation kill switch:** publishing re-reads policy before each post,
  retry and correction; the render sweep re-reads it before each render; and
  `POST /schedules/{id}/attempt` refuses upload authorization while automation
  is paused or in dry-run.
- **Pinned lookups:** render/publishing fetch a pinned render or capture by id
  (`GET /renders/{id}`, `GET /captures/{id}`) instead of scanning the first
  page of a filtered list. The render sweep follows `X-Next-Cursor` instead of
  seeing only the newest ten candidates. Autopilot dedupes per target
  (platform/account/language/variant), not merely per platform.

Verification on the audit machine: **851 backend tests passed** (integration
tests against a disposable PostgreSQL database with real migrations), Python
lint/compile, dashboard **typecheck and production build passed**. That is
code/test evidence only; it is not live-provider, restore or deployment proof.

Still **not implemented / not demonstrated** (do not read the checked-or-not
list in §9 as complete):

- **P0 dashboard workflows remain partial.** This pass added inbox **Promote**
  and **Dismiss** controls, and the review desk/offer page can now **verify**
  or **request re-verification with a recorded reason** instead of requiring a
  hand-called API. Still missing: inbox search/filters/pagination, per-conflict
  resolution, raw-snapshot inspection, studio script/metadata/caption/chapter
  editing and revision save, release-package preview, reschedule/cancel,
  connection tests, notification tests, storage/backup status, and several
  "Needs You" actions (render failure, correction, expiry, token reconnect,
  worker restart). Several pages still render an outage as an empty pipeline
  or zero metrics instead of "unavailable".
- **Release gating is still three divergent checks** (API schedule validation,
  offer freshness helper, publishing worker). This pass made the worker **fail
  closed on a NULL `recheck_at`** (it previously published), but upload
  authorization still does not itself re-check offer freshness, and there is no
  separate public-release endpoint.
- **Format/claim binding stops at generation.** Render registration and
  scheduling do not re-read the script format or the capture's
  `claim_outcome`; the wording guard is English/`official_explainer` only.
- **Mandatory YouTube package policy is not a hard release gate.** Thumbnail,
  caption, playlist and comments handling exist, but the set that blocks a
  release is not fully enforced at scheduling/upload.
- **Editorial/scene-timeline QC and a final human playback-review gate are not
  implemented.** Authenticated playback exists; a recorded human sign-off on
  the final export does not. `-shortest` is gone, but that is not the same as
  scene-timeline sign-off.
- **No durable PostgreSQL-backed job/outbox.** Orchestration remains polling +
  row state. Render registration is not idempotent, upload `lease_expires_at`
  is written but not enforced, sweep-lock release is not holder-scoped, and
  collector cadence is in memory. Render **failures now stop retrying after
  three attempts per script revision/preset** and remain in the dead letter for
  a human, but there is no terminal queue state or automatic recovery. A restart
  loses in-flight render work.
- **Cursor coverage is still partial.** `/render-dead-letter`,
  `/offers/audit/verified`, `/attention`, analytics truncations, `/sources` and
  `/platform-accounts` are not fully paginated. CI's explicit test discovery
  still needs a guard against missing directories.
- **Live-provider and operational proof** remains outstanding: credentials,
  accounts, domain/TLS, S3/R2, real YouTube upload/metrics, image deployment on
  a private network, and database/media restore in a separate environment.

The system remains a **strong prototype in active hardening**, not
production-ready or fully autonomous.

**Scope:** dashboard, API, collectors, verification, capture, render, publishing,
metrics, automation policy, deployment, CI and the existing master plan. The
target is a **YouTube-first** system that becomes fully functional within two
months, then expands.

---

## 1. Summary

Keep the existing project and strengthen it. Do not rebuild it.

The repository already contains a substantial, well-reasoned foundation. The
remaining problem is not missing architecture; it is that several operator
workflows are incomplete, some release gates are advisory rather than blocking,
and the measurement layer can report misleading numbers. Those gaps are what
prevent calling the dashboard "fully functional" today.

Recommended goal for the period:

> **Discover → verify → prepare → review → publish → measure → improve, driven end
> to end from the dashboard, with YouTube as the only public platform.**

Finish that loop before expanding automation to four platforms or adding more
dashboard surface area.

**Priority order:** security → complete dashboard workflows → reliable jobs and
assets → editorial/media quality → YouTube publishing → trustworthy measurement →
guarded automation.

---

## 2. What was checked, and what was proven

Reviewed on 22 October 2026 at commit `448dced`: dashboard routes and interactive
islands, API routers, collectors, verification/extraction, capture, render and QC,
publishing adapters, metrics worker, automation policy and preflight, deployment
configuration, CI workflows and the automation master plan.

| Check performed | Result |
| --- | --- |
| Python test suites (object storage, source adapters, heartbeat, API, verification, render, capture, publishing, metrics, batch, monitor, scripts) | **688 passed, 1 skipped** |
| TypeScript checks (`packages/offer-schema`, `apps/dashboard`) | **Passed** |
| Dashboard production build (`next build`, Turbopack) | **Passed** |
| Python syntax/undefined-name lint (`ruff --select E9,F63,F7,F82,F821`) | **Passed** |
| Working tree after review | **Clean** |

**Not validated — do not assume these work because tests pass:**

- PostgreSQL integration tests (the suite skips itself without
  `MTK_TEST_DATABASE_URL`; no disposable database was available for this run).
- Authenticated browser workflows (the Playwright smoke test only asserts shell,
  navigation and health).
- Real FFmpeg render output and real media QC measurements.
- Backup restore drills.
- Live YouTube/Facebook/Instagram/TikTok uploads and metrics pulls.
- Docker, Bash, FFmpeg and ffprobe were not available on PATH in the review
  environment.

No `.env` was read, no secrets were printed, and nothing was published.

---

## 3. Foundations worth preserving

These are real capabilities and should not be redesigned:

- Snapshot-bound evidence with official-domain checks and signed fetch
  provenance.
- Egress policy, robots.txt permission records and DNS-rebinding-resistant
  pinning.
- Server-enforced state machine and audit log for offer transitions.
- Human redaction-review gate before any render can use captured footage.
- Native 1920×1080 capture, deterministic FFmpeg presets and measured render QC.
- Pinned render bytes, metadata hash, cover, captions and account at schedule
  time.
- Atomic upload-attempt claims and holds on ambiguous remote outcomes.
- YouTube processing/visibility confirmation before marking a post published.
- Automation policy with presets, guardrails, kill switch and a preflight check.
- Worker heartbeats, alert delivery and the read-only "Needs You" inbox.

---

## 4. Findings, prioritised

`P0` = must be fixed before public deployment or unattended autopilot.
`P1` = required during the two-month build.

| Priority | Finding | Recommended enhancement |
| --- | --- | --- |
| **P0** | **No application-level login gate on the dashboard.** Server-rendered pages attach the shared backend service token through `apps/dashboard/src/lib/api.ts`. Protecting API writes does not protect dashboard reads, so anyone who can reach the Next.js host can read the console. | Put the whole console behind authenticated sessions or an access gateway. Prefer secure HTTP-only cookies over long-lived browser `localStorage` tokens. |
| **P0** | **Workers can supply a human reviewer name.** `services/api/api_hardening.py` accepts a caller-supplied identity as a service-token fallback, so a worker could appear as a human approver in the audit trail. | Separate human, administrator, worker and extension credential classes. Workers must not be able to impersonate an approval or change automation policy. |
| **P0** | **Key dashboard workflows are missing.** Backend endpoints exist for evidence attachment, per-source permission review and redaction approval, but the operator cannot complete those tasks from the UI. A blocked item in "Needs You" can therefore have no resolvable action. | Complete evidence inspection, source-permission review, conflict resolution and redaction approval before adding new decorative pages. |
| **P0** | **Schedule validation records a false result instead of refusing.** `services/api/schedules_api.py` (`_revalidate_offer` / transition path) stores `offer_evidence_ok = false` rather than rejecting the transition. A non-blocking gate is not a gate. | One authoritative release check used at scheduling, resume, upload authorization and public release. Fail closed with an actionable operator reason. |
| **P0** | **Scripts can assert an outcome that was never demonstrated.** `services/api/scriptgen.py` produces "I claimed…" hooks without a structured requirement that a successful claim was captured and verified. That is an honesty and platform-policy risk, not only a quality issue. | Introduce explicit formats — **official-document explainer**, **tested tutorial**, **real claim walkthrough** — each with its own evidence, capture and wording requirements. |
| **P1** | **Media locations are overwritten across revisions.** `packages/object_storage/__init__.py` and the render worker reuse stable keys. Hash checks detect replacement, but the previously approved package becomes unavailable. | Content-addressed or revision-scoped keys. Preserve every approved package for audit and restore. |
| **P1** | **Resumable upload recovery is incomplete.** The YouTube session URI exists only inside the upload call, so a restart cannot resume or reconcile. | Persist session URI and byte progress securely; reconcile an interrupted upload before starting another. Do not assume `X-Request-Id` guarantees deduplication. |
| **P1** | **Technical QC is not editorial QC.** `-shortest` can truncate footage or narration, and expected-duration logic accepts the shorter stream; long caption chunks can extend past the measured speech. | Validate against an approved scene timeline rather than the shortest stream. Require speech/action alignment plus a final human playback review. |
| **P1** | **Growth analytics can mislead (reproduced).** Zero values are excluded from the score's weighting, and seconds and retention percentages share one normalisation path. | Preserve zero versus unavailable, separate formats and units, and remove unsupported composite recommendations. |
| **P1** | **Production deployment still resembles development.** Compose runs the dashboard dev server, worker images install dependencies at start, and database/cache ports are published to the host. | Immutable production images, private networking, dedicated writable media/cache volumes, readiness probes and a tested restore. |
| **P1** | **Backlogs can be skipped.** Fixed list limits are applied before completed items are removed, and one successful preset can suppress a still-missing preset. | Cursor pagination plus durable jobs keyed by script revision, language, preset and target account. |

### Two additional concerns

**YouTube package completeness.** Thumbnail, caption, playlist and comment
failures can be recorded while the upload still reports success. Decide which
assets are *mandatory* for release; "video uploaded" must not mean "package
complete".

**CI coverage drift.** `.github/workflows/ci.yml`, `package.json` and
`scripts/verify.sh` run different test sets. Newer source-adapter, capture,
heartbeat and backup-script suites are missing from the CI unit-test command.
Unify discovery so a new test cannot be silently excluded.

### Reproduced analytics defect

`services/api/growth_engine.py` scored the same video differently depending only
on whether engagement was exactly zero:

| Input | Score |
| --- | --- |
| 10,000 views, 0 likes, 0 comments | **100.0** |
| 10,000 views, 80 likes, 0 comments | **65.4** |

Zero engagement is being treated as missing information, which rewards the worst
possible outcome. This must be fixed before any growth recommendation is shown
to an operator, and the composite score must not drive decisions on its own.

---

## 5. What "fully functional dashboard" must mean

A functional dashboard lets the operator **complete work**, not merely observe
that work is blocked.

| Area | Required capabilities |
| --- | --- |
| **Overview** | Today's priorities, upcoming releases, failures, overdue reviews, last successful worker activity, and a clear next action for each item. |
| **Radar / inbox** | Search, filters, pagination, deduplication, shortlist/dismiss, and promote to a tracked offer or explainer. Label heuristic scores as heuristics. |
| **Verification desk** | Attach official sources, inspect snapshots and quotes, resolve conflicts, edit typed claims, review source permissions, and verify/reject with a recorded reason. |
| **Studio** | Edit the selected spoken script, title, description, thumbnail, captions and chapters; save a revision and invalidate affected approvals. |
| **Media review** | Authenticated video playback, seeking, caption preview, secret findings and explicit redaction approve/reject. Basic trim/caption/redaction edits are enough for v1. |
| **Publishing / calendar** | Preview the exact release package, confirm channel and visibility, schedule/reschedule, pause/cancel, inspect upload progress and reconcile held uploads. |
| **Growth** | Date ranges, Shorts versus long-form, metric freshness, "unavailable" labels, retention reports, experiment records and links to the platform's own studio. |
| **Settings / operations** | Connection tests, verified channel identity, permission status, automation limits, notification test, storage health and backup status. |

Across every page:

- Distinguish **empty**, **loading**, **unauthorized** and **service unavailable**.
- Never render "0 items" when the request failed.
- Consistent validation, keyboard accessibility, mobile layout and timezone
  handling.
- Every "Needs You" item resolves through a real workflow, not a dead link.
- Browser tests that perform actions, not only assert headings.

**Acceptance test:** a fresh operator can register a source and take one video
through the entire workflow without calling an API endpoint by hand. Human
recording and studio-only platform actions may remain explicit handoffs.

---

## 6. Two-month implementation plan

**Window:** 22 October – 22 December 2026. Realistic for a tightly scoped
YouTube-first release with one to two experienced developers plus editorial
involvement. With a single developer, defer the timeline editor and all
other-platform expansion.

| Week | Engineering focus | Exit requirement |
| --- | --- | --- |
| **1 — Security and baseline** | Console authentication, scoped credentials, human/service separation, unified CI, disposable PostgreSQL run, YouTube channel/permission check. | Anonymous access blocked; a worker cannot approve as a human; the full DB suite runs in CI. |
| **2 — Complete verification UX** | Inbox promotion, evidence inspection, source-permission review, conflict resolution, verified transitions, actionable errors. | One lead becomes a properly verified offer entirely through the dashboard. |
| **3 — Reliable orchestration** | Durable jobs, pagination, per-variant tracking, bounded retries, immutable asset keys, restart recovery. | Restarting workers loses no queued work; a missing landscape or portrait variant is independently recoverable. |
| **4 — High-quality production** | Spoken-only scripts, format-specific wording, narration/action timing, caption fixes, dependable thumbnails, authenticated playback and redaction review. | Three representative videos pass technical checks and human editorial review. |
| **5 — YouTube publishing completion** | Persisted resumable sessions, processing reconciliation, mandatory package assets, channel verification, permission failures, final upload authorization. | A real private upload survives interruption without duplication; assets and visibility are confirmed. |
| **6 — Useful analytics and growth tools** | Validated report queries, explicit metric definitions, reporting periods, format separation, experiment workflow, compliant data retention. | Supported measurements reconcile with the platform's own studio for matching periods. |
| **7 — Guarded automation pilot** | Shadow decisions, restricted automation, exception handling, approval expiry, daily limits, tested stop behaviour. | A seven-day pilot shows unsafe or uncertain work stops rather than bypassing a gate. |
| **8 — Production hardening** | Production images, networking, monitoring, backup/restore drill, authenticated browser tests, concurrency and failure tests. | Release checklist passes with recorded evidence. |
| **Buffer** | Fix pilot defects, usability polish, finalise runbooks. | Stable YouTube-first release — no new scope. |

### Architecture guidance

Retain **Next.js + FastAPI + PostgreSQL + object storage**. Start with a durable
PostgreSQL-backed job queue/outbox rather than adding several orchestration
products. Keep capture and rendering on hardware that is actually capable; use an
always-on host for scheduling, monitoring and publishing if laptop sleep would
interrupt a release.

**Defer:** four-platform parity, multi-tenant SaaS, a full professional video
editor, broad social scraping and unlimited public autopilot.

---

## 7. YouTube growth plan

### A. Position around trust and usefulness

Recommended promise:

> **"Verified AI and developer opportunities, demonstrated clearly — with
> eligibility, costs and limitations explained."**

Do not become a channel of interchangeable AI-narrated offer slides. YouTube's
[channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en)
explicitly cover repetitive and mass-produced content under the "inauthentic
content" policy. Automation should remove repetitive production work, not remove
original testing, judgement and explanation.

### B. Three focused content pillars

| Pillar | Starting allocation | Examples |
| --- | ---: | --- |
| **Evergreen practical tutorials** | **60%** | Setup guides, real workflows, billing limits, common mistakes, troubleshooting. |
| **Verified timely opportunities** | **30%** | New offers, material pricing changes, relevant releases, approaching deadlines. |
| **Experiments and comparisons** | **10%** | Reproducible tests with disclosed methodology and limitations. |

Choose one primary audience and one spoken language first. Do not double
production by publishing near-identical English and Urdu versions until demand
supports it.

For each topic, answer: who needs this, what useful result will they get, can we
demonstrate or substantiate it, will it still be useful when published, and what
original value do we add?

The radar's "demand" and "competition gap" scores are keyword and internal-backlog
heuristics. They are not measured YouTube demand or competitor research — label
them honestly in the UI.

### C. Sustainable cadence

| Period | Target |
| --- | --- |
| Weeks 1–2 | Channel identity, playlists, topic backlog, several private production samples. |
| Weeks 3–4 | ~1 long-form video + 2 Shorts per week. |
| Weeks 5–8 | ~2 long-form videos + 3 Shorts per week, only if quality and operations stay stable. |
| Period total | **8–12 substantial videos** and **~18–24 Shorts**, adjusted to capacity. |

These are output targets, not promises of subscribers, views or revenue. Shorts
must be genuinely useful standalone pieces that lead into a deeper tutorial — not
an unreadable vertical crop of a desktop recording.

### D. Packaging and viewer experience

For every release:

- Show the useful result or evidence early.
- Remove generic introductions and repeated hooks.
- Use a specific, truthful title and a readable thumbnail.
- State significant eligibility and billing restrictions before the viewer acts.
- Demonstrate important steps clearly; explain failures and alternatives.
- Provide accurate captions and real chapters for suitable long-form content.
- Point to one relevant next video or playlist.
- Keep official links and correction information accessible.
- Disclose affiliate relationships and synthetic content where applicable.

Hashtag volume is not a growth strategy. Topic choice, thumbnail clarity and
viewer satisfaction are.

### E. Weekly learning loop

Review each video at roughly **48 hours, 7 days and 28 days**, allowing for
reporting delays.

- **Long-form:** supported impressions/CTR, watch time, average view duration and
  percentage, retention curve, traffic sources, subscribers.
- **Shorts:** engaged views and Shorts-specific audience behaviour where
  available.
- **Operations:** production time, failures, correction rate, operator effort.
- **Business:** first-party site visits and conversions with appropriate consent.

Compare videos at similar ages and within the same format. A newly published
Short must not be compared with a month-old tutorial.

For packaging experiments use
[YouTube Studio's native title/thumbnail testing](https://support.google.com/youtube/answer/16391400?hl=en)
where eligible. It excludes Shorts and can take up to two weeks. Record
inconclusive results honestly; "seven days or 500 views" is not statistical
proof.

### F. Analytics corrections (required)

1. **Fix the zero-engagement bug** in `services/api/growth_engine.py` and add a
   regression test for the table in §4.
2. **Compliance review.** [YouTube's Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
   restrict replacing API data with independently calculated metrics and restrict
   derived metrics/data retention without explicit approval. Disable the
   YouTube-derived composite growth score until that review is complete;
   relabelling it "our score" is not sufficient.
3. **Validate report queries** against the
   [metrics reference](https://developers.google.com/youtube/analytics/metrics).
   Not every metric visible in the studio is available through the same API
   query, and unsupported combinations fail whole reports.
4. **Do not fall back silently.** Split unsupported report groups so available
   metrics are still stored.
5. **Preserve provenance:** reporting period, retrieval time, metric definition
   and freshness.
6. **Never present a nearest-bucket retention estimate as an exact percentage.**

---

## 8. Safe automation boundaries

### Automate

- Permitted source collection.
- Deduplication and preliminary prioritisation.
- Snapshot acquisition and extraction proposals.
- Draft scripts and packaging.
- Rendering and technical checks.
- Publication of an explicitly authorised package.
- Metrics collection, freshness monitoring and alerting.

### Keep human-controlled initially

- Provider/source ownership approval.
- Ambiguous or conflicting claims.
- Account creation, payments, identity checks and applications.
- Sensitive capture and redaction approval.
- Final editorial approval during the pilot.
- Unknown remote upload outcomes that cannot be reconciled safely.

Roll out in this order: **assisted → shadow automation → private automation →
restricted public automation.** The kill switch must be checked before each new
irreversible operation, not only once at the start of a long publishing sweep.

---

## 9. Release requirements at the end of two months

Call the system functional only when all of these are demonstrated and recorded.
Automated tests now cover the security boundary, blocking release checks,
revision-scoped media keys, resumable-session persistence, package-hold
metadata checks, growth-score units and compliance default, core-list keyset
cursors, per-preset render coverage, bounded render retries, and media range
parsing. Unchecked items below still require live
services, operator evidence or product decisions; do not replace that evidence
with a passing unit test.

- [ ] A complete dashboard-driven production workflow works end to end.
- [ ] Unauthorised visitors and workers cannot reach human-only capabilities.
- [ ] Freshness, evidence, rights, redaction and approval checks **block**
      invalid releases rather than annotating them.
- [ ] Approved media remains available after later revisions.
- [ ] Interrupted uploads resume or reconcile without blind duplication.
- [ ] Mandatory thumbnail/caption/package operations succeed or visibly block
      release.
- [ ] Analytics distinguish zero, missing, delayed and unsupported data.
- [ ] Worker failure, storage failure, token expiry and stop behaviour are tested.
- [ ] Database **and media** restoration succeeds in a separate environment.
- [ ] A monitored pilot provides real operational evidence.

Until then, describe the system as a strong prototype in active hardening — not
as production-ready or fully autonomous.

---

## 10. Related documents

- [Automation master plan (21 October 2026)](automation-master-plan-2026-10-21.md) —
  historical audit, WP01 safety slices and the longer schedule.
- [Go-live checklist](go-live-checklist.md) — secrets, accounts and operator
  checkpoints.
- [Cost, laptop production and VPS fallback (22 October 2026)](cost-laptop-vps-2026-10-22.md)
  — hosting and spend constraints.
- [Render QC](render-qc.md) — measured export checks.
- [Security and redaction](security-and-redaction.md) — capture and secret rules.
- [Runbook](runbook.md) — operating procedures.
