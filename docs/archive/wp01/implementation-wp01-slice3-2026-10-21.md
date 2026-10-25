# WP01 third slice — safe egress, raw-byte retention and fetch provenance

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slices:** [snapshot integrity](implementation-wp01-2026-10-21.md) ·
[offer-type fact pack](implementation-wp01-slice2-2026-10-21.md)
**Master plan:** [§6 steps 2–3, §7, §12 WP01, audit A19](../../automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

Until this slice, verification stored the *derived text* of a page. Nothing
proved the provider ever served it, nothing stopped the verifier from being used
to probe an internal network, and nothing recorded where a redirect actually
went. This slice closes the byte-and-provenance half of the WP01 remainder.

## What changed

### One choke point for outbound verification fetches

New `packages/source_adapters/egress.py`. Every verification fetch now has to
pass:

- **Scheme** — HTTPS only. Plain HTTP is refused unless a caller explicitly
  opts in *and* names the permitted port (used by local fixtures).
- **Credentials** — URLs containing a username or password are refused; the
  verifier never fetches as a user.
- **Host** — `localhost`, `metadata.google.internal` and friends are blocked.
- **Address** — the hostname is resolved and **every** answer must be a global
  unicast address. One private answer rejects the whole name, so a rebinding
  attempt cannot win by listing a public address alongside `127.0.0.1`. IP
  literals are checked directly. Multicast is rejected explicitly because
  Python's `ipaddress` reports it as `is_global` on current versions.
- **Port** — only permitted ports (443 by default).
- **Redirects** — followed manually, one hop at a time, with the full policy
  re-applied to each hop. A permitted page cannot bounce to an internal one.
- **Size** — the body is streamed and bounded (2,000,000 bytes by default).
- **Content type** — image/video/audio/octet-stream/zip/PDF payloads are
  refused as "not reviewed text".

An HTTP error status is **returned**, not raised: a 503, login wall or challenge
means *unavailable*, never proof that an offer ended or is valid (§6 step 2).

### The exact bytes are now retained

`fetch_page_snapshot(..., policy=...)` returns the unmodified response body plus
a provenance record. The worker posts:

- `raw_content_b64` — the exact bytes, base64-encoded on the wire;
- `provenance` — requested URL, final URL, HTTP status, content type, fetch
  time, redirect chain, raw SHA-256, byte length, charset, parser version and
  the acquisition identity.

Migration `014_evidence_fetch_provenance.sql` adds `raw_content BYTEA`,
`raw_hash`, `requested_url`, `fetch_status`, `fetch_content_type`, `fetched_at`,
`fetch_redirects JSONB`, `parser_version` and `fetch_identity` to `evidence`.

The server never trusts the caller:

| Check | Failure |
|---|---|
| base64 decodes, non-empty, ≤ 2,000,000 bytes | 422 at the schema |
| `raw_hash = sha256(raw_content)` recomputed server-side | 422 + database `CHECK` |
| provenance requires raw bytes, and vice versa | 422 |
| `evidence.url` equals `provenance.final_url` | 422 |
| redirect chain ends at the final URL | 422 |
| every URL in the chain is HTTPS and on a currently enabled Tier-A provider domain | 422 |
| `fetched_at` has a timezone and is not in the future | 422 |

### An unavailable page is not evidence

`fetch_page_snapshot` returns a 503/challenge body rather than raising, so the
worker can log it. The worker then **skips** it: a non-2xx response is never
posted as official terms. If no page is usable, no extraction is posted at all —
otherwise a transient outage would overwrite a previous truthful proposal with
silence. Extraction that legitimately finds nothing on a readable page is still
recorded.

### Promotion now requires the bytes

`_gate_verified` refuses `verified` when a supporting official snapshot came
from a machine and has no raw bytes, requested URL or parser version:

> verified requires preserved raw page bytes and fetch provenance for official
> evidence (1 snapshot(s) missing); recapture with the acquisition worker

A **reviewer-attested** snapshot (a human recorded in the audit log) is exempt —
there is no fetch to prove for a hand-entered record. The check is on by default
(`MTK_REQUIRE_FETCH_PROVENANCE=1`); only an explicit `0/false/no/off` disables it
for a deployment still migrating legacy evidence.

Text-only evidence can still be stored and extracted — it simply cannot earn
`verified`. That keeps legacy rows readable without letting them masquerade as
byte-backed proof.

## Test evidence

### Failing first

In a throwaway worktree at `fe4764e`, with only the new/changed test files
copied in:

```
pytest services/api/tests/test_provenance_schema.py \
       services/api/tests/test_verification_gate.py -q
→ 19 failed, 18 passed
```

Of those 19, **14 belong to this slice** (11 provenance-schema cases, the
`no_raw_provenance` gate case, and the two `TestFetchProvenanceGate` cases); the
other 5 are slice-2 offer-type tests carried in the same modified file, which
also fail at this baseline because slice 2 is still uncommitted.

Two collection errors, because the code did not exist:

```
packages/source_adapters/tests/test_egress.py   → ModuleNotFoundError: source_adapters.egress
workers/verification/tests/test_worker_snapshots.py → ImportError: EgressPolicy
```

### Passing after

Against a disposable **PostgreSQL 16.15** (`postgres:16-alpine`, DSN
`postgresql://mtk:mtk@127.0.0.1:55499/mtk_verify`):

```
pytest packages/object_storage/tests packages/source_adapters/tests \
       services/api/tests workers/verification/tests workers/render/tests \
       workers/publishing/tests workers/metrics/tests workers/batch/tests \
       workers/monitor/tests -q
→ 476 passed, 26 warnings, zero skips, exit 0
```

`packages/source_adapters/tests` was added to `scripts/verify.sh` so these
checks cannot silently rot.

```
ruff check services workers packages scripts   → exit 0
compileall -q services workers packages        → exit 0
pnpm typecheck                                 → exit 0
```

82 new tests: 55 egress-policy, 11 provenance-schema, 8 real-PostgreSQL
integration, 5 gate, 3 worker.

New integration coverage:

- `test_raw_bytes_and_provenance_are_preserved` — stored `BYTEA` equals the
  captured bytes, `raw_hash` matches, and the offer response exposes
  `raw_preserved`/`raw_hash`/`parser_version` but never the raw body.
- `test_tampered_raw_hash_is_rejected` — a caller-supplied hash cannot disagree
  with the bytes.
- `test_off_provider_redirect_chain_is_rejected` — `evil.test` in the chain is a
  422 even though the final URL is on the provider domain.
- `test_evidence_url_must_be_the_final_fetched_url`.
- `test_future_fetch_time_is_rejected`.
- `test_verification_requires_raw_provenance_on_real_database` — the extraction is
  `complete=true`, yet `→ verified` is 422 with the recapture message.
- `test_raw_snapshot_database_check_rejects_alteration` — direct `UPDATE` of the
  bytes trips the `CHECK`.
- `test_fetch_provenance_migration_preserves_legacy_and_checks_raw_hash` — upgrade
  from 001–013 leaves legacy rows `NULL` and enforces the new hash constraint.

New worker coverage:

- `test_provenance_and_raw_bytes_are_forwarded_to_the_api` — the worker sends the
  exact bytes plus provenance and stamps its `fetch_identity`.
- `test_verification_fetch_uses_the_egress_policy` — verification passes an
  `EgressPolicy`, so the collector fetch path is not silently reused.
- `test_unavailable_page_is_not_stored_as_terms` — a 503 must not become official
  evidence *and* must not post an empty extraction over a previous proposal.

## Compatibility

- Evidence without raw bytes/provenance is still accepted and stored (legacy and
  reviewer-attested paths).
- `MTK_REQUIRE_FETCH_PROVENANCE=0` disables only the promotion requirement, not
  the validation of provenance that *is* supplied.
- Collection adapters keep the original `Fetcher.fetch` path (polite rate limit,
  no provenance) because they only produce discovery leads. Verification uses
  `Fetcher.safe_fetch`.
- `Fetcher` now holds a second, non-redirecting HTTP client. `close()` closes
  both.

## Remaining — this is not a complete SSRF defence

1. **DNS rebinding is still open.** The name is resolved and validated, but the
   connection is not pinned to the validated address. A resolver that answers
   public during validation and private at connect time wins. Closing this needs
   a pinned-IP transport (connect to the checked address with SNI/Host preserved)
   — the next hardening step.
2. **Trusted acquisition identity is not enforced.** `fetch_identity` records
   *what the worker says it is*; the API does not verify a signature over the
   bytes. A compromised worker could still submit plausible bytes it never
   fetched. Real attestation needs server-side fetching or a signed,
   key-pinned fetcher.
3. **Collection adapters are unguarded.** Only the verification path uses the
   egress policy; `fetch_rss`/`fetch_github_releases`/collector `page_watch`
   still call `Fetcher.fetch` directly.
4. **No robots/terms policy record yet.** The fetch is bounded and polite but
   does not consult `robots.txt` or store a per-source permission decision.
5. **Long-document extraction, freshness, downstream invalidation and legacy
   review** remain open from the earlier slices.

**Next smallest task:** pin the resolved address in the transport so DNS
rebinding cannot redirect the connection, then apply the same policy to the
collector adapters.
