# WP01 ninth slice — extraction coverage is required at promotion

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [sectioned long-document extraction](implementation-wp01-slice8-2026-10-21.md)
**Master plan:** [§6 steps 4–5, audit A04/A13](../../automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

The eighth slice made coverage verifiable: the API recomputes the section count
from the stored snapshot and rejects a truncated claim. But coverage was optional
at ingest, so an extraction that simply omitted the record still reached the
promotion gate with nothing to check. This slice makes the record a condition of
`verified` for machine-collected evidence, while keeping reviewer-attested
snapshots and legacy rows readable.

## What changed

### Promotion gate — `services/api/offers_api.py`

- `_gate_verified` selects the stored extraction's `coverage` alongside `fields`
  and `conflicts`. The gate then runs `_coverage_problems` when
  `MTK_REQUIRE_EXTRACTION_COVERAGE` is on.
- `_coverage_problems` resolves the **machine-collected** official evidence the
  claims actually use (`reviewer IS NULL`) and:
  - returns no problem when every snapshot used is reviewer-attested — a human
    attested it, so there is no acquisition run to account for;
  - blocks with `verified requires an extraction coverage record ...` when machine
    evidence is used and the stored record is missing or empty;
  - blocks when the record does not list **every** machine snapshot the claims
    use, so a truncated run cannot cover one page and cite another.
- The requirement is fail-closed by default. `MTK_REQUIRE_EXTRACTION_COVERAGE=0`
  is the documented migration opt-out for legacy deployments; it is not a
  production setting.

### Deployment documentation

`.env.example` and `infra/docker/docker-compose.yml` describe the flag and its
default, next to the fetch-signature flags.

## What this does and does not prove

- **Does:** every machine snapshot a claim rests on was reported as examined, and
  the reported section count matches the stored text (slice 8 re-derives it at
  ingest). A worker that truncates and omits coverage can no longer be promoted.
- **Does not:** know about pages the worker read but drew no claim from; the gate
  checks the evidence the claims use. It also cannot prove a model *understood*
  each section, and sections remain paragraph groups rather than semantic
  clauses. Semantic *applicable-terms* coverage stays open.

## Test evidence

### Failing first

At `cec97fd` the gate never reads `coverage`, so a machine extraction with
`coverage = NULL` promotes successfully — exactly what the new
`test_missing_coverage_blocks_promotion` asserts must fail. There is no
`_coverage_problems` helper and no default-on flag.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 591 passed, 26 warnings, zero skips, exit 0      (was 586; +5)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_verification_gate.py` (5): missing coverage blocks a
  machine promotion; coverage must list the snapshots the claims use; a
  reviewer-attested snapshot is exempt; the requirement is on by default; the
  documented opt-out accepts a legacy row.
- `services/api/tests/test_integration.py`: all successful promotion paths now
  send coverage (end-to-end flow, snapshot round-trip, re-extraction revocation,
  concurrent proposal/promotion, typed fact-pack offers). The gate's existing
  422 cases still fail for their original reasons, joined with the coverage
  problem where applicable.

## Residual risk (honest gaps)

1. The gate checks coverage for the evidence **claims use**, not every page the
   worker fetched; a page with no extracted claim is invisible to it.
2. Coverage is a structural claim about splitting, not semantic comprehension of
   applicable terms.
3. Legacy rows previously verified stay verified; the requirement applies at the
   next promotion decision.
4. Non-symmetric acquisition identity, ToS review attestation, freshness,
   downstream invalidation and legacy review remain open.

**Next smallest task:** a per-source terms-of-service review attestation — robots
permissions are machine-checked, but no human sign-off that automated reading is
permitted by the provider's terms is captured yet.
