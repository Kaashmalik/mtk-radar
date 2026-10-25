# WP01 eleventh slice — bounded ToS attestation validity and revocation

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [per-source terms-of-service attestation](implementation-wp01-slice10-2026-10-21.md)
**Master plan:** [§5 source registry, §6 step 2](../../automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

The tenth slice recorded who decided that automated reading of a source is
permitted, but the record never aged and could not be withdrawn. Terms change;
a review from years ago authorises collection against a document nobody has
read since. This slice bounds a review's validity and gives a reviewer an
explicit way to take the permission back.

## What changed

### Validity policy — `services/api/tos_review.py`

- A review is valid for `MTK_TOS_REVIEW_TTL_DAYS` days (default **180**,
  clamped to 1..3650; malformed values fall back to the default rather than
  disabling the bound).
- Expiry is derived from the recorded `tos_reviewed_at` — there is no second
  stored timestamp to drift out of sync with the policy. Changing the deployment
  policy therefore re-evaluates every source at once, which is the intent.
- `expires_at()` and `is_valid()` are the single implementation used by the API
  (ingest and listing); the worker consumes the computed `tos_valid` field.

### Evidence ingest — `services/api/offers_api.py`

- Machine-collected evidence (raw bytes + provenance) for a source whose review
  has expired is refused with a 422: *"…has expired; a reviewer must record a
  current review…"*. The missing-review 422 from slice 10 is unchanged.
- Reviewer-attested snapshots remain exempt: a human is attesting that one
  snapshot, not claiming a standing permission.

### Withdrawal — `DELETE /sources/{id}/tos-review`

- Requires a reviewer identity (authenticated token first, `reviewer` query
  fallback; 403 without one) and an existing source (404 otherwise).
- Clears `tos_reviewed_at`, `tos_reviewer` and `tos_reference` together, so the
  CHECK from migration 018 still holds, and writes `tos_review:revoked` to the
  audit log.
- New machine evidence for the source is then refused. Already stored evidence is
  not rewritten or deleted; reviewer-attested snapshots remain possible.

### Visibility

`GET /sources` now returns the review's computed `tos_expires_at` and a
`tos_valid` boolean alongside the slice-10 fields, so an operator can see which
sources are about to lapse before collection starts failing.

### Verification worker

`_official_pages` uses `tos_valid` when the API provides it, falling back to the
presence of `tos_reviewed_at` for an older API, and logs which source it skipped.
It no longer trusts a timestamp alone.

### Deployment documentation

`.env.example` and the compose file document the TTL and its default.

## What this does and does not prove

- **Does:** a standing permission to read a source cannot outlive the deployment
  policy, and a reviewer can withdraw it; both the API and the worker enforce the
  same decision.
- **Does not:** notice that the provider's terms changed while the review is
  still inside its window, re-read the terms, or invalidate claims already
  extracted under an older review. The TTL is deployment-wide, not per-source or
  per-document, and withdrawal does not retroactively demote verified offers.

## Test evidence

### Failing first

At `f33efa6` `_require_source_tos_attestation` only tests `IS NULL` and never
compares the timestamp with the clock, there is no `DELETE` route, `/sources`
has no `tos_valid`/`tos_expires_at`, and the worker skips only when the timestamp
is absent. The expired/revoked cases are accepted as if the review were current.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 602 passed, 26 warnings, zero skips, exit 0      (was 599; +3)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_integration.py` (2): with a one-day policy and a
  review backdated two days, machine evidence is a 422 mentioning expiry and
  `GET /sources` reports `tos_valid = false`; re-recording the review accepts the
  same payload. A reviewer-less revocation is a 403, a revocation with a reviewer
  is a 200, subsequent machine evidence is a 422, the listed source has no
  reviewer and is invalid, and an unknown source is a 404. The slice-10
  attestation test now also asserts the computed expiry.
- `workers/verification/tests/test_worker_snapshots.py` (1): a source reported
  with `tos_valid = false` yields no page.

## Residual risk (honest gaps)

1. Terms can change inside the validity window; nothing compares the reviewed
   reference with the current page.
2. Withdrawal stops new collection but does not invalidate stored evidence,
   verified offers or published artifacts derived from it.
3. The TTL is one deployment-wide number; a per-source or per-contract duration
   is not modelled.
4. The reviewer's judgment is still not machine-checkable.
5. Non-symmetric acquisition identity, semantic applicable-terms coverage,
   coverage for claim-free pages, freshness, downstream invalidation and legacy
   review remain open.

**Next smallest task:** freshness. Evidence and reviews age independently of
offer state; scheduling, capture and upload should refuse to act on a fact pack
whose evidence has passed its recheck window instead of trusting `verified`
indefinitely.
