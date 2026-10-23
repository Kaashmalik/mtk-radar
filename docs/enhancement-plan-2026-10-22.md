# Enhancement plan — full-project audit and two-month YouTube-first roadmap (22 October 2026)

**Plan date:** 22 October 2026 (UTC)

**Baseline commit:** `448dced` — *feat: add laptop-first automation and Needs You inbox (v0.30)*

**Status:** audit and recommendation, followed by implementation work. This is
still not a production-readiness certificate, and not a promise of views,
subscribers or revenue.

**Implementation status (22 October 2026, after the audit, the P1 completion
pass, the hardening pass, the release-integrity pass, and the day-3
operator-workflow pass):** the plan is **not completely implemented**. The
earlier P0/P1 pass closed several code-scoped findings (dashboard login gate,
immutable revision/attempt media keys, persisted resumable upload sessions,
per-preset render-queue coverage, authenticated byte-range playback,
growth-score zero/unavailable handling, and keyset cursors on the core list
endpoints). The day-3 pass then closed the last three code-scoped dashboard
workflow gaps:

- **Per-conflict resolution.** `POST /offers/{id}/conflicts/resolve`
  (human-only via `require=True`) resolves open extraction conflicts one at a
  time — keep the recorded claim (dismissal) or replace it with a corrected
  value that still cites an immutable snapshot on the offer. Unreferenced
  conflicts stay open; clearing the last conflict clears the stale conflict
  correction note. The dashboard renders each conflict as a structured card
  (field, disagreeing values, replacement value + evidence id, per-conflict
  note) instead of a raw JSON dump.
- **Raw-snapshot inspection.** `GET /offers/{id}/evidence/{eid}/snapshot`
  serves the exact `captured_content` and (decode-on-read) `raw_content` a
  claim cites — the only read path for the hash-checked write-only snapshot
  text, served truncated at 200,000 chars with explicit flags. The offer
  page's "Snapshot & provenance" block gained an on-demand text inspector.
- **Studio editing with revision saves.** `POST /studio/scripts/{id}/revise`
  saves an operator-edited script as a NEW immutable version (append-only; the
  approved version keeps its hash so anything already rendered or scheduled
  stays pinned) and re-runs the wording guard on the edited text, so a hand
  edit cannot smuggle in first-person result wording. `POST
  /studio/offers/{id}/variants` adds operator-authored captions, chapters
  (payload `{"chapters": [{time, label}]}`) and YouTube title/description
  drafts (kind `metadata|captions|hook`), all wording-guarded, all drafts that
  still need explicit human approval. The studio page gained a per-script
  revise editor and a package editor; the variant explorer now lists captions
  and hook drafts with the same approve flow.
- **Outage states.** Home, inbox, review desk and calendar now distinguish
  "unavailable" (the API did not answer) from genuinely empty, and never
  render a missing growth score as `0.0/100` or an outage as "nothing
  scheduled".

The hardening pass had earlier closed:

- **Analytics provenance/degradation:** YouTube metric groups are requested
  separately; a provider-rejected group is recorded as unsupported instead of
  discarding the whole report. Metrics snapshots store the report period,
  metric definition, degraded flag/detail, and whether 3-second retention is a
  nearest-bucket estimate. The dashboard labels estimates and partial data;
  aggregates preserve missing-vs-zero instead of forcing `0`.
- **Human-only controls:** `require=True` rejects service, worker, extension
  **and** `automation:*` identities for policy writes, approvals, attestations,
  corrections and ToS reviews.
- **Backlog draining:** `/trends/scan` marks scored items processed, so the
  inbox tail is reachable; `/items` and `/trends` gained keyset cursors.
- **Per-operation kill switch:** publishing re-reads policy before each post,
  retry and correction; the render sweep re-reads it before each render.
- **Pinned lookups:** renders/captures are fetched by id instead of scanning
  the first page of a filtered list; the render sweep follows
  `X-Next-Cursor`.

The release-integrity pass then made the release gate real and
single-sourced:

- **One authoritative release check:** `services/api/release_gate.py` now owns
  "may this go out?". Upload authorization (`POST /schedules/{id}/attempt`),
  the publishing worker (which calls `GET /schedules/{id}/release-check` and
  **fails closed** if the gate is unreachable), and the dashboard preview all
  run the same structured check. The API's offer-freshness helper delegates to
  the same implementation, so there are no longer three divergent checks.
- **Mandatory package policy is a hard gate:** a new human-controlled
  `release_policy` setting (`require_package_assets`, `require_playback_review`,
  strict defaults) gates upload authorization on thumbnail + captions **file**
  + approved metadata for YouTube releases — missing data blocks, never annotates.
- **Final human playback sign-off:** `POST /renders/{id}/playback-review`
  (refuses automation credentials) records who watched the final export; the
  release gate refuses renders without an approved sign-off.
- **Format/claim binding at release:** render registration re-checks
  `assert_format_wording` (a hand-edited script cannot be rendered), and the
  release gate re-reads the pinned script format plus the bound capture's
  recorded `claim_outcome` — a `claim_walkthrough` requires an actual
  demonstration.
- **Render idempotency:** a partial unique index makes re-registering the same
  output for the same script revision return the existing render instead of
  cloning it.
- **Durable owed-work record:** new `jobs` table + `/jobs` API
  (dedupe-keyed enqueue, `SKIP LOCKED` claim/lease, results, dead-lettering,
  `/jobs/stuck`). Schedule creation records the owed publish work; expired
  leases and dead jobs surface in `/attention` (kind `job`) and are **never
  auto-reclaimed** — expired leases are a human decision, like held uploads.
- **Explicit cancellation:** human-only `POST /schedules/{id}/cancel` moves a
  post to a new terminal `cancelled` state with a recorded reason, instead of
  mislabelling it `failed`.
- **Cursor coverage:** `/render-dead-letter`, `/sources`,
  `/platform-accounts`, and `/offers/audit/verified` are now keyset-paginated;
  `/items` gained a `q` search parameter. Attention counts remain global over
  all rows (items are truncated per kind by design).
- **CI guard for test discovery:** `scripts/tests/test_pytest_discovery.py`
  fails any runner where a tests directory exists but is missing from
  pytest.ini `testpaths` (or a listed path has no tests).
- **Dashboard:** full inbox page with search, process-filter tabs and cursor
  pagination; a release-readiness card on the offer page (same gate, same
  problem list, plus cancel); per-render playback sign-off controls; a
  connection metadata-test button on Connections; and a release-policy card in
  Settings.

Verification on this machine (day-3 pass): **903 backend tests passed**
(integration tests against a disposable PostgreSQL database with real
migrations, including four new tests for conflict resolution, snapshot
inspection, script revision and operator variants), Python lint/compile clean,
dashboard typecheck and production build passed. That is code/test evidence
only; it is not live-provider, restore or deployment proof.

Still **not implemented / not demonstrated** (do not read the checked-or-not
list in §9 as complete):

- **All three recurring workers are now job-queue-driven (day-2 pass).** The
  publishing worker claims `publish_schedule` jobs (`/jobs/claim`, SKIP LOCKED
  + lease + reported result) before its classic sweep, INSIDE the sweep lock,
  so one worker can never double-attempt a post. Schedule creation sets
  `run_after` to the publish time; retries (auto-retry transition) and human
  resume **re-arm** the job with a fresh attempt budget; migration 029
  backfills owed publish jobs and is idempotent. **Collectors:** source
  creation enqueues a recurring `collect` job (`collect:{id}`, max_attempts 5);
  `POST /sources/{id}/poll-result` re-arms it — healthy poll → pending at the
  source cadence with a fresh attempt budget, failed poll → retry in 300 s
  keeping attempts, so 5 consecutive failures dead-letter the job into
  operator attention; migration 030 backfills enabled sources (idempotent).
  The collector claims due `collect` jobs through the SAME `_poll` path as the
  sweep; a disabled/removed source resolves its job as done. **Render:** the
  worker mirrors the derived `/render-candidates` list into durable
  `render_package` jobs (dedupe keyed to the exact script version hash, so a
  rewritten script is a NEW job) and drains them via the same per-candidate
  code path as the sweep; the derived candidate list stays authoritative — a
  candidate reappears after a restart by recomputation, so lost work is
  impossible even without the queue, and stale jobs resolve as
  "no longer a render candidate". Every drain degrades fail-open (queue
  unreachable / older API ⇒ sweep-only; the sweep remains the authoritative
  fallback) while safety stays fail-closed at the gate/attempt layers.
  Knobs: `MTK_PUBLISH_JOB_QUEUE=0`, `MTK_COLLECT_JOB_QUEUE=0`,
  `MTK_RENDER_JOB_QUEUE=0`. Integration tests pin the publish lifecycle,
  re-arm, dead-letter and 029/030 backfill semantics; they caught and fixed a
  real 500 in `POST /jobs/{id}/result` (int into a text-concat interval).
  `POST /jobs/{id}/retry` (v0.33) revives a dead/failed job for the operator —
  409 on pending/leased/done/cancelled, 404 unknown.
- **Dashboard workflows (day-2 pass closed several):** this pass added inbox
  search/filter/pagination, the release-readiness card, playback sign-off,
  cancel, connection tests, the release-policy card, AND NOW a reschedule
  control on the calendar (future-time validated, calls
  `POST /schedules/{id}/reschedule`, human-token only), a notification
  delivery-test card in Settings (honest "not configured" state),
  a one-click dead-job retry on the attention page (`POST /jobs/{id}/retry`),
  and a media-backup status card from the `media_backup` setting. The day-3
  pass then added structured per-conflict resolution, raw-snapshot inspection,
  and studio script/caption/chapter/metadata editing with revision save, plus
  outage-aware empty states on the main pipeline pages.
- **The wording guard now covers every format and language (day-2 pass).**
  `assert_format_wording` blocks first-person result wording for
  `official_explainer` in English, Urdu script AND Roman-Urdu
  transliteration, and blocks unproven outcome wording ("claim approved" /
  "کلیم منظور" / "claim approve ho gaya" / "paisay mil gaye"…) for
  `tested_tutorial` in all three too; `claim_walkthrough` legitimately uses
  first person (the demonstrated-capture binding is its gate, checked at
  render registration and in the release gate), so wording there stays
  allowed by design. Render registration re-checks the guard against the
  actual stored script.
- **Attention truncation is by design but bounded:** counts are global;
  per-kind item lists cap at 50 rows.
- **Security/observability hardening added (day-2 pass):** per-IP sliding
  window over auth failures (429 + Retry-After after 15 failures/60s,
  bounded memory, honors `MTK_TRUST_PROXY` for X-Forwarded-For); Prometheus
  text-format `GET /metrics` (request counters by route template, jobs by
  status/kind, schedules/offers by state, render totals, auth-failure IPs —
  under the same bearer gate as every route); dashboard security headers via
  `next.config.ts` (X-Frame-Options DENY, CSP `frame-ancestors 'none';
  base-uri 'self'`, nosniff, Referrer-Policy, Permissions-Policy, HSTS in
  production). A full `script-src` CSP remains future work (Next inline
  hydration scripts need nonce/hash plumbing first).
- **Live-provider and operational proof** remains outstanding: credentials,
  accounts, domain/TLS, S3/R2, real YouTube upload/metrics, image deployment
  on a private network, and database/media restore in a separate environment.
  These cannot be proven from the audit machine; they need an operator with
  real infrastructure.

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
