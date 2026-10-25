# WP01 twelfth slice — freshness at the capture and resume boundaries

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [bounded ToS validity and revocation](implementation-wp01-slice11-2026-10-21.md)
**Master plan:** [§11 expiry/corrections, §17 publishing gates](../../automation-master-plan-2026-10-21.md#17-scheduling-and-publishing)

Freshness was enforced at two boundaries: the transition to `scheduled`
(`_revalidate_offer`) and the publishing worker immediately before upload. Two
boundaries named in the plan were missing. `POST /offers/{id}/captures` checked
only that the offer's state allowed video, so footage could be recorded for an
offer whose recheck had lapsed whenever the state sweep had not run yet. `POST
/schedules/{id}/resume` revalidated the script hash but not the offer, so a
paused post could be re-queued against an expired or overdue offer. The upload
check was doing all the work at the last possible moment.

## What changed

### `services/api/offer_freshness.py` (new)

One read shared by both boundaries: the offer's `expires_at` (absent means no
expiry) and `recheck_at` compared with the clock. It returns a reason string
rather than a boolean, so both endpoints can say *why* they refused, and it
fails closed: a missing `recheck_at` counts as overdue (`NULL > now()` is not
true). It deliberately does not check state; callers keep their own state rules.

### Captures — `services/api/captures_api.py`

After the existing video-allowed-state check, capture registration asks for
freshness and refuses with a 409 naming the reason (`offer has expired` /
`offer recheck is overdue (recheck_at)`) and `§11 freshness`. A fresh verified
offer still records normally. No new migration: the verify transition already
sets `recheck_at`.

### Resume — `services/api/schedules_api.py`

After the script-hash check (which still wins first), resume re-runs
`_revalidate_offer` — the same state, expiry and recheck test used when a post is
scheduled — and, when it fails, reports the specific freshness reason from the
shared helper. An operator must re-verify the offer instead of re-queuing a dead
one. The publishing worker's moment-of-upload check is unchanged and remains the
last line.

## What this does and does not prove

- **Does:** all four named boundaries now consult the same expiry/recheck fact
  pack; a paused post or a new capture cannot rely on the sweep having run.
- **Does not:** make the interval risk-based — `RECHECK_INTERVAL` is still a
  fixed two days for every offer, and can extend past an offer's expiry. It does
  not re-fetch the evidence page, re-read provider terms, or invalidate captures
  and schedules that were legitimate when created.

## Test evidence

### Failing first

At `1e70bde` a capture for a verified offer with `recheck_at` one hour in the
past is recorded with 201, and a paused schedule for the same offer resumes with
200; the new 409s do not exist.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 604 passed, 26 warnings, zero skips, exit 0      (was 602; +2)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_integration.py` (2): a fresh verified offer records a
  capture; an overdue recheck and a past expiry each refuse with 409 and the
  specific reason. A paused schedule for a fresh offer resumes; the same
  schedule refuses while the recheck is overdue, and resumes after the deadline
  is restored.

## Residual risk (honest gaps)

1. `RECHECK_INTERVAL` is a fixed two days and is not derived from the expiry or
   the offer's risk; an offer expiring in six hours is still given a two-day
   recheck deadline.
2. The boundary checks use the stored fact pack; they do not re-fetch the page or
   compare its content with the snapshot.
3. A capture or schedule that was valid when created is not invalidated by a
   later lapse; only new actions are refused.
4. Terms-change detection, claim-free page coverage, non-symmetric acquisition
   identity, semantic applicable-terms coverage, downstream invalidation and
   legacy review remain open.

**Next smallest task:** stop a recheck deadline from outliving the offer it
describes — derive `recheck_at` as `min(now + policy, expires_at)` (and the same
floor for an already-verified offer near expiry) instead of a fixed two days.
