# MTK RADAR AI — Operational Runbook

Week 12 (master plan §18): deployment, backup/restore, credential and source
recovery, and the first production review. This file is the source of truth
for operating the platform; the master plan remains the source of truth for
*why* these rules exist.

---

## 1. Deployment

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD for anything real
docker compose -f infra/docker/docker-compose.yml up -d   # postgres+redis+api+dashboard
docker compose -f infra/docker/docker-compose.yml \
               --profile workers up -d                    # + publishing & monitor
```

- API: `http://localhost:8000` (FastAPI; `/health` wired to CI + compose healthcheck)
- Dashboard: `http://localhost:3000`
- All services `restart: unless-stopped`; postgres data lives in the `pgdata` volume.
- Never commit `.env`. Platform tokens live in the deployment environment or a
  vault (§7) — the database stores credential *references* only.

### Migrations

```bash
python services/api/db_migrate.py            # apply pending (001…007…), recorded in schema_migrations
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

- Schedule `backup.sh` daily (cron or systemd timer). Retention: default 14 days.
- **Monthly drill (mandatory):** restore the newest dump into a throwaway DB
  (`restore.sh` defaults to `mtk_radar_restore` so drills never touch prod),
  run the verification query it prints, and only then discard.
- Backups contain evidence excerpts and metadata — no raw secrets by design
  (redaction gate §11) — but handle them as sensitive regardless.
- Upgrade drill: before any Postgres major upgrade, backup → restore-drill → upgrade.

## 3. Credential & token recovery (§6/§7)

The DB stores only *references* (`env:YOUTUBE_*`, `vault:<path>`), so recovery
means rotating the secret in the environment/vault, never the database.

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
| Account `token_expired` on calendar | same, operator view | §3 recovery |
| Post `auto-paused: offer state -> expired` | offer died mid-schedule | verify the offer; corrections workflow if facts were wrong |
| Recheck due > 0 (analytics) | verified offers overdue recheck | human recheck → `/sweep-stale` demotes if skipped |
| Source stale (analytics red) | collector stopped | check collector worker logs → §4 |

Workers (manual runs when not under compose):

```bash
python workers/collectors/main.py --once
python workers/monitor/main.py --once
python workers/publishing/main.py --once
```

## 6. Retention policy (§13)

- `schema_migrations`: forever (it *is* the schema history).
- `audit_log`: forever (accountability requires it).
- `items` (raw inbox): prune unclaimed candidates older than 60 days.
- `backups/`: prune per backup policy (default 14d).
- Captures/render bundles on disk: archive after the offer retires
  (`expired`/`corrected`); keep the DB rows.

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

## 8. Known gaps (explicit, not hidden)

- Object storage for capture/render files: local paths only — the publishing
  worker fails with "render file not on this host" when scaled out.
- TTS narration is per-segment (`workers/render/narration.py`); a single mixed
  narration track is still pending.
- Reviewer identity is an operator string (no session/SSO yet) — fine for the
  single-operator deployment. Transport-level protection exists: set
  `MTK_API_TOKEN` and every route except `/health` requires
  `Authorization: Bearer <token>` (services/api/api_hardening.py). The
  dashboard and workers attach the token automatically when the env is set;
  compose forwards it. Leave it unset only for throwaway local dev.
- Analytics counts runs on one Postgres instance; no replication/HA.
