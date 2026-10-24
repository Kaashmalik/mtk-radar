# MTK Radar: Evidence-to-Video Automation and Robustness Plan

**Date:** 24 October 2026 · **Audited baseline:** `75ddff3` on `main`

**Status:** PROPOSED — implementation checklist, not a completion certificate.

**Delivery scope:** repository documentation/contributions only. No deployment,
account connection, paid subscription, production migration, or public post is
authorized by this plan. The user explicitly does not want a full local setup.

This is a follow-up to [the earlier 24 October plan](enhancement-plan-2026-10-24-trends-automation.md),
not a duplicate implementation of WP-A–WP-H. Those features now have substantial
code, but their existence does not prove their end-to-end promises. Preserve the
working foundation and fix the integration gaps below first.

## Executive decision

Build **an evidence-first production assistant, not an unattended content farm**:

> Allowed sources → measurable topic observations → ranked research briefs →
> cited scripts and real demonstrations → edited long/short video packages →
> human review → one-click schedule → confirmed publication → measured learning.

The highest-value work is NOT another dashboard or a larger model. It is:

1. Close unsafe privacy, credential-scope, budget, and publishing-status gaps.
2. Repair the collection-to-score data contract: actual engagement observations
   must survive ingestion, deduplication, and rescanning.
3. Add a research-content track rather than forcing every paper/tool into a
   promotion/discount schema.
4. Automate safe public-page/demo recording and scene editing, while keeping
   account actions, redaction, rights, and final playback under human control.
5. Finish the existing scheduling UI with explicit per-platform accounts,
   correctly sized exports, capability checks, and one final confirmation.
6. Finish the browser extension as a scoped, reliable research intake tool.

**Start YouTube-first.** Expand to Facebook/Instagram only after capability and
privacy tests. TikTok Direct Post is not a dependable promise for this
single-project/internal-use application: its current guidelines explicitly
exclude utilities limited to uploading to accounts the developer/team manages
[S08]. Provide a compliant manual-export path rather than promising approval.

"Fully automated" means mechanical work is automatic and exceptions are visible.
It must not mean fabricated screenshots, bypassed platform consent, unsupervised
payment/account actions, or hiding uncertainty. No plan can guarantee hot topics,
views, revenue, or perpetual free hosting.

## Audit scope and verification limits

Reviewed the current README and prior plans; API authentication, ingestion,
source schemas, trend scoring/scanning, production queue, scheduling/release
gates, hashtag engine, cost store/client, capture/render/narration/QC, publishing
adapters and confirmation paths, Compose wiring, dashboard queue/calendar, and
**all four browser-extension files**. References below are relative to this
baseline; line numbers will move after implementation.

### Checks actually performed before the user clarified repository-only scope

| Check | Observed result | What it does NOT prove |
|---|---|---|
| `pnpm typecheck` | Passed | Runtime workflows or API permissions |
| Python suite using existing `.venv` | **886 passed, 3 skipped, 1 failed** | Full database integration or live publication |
| Python failure | `workers/publishing/tests/test_rate_limits.py:93`: `NamedTemporaryFile` is reopened while still held open on Windows, causing `PermissionError` before the mocked 429 | Not evidence of a real Facebook upload failure |
| Focused Ruff check (`E9,F63,F7,F82,F821`) | Passed | Whole-code style/security certification |
| Extension background/options syntax | Passed | Loaded MV3 worker, permissions, offline recovery, or browser UX |
| Small in-memory Python probes | Reproduced budget fail-open, rejection of five new adapter kinds, bytes-cache serialization error, and API cache-hit exception | Not a deployed-stack test |
| Latest remote CI for baseline | Run `40077225919`: Python/Node failed with zero steps; annotation: **account locked due to a billing issue** | Not a code regression result |
| Container/integration availability | Docker command unavailable; full integration/browser checks were not run | No production readiness assertion |

The integration module explicitly skips without `MTK_TEST_DATABASE_URL` and
**wipes the configured schema** when enabled (`services/api/tests/test_integration.py:9–35`).
Future contributors must use a disposable CI database, never a real project DB.
After the user's clarification, no further local runtime setup is part of this
task. No dependencies were installed for this audit.

Web research used primary platform docs, current documentation lookup, and live
discovery pages. This is broad relevant research, **not a claim to have searched
every website**. A feed's popularity signal is not verification of a paper's
results. Sources and access limitations are listed at the end.

## Current system and gap register

### Preserve these implemented foundations

| Area | Present in code | Preserve/extend |
|---|---|---|
| Intake | RSS, page watch, releases, HF papers, HN, GitHub stars, Reddit JSON, Google Trends RSS | Repair contracts and permissions, not another crawler |
| Review | Evidence snapshots, extraction/conflict review, fact packs, source attestation | Add research-specific claim types |
| Ranking | Transparent trend score, observations, promote-to-queue endpoint | Replace heuristic "velocity" with measured series |
| Production queue | Ranked rows, pins, archive/expiry, dashboard actions | Add complete production briefs and accurate readiness |
| Video | Human capture, deterministic scripts, FFmpeg, captions, TTS hook, measured QC, playback review | Add a scene/edit pipeline and safe capture automation |
| Scheduling | Batch creation, batch transitions, pinned render/account/package, calendar | Finish per-target preview, accounts, slots, and click flow |
| Reliability | Durable jobs, leases/touch, locks, retry/dead-letter, upload attempts, YouTube resumable sessions | Strengthen cross-platform reconciliation and ownership |
| Costs | Usage ledger, budget endpoint, caches, provider probe, Costs card | Make money controls truly fail-closed and atomic |
| Extension | MV3 action/context menu, selected-text collection, options, API submission | Harden credentials, permissions, durability, and tests |

### Prioritized findings

**Evidence labels:** R = reproduced by a small no-network probe; C = directly
observed code path; P = official-policy/design limitation needing implementation
review. Severity is priority for this proposed automation, not a claim that an
incident has happened.

| ID | Priority / evidence | Gap and source location | Required outcome |
|---|---|---|---|
| G01 | P0 / C+P | `workers/publishing/platforms/instagram.py:62–75,122–139` accepts `privacy`, but always calls `media_publish` without a private/draft operation. Its docstring falsely promises a private draft. | Reject unsupported privacy before any publishing side effect; preview-only must never call `media_publish`. [S06] |
| G02 | P0 / C | `workers/publishing/main.py:1069–1086` synthesizes `confirmed=True` for adapters without `confirm_publication`. TikTok has `publish_status` but is not reconciled by this branch. | An accepted upload ID is not confirmed publication. Persist remote/container IDs and reconcile status/visibility on every supported platform. |
| G03 | P0 / R | `packages/costing.py:112–132`: cost API failure returns `True`, despite "FAIL-CLOSED" wording. Missing `allowed` also defaults true. | Paid work requires explicit permission; unavailable/invalid budget response falls back to rules or queues work. |
| G04 | P0 / C | `services/api/costs_store.py:249–299` reads spend then allows; no reservation/transaction protects concurrent callers. Extraction asks for permission without predicted tokens or output limit (`extractors.py:317–337`); usage emits only after usable responses. | Reserve conservative per-attempt cost atomically; settle actuals; account for paid failures and retry attempts. Unknown usage cannot mean free. |
| G05 | P0 / C | Extension instructions request the shared API token (`apps/extension/options.html:17–26`). Middleware classifies an extension token but does not restrict routes (`api_hardening.py:315–348`). Non-human-only routes, e.g. `/media/gc`, lack a reviewer gate. | Dedicated revocable intake-only credentials; global deny-by-default role/route matrix. Extension cannot read private media, claim jobs, poison caches, or delete artifacts. |
| G06 | P1 / R | `schemas.py:14,60–65` only permits five old adapter kinds; all five newly implemented trend adapters fail `SourceIn` validation. Seed SQL bypasses this schema. | One authoritative adapter registry used by API, collector, dashboard, seeds, and tests. New sources must be manageable through the UI/API. |
| G07 | P1 / C | `workers/collectors/main.py:147–155` drops every `RawItem.extra`; `main.py:373–390` stores neither excerpt nor selection nor handle, though they affect the hash. `trends_api.py:164–175` cannot score this lost body. | Persist bounded excerpt/context and typed raw observations with retrieval time, source ID, canonical entity, payload hash, and policy provenance. |
| G08 | P1 / C | HF/HN/Reddit IDs are stable, so later engagement counts conflict and disappear; stars survive as title changes, not a structured series. `trends_api.py:233–245` computes velocity from internal score changes, including freshness, not observed engagement. | Story dedup and append-only measurements are separate. Raw count deltas with timestamps drive momentum; missing data remains unknown. |
| G09 | P1 / C | Corroboration groups by `duplicate_group`, set to canonical URL (`main.py:370`; `trends_api.py:217–230`), not the same story across URLs. | Entity/version clustering plus independent-source ownership; syndication does not create independent confirmation. |
| G10 | P1 / R | Google Trends returns RSS bytes into `JsonCache.set_json`, which calls `json.dumps` (`google_trends.py:50–61`; `trendcache.py:106–108`). Normal collector wiring supplies this cache. | Cache text or a typed serialized envelope; live and cached parses must be identical. |
| G11 | P1 / R | `costs_store.cache_get`: Redis/PG hits call `_mem_put(key,value)` at lines 348/357, but the function requires `ttl_s` at line 361. | Cache hits cannot 500. Preserve original expiry; test every cache layer and outage path. |
| G12 | P1 / C | `CostClient` uses `API_URL`/`MTK_API_TOKEN`, not the `--api`/`MTK_API_URL`/`MTK_WORKER_TOKEN` conventions of callers (`packages/costing.py:31,76–87`). | Inject the existing authenticated API client or standardize config; test worker-only credentials and container addresses. |
| G13 | P1 / C | Compose does not pass new `VERIFY_LLM_*`, `TTS_*`, `COST_*` settings to their relevant services; collectors lack `REDIS_URL`; publishing lacks Instagram settings (`infra/docker/docker-compose.yml`). | Validate a documented configuration matrix automatically. A value in `.env.example` must not imply a container receives it. |
| G14 | P1 / C | `github_stars.py:28,50–55` accepts a GitHub token but never sends it. | Use scoped authentication and conditional requests; honor primary/secondary rate limits. [S12] |
| G15 | P1 / C | Queue evidence rank = `25 × COUNT(evidence)` regardless of freshness, distinctness, supporting fields or contradictions (`queue_api.py:40–47`). | Rank by supported required claims and independent/current evidence, not snapshot volume; safety remains a hard eligibility gate. |
| G16 | P1 / C | Queue expiry requires the latest cooling observation to be older than seven days (`queue_api.py:275–289`); regular rescans keep that timestamp fresh. | Track `cooling_since`/last meaningful growth independently from last observation; fixture seven days of continuous cooling. |
| G17 | P1 / C | `queue_api.py:get_queue_row` references `t.freshness_score` through `_RANK_SQL` without grouping that column or the joined trend primary key. List query explicitly groups it. | Verify/fix with real Postgres; do not treat unit mocks as SQL proof. |
| G18 | P1 / C | Promotion creates `offer_type='trend_topic'`, but extraction/script templates remain largely offer-centric. Renderer still exits without capture (`render/main.py:304–310`); capture requires terminal `input()` (`capture/main.py:117–135`). | Research/explainer/tutorial tracks with explicit evidence requirements; automated safe assets for explainers, not removal of capture checks. |
| G19 | P1 / C | Schedule UI sends one selected primary account ID and render ID as shared batch values (`ScheduleForm.tsx:122–164`), although API supports `per_platform`. All four targets remain selectable regardless of capability. | Per-platform account/render/privacy/time preview; only connected/tested/authorized targets enabled. |
| G20 | P1 / C | Batch creation only creates drafts; calendar review excludes drafts (`BatchApprove.tsx:29–32`) and approval/queue are separate transitions. | One explicit "Approve exact packages & schedule" action after review, safely walking existing transitions with per-target results. |
| G21 | P1 / C+P | `best_times` blends views and likes/comments for all platforms without the growth-score switch (`schedules_api.py:774–832`); hashtag rollup also derives YouTube-related aggregates (`1648–1692`). | Audit derived-data permissions and gate all affected paths, not only growth_engine; use approved native metrics and labeled editorial heuristics. [S05] |
| G22 | P1 / C+P | Reddit adapter assumes anonymous public JSON is allowed because volume is low (`reddit_new.py:1–7`). | Off by default until approved access/use is documented; public visibility or robots compliance is not a license. [S10] |
| G23 | P1 / P+C | TikTok's internal-use restriction, required creator-info UI/consent, private-only unaudited restrictions, and server-media transfer rules conflict with a generic unattended cross-poster. Current adapter lacks that full UX. | Manual export/native scheduling by default; approved integration only when eligibility and exact schema tests are demonstrated. [S08–S09] |
| G24 | P2 / C | Hashtags are topic-derived strings, not observations of platform hashtag popularity; "3–5" and title/tag limits are editorial choices, but code labels some as platform law (`hashtags.py:39–60,258–285`). | Separate API rules, channel preferences, relevance, and measured platform-trend claims. Correct obsolete "past 15" YouTube wording; official limit warning is more than 60. [S03–S04] |
| G25 | P1 / C | Cache keys omit provider/base URL, prompt/schema version, evidence URL/language; extraction key truncates text to 8,000 chars. TTS cache holds worker-local paths (`costing.py:175–183`; `narration.py:119–150`). | Versioned, context-complete keys; rebind citations to the current evidence; immutable shared audio refs/hashes instead of local-path dependence. |
| G26 | P2 / C | Calendar conflicts are page-local and bucket only platform/local day (`schedules_api.py:745–771`), missing adjacent pages, midnight cases and distinct accounts. Queue outages become empty/partial lists silently (`queue/page.tsx:48–66`). | Account-aware UTC overlap queries; distinguish unavailable, partial and genuinely empty states. |
| G27 | P1 / C | Media GC pins rows rather than every shared artifact reference; failed/held schedules are excluded and deletion is not serialized with new pins (`media_api.py:233–348`). | Reference/hold-aware mark-and-sweep, grace period and a second pin check; protect evidence and uncertain uploads. Keep dry-run default. |
| G28 | P1 / C | Remote CI is blocked before execution; the repository contains two Windows-invalid `:` filenames. Older docs mix completed banners, stale "today" gaps, and unchecked tasks. | Restore the owner's Actions billing separately; maintain an evidence/status table and portable filenames. No forced reset/rename of others' work. |

### Browser extension: implemented, but not fully production-complete

The extension is a **save-page intake extension**, not a recorder or autonomous
research agent. Its small intended core exists. Calling it "fully implemented"
would overstate the current reliability/security/testing.

| Extension check | Current status | Detailed to-do |
|---|---|---|
| Toolbar save + service worker | Implemented (`background.js:16–28,42–69`) | Test loaded MV3 worker, restart, restricted tabs, missing tab IDs |
| Right-click a link | Incorrect target by code inspection: handler ignores `info.linkUrl` and saves `tab.url` (`25–26,57`) | Save clicked URL; keep page URL as context; selection uses `info.selectionText` when provided |
| Selection/context | Sent to API, not persisted in current item insert | Round-trip excerpt and context with limits and privacy consent |
| Host permissions | Grants `http://*/*` and `https://*/*` at install | Keep activeTab; request only configured API origin at runtime; revoke old origin after change [S15] |
| Credential | Shared bearer token in local storage; options tell user to paste service token | Pairing or dedicated ingest credential, expiry/revoke, masked display, trusted-context storage access; never platform OAuth secrets [S16] |
| API URL | Basic HTML URL field; no explicit scheme/origin restrictions | HTTPS except loopback dev; reject credentials/fragments and accidental endpoint paths; require deliberate approval on origin changes |
| Offline/retry | One fetch; no abort timeout, durable outbox or retry | IndexedDB/storage outbox with client idempotency key, bounded retry/TTL, MV3 alarm-driven recovery and user retry/delete |
| Result UX | Badge only; 401 hint; no duplicate distinction or result link | Saved / duplicate / queued / auth expired / permission denied / rejected / offline; reset stale error hint on success |
| Privacy | Selected text can include secrets or private data | Redact/token warning before upload, strip sensitive URL parameters without breaking canonical identity, domain denylist and explicit send preview |
| Testing/distribution | Syntax checks only in `verify.sh:133–137` | Unit tests with Chrome API stubs, extension-to-API contract tests, persistent-context Chromium E2E in CI, manual Chrome/Edge smoke; no Firefox claim without port/test |

Do not add screenshots/full-page crawling/background browsing by default. Those
would be new permissions and a new privacy scope, not fixes to save-page intake.

## Target operator experience

1. Configure editorial scope, source permissions, target accounts, daily spend
   caps, languages, and publish windows once. Default Assisted mode.
2. Open **Today's video slate**: ten explained candidates, at most three selected
   for research. Each shows **why now**, where popularity was observed, freshness,
   evidence coverage, recording feasibility, expected effort/cost and blockers.
3. Pick one or accept safe automatic shortlisting. System creates a research
   brief, claims ledger, script, storyboard, assets and rendered previews.
4. For public-page explainers the system captures approved pages automatically.
   For logged-in claims, purchases, identity verification or ambiguous rights,
   a precise human task appears rather than a fake completed video.
5. Review final playback/redaction and package previews together. Select exact
   accounts, privacy and slots. **One click schedules the reviewed ready set**;
   blocked targets explain why and cannot advance.
6. Worker uploads at the due time, confirms processing/visibility, and shows real
   permalinks. Unknown remote state is **held**, not blindly retried.
7. Daily digest contains only needed actions: permission expired, claim changed,
   budget reached, capture required, package/QC failed, or publish uncertainty.

### State model to extend, not a second competing scheduler

```text
Discovered → Clustered → Shortlisted → Researching → Evidence ready
  → Script/storyboard ready → Assets ready → Render/QC passed
  → Human playback/package review → Ready to schedule
  → Scheduled → Uploading → Processing → Confirmed

Any stage → Needs you / Held / Rejected / Expired / Corrected
```

Each transition records input hashes, policy version, actor, time and machine-
readable reason. New evidence/script/edit/metadata bytes invalidate only the
dependent approvals; schedules stay bound to the exact reviewed package.

## Evidence-backed research and topic selection

### Coverage strategy

Start within MTK Codex's existing AI/developer/student niche rather than "every
hot topic". Proposed adjustable mix: **50% timely useful AI/dev changes, 30%
evergreen tested workflows, 20% research explainers**. This is a proposal, not a
change to the existing channel mix. Financial/medical/legal claims and account-
abuse topics require specialist review or are excluded from autopilot.

| Feed group | Sources to watch | Cost/cadence proposal | Evidence treatment |
|---|---|---|---|
| Official releases | Provider changelogs; watched maintainer GitHub repos | Conditional fetch, every 4–6 h | First-party evidence for the actual release, not independent proof of performance |
| AI research | HF Papers + linked arXiv revisions, author repos/model cards | 6–24 h, bounded pages | Community interest is discovery; paper statements attributed to authors |
| Developer discussion | HN Algolia/Firebase and permitted community feeds | 30–60 min cache, capped keywords | Demand/questions only, not proof that a claim is true |
| Broad demand | Permitted Google Trends feed or approved alpha API, selected geos | 6 h; fail visibly if unavailable | Regional query interest, not TikTok/YouTube popularity |
| Owned-channel feedback | Native analytics/report metrics with proper authorization | Daily, known reporting delay | Keep metric provenance; custom scoring only where permission allows |
| Programs/perks | Official student, startup, cloud and tool-program terms | Daily or provider-appropriate | Eligibility, expiry, renewal and region must be checked before recording/posting |
| Restricted platforms | Reddit/TikTok/social search | Disabled until approved; manual links allowed under reviewed policy | Never bypass access controls or buy scraped data without rights review |

Source registry additions need retrieval method, ownership/official URL rules,
terms reference + expiry, rate policy, retention, geography, cost ceiling,
parser version and a source-health indicator. A homepage domain alone is not
proof that every repository/author/user on a shared host owns a product claim.

### Data and research contract

Extend existing structures with the following **logical records**; exact table
names/migration numbers are to be designed during implementation after checking
the latest schema. Do not invent migration 037 if another contributor used it.

- **Story identity:** entity/provider + product/version + event + original URL.
  Maintain an alias list, canonical URLs, and cluster confidence/merge history.
- **Signal observations:** source/story IDs, observed_at, published_at, count and
  count type, geo, source URL, payload hash, freshness/availability. Append even
  when the story itself already exists. No forged zeroes for missing samples.
- **Research brief:** viewer question, angle, target audience, content type,
  claim list, counterevidence, limitations, source references, cost/effort estimate.
- **Claim ledger:** claim text, claim class, exact supporting excerpt/snapshot,
  source owner/date, scope (hardware/dataset/version/region), contradicted/unknown
  state, expiry/recheck policy, permitted wording and asset/scene references.
- **Decision snapshot:** score inputs + weights/version + missingness + why
  selected/rejected. A slate is reproducible, not today's opaque model opinion.

For research distinguish **author-reported**, **independently reproduced**, and
**tested by MTK**. A preprint is not peer-review certification. "The authors
report X under Y conditions" is valid when sourced; "X is the best" is not
created from a popularity feed. Demos labeled as simulated cannot stand in for
real product results. The LLM extracts/drafts; it never serves as evidence.

### Selection algorithm proposal

Safety and permission are **hard filters before ranking**. Reject unsupported
high-risk claims, insufficient rights, expired benefits and infeasible captures.
For eligible stories, an initial non-YouTube editorial score can be:

```text
priority = 25% audience fit + 20% measured momentum + 20% claim coverage
         + 15% original/demo value + 10% freshness + 10% production feasibility
         - explicit duplication / uncertainty / production-cost penalties
```

These weights are an experiment, not a scientific virality prediction. Compute
momentum from observed changes per hour against the source's own baseline,
minimum sampling gap and count-reset rules. Avoid mixing absolute HN points
with GitHub stars; show percentile/source components. Treat coordinated copies
as one origin. No new YouTube-derived composite without explicit policy approval
[S05]; preserve the existing growth-score-off default and apply it to adjacent
features too.

Select a diversified top set: cap repeated providers, require a new angle before
revisiting a story, reserve evergreen slots, compare cost per publishable minute,
and keep the operator override/pin. Missing trend coverage is **"relevance-only"**,
not "hot". Do not generate a video every time a count changes.

### Research-to-video readiness gate

- Every material factual claim has a current, retrievable supporting reference.
- Conflicts and unknowns are resolved or explicitly expressed in script.
- Tool claims have official docs; benchmark comparisons disclose versions,
  hardware, dataset and whether independently tested.
- Real demo assets, safe recording recipe and rights are available, or the
  content is explicitly an attributed explainer with appropriate visuals.
- Estimated spend and runtime fit the remaining reservation budget.
- Deadline leaves enough time for production, review, processing and publication.

## Realistic video production and quality gates

**Meaning of realistic:** actual screen recordings, observed outputs, readable
evidence, natural narration and a coherent edit. Not synthetic humans claiming
to be the creator, invented success states, or expensive generated footage used
to imply real testing.

### Separate three production tracks

| Track | Automatic work | Human boundary |
|---|---|---|
| Official/research explainer | Capture allowed public pages, render original diagrams, source cards, quotes, captions, voiceover, citations | Check factual scope, visual rights and final export; no claim of hands-on testing |
| Tested tutorial | Isolated demo project, allowlisted commands, scrubbed fixtures, real output and reproducible measurements | Approve recipe/tool permissions; stop on unexpected side effects |
| Claim walkthrough | Prepare checklist, browser profile, safe overlays, recording checklist, edits | Human handles login, 2FA, eligibility, payment, claim and redaction; no autonomous signup/checkout |

### Scene/edit manifest

Extend the existing render project rather than introducing a second video stack.
Each scene should include: ID, purpose, claim IDs, narration, capture/asset ref +
hash, in/out time, crop/reframe, callout region, caption timing, source card,
rights entry and disclosure. Pin manifest version/hash with the script and media.

Suggested 5–8 minute structure: outcome/question hook → what changed → evidence
and limits → genuine demo or worked explanation → failure/cost/eligibility notes
→ concise recommendation and next step. Shorts are separately edited complete
ideas (roughly 30–90 seconds as an editorial target), not arbitrary crops of a
whole video. Actual platform duration capabilities must be validated live.

To-do:

- [ ] Public-page capture worker with explicit URL recipes, fixture accounts,
  timeouts, browser isolation, denied private-network egress and manual fallback.
- [ ] Optional browser-connected capture launcher for human sessions; never
  expose a remote-control endpoint on the public dashboard by default.
- [ ] Beat-level script/storyboard editor; bound quotes/citations to scenes.
- [ ] Speech/visual alignment per scene, pronunciation dictionary for names,
  silence removal and a real two-pass loudness normalization stage.
- [ ] Keyframe-driven vertical reframing, cursor/callout overlays and safe zones;
  preserve code legibility instead of blindly center-cropping.
- [ ] Derivative Shorts inherit citations and disclose omitted context; cutting
  out a condition/limitation must invalidate the clip's approval.
- [ ] Shared TTS audio assets, optional local-compatible provider for deployments
  that already have suitable hardware; natural recorded voice remains valid.
- [ ] No compulsory AI video/image service. Licensed original diagrams and
  screenshots are cheaper and more credible for this niche.

### QC is both technical and editorial

Keep existing decode/stream/black/freeze/silence/loudness QC and hash binding.
Add scene coverage, source-card legibility, actual font-aware caption widths,
caption speech alignment, missing narration, secret/PII scan in OCR and audio,
and asset rights checks. A keyword scan of a step log alone cannot certify that
a video frame contains no secrets. Automated scans assist, not replace, human
redaction review.

The rendered package must contain video, original captions, source list, cover,
metadata, rights/disclosure manifest, QC report, script/edit hashes and reviewer
sign-off. If TTS fails and capture has no useful audio, hold for audio repair;
do not label a silent/irrelevant-audio export production-ready.

Avoid mass-produced near-identical videos. YouTube's originality/inauthentic-
content policies concern substantive value, not merely whether AI was used
[S01–S02]. Apply synthetic-content disclosure based on the actual platform rule
and content, not an assumption that every use of AI is identical [S07].

## One-click scheduling and platform publishing

### One final action, after meaningful review

Reuse `/offers/{id}/schedules/batch`, `/schedules/batch-transition`, existing
idempotency keys, pinned packages and release checks. Add a **schedule preview
and commit contract**:

1. Preview resolves account capabilities, exact render aspect, captions/cover,
   language, title/description/hashtags, disclosures, privacy, UTC/local slot,
   freshness deadline and predicted quota per target.
2. Operator sees all material content and selects the ready targets. Unsupported
   modes cannot masquerade as private test posts.
3. One confirmation submits an idempotency key plus expected package/policy/
   evidence hashes. The server rejects stale previews and walks existing valid
   transitions under the authenticated reviewer. It does not impersonate one.
4. Return per-target created/scheduled/blocked status and actionable errors;
   retrying a partial result affects only unresolved targets. Never auto-expand
   to additional accounts or silently switch privacy.
5. Calendar uses account-aware capacity/spacing, user timezone and real UTC
   comparisons, with a configurable expiry buffer. No universal "best hour"
   claim from two unrelated posts.

### Platform delivery matrix

| Platform | Near-term choice | Required safeguards |
|---|---|---|
| YouTube | First fully supported automated delivery | Correct OAuth/account, resumable upload, package finalize, processing/privacy confirmation, quota buckets, rights/disclosure, public-post acceptance test |
| Facebook | Conditional second target | Confirm Page/account permissions and chosen upload product, unpublished vs published semantics, processing status, real permalink, token lifecycle contract tests |
| Instagram | Block unsafe "private test" semantics first | Professional-account/login-path capabilities; no fake per-post private mode; public-media or supported resumable upload; durable container ID; status+published ID reconciliation |
| TikTok | Export bundle + native/manual scheduling initially | Direct Post only if approved use case, current creator-info, explicit privacy/interaction choices and consent, music/commercial disclosures, allowed transfer mode and publish status; no invented approval claim |

YouTube's current official quota calculator lists **100 search calls/day and 100
upload calls/day in separate buckets**, plus 10,000 units/day for other endpoints;
each call in those two buckets costs one. This corrects stale quota assertions
in the earlier plan. Verify the actual project's console entitlement, reset zone
(Pacific time), endpoint costs and documentation revision at implementation [S11].
Keep a bucketed quota reservation ledger; invalid/retry requests are not free.

### Hashtags and metadata

- Keep deterministic, relevant topic/provider tags; make counts configurable
  editorial limits, distinct from hard provider/API limits.
- A **"trending hashtag"** label requires platform/region/time/source provenance.
  A trending paper or Google search alone does not prove an Instagram hashtag
  is trending. Otherwise label it **"relevant suggested hashtag"**.
- Do not scrape prohibited trend surfaces or append unrelated `#viral/#fyp`.
- Suggested small defaults: YouTube 0–3 relevant description hashtags, Instagram/
  TikTok up to 3–5 only within current verified capabilities, Facebook 0–2. These
  are testable channel preferences, not guaranteed ranking rules.
- Prioritize title/thumbnail accuracy and the opening/retention. Official YouTube
  guidance says backend tags play a minimal role except e.g. misspellings [S03].
- Retain metadata/citation provenance in the package. Every manual edit must
  revalidate claims and invalidate affected approvals.
- Measure whole-package outcomes at comparable post age. Tag correlations are
  not causal hashtag lift; avoid automated rejection on three confounded posts.
- Preserve native platform metrics and unknown values; label derived measures
  and disable unapproved YouTube derivations [S05].

## Cost controls and deployment

### Contribution workflow is repository-only

No instruction here requires installing Docker, a local database, models, TTS,
browser services, credentials or platform apps on the user's laptop. Deliver
small tested PRs/commits; CI supplies disposable infrastructure where available.
Production configuration and billable services are a separate operator decision.
Do not add a second orchestration SaaS while the existing durable jobs can do it.

### Low-cost runtime architecture for a future deployment

Reuse existing API/dashboard/Postgres/object storage and queues. Keep Redis
optional. Run collection/verification cheaply; scale render work on demand with
one encode job initially. Do not pay for idle GPU infrastructure. If an existing
machine can render reliably, use it as a worker; **laptop-off means that worker
cannot meet a guaranteed posting SLA**. An always-on scheduler/publisher and
shared final media are needed for that promise.

Local/open-weight inference has electricity, hardware, operations and latency
costs. It is not automatically cheaper than a small capped hosted model. Ollama
compatibility is an optional deployment adapter [S17]; Kokoro is an English-first
candidate with Apache-licensed weights, but validate the selected voice/model
license and languages. Do not infer Urdu support from Hindi support [S18].

### Budget design

- Fix G03–G04 before enabling any additional paid automation.
- Disabled-by-default paid features; clear provider/model rates, currency,
  units, effective date, and hard daily/monthly/per-video caps.
- Reserve estimated maximum input/output/audio units under a DB transaction;
  return a short-lived reservation ID bound to job + attempt + provider.
- Require reservation before a paid request; settle actual usage and release
  unused capacity. Retried requests have separate bounded attempt accounting.
- Provider timeouts may have incurred cost: mark unknown and reserve liability
  until reconciled; never discard usage just because JSON validation failed.
- Cap model output, retries, page depth, downloaded bytes, capture runtime,
  render attempts, concurrent encodes and search/ingest volume.
- Separate truly keyless/local providers from paid ones via explicit config;
  budget-service outages permit deterministic/local fallback only when authorized.
- Event IDs prevent duplicate metering. Durable telemetry outbox prevents losing
  costs during an API outage. Alert at 50/80/100% with capped notifications.
- Track cost per **unique video package**, per published post, per approved
  minute and operator minutes; current cost-per-video uses schedule count and
  understates costs when one video is posted on four platforms.

### Illustrative unit economics — assumptions, NOT vendor quotes

Example monthly output: **12 original long videos + 36 derived short edits**.
For an intentionally conservative independent-narration calculation:

| Dimension | Explicit assumption | Example |
|---|---|---|
| TTS | 12 × 5,000 + 36 × 1,000 characters | 96,000 chars before cache/reuse |
| TTS placeholder rate | $15 / million characters | $1.44; replace with actual provider billing units/rates |
| Extraction | 500k input + 100k output tokens, illustrative $0.15/$0.60 per million | $0.135 before retries; not a current model price claim |
| Render compute | 12 × long encode time + 36 × short encode time | Measure wall time, CPU/GPU-hour price and QC overhead; no invented dollar total |
| Retained objects | 100 GB average Standard R2; 10 GB included at current list rate | About $1.35 storage/month, excluding requests/tax/other services [S19] |
| Hosting/backup/operations | Existing or separately selected host | Add real bill; not included above |

Reuse narration and capture for derivatives where editorially appropriate. A
starting **paid-AI ceiling of $5/month** is a proposed configurable operator cap,
not authorization to spend. Do not claim total production costs $5: compute,
backup, monitoring, rights, network and human effort are separate.

### Cache/retention strategy

Keys include normalized full content hash, provider/endpoint, model+revision,
prompt/schema/parser version, source/evidence scope, language, voice/speed/output
format and policy version. Use content-addressed audio/media shared refs, hashes,
and original TTLs. Prevent concurrent cache misses from stampeding providers.

Use source-specific freshness and conditional fetch. Evidence freshness must not
be extended merely by a cache hit. Implement GC as dry-run → reference-aware
mark → grace period → recheck → sweep, with legal/evidence/uncertain-upload holds
and bounded batches. Expired caches/observations also need bounded retention.

## Reliability, security, and observability

1. **Scoped identities:** reviewer / extension-intake / collector / verifier /
   renderer / publisher / metrics roles with an explicit method+route matrix.
   A class label is not authorization. Keep reviewer-only attestation boundaries.
2. **Workflow idempotency:** deterministic stage/variant/hash job keys, unique
   artifact identity, expected-state transitions, transactional enqueue/outbox.
   At-least-once job delivery is normal; exactly-once remote side effects cannot
   be promised across network failure. Unknown upload state must reconcile.
3. **Lease ownership:** unique worker instance + fencing/lease token on touch and
   result; abort or stop new side effects if renewal/ownership is lost. Test
   stale-worker completion after another worker has acquired the job.
4. **Retries:** classify validation/permission/auth/rate-limit/transient/unknown-
   side-effect failures. Honor `Retry-After`, jitter, caps and per-account circuit
   breakers. Do not retry non-retryable consent/eligibility failures.
5. **Token lifecycle:** verify actual provider response schemas, rotating refresh
   tokens, encrypted secret storage and atomic rotation. Current expiry callbacks
   alone do not prove persistence of new secrets across restart. Reauthorization
   is a human task when required; never log credential-bearing responses.
6. **Untrusted research:** page text is data, not tool instructions. Validate
   extracted fields/excerpts server-side; no model-generated shell execution.
   Reject private-network targets and unsafe redirect/DNS rebinding paths in
   fetch/capture workers. Sandboxed demos have no production secrets.
7. **Media/rights:** URL access and selected text can contain tokens/PII. No raw
   browser cookies, account sessions or unredacted recordings in public buckets.
   Temporary public URLs, if used, expose only approved render bytes and expire
   after provider processing; resumable uploads may avoid public hosting [S06].
8. **Observability:** story→claim→script→asset→render→schedule→remote ID trace;
   queue age/stage latency, source health, freshness coverage, cost reservations,
   cache-hit errors, dead jobs, processing delays and confirmed publish rate.
   No high-cardinality secrets/URLs in metric labels.
9. **Operational SLO proposals:** 95% of healthy-source scheduled polls complete
   within two polling intervals; no unsupported factual claim reaches release;
   zero silent paid work after budget denial; zero automatic retry of uncertain
   uploads. Set processing/publishing latency targets after a measured pilot.
10. **Alerts/backups:** durable deduplicated notifications with cooldown, daily
    DB backup, media inventory and off-host copies; scheduled restore drill and
    sample artifact hash checks in the deployment environment, not this task.

## Implementation work packages and acceptance criteria

Each package is a small reviewable PR series; estimates are rough developer-days,
exclude platform reviews, and assume the current code remains the baseline.
Do not mark complete based only on mocked tests.

### EP-00 — Restore contribution confidence (0.5–1.5 days)

- [ ] Record baseline checks and failed/skipped layers without stale green claims.
- [ ] Owner resolves GitHub Actions billing lock; contributors do not change
  billing or provision a paid runner without approval.
- [ ] Make the Windows tempfile test portable; include Windows extension/unit
  coverage alongside Linux where the available CI budget permits.
- [ ] Add filename portability lint and propose a narrow rename of the two
  `:` documents in a separate reviewed change. Preserve their content/history.
- [ ] Add source-of-truth implemented / partial / unproven / planned status in
  traceability docs; reconcile earlier completed banners and stale gap sections.
- **Acceptance:** CI executes actual steps; database, browser and live-platform
  evidence are separately labeled. No production services required locally.

### EP-01 — Safety and financial correctness (2–4 days)

Addresses G01–G05, G12, G21, G27.

- [ ] Capability model distinguishes publish, preview, private/unpublished, export
  and account-level visibility. Block Instagram private test before side effects.
- [ ] Remove automatic confirmed-success fallback; durable remote reconciliation.
- [ ] Fail-closed paid-call permission with conservative atomic reservations,
  per-attempt metering and API-config/auth parity.
- [ ] Route/role permissions and narrow extension credential; review destructive
  GC authorization/reference holds.
- [ ] Apply policy permission switches to best-time, hashtag and other derived-
  metric paths, not just the named growth score.
- **Acceptance:** unknown budget = zero paid calls; concurrent requests cannot
  oversubscribe cap; extension cannot call jobs/media/cost writes; unsupported
  privacy never invokes remote publish; accepted != processing != published.

### EP-02 — Repair discovery and observable momentum (2–4 days)

Addresses G06–G11, G13–G16, G22.

- [ ] Shared adapter registry and source configuration validation across layers.
- [ ] Persist excerpts/context, raw typed measurements and provenance; separate
  append-only observations from deduped story intake.
- [ ] Fix RSS/Redis/PG cache paths and expiry; thread source policy and credentials
  through adapters; send GitHub auth; validate Compose environment contracts.
- [ ] Real source-specific count deltas, reset/staleness handling and cross-URL
  story clustering; no score-change-as-popularity claims.
- [ ] Independent-source handling, novelty/diversity, claim-coverage evidence
  score, real cooling duration, backlog fairness and bounded incremental scans.
- [ ] Source permissions/off switches, with Reddit disabled pending approval.
- **Acceptance:** fixture HN 100→160 points over 2 h yields raw 30 points/h;
  re-fetch appends measurement without duplicate story; unchanged fields cannot
  fake a rising trend; cached Google Trends parses; API can create each adapter.

### EP-03 — Research briefs and content-type gates (2–4 days)

Addresses G17–G18 plus research breadth.

- [ ] Extend existing topic/offer linkage with explainer/tutorial/research content
  type and claim classes; preserve offer-specific eligibility/renewal gates.
- [ ] Versioned claim ledger, sources/counterevidence, proposed angles, research
  brief and reproducible top-slate snapshot.
- [ ] Low-risk auto-shortlist/research controls, daily capacity and budget caps.
  No inference that "promote" means "verified".
- [ ] Fix production queue SQL/readiness/outage semantics, not another queue.
- **Acceptance:** a paper can become an accurately attributed explainer without
  invented coupon/price fields; every substantive sentence resolves to current
  evidence or is labeled analysis; conflicting evidence blocks unsupported copy.

### EP-04 — Finish browser extension (2–3 days)

- [ ] Correct link/selection context-menu targets and persist context end-to-end.
- [ ] Dedicated pairing/token setup, runtime API-host grant, HTTPS validation,
  trusted storage, explicit credential revoke/reset and health probe.
- [ ] Durable bounded offline outbox, abort timeout, idempotency/retry, clear
  statuses and "Open saved item" action using only the returned safe item ID.
- [ ] Privacy/secret preview, text bounds, restricted/private-tab behaviors and
  intentional domain exclusions.
- [ ] Unit/API-contract/loaded-extension E2E tests; contribution/developer docs
  with install steps for testers, not mandatory user-machine setup.
- **Acceptance:** clicked link is saved rather than current page; offline save
  survives worker restart and is delivered once logically; no service/platform
  token required; denied host permission shows a useful action; bad content/401/
  429/duplicate/timeout all have distinct tested states.

### EP-05 — Scene-based real video production (4–7 days)

- [ ] Scene manifest/editor, allowlisted public-page/demo capture, rights and
  citation overlays, aligned narration, readable reframing, clip selection.
- [ ] Shared content-addressed TTS cache and provider/prompt/version parity.
- [ ] Real audio normalization, caption font/overflow/alignment checks, scene
  coverage and visual/audio secret scanning; preserve human playback/redaction.
- [ ] English default; optional Urdu only with validated pronunciation/provider
  capability and genuine translation review.
- **Acceptance:** one allowed explainer produces a reviewable long video and two
  self-contained vertical edits with traceable claims; a claim walkthrough stops
  for login/payment/human actions; all exports pass measured QC and human review.

### EP-06 — One-click reviewed scheduling (2–4 days)

Addresses G19–G20, G23–G24, G26.

- [ ] Per-platform account/render/privacy/metadata preview with disabled targets
  and exact reasons; account-level capability test before enabling selection.
- [ ] Idempotent review-preview commit, explicit draft→review→approve→schedule
  sequencing, stale-hash rejection, safe partial-result recovery.
- [ ] Account-aware UTC slot conflicts across page/day boundaries, expiry buffer,
  manual time override and honestly limited best-time suggestions.
- [ ] Correct hashtags/rule labeling; keep provenance and editable relevant copy.
- [ ] TikTok export bundle/native handoff unless approved integration is proven.
- **Acceptance:** a reviewed package is scheduled on eligible targets with one
  final click; ten repeat submissions create one logical post per target;
  stale/expired/changed package is refused; unapproved targets never publish.

### EP-07 — Recovery, learning and cost optimization (2–4 days)

- [ ] Lease fencing, durable notification/telemetry outboxes, per-account circuit
  breakers, bounded work/retention/GC and token rotation persistence.
- [ ] Comparable-age native metric snapshots and policy-approved experiment
  reports; separate original video vs derivative vs cross-post unit economics.
- [ ] Dashboard shows source outage, partial queue and unknown remote result,
  never false empty lists/success.
- [ ] Failure-injection contracts: provider timeout, duplicate delivery, Redis/
  API outage, exhausted quota, expired token, worker death, changed evidence.
- **Acceptance:** no duplicate publish in crash/retry drills; budget remains
  bounded during outage; restored backup recovers artifact references; selection
  reasons remain explainable and outcome reports label missing/estimated values.

### Recommended order and scope limit

**EP-00 → EP-01 → EP-02 → EP-03**, then EP-04 (extension) and EP-05 (video),
then EP-06 and EP-07. Keep early YouTube-only private-test mode; do not hold core
work waiting for TikTok approvals. Rough scope is **17–32 developer-days**, not
including external approvals or real-world content review. Split into milestones;
do not combine this with TypeScript/Zod/Redis major upgrades or an infrastructure
rewrite. No subagents or parallel implementation are implied by this estimate.

## Example production slate

### Live discovery examples, checked 24 October 2026

The following appeared on the live [HF Trending Papers page][S20] during this
audit. These are **research leads**, not validated claims, global popularity
rankings or completed videos. The page included older papers and repeated cards:
deduplicate by paper ID and distinguish publication date from current visibility.
Counts change, so no point-in-time upvote number is used as a permanent score.

| Lead and discovery reference | Proposed original video angle | Proof/footage needed before production | Proposed relevant tags, NOT verified trending tags |
|---|---|---|---|
| [Harness²](https://huggingface.co/papers/2610.14224) | "What an agent harness changes—and what it cannot prove" | Read paper/maintainer repo; isolated repeatable task; report observed result rather than repeat benchmark superiority | `#AIAgents #AgentHarness #AIResearch` |
| [WeVisOne-VL](https://huggingface.co/papers/2610.31329) | "Detection, OCR and segmentation: one model, three questions" | Official implementation/model availability; same original test images; masks/text/results with failure examples | `#ComputerVision #OCR #AIResearch` |
| [MOSS-Image](https://huggingface.co/papers/2610.23374) | "Can this image model follow a layout? A labeled test plan" | Model/license/hardware check; controlled prompts; permitted outputs; no test claim until run | `#ImageGeneration #OpenModels #AIResearch` |
| [Next-Concept Modeling](https://huggingface.co/papers/2610.14162) | "Parallel text generation explained without the hype" | Primary paper + original diagrams; implementation/benchmark context; authors' claims clearly attributed | `#LanguageModels #AIResearch #TextGeneration` |
| [Looking Ahead](https://huggingface.co/papers/2610.29989) | "How video models plan future frames" | Primary report; licensed examples or original diagrams; label synthetic scenes; do not call generated footage real-world evidence | `#VideoGeneration #AIResearch` |
| [SmolDocling](https://huggingface.co/papers/2503.11576) | "Small document models: what survives a messy invoice?" | Official repo/model card; synthetic non-sensitive invoice fixtures; OCR/layout error review; label older work, not a new launch | `#DocumentAI #OCR #OpenModels` |

The same feed also surfaced financial-trading work. High engagement does not
make it suitable for automatic claims about returns. Deprioritize it for this
channel or require a careful methodological explainer without investment advice.

### Reusable 12-slot slate template

Only the first six slots above have live discovery-page support in this audit;
the following six are **evergreen/proposed**, not asserted to be hot today.

| Slot | Working title / type | Source requirement and real visual | Derivative idea |
|---|---|---|---|
| 7 | "Run a small model: cost, RAM and limits" / tested tutorial | Current official runtime/model docs; record actual hardware, timings and one failure | "The RAM number your demo must disclose" |
| 8 | "Free tier vs trial vs credits" / official explainer | Current provider terms with region/renewal caveats; source cards | "Free does not mean permanent" |
| 9 | "Student program eligibility: check before applying" / terms explainer | Official program rules; no claim of eligibility/acceptance without evidence | "Three checks before a student application" |
| 10 | "Cache your AI calls without stale answers" / tested tutorial | Original instrumented demo with reproducible cache keys, bills/estimates clearly separated | "Why a cache hit can still be wrong" |
| 11 | "Voiceover on a budget: intelligibility first" / comparison | Same consented/original script across permitted voices; report hardware/rates/time at test date | "One name, three pronunciation failures" |
| 12 | "Schedule once, verify twice" / behind-the-scenes | Own approved test package and safe test account; show held/processing/confirmed states without secrets | "Uploaded is not published" |

### Production-list row specification

Every proposed video must carry: topic/story ID; audience question; title and
hook alternatives; why-now evidence/observation times; content type; region/
language; claims/contradictions; primary/independent source links; exact shot/scene
list; required account actions; rights/disclosure; target duration; long/short
outputs; thumbnail concept; relevant tags with provenance; estimated compute/
AI/human cost; priority explanation; review blockers; freshness deadline; account
and slot proposals. A title list alone is not a production plan.

**Example brief — slot 2 (not yet approved):**

- Question: Does one model handle text reading, object location and segmentation
  on the same images, and where does it fail?
- Format: attributed research explainer first; upgrade to tested tutorial only
  after a reproducible run on licensed/original images.
- Hook: show the three *questions* on one original image; do not fabricate the
  model's outputs in advance.
- Scenes: paper/model scope → setup/resources → real three-task results → error
  cases → what the paper reports versus what MTK observed → conclusion/sources.
- Outputs: proposed 6-minute landscape edit; two separate vertical edits about
  OCR failures and segmentation limits, each retaining the relevant caveat.
- Gate: model availability, license, demo budget, source snapshots, actual outputs,
  redaction/QC and playback approval still required.
- Scheduling: YouTube only initially; additional targets shown only after their
  capabilities are tested; timestamps are operator-selected, not invented here.

## Rollout and validation

### Repository delivery rules

- Plans/checklists land as documentation. Implementation follows in small PRs
  referencing gap IDs and acceptance tests. No changes to production services.
- Keep user/unrelated modifications untouched; no force push/reset; fetch before
  pushing and reconcile remote changes non-destructively.
- Check docs/links/portability in CI; do not require every contributor to run the
  full stack. Maintain isolated tests and fixture-driven adapter contracts.
- No real account tokens, selected private page text, raw captures or copyrighted
  research figures committed as fixtures.

### Required test matrix for implementation PRs

| Layer | Required evidence |
|---|---|
| Unit/contracts | Adapter config/parsing/caching, metric normalization, permissions, budget reservation, scene rules, platform metadata |
| Disposable Postgres | Fresh/upgrade migrations, queue SQL, concurrent reservations/transitions/promotions, observation uniqueness, retention pins |
| Extension | Mock Chrome APIs + real MV3 browser CI: link/selection, runtime host grant, token revocation, offline/restart, duplicates, bad URLs |
| Dashboard E2E | Research→queue→review preview→per-target schedule, stale-hash rejection, partial errors, account/timezone handling |
| Media fixtures | Real short original clip→captions/normalization→landscape/vertical→QC; missing audio/frame secrets/caption overflow fail |
| Platform contracts | Versioned official-shaped responses for auth, rotate/refresh, 429, container/processing errors, unknown attempt and confirmation |
| Live pilot, separate operator action | One explicitly approved test per eligible platform, actual visibility/permalink verification, never a fake Instagram private test |
| Recovery | Worker crash after remote side effect, stale lease, API/Redis outage, quota/budget exhaustion, changed source, restore drill |

### Release gates

1. **Foundation gate:** G01–G05 fixed and tested; CI can run. No broader public
   autopilot while privacy/money/auth/status semantics are unresolved.
2. **Discovery gate:** three permitted independent source types, reliable changing
   observations, explanation and source-health states; no mandatory volume quota
   that encourages ingesting irrelevant topics.
3. **Production gate:** one genuine research explainer plus one real tutorial
   through the pipeline; measured QC, source/rights traceability and review proof.
4. **Operator gate:** loaded extension smoke + one-click reviewed scheduling on
   eligible targets; retry/partial/outage behaviors demonstrated.
5. **Pilot gate:** limited cadence, manually approved posts, review each failure
   and correction. Suggested start: two original videos/week and derivatives
   only when they add value, then raise capacity from real cost/quality data.
6. **Expansion gate:** enable low-risk automatic research/production separately
   from approval. Never globally turn off evidence/redaction/playback safeguards.

### Success measures (targets to validate, not present results)

- 100% material claims in released videos traceable to current evidence.
- 100% completed posts have checked remote identity/status, not synthetic success.
- Zero paid requests without valid permission/reservation and no unmetered retry
  loop; missing price/usage stays visibly unknown.
- One final scheduling click for a fully reviewed, ready target set.
- Extension logical save survives transient offline/restart without duplicate
  story creation; denied permission/auth failure is actionable.
- Reduced operator minutes per approved video against a measured baseline.
- Track originality, corrections, useful watch time/native metrics and cost per
  unique package; not just number of posts or unproven hashtag "lift".

**Definition of done:** the operator receives a ranked, genuinely evidenced
production slate; safe mechanical research/asset/edit work happens automatically;
real footage and claims survive review; one explicit confirmation schedules the
exact reviewed packages; publication is reconciled; spend and failures remain
bounded and visible. External approvals and human-only actions remain explicit.

## Research sources and policy constraints

Accessed/searched on **24 October 2026**. Directly fetched sources, current
documentation lookup and official search extracts are distinguished below.
Recheck live rules/version/eligibility during implementation; search excerpts
are not an API contract or a legal opinion.

| ID | Primary source | Retrieval / decision it informs |
|---|---|---|
| S01 | [YouTube monetization policies](https://support.google.com/youtube/answer/1311392?hl=en) | Official search extract: original/authentic value; mass-produced/repetitive content risk |
| S02 | [YouTube spam policy](https://support.google.com/youtube/answer/2801973?hl=en) | Official search extract: do not flood platforms with repetitive automated content |
| S03 | [YouTube video tags](https://support.google.com/youtube/answer/146402?hl=en) | Official search extract: title/thumbnail/description more important; tags usually minimal discovery role |
| S04 | [YouTube hashtags](https://support.google.com/youtube/answer/6390658?hl=en) | Official search extract: relevance; more than 60 ignored; small-count defaults are editorial |
| S05 | [YouTube developer policies](https://developers.google.com/youtube/terms/developer-policies), [compliance guide](https://developers.google.com/youtube/terms/developer-policies-guide), [derived metrics policy](https://developers.google.com/youtube/terms/derived-metrics-policy?hl=en) | Official search extracts: custom metrics/storage need permission-specific review; do not assume every derivation is permitted |
| S06 | [Instagram publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing), [resumable uploads](https://developers.facebook.com/documentation/instagram-platform/content-publishing/resumable-uploads), [media reference](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media) | Current documentation lookup + official extracts: professional-account/login-path requirements, media/container/publish flow; resumable path means public URL is not universally the only option |
| S07 | [YouTube synthetic-content disclosure](https://support.google.com/youtube/answer/14328491?hl=en) | Official search extract: realistic altered/synthetic scenarios; determine actual disclosure per export |
| S08 | [TikTok Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines) | Direct fetch, updated Aug 4 2026: internal-use exclusion, user consent/preview, creator-info, no default privacy, interactions, transfer and branding rules |
| S09 | [TikTok app-review guidelines](https://developers.tiktok.com/doc/app-review-guidelines), [Direct Post reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post) | Official search extracts: personal/private-use approval limitations and unaudited visibility restrictions |
| S10 | [Reddit Data API Terms](https://www.redditinc.com/policies/data-api-terms), [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) | Official search extracts: approved access/commercial-use requirements; anonymous public JSON is not a blanket permission |
| S11 | [YouTube quota calculator](https://developers.google.com/youtube/data/determine_quota_cost) | Direct fetch + current docs lookup, page updated Oct 15 2026: separate search/upload buckets; prefer current page/console over older indexed costs |
| S12 | [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api) | Official search extracts: generally 60 unauthenticated/5,000 authenticated requests/hour; conditional calls and secondary limits |
| S13 | [Google Trends alpha](https://developers.google.com/search/apis/trends), [announcement](https://developers.google.com/search/blog/2025/07/trends-api) | Official search extracts: application-gated alpha; no assumption that this project is approved |
| S14 | [HF Hub API](https://huggingface.co/docs/hub/api), [Daily Papers explanation](https://huggingface.co/blog/daily-papers) | Official search extracts: current API schema reference and community upvote context; author results need separate verification |
| S15 | [Chrome permission declaration](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions), [optional permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions) | Official extracts + current docs lookup: runtime grants for configured hosts instead of install-time all-web access |
| S16 | [Chrome storage](https://developer.chrome.com/docs/extensions/reference/api/storage), [StorageArea access levels](https://developer.chrome.com/docs/extensions/reference/api/storage/StorageArea) | Current docs lookup: restrict local storage to trusted extension contexts; storage is not a platform-secret vault |
| S17 | [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility), [API introduction](https://docs.ollama.com/api/introduction) | Official extracts: optional local/hosted-compatible provider; endpoint/model/auth capabilities differ |
| S18 | [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M), [voices](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) | Maintainer search extracts: model license and voice/language review; no assumed Urdu support |
| S19 | [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) | Official search extract: Standard storage $0.015/GB-month, 10 GB-month included, operations separate and Internet egress free subject to terms |
| S20 | [HF Trending Papers](https://huggingface.co/papers/trending) | Direct live fetch: specific research leads in the slate; popularity page is not independent research validation |

[S01]: https://support.google.com/youtube/answer/1311392?hl=en
[S02]: https://support.google.com/youtube/answer/2801973?hl=en
[S03]: https://support.google.com/youtube/answer/146402?hl=en
[S04]: https://support.google.com/youtube/answer/6390658?hl=en
[S05]: https://developers.google.com/youtube/terms/developer-policies
[S06]: https://developers.facebook.com/documentation/instagram-platform/content-publishing
[S07]: https://support.google.com/youtube/answer/14328491?hl=en
[S08]: https://developers.tiktok.com/doc/content-sharing-guidelines
[S09]: https://developers.tiktok.com/doc/app-review-guidelines
[S10]: https://www.redditinc.com/policies/data-api-terms
[S11]: https://developers.google.com/youtube/data/determine_quota_cost
[S12]: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
[S13]: https://developers.google.com/search/apis/trends
[S14]: https://huggingface.co/docs/hub/api
[S15]: https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
[S16]: https://developer.chrome.com/docs/extensions/reference/api/storage
[S17]: https://docs.ollama.com/api/openai-compatibility
[S18]: https://huggingface.co/hexgrad/Kokoro-82M
[S19]: https://developers.cloudflare.com/r2/pricing/
[S20]: https://huggingface.co/papers/trending
