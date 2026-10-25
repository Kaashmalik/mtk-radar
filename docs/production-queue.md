# Production Queue (v0.35 — WP-C)

One ranked "videos to make" list. Rows are created from **promoted trend
topics** (`POST /trends/{id}/promote` — offer + queue row in one transaction)
and from verified offers awaiting capture. The dashboard's `/queue` page shows
the ranked list with badges and one primary action per offer state.

## Rank formula (recomputed on read — never stored)

    rank = 0.35 · trend + 0.30 · evidence + 0.20 · freshness + 0.15 · fit

| Component | Source | Neutral when unknown |
|---|---|---|
| trend | live score of the linked trend candidate | 0 |
| evidence | 0–100 score, see below | 0 |
| freshness | linked trend's freshness score | 50 |
| fit | operator's preset fit for the video format | 50 |

Evidence is **current support**, not a snapshot count (G15). Only evidence
captured in the last 14 days counts, with `robots_allowed` true and an HTTP
status of 200 or absent. The component is:

    evidence = (40 if any official evidence else 25)
             + 30 × share of the offer's declared claims supported
             + 30 × min(1, independent sources / 2)

Declared claims are the fields the offer actually carries: `promo_code`,
`redemption_url`, `eligibility`, `value` and `claim_steps`. Independence is
distinct `source_id` values. If no current evidence exists, the component is 0.

Because the rank is computed at read time from evidence, adding a verified
snapshot lifts the row without any re-scoring job. Operator pins
(`POST /queue/reorder`) always outrank the computed order.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /production-queue` | ranked, keyset-paginated; archived excluded |
| `POST /trends/{id}/promote` | offer (state `candidate`) + queue row in one transaction, audited; 409 if already promoted |
| `POST /queue/{id}/archive` | operator removal, reason recorded |
| `POST /queue/reorder` | pin the operator's exact order; ids not listed lose their pin |
| `POST /production-queue/expire` | self-archive stale rows (batch worker cadence) |

## Auto-expiry reasons

Deterministic, server-side, visible in `archived_reason`:

- `offer_expired` — the linked offer state is `expired`
- `deadline_passed` — the row's own freshness deadline passed
- `trend_cooled` — the linked trend's **latest** observation has velocity ≤ 0,
  and the last meaningful growth (`last_growth_at`, or the first observation if
  the trend never grew) is older than 7 days. Rescanning cannot reset cooling.

## Safety model

A queue row is a **proposal**. Verification (official evidence), capture
recording, redaction review and publish approval remain exactly where they
were — the queue only decides what the operator sees first. The batch worker
runs expiry under the `collect` stage gate; a manual operator still scans and
promotes explicitly.
