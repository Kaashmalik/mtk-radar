# Cost, laptop production, and VPS fallback — 22 October 2026

This is the planning and operating note for running MTK RADAR AI at the lowest
practical cash cost, with a laptop as the primary host and a small VPS as the
fallback when the laptop is off or travelling.

It covers:

- what the current cost estimate assumes;
- which costs are mandatory and which are optional;
- how to use the GitHub Student Developer Pack, a free domain, Cloudflare and
  the four River models to reduce cash cost;
- the laptop setup, including power, Cloudflare Tunnel, R2, secrets and
  backups;
- the recommended split-VPS fallback and how to cut over safely;
- future recommendations and cost-control rules.

> **Status:** planning guidance, not a quote. Prices, student offers, platform
> policies and model limits change. Re-check the current provider pages before
> buying anything. The safety gates in this repository are not optional and are
> not changed by this document.

---

## 1. Assumptions

The estimates use these assumptions unless a row says otherwise:

| Assumption | Value |
| --- | --- |
| Finished video | 60–120 seconds |
| Renders per video | 2 (16:9 landscape and 9:16 vertical) |
| Posts per platform | 1 |
| Platforms | YouTube, Facebook, Instagram, TikTok |
| Package language | English public package; Urdu voiceover opt-in only |
| Voiceover | Optional; capture audio/captions first |
| LLM extraction | Optional; deterministic rules first |
| Media retention | 90 days |
| Video size for storage math | ~0.25 GB per video across both renders |
| Failed attempts | Allowed for in cost per **QC-passed delivered** video, not hidden |
| Operator review | 30–60 minutes per delivered video including rework |
| Operator time value | $15–$50/hour (opportunity cost if you do it yourself) |
| Month | 30 days |

**Cash cost** below means recurring out-of-pocket spend on hosting, storage,
domain, APIs, models/TTS and monitoring. It excludes the laptop purchase,
electricity and operator time unless stated. **All-in** adds operator time and
rework, including failed attempts.

Platform APIs have no per-post fee, but public YouTube uploads may require a
compliance audit, Instagram needs a professional account plus public HTTPS
media, and TikTok needs an approved developer app. Those are approval and
setup costs, not per-post fees.

---

## 2. Cost scenarios

### 2.1 Managed/cloud baseline (no student credits, no laptop hosting)

This is the planning envelope from the earlier cost review. It is deliberately
wide because hosting, model usage and review time vary significantly.

| Volume | Delivered/month | Cash/month | All-in/month | All-in per QC-passed video |
| --- | ---: | ---: | ---: | ---: |
| 1/day | 30 | $85–$165 | $335–$1,515 | $11–$51 |
| 3/day | 90 | $155–$345 | $905–$4,395 | $10–$49 |
| 10/day | 300 | $330–$655 | $2,830–$14,155 | $9–$47 |

The all-in range includes operator review, rework and failed attempts. It is not
the sum of the cash column plus a fixed hourly rate; it is a planning envelope
for comparing hosting choices. The important conclusion is that **operator
review, not infrastructure, is the dominant cost at every volume**.

### 2.2 Student/free-resource laptop stack

Using the laptop as the host, a free first-year domain, Cloudflare's free
Tunnel/Access/DNS, R2's free 10 GB, GitHub's student benefits and the River
models changes the cash picture substantially:

| Volume | Delivered/month | Estimated cash/month | Notes |
| --- | ---: | ---: | --- |
| 1/day | 30 | $0–$12 | Mostly electricity; R2 usually within/near free tier |
| 3/day | 90 | $3–$18 | R2 overage and backup copy become visible |
| 10/day | 300 | $6–$25 | R2 ~225 GB at 90-day retention; laptop works harder |

These figures exclude laptop hardware and your time. They also exclude one-time
credits such as Render or MongoDB Atlas; those can make a short staging or
failover window cheaper, but they are not a steady-state monthly cost. They
assume:

- the domain is free for year one and renews later;
- R2 stays within or close to the free 10 GB tier at pilot volume;
- the models are included/free within your River access limits;
- GitHub Actions, Pages and Codespaces stay within student quotas;
- no paid TTS, paid LLM fallback, paid monitoring or GPU rental;
- Supabase Free, if used, stays within its database/storage limits and is
  backed up separately;
- the laptop is already owned and is plugged in during the production window.

**The cash floor is real, but it is not the whole cost.** At 1/day you still
spend roughly 10–22.5 hours per month on review if each video takes 20–45
minutes. At 10/day that becomes 100–225 hours per month, which is the real
reason to batch, template and automate review preparation rather than add more
servers.

### 2.3 Cost per video

Use this formula, as required by the master plan's budget guidance:

```text
cost per QC-passed delivered video =
  (API/processing + model/TTS + storage/egress + hosting + monitoring + review
   + failed attempts and abandoned work)
  / number of QC-passed delivered videos
```

Do not report only the successful renders. A cheap render that fails review is
still a cost.

On the all-free laptop stack, cash cost is usually **under $1 per video**; on
the managed/cloud baseline it is roughly **$3–$6 per video**. All-in cost is
roughly **$9–$50 per video**, dominated by review. That is the number to track
weekly.

### 2.4 1 video/day with all the listed resources

This is the specific case: laptop, free student domain, GitHub student benefits,
four River models, Render/MongoDB credits, Supabase Free, Cloudinary Free and
Google Drive 2 TB for year one.

| Item | Estimated monthly |
| --- | ---: |
| Laptop electricity | $3–$10 |
| Domain | $0 in year one; ~$1/month equivalent after renewal |
| Cloudflare DNS/Tunnel/Access | $0 |
| GitHub Pro/Actions/Pages/Codespaces/Copilot | $0 within quotas |
| R2 for 1/day, 90-day retention (~22.5 GB) | ~$0.19 after the 10 GB free tier |
| R2 backup copy / small overhead | $0–$0.50 |
| Supabase Free Postgres | $0 |
| Supabase Storage | $0 (not used for video) |
| Cloudinary Free | $0 (thumbnails only, if used) |
| Google Drive 2 TB | $0 in year one |
| Render $50 credit | $0 while it lasts; not a steady-state cost |
| MongoDB Atlas $50 credit | $0; not used for the core stack |
| River models | $0 within access limits |
| Platform APIs | $0 |
| **Recurring cash total** | **~$3–$11/month in year one** |

So the practical answer is **roughly $0–$15/month cash**, with electricity and a
little R2 overage being the only normal recurring charges. If the laptop runs
24/7 or electricity is expensive, budget the top of that range. After year one,
add domain renewal and whatever you decide to do about Google Drive/2 TB.

Do not count the one-time Render/MongoDB credits as monthly income. They can
cover a short staging or failover window, but when they end the steady-state
cost returns to the table above or to the split-VPS cost in §6.

All-in, 30 videos at 30–60 minutes of review each is 15–30 hours per month. At
$15–$50/hour that is **$225–$1,500/month**, before any cash costs. The free
resources reduce the bill, not the review time.

---

## 3. Mandatory vs optional costs

| Category | Mandatory for a real pilot | Optional / defer | Notes |
| --- | --- | --- | --- |
| Host | Laptop or VPS | GPU host | CPU FFmpeg is enough for 1–3 videos/day if measured |
| Database | PostgreSQL | Managed HA database | Single instance is sufficient at pilot scale |
| Cache | Redis optional | Managed Redis | The app works without Redis; it only caches reads |
| Object storage | R2 or another S3-compatible store | Multi-region replication | Public media requires a dedicated derivative bucket/prefix |
| Domain + TLS | Domain; TLS can be free | Premium DNS | Cloudflare DNS/Tunnel/Access can be free |
| Backups | Off-host DB/media copy | Long archive | A local-only backup is not a backup |
| Platform APIs | OAuth/app review | Paid ads | No per-post API fee; approval time is the real cost |
| Verification | Human evidence/redaction review | LLM extraction | Rules first; LLM is an assistant, never the source |
| Voiceover | Optional | Paid TTS/voice actor | Capture audio/captions first; Urdu stays opt-in |
| Rendering | CPU render | GPU/cloud render | Measure before buying |
| Monitoring | Basic uptime/backup alerts | Paid observability | A log line is not an alert |
| Scheduling | Built-in scheduler | Paid social tool | The repository already schedules and retries |

### 3.1 Fixed-ish costs

- **Domain:** free in year one with eligible student offers; renewal is
  typically a small annual cost. Set a renewal reminder immediately.
- **R2:** 10 GB free, then about $0.015/GB-month; egress is free. At 1/day and
  90-day retention, roughly 22 GB is about $0.19/month after the free tier.
  At 10/day, roughly 225 GB is about $3.23/month.
- **Cloudflare:** DNS, Tunnel and Access can be free at this scale. Verify the
  current Access user limit before relying on it.
- **GitHub:** Pro includes 3,000 Actions minutes/month; public repositories get
  free standard runners. Do not use Actions or Codespaces as a production
  server.
- **Supabase Free:** a managed PostgreSQL pilot option, but only 500 MB of
  database, 5 GB egress, no automatic backups, and projects pause after one
  week without activity. It is not a media host: free file storage is 1 GB with
  a 50 MB per-file upload cap.
- **Platform APIs:** normally no per-post fee. Budget approval time, not a
  per-post bill.

### 3.2 Human review is the real budget

The gates are the product: official evidence, domain checks, script-hash
binding, redaction review, approval, expiry/correction auto-pause and remote
visibility confirmation. They are also where the time goes.

Ways to reduce review time without weakening the gates:

- batch captures instead of setting up the recording environment repeatedly;
- prefill evidence summaries and metadata variants with a free model;
- use one English package and defer Urdu voiceover until the English workflow
  is stable;
- review a checklist, not a blank page;
- keep a library of approved claim wording and platform-specific descriptions;
- measure where review time actually goes before buying more automation.

---

## 4. The student/free-resource stack

### 4.1 GitHub Student Developer Pack

Use these benefits for specific jobs:

| Benefit | Use it for | Do not use it for |
| --- | --- | --- |
| GitHub Pro | Private repo, branch protection, 3,000 Actions minutes/month | A 24/7 worker host |
| GitHub Actions | Tests, typecheck, dashboard build, Playwright | Publishing, persistent DB, long-running workers |
| GitHub Pages | Public privacy policy, terms, contact and landing pages | The Next.js dashboard or video hosting |
| GitHub Codespaces | Remote coding and tests within the monthly quota | Headful capture, production database, platform tokens |
| GitHub Copilot Student | Inline completions and quick edits | Final verification or publish approval |
| 1Password student | Platform tokens, R2 keys, API secrets | Committing `.env` or sharing secrets in chat |

Use Actions to run the existing `scripts/verify.sh` pipeline on pushes and pull
requests. Keep the full verification local before a release; CI is a second
pair of eyes, not a replacement for the release gate.

**Never run the publishing worker in GitHub Actions or Codespaces.** Those
environments are ephemeral, have no durable database/queue, may expose secrets
to workflow logs, and are not an always-on scheduler. They also cannot provide a
stable production callback/identity for platform reviews.

### 4.2 Free domain

Eligible student offers include a first-year domain from partners such as
Namecheap (for example `.me` or `.TECH`) or Name.com. Pick one domain and move
its DNS to Cloudflare. Do not collect domains you will not operate.

Suggested subdomains:

| Hostname | Purpose | Exposure |
| --- | --- | --- |
| `app.example.com` | Dashboard | Cloudflare Tunnel + Access |
| `api.example.com` | API used by the dashboard and remote render workers | Cloudflare Tunnel + Access |
| `media.example.com` | Approved public renders for Instagram | R2 public custom domain only |
| `docs.example.com` | Privacy, terms, contact, landing | GitHub Pages or Cloudflare Pages |

Also use Cloudflare Email Routing for a contact address such as
`hello@example.com`; app reviews often ask for a reachable contact and privacy
policy. Do not publish internal runbooks or operator documentation on the
public site.

The domain is free for the first year only. Put the renewal date and price in
your calendar now; a lapsed domain breaks OAuth callbacks, media URLs and
platform reviews.

### 4.3 Cloudflare Tunnel and Access

Cloudflare Tunnel lets the laptop or VPS serve the dashboard/API without a
public IP or router port-forward:

1. Create a named tunnel in Cloudflare.
2. Route `app.example.com` to `http://localhost:3000`.
3. Route `api.example.com` to `http://localhost:8000`.
4. Put both hostnames behind Cloudflare Access.
5. Keep the API's bearer token and reviewer tokens enabled even behind Access.
6. Set `API_URL=https://api.example.com` (server-side only),
   `MTK_SESSION_SECRET` (≥32 random chars),
   `MTK_CORS_ORIGINS=https://app.example.com` and
   `MTK_PUBLIC_BASE_URL=https://app.example.com`. The browser calls the
   dashboard's same-origin `/api/backend` proxy, so no public API URL is
   compiled into client JavaScript.

Do not expose PostgreSQL, Redis or MinIO through the tunnel. The dashboard and
API are the only browser-facing services. Render workers talk to the API and
object storage outbound; they do not need inbound access.

### 4.4 Cloudflare R2

R2 is a good fit because egress is free and the API is S3-compatible. Use it for
renders, captures and a copy of database backups.

```sh
MTK_STORAGE_BACKEND=s3
MTK_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
MTK_S3_BUCKET=mtk-radar
MTK_S3_REGION=auto
MTK_S3_ACCESS_KEY=...
MTK_S3_SECRET_KEY=...
MTK_PUBLIC_MEDIA_BASE_URL=https://media.example.com
```

**Keep captures and evidence private.** Instagram needs a public HTTPS URL, but
making the entire capture bucket public would expose raw footage. Use a
dedicated public bucket/prefix containing only approved renders, or add a
copy/derivative step before enabling Instagram. The current Compose setup uses
one S3 bucket; treat bucket separation as a setup requirement to verify, not an
assumption.

Do not delete a render before the platform has fetched it and confirmed remote
processing. R2 lifecycle rules are useful for old, unreferenced media, not for
media still in flight.

### 4.5 GitHub Pages for the public legal pages

Create public pages for:

- privacy policy;
- terms of use;
- contact;
- a short "how it works" or landing page.

These are useful for YouTube/Meta/TikTok app review. Keep them static; do not
try to export the authenticated dashboard to Pages. Use a separate directory or
repository so internal documentation is not published accidentally.

### 4.6 One-time Render and MongoDB Atlas credits

The **$50 Render credit** (assumed here to be Render.com) and **$50 MongoDB
Atlas credit** are useful for short experiments and failover drills, not for
permanent core infrastructure. If either credit is from a different provider,
apply the same rule: use it for a time-boxed test, not the production source of
truth.

| Credit | Good use | Do not use it for |
| --- | --- | --- |
| **Render $50** | A short staging API/worker environment; rehearsing the split-VPS cutover; a temporary control plane for a trip | Replacing the laptop or VPS permanently; assuming this Compose stack deploys unchanged |
| **MongoDB Atlas $50** | Independent experiments or a future document/analytics store | The core database; MTK RADAR uses PostgreSQL and has no MongoDB dependency |

**Render.** Render can host Docker web services and background workers and can
provide managed PostgreSQL/Redis, so it can be a temporary control plane if the
services are containerized. The repository currently has an API Dockerfile but
not a complete Render blueprint for the dashboard and every worker; deploying
there requires adapting the Compose services. Treat $50 as a short window (the
exact duration depends on the plan, instance sizes, database and bandwidth you
choose), not as a monthly budget. Use it to rehearse the cutover, run a staging
check, or cover a short trip. Set a hard spend cap and be ready to migrate
before the credit expires.

**MongoDB Atlas.** This project does not use MongoDB. Do not introduce a second
database just to spend the credit: it would split the source of truth and add
backup, monitoring and security work. If a future feature genuinely needs a
document store, use MongoDB as a supplement, never as the system of record for
offers, evidence, schedules or audit history.

**If you use either credit for a real test:**

- keep production credentials out of the experiment;
- do not point the production domain or OAuth callbacks at an environment you
  will delete in a few weeks;
- do not run a second publisher against a separate database;
- export/back up anything worth keeping before the credit ends;
- remove the service and auto-billing after the experiment.

### 4.7 Supabase, Cloudinary and Google Drive: what fits

Short answer:

- **Supabase Free Postgres:** usable as an **optional managed database** for a
  pilot or split-VPS setup, with caveats.
- **Supabase Storage:** not suitable for the video renders; the free plan is
  1 GB with a 50 MB per-file upload cap.
- **Supabase Edge Functions:** possible for a tiny authenticated webhook
  receiver, but not for the API, workers or monitor; see
  [`notifications.md`](notifications.md).
- **Cloudinary Free:** useful for thumbnails/covers if you need image
  transformations; not the primary video origin.
- **Google Drive 2 TB:** useful for **backup and archive**, not public media
  delivery.

| Service | Free/current limit to verify | Good fit | Decision |
| --- | --- | --- | --- |
| Supabase Free Postgres | 500 MB database, 5 GB egress, 2 active projects, pauses after 1 week inactivity, no automatic backups | Managed DB for pilot or split VPS | Conditional |
| Supabase Edge Functions | Limited serverless invocation/CPU quota; short-lived requests only | Tiny authenticated webhook receiver | Optional, not core |
| Supabase Storage | 1 GB, 50 MB max file upload on Free, S3-compatible API | Small thumbnails/assets | Not for video |
| Cloudinary Free | 25 monthly credits shared across storage, transformations and delivery; custom domain is a paid feature | Thumbnails, covers, image transformations | Optional |
| Google Drive Pro 2 TB | 2 TB for the free year; file storage, not a CDN | DB dumps, raw captures, project archive | Backup only |

#### Supabase Free Postgres

Supabase Free is attractive because this project already needs PostgreSQL and
the API only needs a `DATABASE_URL`. It can make the split-VPS mode lighter:
the VPS runs API/publishing/monitor while the laptop does capture/render, and
Supabase hosts the database.

The caveats matter:

- **No automatic backups on Free.** Keep a nightly `pg_dump` on the laptop or
  VPS and copy the encrypted dump to R2 and/or Google Drive. The repository's
  `infra/backup.sh` targets the Compose Postgres container; for Supabase, use a
  host `pg_dump` wrapper with the Supabase connection string.
- **Projects pause after one week of inactivity.** An always-on publisher or
  monitor may keep it active, but a laptop-only setup that is off for a week
  can pause the project. Publishing then fails until the project is resumed.
- **500 MB database limit.** Metadata is small, but evidence text, audit rows
  and long-lived history can add up. Monitor database size and prune only per
  the runbook's retention rules.
- **Connection mode matters.** Use the direct/session connection for
  migrations and dumps; test the transaction pooler with `asyncpg` before
  pointing workers at it. Some poolers do not support prepared statements the
  same way as a direct connection.
- **Egress is 5 GB/month.** Database traffic is small; keep video in R2, not in
  the database or Supabase Storage.

Supabase is a reasonable pilot database **only if** you accept those limits and
keep off-host dumps. Do not treat the free project as a backup or as an
always-on production HA service.

#### Supabase Storage

Supabase Storage is S3-compatible and supports range requests and multipart
uploads, so it looks tempting as a drop-in object store. The Free plan is the
blocker:

- 1 GB total file storage;
- 50 MB maximum file upload on Free;
- a 60–120 second 1080p render can exceed 50 MB, and a pilot needs two renders
  per video plus captures.

Use Supabase Storage only for small thumbnails, covers or other assets that
fit under the cap. Keep video and captures in R2. If you later use it, test the
path-style S3 endpoint, region, access keys and a small upload before changing
`MTK_STORAGE_BACKEND`.

#### Cloudinary Free

Cloudinary is a media transformation and delivery service, not an
S3-compatible bucket. The Free plan gives 25 monthly credits, shared across
managed storage, transformations and delivery; video processing and bandwidth
consume those credits quickly. A custom domain is a paid plan feature, and the
current code has no Cloudinary adapter.

Use Cloudinary only if you need automatic image transformations for thumbnails
or covers, and add a deliberate derivative step that uploads the approved
output and returns a public HTTPS URL. Do not make it the primary video origin
for scheduled publishing without measuring credits and adding an integration
and fallback.

#### Google Drive 2 TB

Google Drive is a good **backup target**:

- copy database dumps, raw captures and project archives;
- keep a separate folder for `mtk-radar/backups` and `mtk-radar/archive`;
- encrypt dumps before upload because they contain evidence excerpts and
  metadata;
- use `rclone` with a dedicated Google Drive remote and a scheduled sync;
- test a restore from Drive, not just the upload.

Example (after `rclone config`):

```sh
# Encrypt a dump first (age or GPG), then copy it off-host.
age -r "$AGE_RECIPIENT" < backups/mtk_radar_latest.dump \
  > backups/mtk_radar_latest.dump.age
rclone copy backups/mtk_radar_latest.dump.age \
  gdrive:mtk-radar/backups/
```

Google Drive is **not** a public media CDN. Sharing links can show an HTML
viewer, require authorization, behave differently for large files, and may not
provide the range/streaming behavior platforms expect. Do not set
`MTK_PUBLIC_MEDIA_BASE_URL` to a Google Drive link. Keep R2 (or another proper
object store with a public HTTPS origin) for Instagram and scheduled media.

The 2 TB benefit is free for one year. Put the expiry date in your calendar and
plan to move backups to R2 or another store before it ends.

#### Recommended combinations

| Setup | Database | Video/media | Backup | When to use |
| --- | --- | --- | --- | --- |
| Cheapest laptop pilot | Local Postgres | R2 | Google Drive + R2 | 1 video/day; laptop on during publish window |
| Lighter split VPS | Supabase Free Postgres | R2 | Google Drive + R2 | Laptop off/travel; accept Free DB limits |
| Avoid | Any database without off-host backups | Supabase Storage, Google Drive or Cloudinary as the primary video origin | Laptop-only | Platforms may fail to fetch; limits and costs surprise you |

---

## 5. Laptop production setup

### 5.1 Host baseline

A practical pilot machine:

- 8 CPU cores preferred; 4 cores can work for less than one video/day;
- 16 GB RAM preferred; 8 GB is workable if Redis/MinIO are not run and only one
  render runs at a time;
- 100 GB free SSD; 200 GB preferred if media is kept locally;
- wired Ethernet preferred; Wi-Fi is acceptable for a pilot;
- laptop plugged in, vents clear, and never running closed in a bag.

CPU FFmpeg rendering is fine at pilot volume. Measure render time on the actual
host before promising a schedule. For 10/day, a laptop may spend several hours
per day rendering; that is the point at which a dedicated render host or a
larger VPS makes sense.

### 5.2 Start the stack

```sh
cp .env.example .env          # fill it in; never commit it
docker compose -f infra/docker/docker-compose.yml up -d \
  postgres redis api dashboard
docker compose -f infra/docker/docker-compose.yml exec api python db_migrate.py
```

Start only the workers you need:

```sh
docker compose -f infra/docker/docker-compose.yml --profile workers up -d \
  collectors verification batch render publishing monitor metrics
```

The current Compose file is development-oriented. The dashboard runs
`npm install && npm run dev`, and the render service installs FFmpeg on start.
For daily laptop use, build two small production images once (dashboard
production image, render image with FFmpeg) or run the render worker on the
host. That saves time and network on every boot and avoids treating a package
install as part of production startup.

### 5.3 Current Compose gaps to fix before relying on it

These are real gaps in the current repository configuration; fix them in the
deployment or run the affected worker on the host:

1. **Instagram credentials are not passed to the publishing worker.** Add
   `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN` and
   `MTK_PUBLIC_MEDIA_BASE_URL` to the publishing service environment (or run
   the publisher on the host with them set).
2. **`VERIFY_LLM_*` is not passed to the verification worker.** The LLM
   extractor is optional; if you use it, add the variables to the verification
   service or run the worker on the host.
3. **`TTS_*` is not passed to the render worker.** Voiceover is optional; add
   the variables only when you deliberately enable it.
4. **One S3 bucket is used for captures and renders.** Do not make the capture
   bucket public for Instagram; separate approved public derivatives first.

### 5.4 Power and sleep

The laptop is the server, so sleep equals downtime. Use a publish window and
keep the machine awake during it:

- **macOS:** `caffeinate -dimsu` while the publish window is active.
- **Linux:** prefer a desktop power profile that disables suspend while
  plugged in, or wrap the window in
  `systemd-inhibit --what=sleep:idle --why="MTK publish window" ...`.
- **Windows:** set the plugged-in standby timeout to never for the window, or
  use a small PowerShell keep-awake script; restore the normal setting after.

Do not disable thermal protection or run the laptop in a closed bag. If the
laptop sleeps, the publisher simply does not run; on wake, due posts are picked
up if they are still valid. If a post must go out at an exact time, either keep
the laptop awake or use the split VPS from §6.

Add an external uptime check (for example a free HTTP monitor) against the
dashboard or a small health endpoint. A local log cannot alert you when the
whole laptop is off.

### 5.5 Daily operating window

A realistic 1-video/day block:

| Step | Time |
| --- | ---: |
| Start stack, check holds/expiring offers, collect | 10 min |
| Capture the real walkthrough | 15–25 min |
| Redaction review and evidence recheck | 10–20 min |
| Script/metadata review, render, approve | 10–20 min |
| Schedule inside the publish window and confirm remote status | 5–10 min |

Batch two or three captures in one session when possible. The setup and
redaction review are the expensive parts, not the FFmpeg command.

### 5.6 Secrets

- Keep `.env` out of git; use mode `600` and full-disk encryption.
- Store production secrets in 1Password or the OS keychain; inject them at
  start, do not paste them into the dashboard.
- Use a separate OS user/profile for production and platform accounts.
- Use long-lived, least-privilege platform tokens; rotate on a schedule and
  immediately after a lost device or suspicious activity.
- Keep `MTK_API_TOKEN`, reviewer tokens, `MTK_FETCH_SIGNING_KEY`, R2 keys and
  platform OAuth credentials distinct. Do not reuse a model API key as a
  platform token.

### 5.7 Backups and recovery

```sh
bash infra/backup.sh 14
```

When `MTK_S3_*` is configured on the host, the script also copies the dump to
the object store. A backup that exists only on the same laptop is not a backup.

Monthly:

```sh
bash infra/drill.sh
```

or restore the newest dump into a throwaway database and compare row counts and
migration counts. Keep the restore drill as a release-blocking habit.

Also back up:

- `.env` or the vault references (not plaintext in the same backup as the DB);
- the R2 bucket configuration and public-domain settings;
- Cloudflare Tunnel configuration and Access policies;
- platform app IDs, OAuth client IDs and credential *references* (not secrets).

---

## 6. When the laptop is off: VPS fallback

### 6.1 Choose the mode deliberately

| Mode | What runs where | Best for | Main tradeoff |
| --- | --- | --- | --- |
| **Laptop only** | Everything on the laptop | 1 video/day, laptop on during a publish window | No publishing while asleep/offline |
| **Split VPS (recommended fallback)** | VPS: PostgreSQL, Redis, API, publishing, monitor, metrics, collectors/verification/batch; laptop: capture, render, review | Reliable scheduled publishing; travel; laptop can sleep | Two hosts to maintain; one control plane to keep safe |
| **Full VPS** | Everything except human capture | Short trips or higher volume where render must also run remotely | CPU/storage cost; capture still needs a human machine |

The split VPS is the best reliability upgrade for a small extra monthly cost.
The laptop remains the render/capture workstation; the VPS owns the queue and
publisher so already-rendered scheduled posts can go out while the laptop is
closed.

The full VPS does **not** remove the human capture/redaction step. It only moves
render and publishing. At pilot volume, that is usually unnecessary.

### 6.2 Split-VPS cost

| Item | Estimated monthly |
| --- | ---: |
| 2 vCPU / 4 GB VPS, 40–80 GB SSD | $6–$20 |
| VPS snapshots/backups | $1–$5 |
| R2 beyond free tier | $0–$3 |
| Domain | $0 year one; renewal later |
| **Total cash** | **~$7–$28** |

Use a provider and region that are reliable for your audience and platform
APIs. Cheap is not useful if the VPS is oversold or your uploads stall. Check
included bandwidth; 1/day is small, 10/day with four platforms is not.

### 6.3 VPS sizing

- **Control plane only (split mode):** 2 vCPU / 4 GB RAM / 40–80 GB SSD is a
  reasonable starting point for PostgreSQL, Redis, API, publishing, monitor,
  metrics, collectors, verification and batch. Measure before moving render.
- **Full stack with render:** start at 4 vCPU / 8 GB RAM / 100 GB+ SSD and
  benchmark 1080p H.264 render time. Disk and CPU are the bottlenecks.
- **Database:** keep PostgreSQL on the VPS for the pilot; a managed database is
  an optional reliability/cost upgrade, not a requirement. Supabase Free can
  remove Postgres from the VPS, but its pause behavior, 500 MB limit and lack
  of automatic backups mean you still need off-host dumps and monitoring.
- **Object storage:** use R2 from both hosts. Do not copy large media between
  the laptop and VPS by hand. Do not put video in Supabase Storage or Google
  Drive.

### 6.4 Cutover procedure (laptop → split VPS)

Treat the VPS as a **single control plane**, not a second independent
deployment. Two publishers writing to different databases is how duplicate
posts happen.

1. **Stop the laptop publisher first.** Stop `publishing`, and optionally
   `collectors`, `verification`, `batch`, `monitor` and `metrics` on the laptop.
   Let in-flight uploads finish; check the calendar for HELD/unknown outcomes.
2. **Back up and verify the laptop database.**
   ```sh
   bash infra/backup.sh 14
   ```
   Confirm the dump exists and restore it into a throwaway database before
   relying on it.
3. **Provision the VPS.** Install Docker/Compose, clone this repository, and
   copy `.env` through 1Password or another secret channel.
4. **Set the VPS environment.** At minimum:
   - `POSTGRES_PASSWORD`, `DATABASE_URL`;
   - `MTK_API_TOKEN`, `MTK_FETCH_SIGNING_KEY`;
   - `MTK_STORAGE_BACKEND=s3`, `MTK_S3_*`;
   - `MTK_SESSION_SECRET` (required for dashboard login);
   - `MTK_PUBLIC_MEDIA_BASE_URL`, `MTK_CORS_ORIGINS`,
     `API_URL`, `MTK_PUBLIC_BASE_URL`;
   - platform OAuth credentials and Instagram variables;
   - model/TTS variables only if you use them.
5. **Start PostgreSQL, Redis and the API on the VPS.** Run migrations, restore
   the newest dump into a fresh database, verify row counts and `/health`.
6. **Start only the control-plane workers on the VPS:** `publishing`,
   `monitor`, `metrics`, and optionally `collectors`, `verification` and
   `batch`. Do not start the laptop publisher again.
7. **Point the laptop render worker at the VPS API**, not at its local API:
   `API_URL=https://api.example.com`, same `MTK_API_TOKEN`, same R2 bucket.
   Render on the laptop, write approved derivatives to R2, and let the VPS
   publisher pick them up.
8. **Move Cloudflare Tunnel/Access to the VPS** for `app` and `api`. Keep the
   laptop tunnel off so only one host answers.
9. **Test with a private post.** Confirm upload, remote processing/visibility,
   metrics and a correction path before enabling normal schedules.
10. **Keep the laptop render/capture path.** The laptop can be off when no new
    video is being produced; scheduled, already-rendered posts still publish
    from the VPS.

To reverse the cutover, stop the VPS publisher, back up the VPS database,
restore it on the laptop, point DNS/Tunnel back, and start exactly one
publisher. Never run both publishers against separate queues.

### 6.5 VPS hardening checklist

- SSH keys only; disable password login; firewall allows only SSH and the
  Cloudflare Tunnel outbound path.
- Cloudflare Access on dashboard/API; no public PostgreSQL, Redis or MinIO.
- Automatic security updates; reboot window outside publish times.
- Off-host backups and a tested restore; VPS provider snapshots are not a
  substitute for a database dump.
- Disk-space and backup-failure alerts; a full disk can stop uploads silently.
- Pin image versions and avoid `apt-get`/`npm install` on every container
  start.
- Timezone set consistently; schedule windows and monitoring use the same
  timezone assumptions.
- Non-root services where practical; read-only code mounts; explicit writable
  volumes.

---

## 7. Future recommendations

### 7.1 Protect the trust gates

- Keep official evidence, domain ownership, script-hash binding, redaction
  review and human approval as hard gates.
- Keep the LLM as an extractor/assistant. It must never become the evidence
  source or the final approver.
- Keep expiry and correction auto-pause. A delayed post is better than a wrong
  public post.
- Do not call a video published until remote processing/visibility is
  confirmed.

### 7.2 Measure the right number

Track weekly:

- cash cost per QC-passed delivered video;
- operator minutes per video and where they go;
- failed attempts and abandoned work;
- platform approval/processing delays;
- storage growth and egress;
- quota usage (especially YouTube upload and metadata calls).

If review is 80% of the cost, optimize review preparation, not the server bill.
If render time is the bottleneck, measure before buying a GPU.

### 7.3 Control storage and retention

- Keep 90-day media retention for the pilot unless a platform or legal
  requirement says otherwise.
- Prune unreferenced renders and captures; never prune media that is still
  being fetched or is needed for a correction.
- Keep evidence snapshots and audit history according to the runbook and
  applicable terms; do not confuse media retention with evidence retention.
- Add lifecycle rules to the public derivative bucket, not the private capture
  bucket.

### 7.4 Tokens and platform operations

- Rotate platform tokens and R2 keys on a schedule and after any device loss.
- Use least-privilege scopes; keep the YouTube Analytics read scope needed for
  metrics.
- Request a YouTube quota audit when upload volume or metadata calls approach
  the daily quota. Stagger uploads and avoid unnecessary thumbnail/caption
  calls.
- Re-verify Meta app review, Instagram professional-account/public-media
  requirements and TikTok app approval before scaling.
- Keep a manual takedown/correction path even when automation is enabled.

### 7.5 Do not let expiring credits become core infrastructure

Azure, Heroku, Render and similar credits are useful for experiments, staging
or a short migration test. They are not a permanent production plan. Migrating
the database, OAuth callbacks and media at short notice costs more than the
credit saved.

The MongoDB Atlas credit is not a reason to add MongoDB. MTK RADAR uses
PostgreSQL; a second database increases backup, monitoring and consistency
work. Spend that credit only on a genuinely separate experiment.

Likewise, do not run production on GitHub Actions, Codespaces or GitHub Pages.
They are excellent for CI, development and static legal pages; they are not a
persistent API/database/publisher.

### 7.6 When to upgrade the setup

| Trigger | Upgrade |
| --- | --- |
| Posts miss their window because the laptop sleeps | Split VPS for API/publishing |
| Travel or unreliable home internet | Split VPS + external uptime monitor |
| Render blocks daily work | Dedicated render mini-PC or full VPS |
| 10+/day sustained | Larger control plane, batch capture days, part-time reviewer, storage lifecycle rules |
| Review backlog grows | Templates, model-assisted prep, batching; do not lower gates |
| YouTube quota or platform review limits growth | Quota audit, platform-specific scheduling, fewer but better videos |

### 7.7 Keep the first-year student stack simple

The highest-leverage free resources are the **domain + Cloudflare + R2 +
GitHub CI + the four River models**. Add the rest only when they solve a
measured problem:

- **DeepSeek V4.1 Flash 1017** — coding, migrations, debugging, release work.
- **DeepSeek V4.1 Flash** — bulk extraction, log triage, metadata drafts.
- **GLM 5.3 Flash** — Urdu/English copy, second-opinion review, policy wording.
- **NVIDIA Nemotron 3.5 Super VL** — screenshots, frames, thumbnails, visual QC.

Use the strongest/highest variant for code and final review, and cheaper/lower
variants for bulk work. Keep the runtime deterministic unless a model adds
measured value. Do not send platform credentials, private captures or personal
data to free models.

### 7.8 Does the system use n8n?

**No.** MTK RADAR does not use n8n in the current stack.

- The repository has its own worker loops: `collectors`, `verification`,
  `batch`, `render`, `publishing`, `metrics` and `monitor`.
- Scheduling and retries live in the API/worker code, with the database as the
  source of truth.
- n8n was evaluated and deliberately **not adopted**: its Sustainable Use
  License is not a standard OSI license, and adding it would create another
  deployment surface, another place for secrets, and a second scheduler/source
  of truth.
- There is no n8n service in `infra/docker/docker-compose.yml`, no n8n package
  dependency and no n8n workflow in the repository.

For a one-laptop setup, do not add n8n just to send alerts or move files. The
existing monitor worker now sends an optional JSON webhook and/or SMTP email
digest; see [`notifications.md`](notifications.md). If you later use n8n for a
genuinely separate notification experiment, keep it outside the publishing path
and do not let it own approvals, schedules or evidence.

---

## 8. Decision summary

- **For a 1-video/day pilot:** use the laptop, a free first-year domain,
  Cloudflare Tunnel/Access, R2, Supabase Free if you want managed Postgres,
  Google Drive for backups, GitHub CI and the free models. Keep posts inside a
  laptop-on window. Cash cost is roughly **$3–$11/month in year one**, or up to
  about **$17** if the laptop runs 24/7 or electricity is expensive; review
  time is the real cost. All-in with 30–60 minutes of review per video is
  roughly **$225–$1,500/month**.
- **For orchestration:** use the built-in workers and scheduler. **Do not add
  n8n** to the core publishing path; it is not used by this repository and would
  add a license/deployment/second-source-of-truth problem.
- **For reliable scheduled publishing:** add the split VPS. Keep the laptop for
  capture/render; let the VPS own PostgreSQL, API, queue and publishing. Expect
  roughly $7–$28/month extra cash before domain renewal.
- **For a full remote stack:** use a larger VPS or dedicated render host only
  after measuring CPU, disk and bandwidth. Capture and redaction still need a
  human machine.
- **For a short trip or cutover drill:** the Render credit can fund a temporary
  control plane if the services are containerized; otherwise use the split VPS.
  The MongoDB Atlas credit is for a separate experiment, not the core database.
- **For managed Postgres:** Supabase Free is workable as a pilot database with
  off-host dumps, but not with its Storage as the video origin. Keep R2 for
  renders; use Google Drive for encrypted backups, not public media.
- **Never trade away:** official evidence, domain checks, script-hash binding,
  redaction review, human approval, expiry/correction pause, or remote
  visibility confirmation.

---

## 9. Related documents

- [`runbook.md`](runbook.md) — deployment, migrations, backup/restore, credential
  recovery and incident playbooks.
- [`go-live-checklist.md`](go-live-checklist.md) — keys, platform connections and
  the first real post.
- [`automation-master-plan-2026-10-21.md`](automation-master-plan-2026-10-21.md) —
  capacity, budget guidance and the cost-per-QC-passed-video rule.
- [`security-and-redaction.md`](security-and-redaction.md) — secrets, capture and
  privacy rules.
- [`open-source-integrations.md`](open-source-integrations.md) and
  [`third-party-notices.md`](third-party-notices.md) — why n8n, Postiz and
  similar platforms are not part of the core stack.
- [`first-offer-recipe.md`](first-offer-recipe.md) — the one-video pilot recipe.

## 10. References to re-check before purchase

- GitHub Student Developer Pack: <https://education.github.com/pack>
- GitHub Actions billing: <https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions>
- Cloudflare Tunnel: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>
- Cloudflare R2 pricing: <https://developers.cloudflare.com/r2/pricing/>
- Cloudflare R2 public buckets: <https://developers.cloudflare.com/r2/buckets/public-buckets/>
- Render pricing: <https://render.com/pricing>
- Render Docker services: <https://render.com/docs/docker>
- MongoDB Atlas pricing: <https://www.mongodb.com/pricing>
- Supabase pricing and Free limits: <https://supabase.com/pricing>
- Supabase Storage S3 compatibility: <https://supabase.com/docs/guides/storage/s3/compatibility>
- Cloudinary pricing and credits: <https://cloudinary.com/pricing>
- Google Drive file/storage limits: <https://support.google.com/drive/answer/37603>
- YouTube API quota: <https://developers.google.com/youtube/v3/determine_quota_cost>
- Instagram content publishing: <https://developers.facebook.com/docs/instagram-platform/content-publishing>
- TikTok Content Posting API: <https://developers.tiktok.com/doc/content-posting-api-get-started>
