# WP01 tenth slice — per-source terms-of-service review attestation

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [mandatory extraction coverage](implementation-wp01-slice9-2026-10-21.md)
**Master plan:** [§5 source registry, §6 step 2, audit A19](../docs/automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

`robots.txt` is a machine-readable technical permission. It is not contractual
consent: a host can allow crawling and still forbid automated collection of its
terms in its terms of service. Until this slice the system proved the former and
merely assumed the latter — nothing recorded that a human had read the provider's
terms and decided automated reading was permitted. This slice records that
decision per source and refuses new machine-collected evidence without it.

## What changed

### Migration 018 — `sources`

`tos_reviewed_at`, `tos_reviewer`, `tos_reference`, with a CHECK that all three
are set together (reviewer and reference non-blank) or all are `NULL`. A
timestamp without a named reviewer is not an attestation, and the database says
so. Pre-018 sources stay `NULL` and remain readable.

### `POST /sources/{id}/tos-review`

- Body: `reference` (3–500 characters, must contain a non-space) pointing at the
  terms/ticket/document the reviewer read, and an optional `reviewer`.
- The reviewer is bound from the authenticated reviewer token when present;
  otherwise the explicit body field is recorded (service callers and open-dev
  mode). With neither, the request is a 403 — an unattributed attestation is not
  an attestation.
- Re-recording replaces the previous values; the audit log
  (`tos_review:recorded`) keeps the history. An unknown source is a 404.
- `GET /sources` exposes the three fields so the dashboard and the worker can see
  which sources are cleared.

### Evidence ingest — `services/api/offers_api.py`

- Machine-collected evidence (a `provenance` record, i.e. `raw` bytes + fetch
  chain + signature) is refused with a 422 when the source has no recorded
  review, and when it names no source at all.
- Reviewer-attested snapshots — no provenance, a human named in the record — stay
  exempt; that is the manual path.
- `MTK_REQUIRE_TOS_ATTESTATION` defaults on; `0` is the documented
  legacy-migration opt-out, not a production setting. The flag is read per
  request, so turning it on blocks the next write without a restart.
- Evidence stored before the attestation is not rewritten or deleted; the
  requirement applies to new collection.

### Verification worker

- `_official_pages` now returns `(url, source_id)` pairs and skips a source with
  no `tos_reviewed_at` when the requirement is on, logging which source was
  skipped. It no longer fetches bytes it is not allowed to keep.
- The evidence payload carries `source_id`, so the server can attribute the
  permission check to the exact source rather than "some enabled source of this
  provider".

## What this does and does not prove

- **Does:** before any new machine snapshot is stored, a named human recorded that
  the source's terms permit automated reading, with a reference and a timestamp;
  the worker refuses to read unattested sources.
- **Does not:** judge whether the reviewer read the right document, or whether the
  terms changed after the attestation. There is no expiry or revocation flow yet —
  re-recording replaces the attestation, and an expired review is invisible to the
  system. Attestation is per source, not per URL.

## Test evidence

### Failing first

At `ccf9761` there is no endpoint, no columns and no flag: machine evidence for a
source with no review is accepted with 201, and `_official_pages` returns bare
URLs. The new tests cannot even call the endpoint.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 599 passed, 26 warnings, zero skips, exit 0      (was 591; +8)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_integration.py` (6): machine evidence for an
  unattested source is a 422 and succeeds after the review is recorded (with the
  fields exposed on `GET /sources`); the endpoint requires a reviewer (403),
  rejects a blank reference (422) and an unknown source (404); machine evidence
  must name its source; a reviewer-attested snapshot is exempt; the documented
  opt-out accepts a legacy source; the 017→018 upgrade leaves legacy rows
  unattested and the CHECK refuses a partial attestation.
- `workers/verification/tests/test_worker_snapshots.py` (2): an unattested source
  yields no page and an attested source yields `(url, source_id)`; the standard
  run now asserts the evidence names its source.

## Residual risk (honest gaps)

1. No review expiry, revocation or re-attestation trigger: terms change and the
   old attestation keeps authorising collection.
2. The reviewer's judgment is not machine-checkable; the record shows who claimed
   what, with a reference, not that the claim is correct.
3. Per-source, not per-URL or per-section-of-terms semantics.
4. Non-symmetric acquisition identity, semantic applicable-terms coverage,
   freshness, downstream invalidation and legacy review remain open.

**Next smallest task:** give the attestation a bounded validity (reviewed terms
expire) and re-check it at collection time, so a stale attestation stops
authorising new reads instead of lasting forever.
