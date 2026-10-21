# WP01 sixth slice — robots.txt permission record

**Date:** 21 October 2026 (UTC)
**Work package:** WP01 — P0 evidence and verification integrity (still **IN_PROGRESS**)
**Preceding slice:** [collector adapters through the egress policy](implementation-wp01-slice5-2026-10-21.md)
**Master plan:** [§3 source registry, §6 steps 2–3](../docs/automation-master-plan-2026-10-21.md#6-official-verification-and-source-attribution)

Slice 5 made every adapter fetch policy-bound, but nothing asked the provider
whether the read was permitted. A three-second delay and a bounded body are
politeness, not permission. This slice consults `robots.txt` **before** the
verification worker reads an official page and records the answer with the
evidence, so a later reviewer can see why the bytes were allowed to exist.

## What changed

### Decision function — `packages/source_adapters/permissions.py`

`check_robots(domain, *, fetcher, user_agent, policy, clock, path)` returns a
frozen `RobotsDecision(domain, robots_url, checked_at, allowed, status, reason)`.
The `robots.txt` read itself goes through `safe_fetch`, so it inherits the
HTTPS-only / public-address / pinned / bounded policy from slices 3–5.

Fail-closed matrix:

| `robots.txt` result | Decision | Why |
|---|---|---|
| `2xx`, parsed, path allowed | allowed | RFC 9309 matching via `urllib.robotparser` |
| `2xx`, parsed, path disallowed | denied | explicit refusal |
| `400/404/410/451` | allowed | no published policy |
| `401/403` | denied | auth wall is not consent |
| `429` | denied | rate limit is not consent |
| every `5xx` | denied | policy unreadable |
| egress-policy refusal / transport error | denied | cannot verify permission |
| unparseable body, non-bare host | denied | never guess a policy |

### Worker — `workers/verification/main.py`

`Verifier._permission(url)` caches one decision per host for the run. Before
each official page fetch the worker checks the decision and, when denied, skips
the page with a warning — nothing is fetched, stored or extracted. When the page
is read, the decision travels with the provenance payload:

```json
"robots": {
  "robots_url": "https://example.com/robots.txt",
  "checked_at": "2026-10-21T11:59:00+00:00",
  "allowed": true,
  "status": 200
}
```

### Server — schema, validation, storage, gate

- `RobotsPermission` in `services/api/schemas.py` refuses an `allowed` decision
  that hides an auth wall, rate limit or server error (`status` must be present
  and not 401/403/429/≥500).
- `_validate_provenance` now requires `robots`, rejects `allowed != true`,
  requires a timezone, rejects a future `checked_at`, requires
  `checked_at <= fetched_at`, and requires the URL to be
  `https://<fetched-host>/robots.txt`.
- Migration `015_evidence_robots_permission.sql` stores
  `robots_url / robots_checked_at / robots_allowed / robots_status`, requires the
  record to be all-or-nothing, and requires `robots_allowed IS TRUE` whenever raw
  bytes are retained. That last constraint is `NOT VALID`: rows captured between
  migrations 014 and 015 keep their bytes but are re-checked by the gate.
- `_provenance_problems` (the promotion gate) now also requires a robots record
  for machine-collected official evidence; reviewer-attested snapshots remain
  exempt because a human action, not a fetch, produced them.
- `GET /offers/{id}` exposes the robots fields next to the existing provenance.

## Test evidence

### Failing first

At `82be2b7` the module under test did not exist:

```
pytest packages/source_adapters/tests/test_permissions.py
→ ModuleNotFoundError: source_adapters.permissions
```

The same is true of the new schema fields, the migration and the gate columns, so
the slice's tests cannot pass before the slice.

### Passing after

```
pytest (full suite, isolated PostgreSQL 16.15)
→ 520 passed, 26 warnings, zero skips, exit 0      (was 492; +28)
ruff check services workers packages scripts       → exit 0
compileall -q services workers packages            → exit 0
pnpm typecheck                                     → exit 0
```

New coverage:

- `packages/source_adapters/tests/test_permissions.py` (13): allow, disallow,
  path scoping, other user agents, 404, 401/403, 429, 503, egress refusal,
  transport failure, non-bare host, exact provenance shape.
- `services/api/tests/test_provenance_schema.py` (7 new): allowed decision
  parsed, no raw bytes, server error/auth wall/rate limit/absent status rejected,
  refusal representable, bad URL rejected.
- `services/api/tests/test_integration.py` (4 new): robots is stored and shown,
  missing decision → 422, disallowed decision → 422, decision from another host
  → 422, plus a 014→015 upgrade test proving legacy bytes keep no invented
  permission and new rows require one.
- `services/api/tests/test_verification_gate.py` (2 new): missing and disallowed
  robots block promotion.
- `workers/verification/tests/test_worker_snapshots.py` (3 new): refusal prevents
  the fetch and the evidence, one check per host, decision forwarded verbatim.

## Residual risk (honest gaps)

1. **Terms of service are not machine-checkable.** Robots.txt is an automated
   signal; a provider's ToS is a legal/human judgement. No per-source ToS review
   attestation is recorded yet — a robots-permitted page can still be read
   against a ToS that forbids it.
2. **The decision is not persisted between runs.** The worker re-checks once per
   host per sweep (a handful of extra requests), which is conservative but not
   cached in the registry.
3. **`robots.txt` itself can lie or lag.** The record proves what the host said
   at fetch time, not that the underlying offer is real.
4. Trusted acquisition identity, long-document extraction, freshness, downstream
   invalidation and legacy review remain open.

**Next smallest task:** trusted acquisition identity — the record says
"verification-worker fetched this", but nothing cryptographically binds the bytes
to that process.
