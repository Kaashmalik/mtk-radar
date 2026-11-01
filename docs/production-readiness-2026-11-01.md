# Production-readiness gate list — 2026-11-01

Canonical go-live gate list from the 2026-11-01 five-way production-readiness
review. One page, actionable checkboxes. Companion documents: the
[EP implementation log](ep-implementation-log.md) (per-commit evidence), the
[2026-10-28 gap audit](enhancement-plan-2026-10-28-gap-audit.md) (what the
review re-checked), the [go-live checklist](go-live-checklist.md) (operator
procedure), and the [implementation roadmap](implementation-roadmap-2026-10-25.md)
(PROOF ledger). Nothing here certifies a release by itself — every open box
below blocks "production-ready".

## Marked done by the review (P0, file-verified in the tree)

- [x] **History purge (gap audit H1).** The 2026-10-12 customer
  contact/location archive, an unrelated binary and a mistakenly committed
  external project were removed from git history; the rewritten lineage was
  force-pushed (`fa05c1f` root). Full record, backup-bundle path and
  GitHub-GC caveat: [security-and-redaction.md](security-and-redaction.md)
  incident log.
- [x] **EP-05 / EP-06 / EP-07 implemented** — scene-based video (ffmpeg
  capture opt-in, 12 Mbps presets, explicit delivery flags, loudnorm
  applied-then-verified, vertical reframe, storyboard editor + page-capture
  worker, content-addressed narration, font-measured captions),
  approve-and-queue + per-platform scheduling + TikTok consent + YouTube
  quota ledger, and lease fencing + circuit breakers + durable outbox +
  worker heartbeats. See the [gap audit](enhancement-plan-2026-10-28-gap-audit.md).
- [x] **Compose env-file wiring.** Deploys boot from the generated
  deployment env file (`docker compose --env-file infra/.env …`); the compose
  file fails fast when `POSTGRES_PASSWORD` is unset — no silent dev-default
  credential on a real deploy. `scripts/deploy.sh` mints the value into
  `infra/.env` on first run.
- [x] **Timezone data pinned.** `tzdata` in `services/api/requirements.txt`
  supplies zoneinfo where the OS has none (YouTube Pacific quota day,
  schedule time zones).
- [x] **API startup guard.** The API refuses to run unauthenticated outside
  dev-open mode (explicit opt-in only: `MTK_ALLOW_UNAUTHENTICATED=1`).
- [x] **Public-HTTPS path.** cloudflared `tunnel` compose overlay publishes
  only the dashboard; the API keeps its loopback bind; `MTK_TUNNEL_TOKEN`
  carries the tunnel connector token.
- [x] **Same-pass robustness fixes** — encode timeout + lease cap, render
  SIGTERM handling, legacy media-path confinement, request size/rate
  middleware, automation-actor attribution, publishing/collector
  `ValueError` guards, TikTok ≤64 MiB up-front refusal, dashboard standalone
  output + healthcheck, extension terminal-failure cap. Knob per fix:
  [gap audit](enhancement-plan-2026-10-28-gap-audit.md) §2026-11-01.

## Execution proof still owed (review could not execute these)

- [ ] **PROOF-04 — a green CI run.** The GitHub Actions billing lock
  **persists**; do not claim CI is fixed anywhere. Interim convention: see
  the last section.
- [ ] **PROOF-05 — live private/test post per provider.** Needs the owner's
  OAuth keys; run [`scripts/provider_private_smoke.py`](go-live-checklist.md) `--live`
  and commit the JSON artifact under [`evidence/`](evidence).
- [ ] **PROOF-06 — dated real-render QC artifact.** One real ffmpeg encode
  through measured QC; store the report artifact with its date.
- [ ] **Full `pnpm verify` re-run after the 2026-11-01 fixes**, timestamped
  into `docs/evidence/` (convention below).
- [ ] **Migrations 041→044 on a real database** (`db_migrate.py` enforces
  numbering and refuses gaps; the last full real-runner proof, 2026-10-25,
  covered 001→040).

## Operator actions (owner only — no code can do these)

- [ ] Mint/check the deploy secrets: `MTK_API_TOKEN`, `MTK_WORKER_TOKEN`,
  `MTK_EXTENSION_TOKEN`, `MTK_SESSION_SECRET`, `POSTGRES_PASSWORD`
  ([go-live checklist §2](go-live-checklist.md); `scripts/deploy.sh` mints
  them into `infra/.env` on first run).
- [ ] Complete provider OAuth consent per platform and connect the accounts
  ([go-live checklist §3](go-live-checklist.md)).
- [ ] Tunnel credentials: set `MTK_TUNNEL_TOKEN` (the tunnel's connector
  token) for the cloudflared `tunnel` overlay, or terminate TLS with your
  own proxy.
- [ ] Run the first real post end-to-end, private first
  ([go-live checklist §4](go-live-checklist.md)).
- [ ] Confirm backup off-site wiring: `MTK_S3_*` configured so
  `infra/backup.sh` copies every dump off-host and **a failed copy fails
  the backup**; confirm the monthly drill timer is armed.
- [ ] Decide the local object-store source: upstream MinIO gated all free
  image pulls on 2026-11-01 (Docker Hub repo deleted; quay.io refuses
  anonymous pulls with 401). Options: authenticated `docker login quay.io`
  for the compose storage profile, `MTK_S3_*` pointed at an external
  S3-compatible store (AWS/R2/B2), or a replacement image. Until decided,
  the stack runs with media on named volumes — fully functional
  single-host, but without multi-host `s3://` media refs.
- [ ] Delete the pre-rewrite backup bundle
  (`D:\MalikTech\mtk-radar-pre-rewrite.bundle`) after verifying the rewritten
  history — the bundle still contains the purged personal data.
- [ ] Re-clone (or hard-reset) every existing clone to the rewritten
  history; treat any old-lineage fork/clone as still containing the purged
  data. If caches of the old commits matter, request an accelerated GitHub
  GC via Support.

## Interim evidence convention while CI is billing-locked

Until PROOF-04 closes, no document may cite CI as proof. The accepted
substitute: after every significant pass, run `pnpm verify`, then commit the
full timestamped output and a metadata sidecar under
[`evidence/`](evidence):

```
docs/evidence/verify-pnpm-YYYY-MM-DD.log     # full stdout+exit status
docs/evidence/verify-pnpm-YYYY-MM-DD.json    # commit, date, platform, counts
```

The existing pattern to follow is the
[2026-10-25 evidence log](evidence/verify-pnpm-2026-10-25.log) and its
[metadata sidecar](evidence/verify-pnpm-2026-10-25.json). A claim without a
committed artifact is a proposal, not a proof.
