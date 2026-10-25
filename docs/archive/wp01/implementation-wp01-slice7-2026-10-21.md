# WP01 seventh slice — signed fetch provenance

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [robots.txt permission record](implementation-wp01-slice6-2026-10-21.md)
**Master plan:** [§6 steps 2–3, audit A03/A19](../../automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

`fetch_identity` is a string the caller chooses. The API could prove that the
bytes matched the hash it was given, but not who produced the record — any
client with the service token could claim to be the verification worker. This
slice signs the provenance with a deployment key so a machine-evidence row is
attributable to a holder of that key.

## What this proves — and what it does not

It proves: *a process holding the deployment signing key produced this exact
record*. It does **not** prove the bytes were actually fetched: a compromised
worker can sign a lie, and because the key is symmetric the API holds it too.
Closing that gap needs asymmetric signing (API keeps only a public key) or
server-side fetching; that remains open and is recorded as such.

## What changed

### Canonical form + HMAC — `services/api/fetch_attestation.py`

A pure-stdlib module shared by both sides (the API imports it; the verification
worker adds `services/api` to `sys.path`), so there is exactly one
canonicalisation implementation.

- Only `requested_url, final_url, http_status, content_type, fetched_at,
  redirects, raw_sha256, parser_version, fetch_identity, encoding, robots` are
  covered. Unknown keys (`byte_length`, notes) are ignored.
- URLs are lower-cased, default ports dropped, empty paths become `/`, fragments
  dropped; timestamps are converted to UTC ISO-8601; redirect order is preserved.
- JSON is emitted with sorted keys, no whitespace and ASCII escapes;
  `HMAC-SHA256` over those bytes, 64 lower-case hex characters.
- Keys shorter than 32 bytes are refused (`ValueError` on sign, `False` on
  verify) instead of being used silently.

### Worker — `workers/verification/main.py`

After `fetch_identity` and the robots decision are attached, the worker signs the
provenance and sends `provenance.signature`. Without `MTK_FETCH_SIGNING_KEY` it
sends nothing and logs a warning at startup (the API then rejects the record); it
never invents a signature. A key shorter than 32 characters is logged as an error
and the sign call fails closed.

### Server — schema, validation, storage, gate, config

- `EvidenceProvenance.signature` is 64 lower-case hex or absent.
- `_validate_provenance` verifies the signature **after** the URL chain checks so
  an off-provider redirect is still reported as such. Missing key → `503`
  (deployment misconfiguration); missing/invalid signature → `422`.
- Migration `016_evidence_fetch_signature.sql` stores `fetch_signature` with a
  hex-shape CHECK. There is deliberately no “raw bytes imply signature” CHECK:
  `MTK_REQUIRE_FETCH_SIGNATURE=0` is a documented migration opt-out and a hard
  constraint would make it impossible.
- The promotion gate requires a signature for machine-collected official
  evidence; reviewer attestations stay exempt. `GET /offers/{id}` exposes it.
- `.env.example` and the compose API service document
  `MTK_FETCH_SIGNING_KEY` / `MTK_REQUIRE_FETCH_SIGNATURE`.

## Test evidence

### Failing first

At `09640ac`, `services/api/fetch_attestation.py` and the schema field do not
exist, so `test_fetch_attestation.py` fails at import and the API rejects every
provenance payload with an unknown `signature` field (or without one once the
field exists). The slice's tests cannot pass before the slice.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 548 passed, 26 warnings, zero skips, exit 0      (was 520; +28)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `services/api/tests/test_fetch_attestation.py` (15): canonical stability,
  unknown fields ignored, URL/timestamp/redirect normalisation, naive timestamps
  not signed, robots shape, roundtrip, wrong key, tampering of every signed
  field, missing/garbage/uppercase signatures, short-key refusal, and signing the
  parsed pydantic model.
- `services/api/tests/test_integration.py` (5 new): signature stored and shown,
  unsigned → 422, tampered signature → 422, missing server key → 503, opt-out
  stores an explicitly unsigned record; plus a 015→016 upgrade test proving
  legacy rows stay `NULL` and a non-hex signature is refused by the database.
- `services/api/tests/test_verification_gate.py` (3 new): missing signature
  blocks promotion, requirement on by default, opt-out works for legacy rows.
- `services/api/tests/test_provenance_schema.py` (4 new): signature shape.
- `workers/verification/tests/test_worker_snapshots.py` (2 new): the worker signs
  when configured (and any post-sign edit fails verification); no key means no
  invented signature.

## Residual risk (honest gaps)

1. **Symmetric key.** The API can forge a record as easily as the worker. The
   signature bounds *who may submit*, not that a fetch happened.
2. **Key handling is deployment work.** Rotation, storage in a vault and least
   privilege for the worker are not automated here.
3. **A compromised worker still lies**, and it can replay a genuine signature for
   bytes it no longer has — the signature covers the record, not a fresh fetch.
4. Terms-of-service attestation, long-document extraction, freshness, downstream
   invalidation and legacy review remain open.

**Next smallest task:** long-document section extraction — verification currently
refuses a snapshot above 250k characters and the rules extractor reads one blob,
so applicable terms on long pages can be missed.
