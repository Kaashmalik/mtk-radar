# WP01 fourth slice — DNS-rebinding-resistant egress

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [safe egress + raw-byte provenance](implementation-wp01-slice3-2026-10-21.md)
**Master plan:** [§6 step 2, audit A19](../docs/automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

Slice 3 validated the resolved addresses but let the HTTP stack resolve the name
again when it connected. A hostile or compromised resolver could answer with a
public address during validation and with `127.0.0.1` a moment later. This slice
pins the connection to the address that was actually checked.

## What changed

`EgressPolicy.pin_addresses` (default **on**) makes each hop connect to the
validated address while keeping the provider name in both places that matter:

| Layer | Value | Why |
|---|---|---|
| TCP destination | validated IP | the resolver cannot re-point it |
| `Host` header | provider hostname (and port if non-default) | virtual hosting, on-provider checks |
| TLS `server_hostname` | provider hostname | certificate verification still names the provider |

httpcore 1.0.9 reads the `sni_hostname` request extension
(`httpcore/_sync/connection.py:106` and `:150`), so the TLS handshake uses our
name even though the socket goes to an IP. IPv6 addresses are bracketed in the
URL and in `Host`.

Three supporting decisions:

- **Redirects resolve against the logical URL.** A relative `Location` must not
  inherit the pinned IP as the new hostname; it is joined to the provider URL
  and then re-resolved, re-validated and re-pinned as its own hop.
- **No keep-alive on the verification client.** httpcore pools connections by
  origin, which is now the IP. Two provider names on one address could
  otherwise share a TLS session negotiated for the other name.
- **Ambient proxies are ignored** (`trust_env=False`). An `HTTPS_PROXY` would
  bypass the pin entirely.

`EgressResult.final_url` and `redirects` report the logical provider URLs, never
the pinned address, so provenance stored by the API stays meaningful.

## Test evidence

### Failing first

At `a1dd206`, with only the new tests and the Host-routing test helper:

```
pytest packages/source_adapters/tests/test_egress.py -q
→ 5 failed, 58 passed
```

The failures were `pin_addresses` not existing, the socket still going to
`example.com`, and neither IPv6 nor per-hop pinning being applied.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 485 passed, 26 warnings, zero skips, exit 0
ruff check services workers packages scripts   → exit 0
```

9 new tests:

- `test_socket_targets_the_validated_address` — request URL host is the
  validated IP, `Host` is the provider, `sni_hostname` is the provider.
- `test_each_redirect_hop_is_resolved_and_pinned_again` — a resolver that
  changes its answer between hops is visible in the request log, and both hops
  carry the provider authority.
- `test_relative_redirect_resolves_against_the_hostname_not_the_ip`.
- `test_dns_is_rechecked_even_when_the_name_was_seen_before` — no cross-request
  DNS cache; a second fetch that resolves privately is refused.
- `test_ipv6_pin_is_bracketed`, `test_pinning_can_be_disabled_only_explicitly`,
  `test_default_policy_pins`, `test_pinned_request_still_reports_the_logical_url`.
- `test_host_header_survives_pinning_over_a_real_socket` — a real loopback
  HTTP server confirms httpcore (not the test mock) sends `Host: example.test`
  while the socket goes to `127.0.0.1`.

## Residual risk — stated plainly

1. **No live TLS handshake is exercised by the automated suite.** Pinning is
   proven at the request-construction level and over a real socket, and
   httpcore's handling of `sni_hostname` was read in the installed source, but
   this environment has no test certificate tooling. A deployment smoke test
   against a real provider page is still required before relying on it.
2. `pin_addresses=False` exists for fixtures. It must never be set in
   production.
3. **Collector adapters still call `Fetcher.fetch`** (HTTPX auto-redirects, no
   policy). Only the verification path is protected today.
4. Trusted acquisition identity, the robots/terms permission record, long
   document extraction, freshness, downstream invalidation and legacy review
   remain open.

**Next smallest task:** route `fetch_rss`, `fetch_github_releases` and collector
`page_watch` through the same policy (they need a response shim for
`.content`/`.json()`), then design the per-source robots/terms decision record.
