# Whole-System Review — 2026-10-23 (day-4/5 hardening)

Four parallel read-only audits covered (1) API core & security, (2) content
generation & analytics, (3) workers & packages, (4) dashboard/DB/docs —
~38 findings total. This note records what was fixed and what was deferred,
so the backlog is explicit instead of tribal.

## Fixed in this pass (with tests)

**Fail-closed / authorization (P0–P1)**
- Release gate: NULL render/package sha256 → blocking `render_hash_missing`
  (was silently skipped); NULL pinned render language → blocked; an approved
  script version no longer among the offer's scripts → blocking
  `script_missing` (was silently skipping claim/capture checks); a non-dict
  stored `release_policy` fails closed to strict defaults instead of 500ing.
- `POST /offers/{id}/transition` to `verified` now requires a human reviewer
  credential (or an authorized `automation:verify` actor) — a plain
  service/worker token could previously verify an offer and skip the stage
  policy guardrails. Dev-open mode (CREDENTIAL_DISABLED) keeps its fallback.
- Schedule `transition` runs in one transaction with `SELECT … FOR UPDATE`;
  concurrent transitions can no longer validate on a stale read and overwrite
  each other's state/pins.
- Automation daily budget is counted inside the same transaction behind
  `pg_advisory_xact_lock` — the old check-then-act let N concurrent
  approvals exceed `auto_publish_max_per_day`.

**Honesty of generated copy (P0)**
- Studio generation now loads the latest extraction `fact_pack` (mirrors the
  offers path) so contradicted/unknown facts render as such.
- Urdu scripts: unknown/contradicted eligibility no longer renders as
  "کھلی اہلیت"; a missing deadline emits the no-expiry warning (was silent);
  an unknown renewal price renders "درج نہیں" instead of the invented
  "عام قیمت"; the closing summary derives خودکار تجدید from
  `renewal.autoRenew` instead of asserting it unconditionally.
- Title suffix is format-aware: only `claim_walkthrough` may say
  "real claim walkthrough"; `official_explainer` → "official terms
  explained", `tested_tutorial` → "tested tutorial"; unknown formats get a
  neutral label. `content_studio` passes the script format through.
- `_eligibility_line` derives "(application-based)" from a real application
  signal (fact-pack `benefit_type`), never from `newCustomerOnly`.
- `growth_engine` normalizes `avg_view_percentage` (0..100) to a fraction —
  it was read as 0..1, pinning the retention score at 100 ("4825%" wording).

**Correctness & dedup (P1)**
- `items` ingest now enforces the documented canonical-URL + text-hash dedup:
  migration `031_items_canonical_dedup.sql` (collapses dupes, adds a unique
  partial index) + target-free `ON CONFLICT DO NOTHING`. A resubmission with
  a fresh `external_item_id` no longer creates a second row.
- Publish job rows are armed when a post ENTERS the queue (the `scheduled`
  transition), not at draft creation — create-time jobs were claimed against
  drafts and dead-lettered into attention as noise.
- `jobs/result` failures without `retry_after_s` get a 60s default backoff —
  `run_after = now()` caused a claim→fail hot loop until dead-letter.
- Locks: `release` REQUIRES the holder (name-only release could free another
  worker's lock); publishing/metrics workers acquire with a unique holder
  (`name-worker-<pid>`), TTL 3600, re-assert the lock before each upload and
  abort the sweep fail-closed when it is lost.
- `object_storage`: `parse_s3_ref` rejects `..`/leading `/` (same rule as the
  local driver); `materialize` refuses traversal refs and anchors the cache
  destination inside `cache_dir`; `capture_key` runs the filename through
  `_safe_part`.
- `api_paging`: a FULL page without `X-Next-Cursor` raises instead of
  silently ending the collection (dropped cursors meant failed posts were
  never retried).
- Publishing: `_materialize_checked` fails closed when an asset path has no
  pinned sha256 (covers/captions were uploaded unverified); pin fields read
  via `.get` with explicit "missing pin" messages (no opaque KeyErrors);
  `TransportUnauthorized` during package finalize marks the account expired
  like a token expiry; a mid-sequence upload failure reverts the render row
  to consistent local paths; attempts/results log response status only, no
  raw upstream bodies.
- Metrics: one malformed provider payload logs and continues — it can no
  longer abort the whole sweep; Graph adapters type-guard `resp.json()`
  before `.get("data")`.
- `api_hardening`: reviewer-token lookup prefers the shared pool; unknown
  tokens are negatively cached (5s) — invalid tokens used to open a fresh
  Postgres connection per request.
- Unbounded queries capped (`stale_offers` 500, evidence 200, corrections
  200, impact renders/captures 200/200, schedules 500, scripts 200);
  `/health` and schedule-insert failures return opaque details (DB text is
  logged server-side, not echoed); create-schedule file hashing moved off
  the event loop (`asyncio.to_thread`); trends `limit` accepts only ≥1;
  `POST /items` maps a malformed URL to 422; CORS localhost defaults apply
  ONLY when no origin is configured.

## Deferred (triaged, not forgotten)

| Item | Where | Severity | Why deferred |
|---|---|---|---|
| QC caption width uses one 0.60×font-size estimate | `workers/render/qc.py` | P3 | Documented approximation; real fix needs font-aware measurement. Not conservative for Urdu Nastaliq — revisit with real metrics. |
| `retention_3s_estimated` defaults False when no retention reported | `workers/metrics/main.py` | P3 | Column is NOT NULL; consumers already treat NULL retention as unavailable. Provenance-semantics cleanup only. |
| Trends list `summary`/`bands` are page-local but read as totals | `services/api/trends_api.py` | P2 | Global counts exist in analytics; rename to `page_total` or compute with COUNT FILTER in a follow-up. |
| Analytics cache hits return JSON-converted types (Decimal→str) vs misses | `services/api/cache.py`, `analytics_api.py` | P2 | Needs payload normalization before caching; risk of touching many response shapes. |
| Fact-pack not consulted for promo/value at render time (defense-in-depth) | `scriptgen.py`, `seo.py` | P2 | Verification gates already block contradicted fields before `verified`; consistent suppression is a larger generator change. |
| Release gate does not recompute `build_thumbnail_text` parity | `release_gate.py` vs `workers/render/covers.py` | P2 | Byte-identical today with an equality test; parity belongs behind an import boundary the API doesn't have yet. |
| Urdu-voiced offers get English cover copy | `content_studio_api.py` | Intent | English-first metadata policy; confirm with operator before switching covers to RTL. |
| Prometheus label escaping for status/kind | `metrics_api.py` | P3 | Values are DB-validated enums today; only matters if free-text labels appear. |
| Render lease (3600s) not renewed for >1h encodes | `jobs_api.py` / render worker | P2 | Documented reclaimed-lease design; monitor stuck-lease alerts, then add renewal. |
| `redact.py` short-key (<20 char) patterns and GCP JSON keys | `services/api/redact.py` | P3 | No false-negative found for current providers; extend when a provider with short keys is added. |
| `document_sections` cap enforced only at boundaries | `services/api/document_sections.py` | P3 | Split logic itself verified; add an internal assert when callers bypass the schema. |

## Verification

`pytest`: 941 passed (was 916 — 25 new tests). `ruff check .`: clean.
`compileall`: clean. `pnpm typecheck`: clean. Dashboard build: clean.
