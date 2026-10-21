# WP01 thirteenth slice — a recheck deadline cannot outlive the offer

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [freshness at capture and resume](implementation-wp01-slice12-2026-10-21.md)
**Master plan:** [§11 expiry and corrections](../docs/automation-master-plan-2026-10-21.md#11-corrections-and-impact)

The twelfth slice made capture and resume respect `recheck_at`. It also exposed
an inconsistency in how that deadline is written: every transition to `verified`
set `recheck_at = now() + 2 days`, regardless of the offer's own expiry. An offer
expiring in six hours therefore carried a recheck deadline two days after it
would be dead — a window that can never be honoured. The freshness checks would
still refuse the offer once `expires_at` passed, so nothing unsafe was published,
but the stored record claimed a review opportunity that did not exist.

## What changed

### `services/api/offers_api.py` — transition to `verified`

The deadline is now the earlier of the policy interval and the offer's expiry:

```sql
recheck_at = LEAST(now() + <policy interval>,
                   COALESCE(expires_at, 'infinity'::timestamptz))
```

- No expiry → the two-day policy, unchanged.
- A distant expiry → the two-day policy, unchanged.
- An expiry inside the policy window → `recheck_at = expires_at`, so the offer is
  never described as fresh past its own end.
- An offer verified with an expiry already in the past gets a past deadline and
  is immediately stale at the capture/resume/schedule boundaries, rather than
  inheriting two days of false comfort.

No migration and no backfill: existing rows keep their stored `recheck_at`; the
rule applies to the next verification. `RECHECK_INTERVAL` itself is still a fixed
two days — this slice only stops it from outliving the offer.

## What this does and does not prove

- **Does:** every newly verified offer has `recheck_at <= expires_at` (when it has
  an expiry), and the freshness boundaries from slice 12 read a coherent record.
- **Does not:** make the interval risk-based in any other sense (offer type,
  provider trust, claim volatility), backfill existing rows, or refuse to verify
  an already-expired offer in the first place. It does not re-fetch the page at
  the deadline; that remains the sweep/monitor's job.

## Test evidence

### Failing first

At `5807251` an offer expiring in six hours is verified with
`recheck_at = now() + 2 days`, so `recheck_at <= expires_at` is false. Both new
tests fail on that assertion; the second (distant expiry) passes before and
after, and is included to prove the policy is capped rather than replaced.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 606 passed, 26 warnings, zero skips, exit 0      (was 604; +2)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage (`services/api/tests/test_integration.py`):

- an offer expiring in six hours, set through `PATCH /offers/{id}` before
  verification, gets `recheck_at` at or before `expires_at` and still in the
  future;
- an offer expiring in thirty days keeps the two-day policy (between one and
  three days from now).

## Residual risk (honest gaps)

1. The policy is still one fixed interval; offer type, provider trust and claim
   volatility do not influence it.
2. Existing verified rows are not backfilled, so a legacy row can still carry a
   deadline beyond its expiry until it is re-verified.
3. Verification does not refuse an already-expired offer; it produces an
   immediately stale record instead. A dedicated expiry gate at promotion is
   still open.
4. Terms-change detection, claim-free page coverage, non-symmetric acquisition
   identity, semantic applicable-terms coverage, downstream invalidation and
   legacy review remain open.

**Next smallest task:** an explicit legacy audit that runs today's gate against
each stored `verified` offer and reports which ones could not earn that state
now — the inventory the plan's "reclassify legacy verified records" step needs,
without a destructive bulk migration.
