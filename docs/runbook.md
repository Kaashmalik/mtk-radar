# MTK RADAR AI — Operational Runbook

Week 12 (master plan §18): deployment, backup/restore, credential and source
recovery, and the first production review. This file is the source of truth
for operating the platform; the master plan remains the source of truth for
*why* these rules exist.

Companion documents:
- [`go-live-checklist.md`](go-live-checklist.md) — what the operator adds
  (keys, social connections) and the first real post.
- [`cost-laptop-vps-2026-10-22.md`](cost-laptop-vps-2026-10-22.md) — cost
  scenarios, laptop hosting, student/free resources and the split-VPS fallback
  when the laptop is off.
- [`notifications.md`](notifications.md) — monitor webhook/email setup,
  payload schema, Gmail/SMTP example and free-Supabase boundaries.
- [`render-qc.md`](render-qc.md) — measured render-quality thresholds,
  intentional-still exemptions, dead-letter triage and the fail-closed gate.
- [`master-plan-traceability.md`](master-plan-traceability.md) — every master
  plan item mapped to its code and its proof.
- [`third-party-notices.md`](third-party-notices.md) / [`upgrade-checklist.md`](upgrade-checklist.md)
  — the open-source inventory and how it is upgraded.
- [`open-source-integrations.md`](open-source-integrations.md) — why each
  external project was adopted or not.

---

## 1. Deployment

```bash
bash scripts/deploy.sh --with-workers          # one command: secrets + build + boot + smoke check
# optional S3-compatible storage alongside workers:
bash scripts/deploy.sh --with-workers --with-storage
# or, manually (builds immutable images):
# docker compose -f infra/docker/docker-compose.yml --profile workers up -d --build
```

`scripts/deploy.sh` generates `infra/.env` with strong random tokens on first
run, builds the immutable images, starts the stack, waits for health, and
runs a connected smoke check (authorized `/attention` + dashboard `/api/health`).
Schema migrations apply automatically before the API starts (the one-shot
`migrate` service runs `services/api/db_migrate.py`; re-running only applies
new files). To upgrade a running host: `git pull && bash scripts/deploy.sh --with-workers`.

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD for anything real
./scripts/mtk-start.sh        # API + dashboard + migrations + worker profile
```

### Production images, private networking and dev mode (v0.31)

The base compose file is now deployment-shaped:

- `api`, `dashboard` and the shared worker image are **built once** and start
  without `pip install`, `npm install` or `apt-get` on every restart.
- PostgreSQL, Redis and MinIO are **not published to the host**; only the
  dashboard (`3000`) is exposed and the API binds to `127.0.0.1:8000` for a
  local reverse proxy. Nothing else on the network can reach the database.
- Media lives on explicit named volumes (`storage-data`, `render-projects`,
  `storage-cache`) — `docker compose down` keeps them; `down -v` destroys them.
- The dashboard has a `/api/health` liveness probe; the API `/health` probe
  already checks the database and migration readiness.

For host-side development (published Postgres/Redis/MinIO ports, live-reload
API, Next dev server with a bind mount):

```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/docker-compose.dev.yml up --build
```

Never use the dev override on a reachable host: it republishes the database
and cache ports.

### Laptop-first start, heartbeats and the Start button (v0.30)

`scripts/mtk-start.sh` is the host-side launcher. It starts Postgres/Redis,
builds and starts the API/dashboard, applies pending migrations, then starts
the long-running workers. The dashboard’s **Start automation** button never
talks to Docker: `POST /automation/start` runs a fresh preflight, refuses to
arm if any expected worker is missing/stale, and then writes a safe policy
preset (assisted or private autopilot; public autopilot needs an explicit
acknowledgement).

- **Needs You** (`/attention`) aggregates redaction reviews, offer/post
  approvals, render/QC failures, publishing holds, expiries, corrections,
  reconnect prompts, budget exhaustion and worker health.
- **Worker health** (`GET /workers`) comes from `worker_heartbeats`; a worker
  posts every 60s. A stale/missing beat is an alert. Capture is intentionally
  absent because it is a human-operated browser, not a daemon.
- **Autopilot requires an alert channel.** `GET /automation/preflight?mode=
  autopilot_private` fails when neither webhook nor email is configured, so an
  unattended laptop cannot fail silently. Assisted mode only warns.
- A sleeping/off laptop cannot alert you. Keep an external uptime check on the
  API/dashboard once the pilot becomes relied upon.
- systemd user unit and desktop shortcut: `infra/systemd/mtk-radar.service`,
  `infra/desktop/mtk-radar.desktop`; install notes in
  `infra/systemd/README.md`. Stop with `./scripts/mtk-stop.sh` (volumes kept).

- API: `http://localhost:8000` (FastAPI; `/health` wired to CI + compose healthcheck)
- Dashboard: `http://localhost:3000`
- All services `restart: unless-stopped`; postgres data lives in the `pgdata` volume.
- Never commit `.env`. Platform tokens live in the deployment environment or a
  vault (§7) — the database stores credential *references* only.

### Migrations

```bash
python services/api/db_migrate.py            # apply pending (001…024…), recorded in schema_migrations
```

Policy: numbered SQL files under `services/api/db/migrations`, strictly ordered,
each applied in one transaction, never re-run. A numbering gap aborts the run
(a lost/renamed migration must be investigated, not skipped). New migrations
continue the `NNN_name.sql` sequence.

## 2. Backup & restore

```bash
./infra/backup.sh 14          # pg_dump -Fc; keep 14 days (tune to your policy)
./infra/restore.sh backups/mtk_radar_YYYYMMDDTHHMMSSZ.dump mtk_radar_drill
```

- Automation (v0.18): `infra/systemd/` ships install-and-forget timers —
  `mtk-radar-backup.timer` (daily 03:00, `Persistent=true` catch-up) and
  `mtk-radar-restore-drill.timer` (monthly, newest dump → throwaway DB). See
  `infra/systemd/README.md`; on hosts without systemd, cron lines are included.
- Verified drills + off-host copy (v0.24): `infra/drill.sh` restores the
  newest dump into a throwaway database and COMPARES ROW COUNTS (and the
  applied-migration count) against production — a restore that "succeeds" but
  restores the wrong data now fails the drill loudly. When `MTK_S3_*` is
  configured, `infra/backup.sh` also copies every dump to the object store
  (`scripts/upload_backup.py`, zero-dependency S3 client) and prunes old
  copies with the same retention; a failed copy fails the backup.
- **Monthly drill (mandatory):** restore the newest dump into a throwaway DB
  (`restore.sh` defaults to `mtk_radar_restore` so drills never touch prod),
  run the verification query it prints, and only then discard.
- Backups contain evidence excerpts and metadata — no raw secrets by design
  (redaction gate §11) — but handle them as sensitive regardless.
- Upgrade drill: before any Postgres major upgrade, backup → restore-drill → upgrade.

## 3. Credential & token recovery (§6/§7)

The DB stores only *references* (`env:YOUTUBE_*`, `vault:<path>`), so recovery
means rotating the secret in the environment/vault, never the database.

### Reviewer identity tokens (v0.16)

Dashboard users authenticate with personal tokens (reviewers table — only the
sha256 is stored). From `services/api/` (or `docker compose exec api …`):

    python -m scripts.mint_reviewer --name Kashi   # plaintext shown exactly once
    python -m scripts.mint_reviewer --list
    python -m scripts.mint_reviewer --revoke Kashi # instant; cache clears ≤60s

Re-minting a name replaces its token (old one stops working). Sign in at
`/login` with the token; the API is checked via GET `/whoami` before a signed
HttpOnly session cookie is issued. The nav shows the authenticated name.
Browser JavaScript never reads the token: interactive calls go through the
same-origin `/api/backend` proxy. Revoking a reviewer invalidates the token on
the next API call (the session cookie itself expires after 12h).

Dashboard sessions require `MTK_SESSION_SECRET` (≥32 random chars). Missing or
too-short values fail closed — only the login page renders, with a configuration
error. Rotating the secret signs every operator out.

### YouTube (OAuth2 refresh token)

1. Symptom: calendar shows account `token_expired`; monitor logs
   `ALERT token expiry … refresh rejected (400/401) — operator must re-consent`.
2. Re-run the OAuth consent flow for the MTK RADAR AI client
   (Google Cloud Console → OAuth client) to mint a new refresh token.
3. Update `YOUTUBE_REFRESH_TOKEN` (and rotate `YOUTUBE_CLIENT_SECRET` if it
   leaked) in the deployment env/vault only.
4. Nothing to update in the DB — the publishing worker refreshes on the next
   sweep and reports the new expiry (`/platform-accounts/{id}/refreshed`
   flips the account back to `active`).
5. Paused posts stay paused — resume them deliberately from the calendar
   (human gate; the offer is rechecked before publish regardless).

### Facebook (Page token)

1. Symptom: uploads fail with Graph error 190 → account `token_expired`.
2. Mint a fresh long-lived Page token (Graph API Explorer → Page access token);
   update `FACEBOOK_PAGE_ACCESS_TOKEN` in env/vault.
3. Re-register the credential reference if the source reference changed:
   `POST /platform-accounts` (idempotent per platform+handle, resets to active).
4. Resume paused posts after confirming the test upload.

### Long-lived token auto-renewal (WP-G — Facebook/Instagram, 2026-10-24)

Before resorting to the manual recovery above, the publishing worker renews
Facebook/Instagram long-lived tokens itself on a ~45-day cadence
(`MTK_TOKEN_REFRESH_CADENCE_D`, with a 14-day expiry margin) using Meta's
`fb_exchange_token` grant. Playbook:

- **Requirement:** `FACEBOOK_APP_ID` + `FACEBOOK_APP_SECRET` (or
  `INSTAGRAM_APP_ID`/`INSTAGRAM_APP_SECRET`, or per-account prefix variants).
  Without app credentials the sweep logs a skip and the expiry **monitor
  stays the fallback** — nothing breaks, renewal is simply manual.
- **Success:** the new expiry is reported to
  `POST /platform-accounts/{id}/refreshed` (expiry only — the token itself
  never leaves the worker process). Calendar shows the extended date.
- **Refusal** (400/401/403 from the exchange): the account is marked
  `token_expired` → it appears in Needs-You. **This is not silent:** do §3
  manual recovery (re-consent → fresh long-lived token), then resume.
- **At most one attempt per account per day** — a refused exchange never
  becomes a per-sweep hammering loop against the OAuth endpoint.
- TikTok/YouTube renew in-flight already (refresh-token hooks); no sweep
  action exists for them by design.

Verify the mechanism after configuring app credentials:
`python -m pytest workers/publishing/tests/test_token_maintenance.py -q`.

### TikTok (Content Posting API)

Requires an approved developer app with `video.publish`. Same pattern:
re-consent → new refresh token → update `TIKTOK_*` env → next sweep reactivates.

### Revocation

Operator removes access on the platform side: `POST /platform-accounts/{id}/revoke`,
then remove the env secret. Audit trail records it (`audit_log`).

## 4. Source registry recovery

- Registry contents live in the `sources` table; re-seed a fresh environment:

```bash
python services/api/scripts/seed_sources.py   # idempotent canonical-URL sources
```

- A source that fails repeatedly: disable it
  (`PATCH`/update ` sources.enabled = false`) rather than deleting — the audit
  trail and item history should survive.
- Freshness SLO: every enabled source polled within 72h; the analytics page
  colors >24h amber and >72h red.

## 5. Daily operations & incidents

| Alert | Meaning | Runbook step |
| --- | --- | --- |
| `ALERT token expiry …` (monitor) | dead platform session | §3 recovery |
| `attention.worker` | a worker heartbeat is stale/missing | run `scripts/mtk-start.sh`; check worker log |
| `attention.render_failed` / `publish_failed` | dead-letter or held post | Queue / Calendar; never retry blindly |
| Account `token_expired` on calendar | same, operator view | §3 recovery |
| Post `auto-paused: offer state -> expired` | offer died mid-schedule | verify the offer; corrections workflow if facts were wrong |
| Recheck due > 0 (analytics) | verified offers overdue recheck | human recheck → `/sweep-stale` demotes if skipped |
| Source stale (analytics red) | collector stopped | check collector worker logs → §4 |

### 5.1 Alert delivery (webhook / email)

The monitor logs every alert even when delivery is unconfigured. To send the
same digest off-host, set `MTK_NOTIFY_WEBHOOK_URL` and/or the `MTK_SMTP_*` +
`MTK_NOTIFY_EMAIL_TO` variables from [`.env.example`](../.env.example) and
restart the monitor. The payload is `mtk-radar.notification.v1`; see
[`notifications.md`](notifications.md) for the schema and security rules.

```bash
# One test through every configured channel (prints no secrets)
python workers/monitor/main.py --test-notification

# Compose
docker compose -f infra/docker/docker-compose.yml \
  --profile workers run --rm monitor \
  python workers/monitor/main.py --test-notification
```

Delivery is best-effort with no retry queue: a dead webhook or SMTP server is
logged and the next sweep continues. The monitor log remains the durable
record. An identical alert set is suppressed for `MTK_NOTIFY_COOLDOWN_S`
(default one hour) after a fully successful delivery, so a persistent token
problem does not email every five minutes; a partial failure is retried.
Email is a digest only when alerts exist — there is no quiet-time heartbeat.
The notification sender is part of the monitor; it does not need Supabase or
n8n.

Workers (manual runs when not under compose):

```bash
python workers/collectors/main.py --once
python workers/monitor/main.py --once
python workers/publishing/main.py --once
python workers/metrics/main.py --once     # v0.18: audience metrics sweep
python workers/batch/main.py --once       # v0.19: script generation + readiness
python workers/render/main.py --sweep    # v0.19: render the ready queue
```

Failed posts auto-retry with exponential backoff (base × 2^attempts, cap
`MTK_PUBLISH_MAX_RETRIES`, default 3). Posts still failed after the cap — or
refused because the script changed post-approval (409) — need operator review
on the calendar (resume/approve or cancel).

Render QC (v0.29): only `rendered / passed` rows can enter a schedule or
upload. The render sweep probes, fully decodes, and checks black/freeze/silence,
loudness/true peak and caption safe area, then stores the measured report.
Failures appear in **Queue → Render QC & dead letter**; fix the source and
re-render. Legacy renders are `not_checked` and must be re-rendered. Thresholds
and intentional-still ranges are in [`render-qc.md`](render-qc.md).

Save-link extension (v0.17): configure API URL + worker token via its options
page (right-click icon → Options). The page gesture sends `POST /items` with
the Bearer token; 401s surface on the toolbar badge with a hint.

Operator console (v0.19/v0.20): every configuration surface lives in the
dashboard — **Sources** (register what the collectors poll, see poll
health), **Connections** (register social accounts + where their credentials
live), **Settings** (publish windows, pipeline status), **Queue** (what the
automation renders vs what waits on you). Secrets never pass through the
browser.

Language policy (v0.27): **Settings → Language policy** controls the spoken
language independently from the published package. Defaults are English
voiceover, English titles/descriptions/hashtags/covers and English on-screen
captions. To produce an Urdu-spoken version, enable **Urdu voiceover** first.
The API rejects disabled languages in Content Studio, render registration and
scheduling, and the renderer skips them; the settings UI keeps the written
package and captions English and only exposes the spoken language. Captions are
built from the capture step log, wrapped to fit the frame, and use DejaVu Sans
by default (`MTK_CAPTION_FONT` overrides it). See
[`language-policy.md`](language-policy.md).

Duplicate protection (v0.23): the worker announces an upload
(`POST /schedules/{id}/attempt`) before it starts. If the outcome never
arrives (worker died mid-upload), the post is HELD — the calendar shows a
warning, the auto-retry sweep skips it, and a human verifies on the platform
before re-queueing. A duplicate public post is worse than a delayed one.

### 5.2 Trend radar playbook (WP-A–C, 2026-10-24)

The radar is a durable job, not a cron hope: migration `032` arms a
`jobs` row with `dedupe_key = 'trend_scan'`; the collector worker claims it,
scans all enabled trend sources (Tier-B leads only — see
[`source-registry.md`](source-registry.md)), and re-arms the job on a healthy
result via `POST /trends/scan-result` (attempts reset, `run_after` advances).
Manual trigger stays available: `POST /trends/scan`.

Symptoms and actions:

| Symptom | Meaning | Action |
| --- | --- | --- |
| Radar page "No leads", sources green | scan job dead-lettered | check `GET /jobs?kind=trend_scan` → `POST /jobs/bulk-retry {"ids": [...]}` (**human-only**, reviewer credential) or `POST /trends/scan` once |
| One source red in **Sources** | collector/adapter failure | worker log → fix endpoint/quota → the next sweep picks it up; a story pulsing on ≥2 sources keeps its corroboration |
| `velocity`/`peak` look frozen | no new observations | check `trend_observations` rows for the topic; the scan appends a datapoint per scan when the story is still live |
| Same story twice | title/entity dedup missed | report; `items_canonical` dedup runs at collect time (migration 031) |

Promote flow (human decision): radar card → `POST /trends/{id}/promote`
creates an offer + production-queue entry in ONE transaction (audited). The
trend stays a lead; the offer still needs official evidence to verify —
promotion never bypasses the verification gate.

### 5.3 Bulk un-wedge, media GC & lease heartbeat (WP-G, 2026-10-24)

- **Bulk un-wedge** — after an outage that dead-lettered many jobs:
  `POST /jobs/bulk-retry` with reviewer credentials only (service tokens get
  403; automation never bulk-requeues). It revives ONLY `dead`/`failed` rows —
  leased (in-flight) and pending work is never re-armed — capped at 200,
  filterable by `kinds`, per-id results + an `audit_log` entry
  (`jobs:bulk_retry`).
- **Media GC** — unpinned render/capture artifacts older than
  `MTK_MEDIA_RETENTION_DAYS` (default 90) are reclaim candidates:
  1. `POST /media/gc {"dry_run": true}` → the exact candidate list, nothing touched;
  2. review; artifacts referenced by a schedule whose state is not
     cancelled/failed are always exempt (their package must stay byte-exact);
  3. `POST /media/gc {"dry_run": false}` deletes and writes the audited
     `media:gc` entry with every removed ref.
- **Render lease heartbeat** — long encodes auto-renew their job lease every
  `MTK_RENDER_LEASE_TOUCH_S` (default 600 s). If you see
  `lease renewal … refused (409)` in the render log the job lost its lease to
  a restart — check whether anyone claimed it before re-running.

### 5.4 Rate-limited platforms (WP-G, 2026-10-24)

When a platform answers 429 (or Graph code 4 / subcode 2446852), the worker
records `retry_after_s` (parsed from `Retry-After` / `x-ratelimit-*`) in the
post's `outcome_detail`, marks the post failed (never held — nothing was
uploaded, no duplicate risk), and the auto-retry sweep waits
**max(its own backoff, the server-said delay)**. No action needed: do NOT
manually requeue faster than the recorded delay — hammering a throttled
endpoint only extends the ban.

Concurrency safety (v0.22): worker sweeps take a named lock
(`POST /locks/acquire`) before working the queue, so a deploy overlap or a
manually started second worker cannot upload the same post twice. A lock
that ages out (worker died) is taken over automatically. `GET /locks` shows
who holds what.

Cache layer (v0.22): the dashboard's aggregate read is served from Redis for
30 s when Redis is configured. Redis is OPTIONAL — without it (or with it
down) every request computes fresh; the cache never fails a request.

Health probe (v0.20): `GET /health` reports the database state AND the
applied/total migration counts — a reachable database with a missing
migration is visible instead of failing later under load. Use it as the
readiness gate in your deploy pipeline.

Full local verification (one command, same steps as CI):

```bash
pnpm verify          # lint → compile → tests (real Postgres) → typecheck →
                     # dashboard build → compose/CI/extension checks → browser E2E
pnpm verify --fast  # same, without the browser smoke test
```

## 6. Retention policy (§13)

- `schema_migrations`: forever (it *is* the schema history).
- `audit_log`: forever (accountability requires it).
- `items` (raw inbox): prune unclaimed candidates older than 60 days.
- `backups/`: prune per backup policy (default 14d).
- Captures/render bundles on disk: archive after the offer retires
  (`expired`/`corrected`); keep the DB rows.
- Media artifacts (videos/captions/covers) not pinned by a live schedule:
  reclaimable after `MTK_MEDIA_RETENTION_DAYS` (default 90) via
  `POST /media/gc` — dry run first, audited apply (WP-G §5.3 playbook).

## 7. First production review (plan §"build one complete case study")

Before treating the pipeline as production, complete ONE offer end-to-end and
measure (docs/first-offer-recipe.md drives the steps):

- [ ] `.TECH`-style verified offer: collected → verified (official evidence,
  domain-checked) → approved → scripted → captured (redaction-reviewed) →
  rendered (2 presets + captions) → private test upload on YouTube
- [ ] Token-expiry recovery exercised for real (not just in tests)
- [ ] One scheduled post paused by the expiry trigger (deliberately expire it)
- [ ] One correction logged and linked to the affected videos
- [ ] Backup + restore drill completed; row counts verified
- [ ] Metrics recorded: time spent, missed details, corrections needed,
  rendering reliability, platform upload friction — these decide what gets
  automated next
- [ ] CI green on `main`; `python -m compileall services workers packages` clean

## 8. Object storage (v0.15)

Capture videos, renders and captions live in **object storage**; the DB stores
portable *refs*, never host-local paths. Render, publishing and review can then
run on different hosts.

| Ref form | Meaning |
| --- | --- |
| `s3://<bucket>/<key>` | S3-compatible store (MinIO/AWS/R2/B2) — the multi-host option |
| `local://<key>` | shared filesystem root (NFS/bind mount) — single-host option |
| `projects/…` / `/abs/path` | legacy rows (pre-v0.15): resolved against the worker's CWD, unchanged |

**Env** (see `.env.example`):
- `MTK_STORAGE_BACKEND` unset → legacy relative-path flow (everything still works single-host).
- `local` → files under `MTK_STORAGE_LOCAL_ROOT` (default `./storage`).
- `s3` → needs `MTK_S3_ENDPOINT`, `MTK_S3_BUCKET`, `MTK_S3_ACCESS_KEY`, `MTK_S3_SECRET_KEY`, `MTK_S3_REGION`.
- `MTK_STORAGE_CACHE` — where publishing/render materialize refs (default `./.storage-cache`).

**Flow:** capture worker uploads its recording and registers a ref; render
worker materializes the capture ref (env-configured driver), renders, uploads
mp4 + captions, registers refs; publishing worker materializes the render ref
to its cache before platform upload — a ref that can't be produced on that
host fails the post with an actionable message ("set MTK_STORAGE_BACKEND or
run on the render host") instead of a silent file-missing error.

**Compose:** `docker compose --profile workers --profile storage up` starts
MinIO + bucket creation (`storage-init`). The render worker ships in the shared
worker image with ffmpeg preinstalled and writes to the `render-projects` and
`storage-cache` volumes; with `MTK_STORAGE_BACKEND=local` the API reads the same
`storage-data` volume, and with `s3` it streams ranges straight from MinIO/S3.

**Implementation:** `packages/object_storage/` — zero-dep (httpx only),
hand-rolled AWS SigV4 validated against AWS's published test vectors *and*
against a live S3-compatible server (put / get / exists / delete round-trip).
All 18 storage tests run in CI and `pnpm test`.

Migration of legacy rows: none required — plain paths keep resolving as
before. Re-rendering an offer with `MTK_STORAGE_BACKEND` set refreshes its
rows to refs.

## 9. Known gaps (explicit, not hidden)
- **Human vs automation (v0.26)**: each stage — collect, verify, script,
  render, approve, schedule — is controlled by
  `settings.automation_policy` in **Settings → Automation control**. The
  default is **assisted** (mechanical stages automatic; approve and schedule
  human). The API re-checks the policy on every gated write, so workers cannot
  bypass a human stage; guardrails cover confidence, evidence freshness,
  render/redaction/hash, unsafe commands, platform/privacy, and a daily
  auto-approval budget. Always-human guarantees: capture recording (§4),
  redaction review (§4), resuming a paused post, and final publish is only
  possible for posts that were approved and scheduled. A global **Pause all
  automation** switch and **dry-run** are in the same page. See
  `docs/automation-and-human-control.md`. Operator console: **Sources**,
  **Connections** (register accounts and where their credentials live),
  **Settings** (automation policy, live status, publish windows), **Queue**
  (what is rendering, what is waiting on you). Go-live procedure:
  `docs/go-live-checklist.md`; one-command verification: `pnpm verify`.
- **Instagram (v0.19)**: adapter implemented (Graph content publishing:
  container → transcoding wait → publish) and wired into publishing + metrics.
  Needs a professional (business/creator) account bound to a Page AND a
  public https media URL (`MTK_PUBLIC_MEDIA_BASE_URL`) — the Graph API
  fetches the video itself.
- **Audience analytics (v0.18)**: the metrics worker pulls per-video views,
  likes, comments and watch time from the official YouTube Analytics API and
  Meta Graph video_insights into `post_metrics` (one snapshot per UTC day,
  idempotent re-pulls); `/analytics` exposes reach totals + per-post content
  performance, rendered on the dashboard. Not yet measured: TikTok (insights
  need an approved developer app + undocumented scopes — skip by design),
  Instagram (no adapter yet — needs a linked business account), retention
  curves and click-through (needs platform reporting dims; snapshots keep the
  raw payload for re-parsing). YouTube pulls 403 without the
  `yt-analytics` OAuth scope — re-consent the client to add it.
- TTS narration mixing: v0.17 replaced the homogeneous-codec stream-copy with
  a re-encode (libmp3lame 44.1 kHz) plus an ffprobe duration gate (≥85% of
  summed segments, else capture-audio fallback) — a provider/model change
  between batches can no longer silently corrupt boundaries.
- Reviewer identity: personal hashed tokens bind every dashboard/API action to
  a named reviewer — audit_log.actor comes from the token, not the request body.
  The dashboard exchanges a token for a signed, HttpOnly session cookie; the
  token never reaches browser JavaScript and the shared `MTK_API_TOKEN` is
  server-side only. Service/worker/extension credentials cannot name a human:
  approval, ToS attestation, redaction review and corrections require a
  reviewer credential (or an explicit `automation:<stage>` actor where policy
  allows automation). This is still a single-operator token-login model, not
  SSO/password auth or multi-tenant identity.
- Publishing safe-guards: approval-hash binding + expiry gates (v0.16),
  auto-retry with exponential backoff capped at `MTK_PUBLISH_MAX_RETRIES`
  (v0.17), correction notices pushed into already-published YouTube
  descriptions by the worker sweep (v0.18 `apply_correction_notice`,
  idempotent via `description_patched_at`). Remaining exposure: the
  worker-host clock is trusted for due/retry timing; non-YouTube platforms
  have no description write-back API available to us (manual follow-up).
- Publish windows (v0.18): operator-configurable via
  `PUT /settings/publish_windows` (defaults to a single 18:00 PKT slot);
  the ScheduleForm renders quick-picks from the setting. Still hardcoded:
  the display timezone is Asia/Karachi everywhere (fine for a PKT operator).
- Extension (v0.17): configured via its options page (API URL + worker token);
  the save action surfaces 401/connection problems on the badge. Not yet:
  packaging/store hardening (icons, CSP review, MV3 store listing).
- Backup automation (v0.18): systemd timers in `infra/systemd/` — daily
  backup, monthly restore drill into a throwaway DB; the drill unit going red
  means backups are unusable. Not yet: off-machine backup copy (e.g. rclone
  to object storage) — the dumps stay on the deploy host.
- Postiz / cross-posting service: intentionally not integrated (the plan
  marks it optional; platform adapters cover it).
- Analytics counts runs on one Postgres instance; no replication/HA.

## 10. Test & automation layers (v0.14)

CI (`.github/workflows/ci.yml`) runs four levels on every push/PR:

1. **Lint** — `ruff --select E9,F63,F7,F82` (see ruff.toml) catches undefined
   names and broken call shapes — the class of defect behind the week-12
   analytics 500s.
2. **Unit tests** — pure logic: state machine, redaction, scriptgen,
   migration policy, narration assembly.
3. **Integration tests** — `services/api/tests/test_integration.py` runs the
   REAL migration runner against a disposable Postgres service, then drives
   the full review pipeline over HTTP: ingest dedup → promote → evidence
   domain checks → extraction → state-machine gates → analytics. Locally:
   `MTK_TEST_DATABASE_URL=postgresql://... pytest services/api/tests/test_integration.py`
   (point it at a DISPOSABLE database — the schema is wiped at start).
4. **E2E smoke** — `apps/dashboard/e2e/smoke.spec.ts` runs the production
   dashboard build against the real API + DB (health dot, routes, live data).

Dependency updates are automated via Dependabot (weekly grouped for npm/pip,
monthly for actions/docker; postgres major bumps are deliberately excluded —
they need a migration runbook, not a bot).
