# WP01 fifteenth slice — blast radius in the legacy audit

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [read-only legacy audit](implementation-wp01-slice14-2026-10-21.md)
**Master plan:** [§17 scheduling/publishing, legacy review](../docs/automation-master-plan-2026-10-21.md#17-scheduling-and-publishing)

The audit listed the verified offers that would fail today's gate, but an
operator still had to call `/offers/{id}/impact` once per failure to learn
whether anything was queued or already published from it. The plan's legacy step
explicitly covers "queued legacy releases", so the inventory needs to say whether
a failing offer has work depending on it before anyone reclassifies it.

## What changed

### `services/api/offers_api.py` — audit entries carry counts

- `_impact_counts(pool, offer_id)` returns `schedules`, `scheduled`, `published`,
  `renders` and `captures` for one offer in a single query.
- Every failing entry in `GET /offers/audit/verified` now includes that `impact`
  object. Counts, not ids, keep the report compact; `/offers/{id}/impact` remains
  the per-offer detail view.
- Nothing is paused, demoted or written. The test asserts that a scheduled row
  for a reported offer is still `scheduled` after the audit runs.

## What this does and does not prove

- **Does:** an operator can see, in the same report, whether a failing verified
  offer has scheduled or published work before deciding to reclassify it.
- **Does not:** pause that work automatically (the offer-state trigger does that
  on an actual demotion), list the individual schedule/post ids, or find
  artifacts that are no longer represented by a schedule row. It is still a
  point-in-time report.

## Test evidence

### Failing first

At `35db816` a failing audit entry has no `impact` key, so the extended audit
test raises `KeyError` on `failed[bad]["impact"]`.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 608 passed, 26 warnings, zero skips, exit 0      (no new test functions)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

The slice-14 audit test now inserts one `scheduled` row for the failing offer and
asserts `impact.schedules == 1`, `impact.scheduled == 1`, and that the row is
still `scheduled` afterwards (read-only).

## Residual risk (honest gaps)

1. Counts only; an operator still needs `/offers/{id}/impact` for ids and states
   of the derived work.
2. No automatic pause or correction on audit; that requires a human transition,
   by design.
3. Published artifacts that lost their schedule row are not counted.
4. Terms-change detection, claim-free page coverage, non-symmetric acquisition
   identity, semantic applicable-terms coverage, downstream invalidation and the
   human reclassification itself remain open.

**Next smallest task:** a reviewer-recorded bulk reclassification path for the
audited offers, so an operator can demote a reviewed batch with one audit entry
per offer instead of repeating the single-offer transition by hand.
