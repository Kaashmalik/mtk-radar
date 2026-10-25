# WP01 second slice — offer-type terms contract and explicit fact-pack statuses

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [first snapshot-bound verification slice](implementation-wp01-2026-10-21.md) (commit `0dbd7df`, verified at `fe4764e`)
**Master plan:** [§6 steps 5–9, §12 WP01](../../automation-master-plan-2026-10-21.md#12-ordered-implementation-work-packages)

This slice closes the two WP01 remaining items:

- semantic/type-specific terms tests — negation, renewal versus initial price,
  excluded regions, ambiguous deadlines, missing critical restrictions;
- server-derived offer-type completeness and explicit
  `supported / contradicted / unknown / not_applicable` statuses, with the
  invented eligibility and zero-cost wording removed and the approved fact
  pack synchronized into script and platform-metadata fields.

It does **not** complete WP01. Acquisition provenance, long-document extraction,
freshness, downstream invalidation, legacy release review and deployment remain
open (§ *Remaining*).

## What changed

### The fact pack is server-derived, never caller-derived

New `services/api/offer_terms.py` builds one status per claim field:

| Status | Meaning |
|---|---|
| `supported` | the claim is literally present in the official snapshot **and** nothing in the quoted terms contradicts it |
| `contradicted` | the quoted official terms state the opposite |
| `unknown` | the inspected terms do not establish the claim |
| `not_applicable` | the offer type does not require this field |

Completeness is no longer a caller hint. `complete` is still accepted for
compatibility and still ignored: the server derives the pack, derives
completeness from it, and re-derives both at promotion time.

The claim vocabulary expanded from 6 to 9 fields:

```
promo_code  price  value  benefit_type  eligibility  regions  expiry  renewal  auto_renew
```

### Semantic checks that abstain instead of guessing

Detection is deliberately narrow and sentence-scoped, so a phrase about one
thing cannot contradict a claim about another:

- **Negation/exclusion** — a cue must sit in the *same sentence* as the quoted
  value (`"Shipping is not free. The plan costs $10 per month."` does **not**
  contradict a `$10` price). Decimal points are not sentence boundaries.
- **Renewal versus initial price** — a price claim must declare `basis`
  (`initial` or `renewal`). No basis inside a renewal clause → `unknown`.
  `basis=initial` next to a renewal clause → `contradicted`. A renewal figure
  can never be presented as the price a viewer pays first.
- **Excluded regions** — `regions` claims carry `excluded_regions`. A
  `worldwide` claim with any exclusion is `contradicted`; an exclusion the claim
  does not record is `unknown`.
- **Ambiguous deadlines** — only a specific date is `supported`. `no expiry`,
  `never expires`, `ongoing`, `TBD`, `end of year` are `unknown` with the reason
  *"no expiry stated in the inspected terms — this is not proof that the offer
  never expires"*.
- **Free versus free-adjacent** — `benefit_type=free` needs a free *benefit* cue.
  `"Members get free shipping"` is `unknown`, not a free offer.
- **Classified claims** (`benefit_type`, `auto_renew`) hold the server's
  normalization, not page text, so literal-support checking is replaced by cue
  matching. Everything else must still be quoted verbatim.

### Offer-type checklists (§6 "Required fact-pack gates by format")

| offer type | fields that must be `supported` |
|---|---|
| `free_trial` | value, benefit_type, eligibility, expiry, renewal, auto_renew |
| `credits` | value, benefit_type, eligibility, expiry |
| `student_perk` | value, benefit_type, eligibility, expiry |
| `model_access` | value, benefit_type, eligibility |
| `domain_discount` | price, eligibility, renewal, auto_renew |
| `release_explainer` | value, eligibility, expiry |
| `walkthrough` | value, eligibility, expiry, renewal |

Checklists are **additive**: an offer type with no published contract (e.g.
`coupon`, `discount`) keeps the previous baseline core — one incentive
(`promo_code`/`price`/`value`) plus one context claim (`eligibility`/`expiry`) —
and the pack records that its fields are not covered by a type contract. The
existing gate is never loosened; known types get stricter.

A `contradicted` claim is always reported, including on optional fields: a
conflict is quarantined for review, never auto-corrected into the more
attractive claim.

### Persistence and the promotion gate

Migration `013_extraction_fact_pack.sql` adds `fact_pack JSONB` (object-only
`CHECK`) and `offer_type TEXT` to `extractions`. The pack is stored so a reviewer
can see *why* a proposal passed or was blocked.

The gate re-derives the pack against the **current** `offers.offer_type`, never
the stored one, and `offer_type` is now a material field: re-typing an offer
demotes a verified record to `evidence_needed`. A stale pack cannot be
inherited.

### Truthful wording (A13)

`services/api/scriptgen.py` and `services/api/schedules_state.py` no longer turn
an unknown into a selling point:

| Before | After |
|---|---|
| `Open eligibility — but confirm current terms` | `Eligibility is not stated in the inspected terms — confirm the current audience on the official page. Do not present this offer as open to everyone.` |
| `expiry — see terms` | `no expiry stated in the inspected terms` (explicitly *not* "never expires") |
| `ongoing cost: none stated` | `ongoing cost not stated in the inspected terms. Unknown renewal is not free…` |
| `Genuine end-to-end claim of …` | `Official offer walkthrough: … Results depend on your account and eligibility.` |
| `Check official terms for current eligibility.` | `Eligibility not stated in the inspected terms — check the official terms for the current audience.` |

### Worker extraction

`workers/verification/extractors.py` now proposes the typed claims so the
contract has something to check: `benefit_type` (free / discounted /
application_based), `regions` with `excluded_regions`, `auto_renew`, and
`basis` on prices. Every typed value is still verified by the server; a wrong
guess becomes `unknown`, not a claim.

## Test evidence

### Failing first

The new/changed suites were run in a throwaway worktree at `fe4764e` with only
the new test files copied in:

```
pytest services/api/tests/test_verification_gate.py workers/verification/tests/test_verification.py -q
→ 13 failed, 30 passed
pytest services/api/tests/test_offer_terms.py -q
→ 1 collection error (module offer_terms does not exist)
```

The 13 behavioural failures map one-to-one to this slice:

- `test_free_trial_without_billing_terms_is_blocked`
- `test_free_trial_with_every_required_claim_passes`
- `test_negated_eligibility_contradicts_the_claim`
- `test_renewal_price_never_passes_as_the_initial_price`
- `test_ambiguous_deadline_stays_unknown`
- `test_free_benefit_is_classified`
- `test_discount_is_classified`
- `test_price_inside_a_renewal_clause_is_labelled_renewal`
- `test_price_outside_a_renewal_clause_is_labelled_initial`
- `test_worldwide_claim_is_extracted`
- `test_eligible_regions_are_extracted`
- `test_excluded_region_is_recorded`
- `test_auto_renew_yes_and_no`

### Passing after

Against a disposable **PostgreSQL 16.15** (`postgres:16-alpine`, DSN
`postgresql://mtk:mtk@127.0.0.1:55499/mtk_verify`):

```
pytest packages/object_storage/tests services/api/tests \
       workers/verification/tests workers/render/tests workers/publishing/tests \
       workers/metrics/tests workers/batch/tests workers/monitor/tests -q
→ 394 passed, 26 warnings, zero skips, exit 0
```

```
ruff check services workers packages scripts   → exit 0
compileall -q services workers packages        → exit 0
pnpm typecheck                                 → exit 0
```

Word-guarantee regression tests (`test_scriptgen.py::TestUnknownWording`,
`test_schedules.py::TestPlatformMetadataUnknownWording`) lock the A13 wording in
place: unknown eligibility never renders as "open eligibility" or "open to
everyone", an absent expiry is never promoted to "never expires", unknown renewal
is never rendered as "none stated" or "no ongoing cost", contradicted
eligibility/renewal force an explicit manual-review line, and metadata no longer
claims a "genuine end-to-end claim".

Integration coverage added (real PostgreSQL, real migrations, real triggers):

- `test_fact_pack_is_persisted_and_returned` — pack returned by the API, stored
  in `extractions.fact_pack`, exposed on the reviewer-facing offer response.
- `test_fact_pack_column_accepts_only_a_json_object` — the migration `CHECK`
  rejects a JSON list.
- `test_unknown_required_claim_blocks_promotion` — a `free_trial` with only
  promo code + eligibility has `value/benefit_type/expiry/renewal/auto_renew`
  `unknown`, `complete=false`, and `→ verified` returns 422.
- `test_complete_typed_offer_promotes` — the same offer with every required claim
  quoted promotes to `verified`.
- `test_contradicted_claim_blocks_promotion` — `"Students are not eligible"`
  makes eligibility `contradicted` and blocks promotion.
- `test_retyping_an_offer_rechecks_against_the_new_contract` — `coupon → verified`,
  re-type to `free_trial`, offer demotes to `evidence_needed`, and re-promotion
  fails on the new checklist.

## Compatibility

- `complete` remains accepted and remains non-authoritative.
- Existing `coupon`/`discount` offers keep the baseline core, so previously valid
  WP01 fixtures still pass unchanged.
- `fields` now allows up to 12 entries (was 6) because typed checklists can
  require six claims at once.
- `basis` is only valid on a `price` claim and must be `initial` or `renewal`;
  `excluded_regions` is only valid on a `regions` claim. Both are hard 422s.
- The `extractions` table gains two columns; migration 013 is append-only.

## Remaining — do not mistake a status for truth

1. **Semantic coverage is narrow.** The contract detects the cues it knows and
   abstains otherwise, which is why unmapped offer types still only get the
   baseline. It is not a natural-language entailment check; a paraphrase that
   avoids every cue becomes `unknown` (safe, but not verified).
2. **Acquisition provenance is still unproven.** Persisted data is extracted page
   text, not original HTTP/HTML bytes, redirect chain or a trusted fetch identity.
3. **Long-document extraction.** The optional model extractor still slices the
   prompt at 8,000 characters; versioned section-based extraction is open.
4. **Freshness and propagation.** Evidence age, revalidation at every boundary
   and propagation to approved packages are open. Re-typing demotes one offer; it
   does not sweep downstream artifacts.
5. **Legacy records.** No bulk reclassification of existing verified records or
   queued legacy releases has been performed.
6. **Deployment.** Local tests are not a production deployment.

**Next smallest task:** preserve original HTTP/HTML bytes and fetch provenance
with trusted acquisition identities and full SSRF/egress defences — the next
unchecked WP01 item, because every status above is only as trustworthy as the
bytes it was derived from.
