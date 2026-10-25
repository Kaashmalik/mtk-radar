# WP01 sixteenth slice — coverage for claim-free pages

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 22 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [audit blast radius](implementation-wp01-slice15-2026-10-21.md)
**Master plan:** [§17 scheduling/publishing, legacy review](../../automation-master-plan-2026-10-21.md#17-scheduling-and-publishing)

The ninth slice required the stored `coverage` record to list every machine
snapshot a claim cites. That still left one hole: a worker could read a page,
draw no claim from it because the page contradicted the offer, and omit it from
coverage. The claims pointed only at the agreeable page, so the gate saw a
consistent, fully covered extraction.

## What changed

### `services/api/offers_api.py` — the acquisition window is the run

- `_verified_problems` now reads the stored extraction's `created_at` and
  passes it to `_coverage_problems`.
- `_coverage_problems` keeps its claim-based requirement and adds a second set:
  every machine-collected (`reviewer IS NULL`), official, domain-ok evidence row
  for the offer whose `captured_at` falls after the previous extraction and at or
  before this extraction.
- Coverage must list the union of both sets. A page with no claims still counts.
- Reviewer-attested snapshots stay exempt: there is no machine run to account
  for, and the window query excludes them.
- The failure message is
  `extraction coverage does not include every machine-collected snapshot from this acquisition run (pages with no claims still count)`.

### Why a window instead of a client-supplied run id

`evidence.captured_at` is not part of the evidence request; it defaults to
`now()` on insert. The gate therefore uses a server-side timestamp, not a value
the worker can choose. The "run" is defined as the rows inserted after the
previous extraction for that offer, so no schema change or new identifier is
needed and legacy rows keep their old behaviour.

## What this does and does not prove

- **Does:** within one acquisition window, a promotion cannot cite only the page
  that agreed while silently dropping another machine snapshot that was already
  stored for the same offer.
- **Does not:** force the worker to store a page at all. A worker that decides
  not to ingest an unhelpful page before the extraction is still outside the
  gate's view. A worker that posts evidence *after* the extraction also lands in
  the next window. Closing that requires server-side fetching or a
  worker-generated run id bound into the signed provenance; both remain open.
- **Does not:** judge whether the pages that were stored are the *applicable*
  terms. The window is structural, not semantic.

## Test evidence

### Failing first

At `a22fae8` the coverage gate only resolved evidence ids cited by claims, so a
test that stores a second official snapshot with no claims and covers only the
cited one promoted successfully. The new integration test expects a 422 there.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 610 passed, 26 warnings, zero skips, exit 0
ruff check packages services workers                 → exit 0
compileall -q packages services workers              → exit 0
pnpm typecheck                                       → exit 0
```

New tests:

- `test_verification_gate.py::TestExtractionCoverageGate::test_coverage_includes_claim_free_pages_from_the_same_run`
  — unit fake with two machine snapshots; coverage of one blocks, coverage of
  both passes.
- `test_integration.py::test_coverage_must_include_claim_free_pages_from_the_run`
  — real PostgreSQL: second snapshot with no claims, partial coverage blocks
  promotion, full coverage promotes.
- The gate fake now filters `reviewer IS NULL` for the window query and carries
  `created_at`, so reviewer-attested exemptions still behave like the real SQL.

## Residual risk (honest gaps)

1. Evidence inserted after the extraction is not in that extraction's window; a
   worker can still defer an inconvenient page past promotion.
2. An entire page never sent to the API is invisible, as before.
3. The window is time-based. Two processes writing evidence and extraction for
   one offer concurrently can assign a row to the wrong side of the boundary;
   there is no run id to disambiguate.
4. Terms-change detection, non-symmetric acquisition identity, semantic
   applicable-terms coverage, risk-based recheck intervals, downstream
   invalidation, bulk legacy reclassification and deployment with owner approval
   remain open.

**Next smallest task:** bind the acquisition run into the signed provenance (or
fetch server-side), so a worker cannot move evidence across the extraction
boundary or omit a page it actually read.
