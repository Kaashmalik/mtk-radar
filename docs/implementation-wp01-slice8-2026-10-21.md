# WP01 eighth slice — sectioned extraction of long documents

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [signed fetch provenance](implementation-wp01-slice7-2026-10-21.md)
**Master plan:** [§6 steps 4–5, audit A04/A13](../docs/automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

Verification refused any official page above 250,000 characters (`250_000` in the
evidence schema and in the worker), and the optional LLM extractor read
`text[:8000]` — a silent cut of everything after 8,000 characters. Long terms
pages, which is exactly where the restrictions live, could therefore never be
verified. This slice replaces both behaviours with a bounded, versioned,
lossless split and an explicit coverage record that the API re-derives from the
stored snapshot.

## What changed

### Versioned splitter — `services/api/document_sections.py`

Pure stdlib, shared by the API and the worker through the same `sys.path` shim as
`fetch_attestation.py`, so producer and verifier always agree on the boundary
rule.

- `paragraph-groups/1`: consecutive paragraphs (blank-line separated) are grouped
  while the group stays within `MAX_SECTION_CHARS = 6000`; a single larger
  paragraph is cut at the last sentence end in the window, then at a word
  boundary, then hard.
- Sections are contiguous slices of the input: joining them reproduces the text
  character for character. Nothing is dropped, trimmed or summarised.
- 6,000 characters stays below the LLM prompt's 8,000-character truncation, so a
  configured model now receives the whole section instead of a cut document.
- `MAX_DOCUMENT_CHARS = 2_000_000` matches the egress byte bound. A larger
  document is **refused** for review, never cut.

### Worker — `workers/verification/main.py`, `extractors.py`

- `extract_document()` runs the existing extractor over **every** section and
  returns the section count. A claim found in a later section is still extracted.
- Two sections that disagree about a value produce a conflict
  (`document sections disagree`, with both section indexes) and the first value is
  kept for display — never the more attractive one. A conflict blocks promotion
  for reviewer triage, as before.
- Region exclusions found in different sections are unioned, so a later section
  cannot hide an exclusion.
- The worker sends `coverage` with each extraction proposal: version, total
  sections, section ceiling and the evidence UUIDs it read. Sections are counted
  per evidence row (a duplicate evidence id is not counted twice).

### Server — schema, recomputation, storage, exposure

- `EvidenceIn.captured_content` accepts up to `MAX_DOCUMENT_CHARS` (was 250,000).
- `ExtractionIn.coverage` is a strict object: version, `sections_total`,
  `max_section_chars`, non-empty `evidence_ids`; unknown keys are rejected.
- `_validate_coverage` recomputes the section count from the stored
  `captured_content` of every referenced snapshot and rejects a mismatch with a
  422 that names truncation as the likely cause. Foreign evidence ids, an unknown
  version and a different section ceiling are also 422s.
- Migration `017_extraction_coverage.sql` stores the normalised coverage; legacy
  and manual proposals keep `NULL`, and the API never invents a value for them.
  `GET /offers/{id}` exposes it.

## Test evidence

### Failing first

At `eeb5912` there is no `document_sections` module, so the section tests fail at
import; `EvidenceIn` rejects a 300,000-character snapshot; the worker raises on a
page above 250,000 characters; `ExtractionIn` rejects unknown keys, so a
`coverage` payload is a validation error; and there is no `coverage` column.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 586 passed, 26 warnings, zero skips, exit 0      (was 548; +38)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_document_sections.py` (15): version pin, empty/short
  documents, paragraph grouping, boundary splits, sentence/word/hard cuts,
  losslessness, contiguity, the default ceiling staying under the LLM limit,
  determinism and refused ceilings.
- `workers/verification/tests/test_sections.py` (6): every section is passed to
  the extractor in order, later-section claims are found, cross-section
  disagreement becomes a conflict (first value kept), agreement is not a
  conflict, and exclusions from later sections are unioned.
- `workers/verification/tests/test_worker_snapshots.py` (3): a 500k-character
  document is accepted and sectioned, coverage is posted with the recomputable
  count, a document above the ceiling is refused, and the standard run still
  posts one section for a short page.
- `services/api/tests/test_extraction_schema.py` (11): a 300k snapshot is
  accepted, and coverage shape is strict (version pattern, bounds, UUIDs,
  non-empty ids, unknown keys).
- `services/api/tests/test_integration.py` (6): coverage is recomputed, stored
  and exposed; a truncated claim, wrong version, different ceiling and foreign
  evidence are all 422; the 016→017 upgrade keeps legacy rows uncovered.

## Residual risk (honest gaps)

1. **Coverage is not yet a promotion gate.** It is verified whenever it is sent,
   and the worker always sends it, but a manual/legacy caller may omit it. Making
   it mandatory (with a reviewer exemption) is the next slice.
2. **Sections are paragraph groups, not semantic clauses.** A clause split across
   a boundary can still lose context, though no text is dropped.
3. **The count proves the split, not comprehension.** The API can prove the worker
   sectioned the stored text; it cannot prove a model "understood" every section.
   The rules extractor does run on every section.
4. **Per-section LLM cost grows linearly** with document length; prompt caching or
   a section triage step is not implemented.
5. Terms-of-service attestation, freshness, downstream invalidation and legacy
   review remain open.

**Next smallest task:** make coverage mandatory at promotion for machine evidence
(reviewer-attested snapshots exempt), so an extraction that omits it cannot earn
`verified` while legacy rows stay readable.
