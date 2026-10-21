# WP01 fourteenth slice — a read-only legacy audit of verified offers

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [expiry-capped recheck deadline](implementation-wp01-slice13-2026-10-21.md)
**Master plan:** [§6 official verification, legacy review](../docs/automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

The plan's legacy step — "review/reclassify existing verified records and queued
legacy releases as unverifiable where necessary" — has no starting point. Rows
verified before provenance, coverage and the typed fact pack existed stay
`verified` and readable, which is intentional, but nobody can list which of them
would fail today's gate. The gate itself raised from inside a single function, so
any separate report would have been a second implementation that could drift.

## What changed

### `services/api/offers_api.py` — one implementation, two callers

- `_verified_problems(pool, offer_id)` now contains the whole revalidation:
  latest extraction, schema validation, the typed contract against the current
  offer type, provenance and extraction coverage. It returns a list of reasons.
- `_gate_verified` is a thin wrapper: it calls `_verified_problems` and raises the
  same 422 with the same `"; "`-joined text as before. Every existing promotion
  path and error message is unchanged, and the audit cannot disagree with a
  promotion decision.

### `GET /offers/audit/verified` (new, read-only)

- Returns `checked`, `failed`, the failing `offers` (id, title, provider,
  updated_at, `problems`) and which requirements were active during the scan
  (`fetch_provenance`, `extraction_coverage`).
- Bounded by `limit` (default 200, max 2000) and ordered oldest-updated first, so
  the stalest records surface first. It never changes state, pauses anything or
  writes an audit entry: reclassification remains an explicit human transition.
- The route is `/offers/audit/verified` (two path segments), so it cannot be
  captured by the single-segment `/offers/{offer_id}` route.

## What this does and does not prove

- **Does:** for any given verified offer, an operator can see the exact reasons a
  fresh promotion would be refused, computed by the same code that refuses it.
- **Does not:** demote anything, judge whether a legacy offer is *actually* false,
  report the schedules/posts derived from a failing offer, or apply the ToS
  attestation check (that is enforced at evidence ingest, not at promotion). It
  is a point-in-time inventory, not a background monitor.

## Test evidence

### Failing first

At `b8aa54c` there is no audit route and no callable problem list: the checks
exist only inside `_gate_verified`, which raises on the first non-empty result.
Both new tests receive 404 for the route.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 608 passed, 26 warnings, zero skips, exit 0      (was 606; +2)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage (`services/api/tests/test_integration.py`):

- a verified offer whose latest extraction has lost its coverage record appears
  in the audit with a coverage problem, while a healthy verified offer in the
  same database does not; the audit leaves both in `verified`;
- a row forced to `verified` with no extraction is reported with exactly the
  gate's existing "requires structured extraction with official snapshot
  evidence" reason.

## Residual risk (honest gaps)

1. The audit is manual: nothing schedules it, alerts on a rising `failed` count,
   or prevents new legacy rows appearing between runs.
2. It does not list the schedules, renders or published posts derived from a
   failing offer; downstream invalidation remains open.
3. Results are capped and read in one pass with per-offer queries; a very large
   backlog needs pagination rather than a bigger limit.
4. Terms-change detection, claim-free page coverage, non-symmetric acquisition
   identity, semantic applicable-terms coverage and downstream invalidation
   remain open.

**Next smallest task:** include the derived work in the same report — for each
failing verified offer, the schedules/renders/published posts that depend on it —
so an operator sees the blast radius before reclassifying.
