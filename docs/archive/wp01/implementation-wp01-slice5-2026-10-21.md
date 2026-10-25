# WP01 fifth slice — collector adapters through the egress policy

> **Historical.** Superseded by the [implementation roadmap](../../implementation-roadmap-2026-10-25.md) and the [EP implementation log](../../ep-implementation-log.md). Kept for the audit trail; test counts and statuses are historical.


**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [DNS-rebinding-resistant egress](implementation-wp01-slice4-2026-10-21.md)
**Master plan:** [§6 step 2, audit A19](../../automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

Slice 4 pinned verification fetches against DNS rebinding, but the discovery
collectors (`fetch_rss`, `fetch_github_releases`, collector `page_watch`) still
used `Fetcher.fetch` — polite, auto-redirecting, and entirely unguarded against
SSRF. A malicious feed URL or crafted GitHub redirect could point the collector
at the metadata service or an internal host. This slice routes every adapter
fetch through the same egress policy as verification.

## What changed

`Fetcher.fetch_policy(url, *, headers, params, policy)` — new method on
`packages/source_adapters/client.py`. It reuses the existing `safe_fetch`
(hop-validated redirects, bounded body, pinned connection, public addresses
only) and reconstructs an `httpx.Response` so existing collection code
(`.content`, `.json()`, `raise_for_status()` semantics) keeps working. A
non-2xx final status raises; a policy violation raises `EgressError`.

All three adapters now opt in:

| Adapter | Change |
|---|---|
| `fetch_rss(feed_url, fetcher, *, policy=None)` | `fetch_policy` with the feed `Accept` header; `policy` defaults to `EgressPolicy()` |
| `fetch_github_releases(repo, fetcher, token, per_page, *, policy=None)` | `fetch_policy` with `Accept` + optional `Authorization`; `policy` defaults to `EgressPolicy()` |
| `fetch_page_snapshot(..., policy=None)` | Collector path now uses `fetch_policy(EgressPolicy())`; provenance is still attached only on the explicit verification path |

Callers that need an exception (local test fixtures, legacy internal feeds) pass
an explicit permissive policy — e.g.
`EgressPolicy(allow_plain_http=True, allow_private=True, allowed_ports={8099})`.
The default stays strict: HTTPS, port 443, public addresses only.

## Test evidence

### Failing first

At `f56bb9e`, with only the new and changed test files:

```
pytest packages/source_adapters/tests/test_egress.py workers/verification/tests -q
→ 2 failed (the Fetcher fakes lacked fetch_policy and there was no
   fetch_policy coverage at all)
```

The failing-first point is small because the module under test is thin: the
policy machinery was already proven in slices 3–4; this slice is the wiring.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 492 passed, 26 warnings, zero skips, exit 0
ruff check services workers packages scripts   → exit 0
compileall -q services workers packages        → exit 0
pnpm typecheck                                 → exit 0
```

9 new tests in `packages/source_adapters/tests/test_egress.py::TestFetchPolicy`:

- `test_returns_final_response_for_collector_code` — `.status_code`, `.content`,
  and logical `resp.url` (provider hostname, not the pinned IP).
- `test_private_redirect_is_refused_for_collectors_too` — SSRF through a
  collector redirect is blocked.
- `test_non_2xx_final_raises_like_fetch` — `HTTPStatusError` preserved.
- `test_params_reach_the_first_hop_only` — query params survive pinning.
- `test_custom_headers_reach_the_request` — e.g. `Accept: application/rss+xml`
  merges over client defaults.
- `test_http_is_refused_by_default` / `test_http_allowed_with_explicit_permissive_policy` —
  the strict opt-in and the fixture escape hatch.
- Plus the fakes in two test files were updated to implement `fetch_policy`
  (they previously failed with `AttributeError`).

## Residual risk

1. RSS/feed content itself is not sanitized: `feedparser.parse(resp.content)`
   and GitHub JSON parsing trust the upstream payload (parsing bugs are out of
   scope for this slice; the policy only guards transport).
2. No per-source robots/terms permission record yet — the fetch is bounded and
   polite but does not consult `robots.txt`.
3. Trusted acquisition identity, long-document extraction, freshness,
   downstream invalidation and legacy review remain open.

**Next smallest task:** the per-source robots/terms decision record, or the
trusted acquisition identity (the API cannot yet prove which process fetched the
bytes — `fetch_identity` is a claim, not an attestation).
