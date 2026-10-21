# WP01 implementation checkpoint — snapshot-bound verification

**Date:** 21 October 2026 (UTC)

**Status:** First WP01 integrity slice implemented and tested locally. **WP01 remains IN_PROGRESS; public autopilot is not production-approved.**

## Delivered

- Strict extraction fields with a snapshot UUID, HTTPS URL, literal value and supporting quote; unknown fields/control flags, malformed identities, non-finite confidence and invalid text are rejected.
- The API calculates completeness instead of trusting `complete=true`. Every proposed field must reference official evidence from the same offer, match its exact URL, and have a verbatim quote in retained hash-checked text. Values must occur literally in their quotes, with case/whitespace normalization and token/numeric boundaries.
- Nonempty conflict reports block verification. Stored/legacy extractions are checked again during promotion, not grandfathered by their old completeness flag.
- Current enabled Tier-A ownership is required, with exact provider matching rather than `ILIKE` wildcard semantics. Explicit source IDs must belong to that provider and remain authorized. Domain matching uses HTTPS, IDN normalization and subdomain boundaries.
- Migration `012_evidence_snapshot_text.sql` retains bounded extraction text and checks its SHA-256 at the database boundary. Legacy rows retain NULL text; no historical content is invented.
- Evidence deduplication includes URL, content hash, snapshot availability, authority and nullable source identity. Repeat submissions return the existing evidence UUID; equal bytes from different URLs/authority records do not silently inherit another record's provenance.
- The verification worker fetches a page once and submits/extracts the same untruncated text. A snapshot over 250,000 characters is held rather than silently cut. Its final URL must remain within the provider allowlist; the API checks it again.
- The worker attaches the API's returned snapshot UUID, waits for successful evidence/extraction persistence, honors server completeness, and preserves both model-reported and cross-page conflicts. Collector excerpts retain the existing 2,000-character default.
- New extraction and offer promotion serialize on the offer row inside short transactions. New extraction revokes previous verification even if its new core passes; the existing database trigger pauses scheduled posts. `clock_timestamp()` records proposal insertion time after lock acquisition.

## API compatibility and rollout

**No remote or existing application database was migrated in this delivery.**

1. Back up the target database and confirm the current migration state. Follow the existing deployment runbook and obtain the deployment owner's approval.
2. Apply migration 012 using the existing migration runner before starting the new API. It is append-only; migrations 001–011 are unchanged. Postgres 16 is the supported target (`NULLS NOT DISTINCT` requires Postgres 15+).
3. Deploy the API and verification worker together in a controlled maintenance/canary window. Keep unattended public publishing off until the remaining P0 work is accepted.
4. New official evidence submissions must include nonblank `captured_content` (maximum 250,000 Unicode characters, up to 1 MB UTF-8). The API hashes those exact text bytes. Raw text is not added to the general offer/workspace response.
5. Each extraction field now requires `value`, `evidence_id`, `evidence_url`, and `excerpt`; `confidence` is optional diagnostic data. `complete` remains accepted for compatibility but is not authoritative. Responses return server-calculated `complete` and `validation_errors`; incomplete but structurally valid proposals are retained for review, not promoted.
6. Recapture/re-extract hash-only legacy evidence. Matching new text creates a new snapshot identity instead of modifying the old row. This checkpoint does **not** bulk-demote all pre-existing verified records; keep publishing disabled until legacy records and remaining release gates are reviewed.
7. Prefer a forward fix if rollout fails. Do not remove the new column/index or restore the old hash-only uniqueness rule over new data without a reviewed migration: newer valid rows may share text across distinct URLs/authority records. Rolling back application code also restores the former weak verification behavior.

Example extraction field (illustrative, not a live offer):

```json
{
  "fields": {
    "promo_code": {
      "value": "SAVE2026",
      "evidence_id": "<UUID returned by the evidence API>",
      "evidence_url": "https://example.com/terms",
      "excerpt": "Use code SAVE2026 for verified students only."
    },
    "eligibility": {
      "value": "students",
      "evidence_id": "<same evidence UUID>",
      "evidence_url": "https://example.com/terms",
      "excerpt": "Use code SAVE2026 for verified students only."
    }
  },
  "conflicts": []
}
```

## Test evidence

- Before implementation, the new gate regression suite produced **12 failures / 1 pass**, reproducing trust in forged completeness, conflicts, unsupported evidence and malformed legacy input.
- PostgreSQL **16.15** test binaries were downloaded into the approved temporary directory from the Zonky Maven Central distribution already referenced by the repository README, and checked against its published SHA-256. A new loopback-only cluster and disposable database were created solely for this task; no `.env` or existing database URL was used.
- Tests cover fresh installation through migration 012; rollback-only schema upgrade from 001–011 with legacy evidence preserved; SQL hash constraints; API snapshot/dedup round trips; forged and missing completeness; foreign evidence; invented quotes/values; source disable/downgrade/owner changes; legacy revalidation; concurrent replacement/promotion; and scheduled-post pausing.
- Worker tests use mocked HTTP, not live provider or model services. They verify single fetch, full text/footer retention, final URL recording, source restrictions, persistence failure, server refusal, and cross-page conflict preservation.

Final command results are recorded in the master-plan implementation ledger. No live offer, OAuth, model, video rendering, browser E2E or public publishing validation is claimed by these tests.

Final combined result: **325 tests passed, zero skipped, 21 existing deprecation warnings**, including the real PostgreSQL integration and migration-upgrade cases. Python lint, compilation and TypeScript typecheck also passed. The disposable server is stopped after validation; it is not an application deployment.

## Remaining — do not mistake literal support for truth

1. **Semantic/type-specific verification:** the baseline core is still incentive (`promo_code`, `price` or `value`) plus eligibility/expiry context. Literal occurrence does not prove benefit applicability, resolve negation, distinguish initial/renewal price, or establish country/deadline/billing terms. Critical unknowns must be handled by the next WP01 slice before guarded autopilot.
2. **Acquisition provenance:** persisted data is extracted page text, not original HTML/HTTP bytes, redirect chain, signed fetch provenance or an independently trusted remote retrieval. Authorized callers can submit text; hashes prove retained-text integrity, not that a provider actually served it. Controlled fetcher identities, raw-byte storage and complete SSRF/redirect/egress defenses remain open.
3. **Long-document model extraction:** deterministic extraction sees retained text, but the existing optional model extractor still has its 8,000-character prompt slice. Versioned section-based extraction, strict gateway validation and admission evaluation remain WP01/WP07 work. The page parser is still a lightweight tag remover, not a complete document parser.
4. **Freshness and propagation:** risk-based evidence age, fresh capture/upload rechecks, provider/terms changes invalidating every downstream artifact, legacy queue review and full-package approvals remain open. Changing source authorization blocks a new verification attempt; it does not yet proactively revoke every already-verified dependent record.
5. **Authorization and publishing:** service/reviewer role separation, fail-closed upload leases, immutable approved media/metadata/account pinning, remote reconciliation and platform-policy fixes remain WP02–WP04 work.
6. **Editorial safety:** script facts are still taken from offer fields; synchronizing approved fact packs, truthful unknown/format wording, premium media QC and metadata are separate unchecked tasks.

**Next smallest task:** define offer-type completeness and unknown/conflict statuses, then add negative/renewal/region/expiry fixtures so literal quotes cannot be mistaken for claimable, universal or free offers. Keep the safety-first work-package order in the [master plan](automation-master-plan-2026-10-21.md).
