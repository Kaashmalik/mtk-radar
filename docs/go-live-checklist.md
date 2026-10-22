# Go-live checklist — keys, connections, first real post

Master plan §18 week 12 ("deployment, backup/restore, credential and source
hygiene") and §6 (official platform APIs). This file is the operator's
runbook for the things **no policy can automate**: secrets and account
consent. Everything else is automated or human-controlled by the policy in
**Settings → Automation control**, and proven by the test suite. It also covers
deployment, operator checkpoints and language packaging. Code and mocked tests
do not establish full end-to-end or production readiness. See the
[21 October 2026 audit and enhancement plan](automation-master-plan-2026-10-21.md)
for current gaps, actual checks run and release-blocking safety work. The
historical verification counts below must be re-proven for each release.

**Rule zero:** secrets live in the deploy environment (or a vault), never in
the database, never in the browser, never in git. The database only records
*where* a credential lives (`credential_source`, e.g. `env:YOUTUBE_`).

---

## 0. What is already verified (no keys needed)

| Area | How it is proven |
| --- | --- |
| API + DB | integration tests against real Postgres 16, migrations 001→012 applied by the real runner |
| State machine (§3) | unit/integration tests — illegal transitions, expiry, hash-binding, redaction and automation gates |
| Workers | collector, verification, monitor, publishing, metrics, batch, render — unit-tested + live `--once` sweeps |
| Dashboard | production build + Playwright smoke against the real API (4 browser tests) |
| Object storage | S3-compatible driver tested against a real S3 mock (moto) |
| Backup/restore | `infra/backup.sh` + `infra/restore.sh` + systemd timers (`infra/systemd/`) |
| Extension | MV3 manifest + service worker + options page, syntax-checked in CI |

Run everything yourself:

```bash
cp .env.example .env          # then fill in the keys from §2/§3
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml exec api python db_migrate.py
pnpm verify                    # the full pipeline (same steps as CI)
```

---

## 1. Start the stack

```bash
cp .env.example .env
docker compose -f infra/docker/docker-compose.yml up -d \
  --profile workers --profile storage
docker compose -f infra/docker/docker-compose.yml exec api python db_migrate.py
curl -s localhost:8000/health        # {"status":"ok","service":"api","version":"0.28.0"}
```

Then open **Settings → Automation control** and confirm the default **Assisted**
mode: collect/verify/script/render may run automatically, while **approve** and
**schedule** stay human. Keep it there until you have watched several complete
videos and posts; switch one stage at a time (see
[`automation-and-human-control.md`](automation-and-human-control.md)).

Open **Settings → Language policy** and leave the English-first defaults on:
English title/description/hashtags/cover and English on-screen captions. Leave
**Enable Urdu voiceover** off unless you specifically want an Urdu-spoken
version; if you enable it, generate/render the Urdu version separately. See
[`language-policy.md`](language-policy.md).

Services (compose file `infra/docker/docker-compose.yml`):

| Service | Role | Human gate? |
| --- | --- | --- |
| `api` | FastAPI + Postgres + Redis | no |
| `dashboard` | operator console (Next.js) | no |
| `collectors` | polls registered sources → inbox | no |
| `batch` | generates scripts, reports readiness, and (only when enabled) approves/schedules inside guardrails | per policy |
| `render` | renders the ready queue (ffmpeg) | per policy |
| `monitor` | expiry/token sweeps, alerts | no |
| `publishing` | uploads posts that are already approved **and** scheduled; retries per policy | approval only |
| `metrics` | pulls audience numbers per post | no |

Redis is optional: it caches the dashboard's aggregate read for 30 s. If it
is not running, everything still works (fresh numbers on every request).

**Human gates that stay human (by design):** evidence verification (§3),
capture recording (§4), redaction review (§4), publish approval (§17).

---

## 2. The keys (copy into `.env`)

### 2.1 Deploy secrets

```bash
# shared worker/API token — required for anything beyond localhost
openssl rand -hex 32            # → MTK_API_TOKEN
# database password
openssl rand -hex 16            # → POSTGRES_PASSWORD
# public origin of the dashboard (caption correction permalinks, §11)
# → MTK_PUBLIC_BASE_URL=https://radar.yourdomain.tld
```

### 2.2 Reviewer identity (who the audit log names)

```bash
docker compose -f infra/docker/docker-compose.yml exec api \
  python -m scripts.mint_reviewer --name "Kashi"
# paste the token into the dashboard identity box (top-right)
```

Every approval, correction, connection and setting change is bound to this
identity in `audit_log` (§15).

### 2.3 Optional extras

| Key | Why |
| --- | --- |
| `GITHUB_TOKEN` | raises collector rate limits for GitHub sources |
| `MTK_S3_*` (+ `MTK_STORAGE_BACKEND=s3`) | portable renders/captures **and** the off-host copy of every backup (recommended) |
| `MTK_S3_*` + `MTK_STORAGE_BACKEND=s3` | portable renders/captures (any S3-compatible store) |
| `MTK_PUBLIC_MEDIA_BASE_URL` | public CDN/bucket origin — **required for Instagram** |

---

## 3. Connect the social accounts

### 3.1 YouTube (Data API + Analytics API)

1. Google Cloud console → new project → enable **YouTube Data API v3** and
   **YouTube Analytics API**.
2. OAuth consent screen → *External*, add your Google account.
3. Credentials → OAuth client ID → *Desktop app* (or Web, for the refresh
   flow used here).
4. Authorize with scopes:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.force-upload`
   - `https://www.googleapis.com/auth/yt-analytics.readonly` ← **without this
     the metrics worker gets 403 and audience numbers stay empty**
5. Exchange the consent code for a refresh token, then set:
   `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
6. Dashboard → **Connections** → platform *YouTube*, handle (e.g.
   `mtk-radar-main`), credential source `env:YOUTUBE_` → **Connect account**.

### 3.2 Facebook (Pages)

1. Meta app → *Business* → add the **Facebook Login** product.
2. Get a **long-lived Page access token** for the target Page
   (`/me/accounts` → extend expiry).
3. Set `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`.
4. Connections → *Facebook*, handle, `env:FACEBOOK_` → Connect.
   Scopes: `pages_manage_posts`, `pages_read_engagement`, `read_insights`.

### 3.3 Instagram (professional account, bound to a Page)

1. The IG account must be **Business or Creator** and linked to a Page.
2. Token with `instagram_basic`, `instagram_content_publish`,
   `instagram_manage_insights` → `INSTAGRAM_USER_ID`,
   `INSTAGRAM_ACCESS_TOKEN`.
3. The media must be reachable over **public https** (the Graph API fetches
   it) → set `MTK_PUBLIC_MEDIA_BASE_URL` to your CDN/bucket origin and make
   the render objects public.
4. Connections → *Instagram*, `env:INSTAGRAM_` → Connect.

### 3.4 TikTok (optional, needs an approved app)

`TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` — the
Content Posting API only works for approved apps; without approval the
adapter stays disabled (posts are skipped, not failed).

---

## 4. First real run (15 minutes, no risk)

1. **Seed a source** — Dashboard → **Sources** → add a Tier-A provider
   (`provider`, `canonical_domain`, `trust_tier: A_provider_owned`). This is
   where the collectors find their work; without a source nothing is
   collected. (CLI alternative: `python services/api/scripts/seed_sources.py`.)
2. **Collect** — `docker compose … run --rm collectors` (or wait for the
   service). Items land in the Inbox.
3. **Review** — Inbox → *Review desk*: attach an **official** evidence URL
   from the provider's own domain, extract the claim fields, then transition
   to `verified` (the gate refuses anything unearned).
4. **Script + render (automatic)** — the batch worker generates the script;
   after you record a capture (below) and pass redaction review, the render
   service renders it by itself. Watch it in **Queue**.
5. **Record the capture (the only human recording step)** — on a machine
   with a display:
   ```bash
   pip install -r workers/capture/requirements.txt
   python -m playwright install chromium
   python workers/capture/main.py --offer <offer-id> --api http://localhost:8000
   ```
   Playwright drives the mechanics; **you** perform every account action.
6. **Redaction review** — Dashboard → offer page → review the capture, then
   attest it is clean (release-blocking, §4).
7. **Approve + schedule** — offer page → *Approve for video* → schedule the
   post (privacy = **private** for the first run). The calendar shows the
   publish windows you configured in **Settings**.
8. **Watch it publish** — `docker compose … logs -f publishing`. The post
   lands as private/unlisted; flip visibility in the platform UI.
9. **Measure** — `docker compose … logs -f metrics`; the numbers appear in
   **Analytics → Audience reach** and on the post row.
10. **Correct it (if needed)** — offer page → *Record correction*. The
    worker pushes the correction notice into the published description
    (YouTube) and pauses affected scheduled posts.

---

## 5. Operations

| Task | Where |
| --- | --- |
| Nightly backup | `infra/systemd/mtk-radar-backup.timer` (daily 03:00) |
| Monthly restore drill | `infra/systemd/mtk-radar-restore-drill.timer` — a red unit means backups are unusable (the drill compares row counts, not just "it restored") |
| Dead platform token | `ALERT token expiry …` in the publishing log → re-consent (§3) → account returns to `active` |
| Offer expired | monitor sweep auto-pauses scheduled posts; the offer page shows the correction path |
| Metrics empty | check the OAuth scope (`yt-analytics.readonly`) and the metrics worker log |
| Post shows "HELD" on the calendar | a previous upload's outcome is unknown — check the platform first (it may already be live), then re-queue or cancel the post |
| Reviewer token lost | `python -m scripts.mint_reviewer --name "Kashi"` → mint a new one |

Full incident procedures: `docs/runbook.md` (§3 recovery, §5 daily ops,
§6 retention, §9 known gaps). What each master-plan item maps to:
`docs/master-plan-traceability.md`.
