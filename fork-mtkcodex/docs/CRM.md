# Lead CRM, inbox & outreach runbook

The marketing site doubles as the MTK Codex CRM. Everything lives in this Next.js app — no
third-party CRM or chat subscription.

| Page | What it does |
|---|---|
| `/admin` | Leads: pipeline table, filters, bulk actions, import/export, today's to-dos, live visitors |
| `/admin/inbox` | One inbox for **website live chat, WhatsApp and email** — read and reply from anywhere |
| `/admin/deals` | Kanban for work in progress (discovery → proposal → in progress → delivered) |
| `/admin/outreach` | Click-to-send WhatsApp queue for cold outreach (from your own phone) |
| `/admin/analytics` | Traffic, live visitor map with city/region/country, outreach numbers |
| `/admin/settings` | Which channels are connected, phone/desktop alerts, webhook URLs |
| `/admin/docs` | Short in-app playbook |

On a phone, install the admin as an app (Settings → *Install on your phone*) and turn on alerts.

---

## 1. Go-live checklist

Do these in order. Steps 0–2 are required; every channel after that is optional and switches
on by itself once its env vars are set. All values go in your host's environment variables
(**Netlify → Project configuration → Environment variables**), then **redeploy**. For local
testing put the same values in `.env.local` (gitignored).

### Step 0 — Hosting on Netlify (free, commercial use allowed)

Vercel's free Hobby plan is for non-commercial sites only, so the site runs on **Netlify's free
plan**, which allows business sites. The code is host-neutral: visitor locations and client IPs
are read from Netlify, Vercel or Cloudflare headers automatically, and `netlify.toml` holds the
build settings. Do this on your laptop, in order:

1. **Database first.** Finish Step 1 (Supabase + all four migrations). The site needs it to save anything.
2. **Create the site.** [app.netlify.com](https://app.netlify.com) → *Add new project* → *Import an
   existing project* → GitHub → pick the repository and the branch to deploy (`main` once the
   pull request is merged). Netlify reads `netlify.toml`; don't change the build settings.
3. **Environment variables.** *Project configuration → Environment variables → Import from a .env
   file*. Paste the contents of your filled-in `.env.local` (see `.env.example`). Keep the scopes
   on *Builds* **and** *Functions*. Set `NEXT_PUBLIC_SITE_URL=https://mtkcodex.tech`.
   `NEXT_PUBLIC_*` values are baked in at build time, so **redeploy after changing them**.
4. **Deploy** (*Deploys → Trigger deploy*). Test on the free address Netlify gives you
   (`https://<name>.netlify.app`): open `/admin/login`, sign in, open `/admin/settings`.
5. **Connect the domain.** *Domain management → Add a domain* → `mtkcodex.tech` (add `www` too).
   Pick **one** DNS option:

   **Option A — Netlify DNS (recommended, everything in one place)**
   1. Choose *Set up Netlify DNS*. Netlify lists four nameservers.
   2. Before switching, re-add your email records in Netlify DNS: the Resend DKIM (`resend._domainkey`),
      `send` MX + TXT, receiving MX and `_dmarc` TXT from Step 3 (copy them from Resend → Domains).
   3. At your **.tech registrar's control panel** (where you bought the domain) → *Nameservers*:
      replace `ns1.vercel-dns.com` / `ns2.vercel-dns.com` with Netlify's four nameservers.
   4. Wait for propagation (often under an hour, up to 24–48 h). Netlify issues the HTTPS
      certificate automatically.

   **Option B — keep DNS at Vercel (fewest changes)**
   1. In Vercel, remove `mtkcodex.tech` from the old *project* but keep it under *Domains* (DNS stays at Vercel).
   2. In Vercel → Domains → `mtkcodex.tech` → DNS records, point the site at Netlify using the exact
      values Netlify's domain screen shows: an `A` record for `@` (Netlify's load balancer IP,
      `75.2.60.5` at the time of writing) and a `CNAME` for `www` → `<name>.netlify.app`.
      Leave the Resend email records as they are.

6. **Webhooks need no change** — they use the domain: `https://mtkcodex.tech/api/email/webhook`
   (Resend) and `https://mtkcodex.tech/api/whatsapp/webhook` (Meta). After DNS switches, send a
   test email and a chat (Step 7).
7. **Retire Vercel** only after the Netlify site works on `mtkcodex.tech`: delete the Vercel project
   (with Option B keep the domain in your Vercel account, because it still serves DNS).
8. **Watch usage.** The free plan has 300 credits a month and **pauses the site if they run out**;
   Netlify emails you at 50 %, 75 % and 100 %. Check *Usage* weekly at first. The live chat polls
   adaptively (3 s mid-conversation, 8 s idle, 30 s in the background, then stops) to stay light.
   If you outgrow the free plan, the next free step is your own small server (e.g. Oracle Cloud
   Always Free) behind Cloudflare — the app already reads Cloudflare's location headers (turn on
   *Add visitor location headers* in Cloudflare → Rules → Managed Transforms).

Limits to know: serverless functions time out after 10 s (imports are sent in chunks of 200 rows
for that reason), and the filesystem is read-only, so production always uses Supabase.


### Step 1 — Database (required) · Supabase free tier

1. Create a project at [supabase.com](https://supabase.com).
2. SQL Editor → run each migration **in order**, once:
   `supabase/migrations/0001_leads.sql` → `0002_analytics.sql` → `0003_first_contacted.sql` → `0004_crm_v2.sql`.
   Run `0004` **before** deploying this version: the new code writes columns it adds.
3. Project Settings → API keys → copy the **Project URL** and the **secret** key
   (`sb_secret_…`, or a legacy `service_role` key).
4. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

RLS is on for every table with no policies, so only the server (secret key) can read data.
Free Supabase projects pause after a week with no activity; normal site traffic keeps it awake.

### Step 2 — Admin login (required)

| Variable | Value |
|---|---|
| `ADMIN_EMAIL` | your login email |
| `ADMIN_PASSWORD` | a long password |
| `ADMIN_SESSION_SECRET` | 32+ random bytes, e.g. `openssl rand -hex 32` (also keys the analytics hash and chat resume links) |
| `NEXT_PUBLIC_SITE_URL` | `https://mtkcodex.tech` (used in alert and email links) |

### Step 3 — Email: send and receive · Resend free (3,000 emails/month, 100/day)

Add these records wherever your DNS lives: **Netlify DNS** after Step 0 option A, or **Vercel →
Domains → mtkcodex.tech → DNS Records** if you kept DNS at Vercel (option B). Today the
nameservers are `ns1/ns2.vercel-dns.com`. If you do email before moving DNS, re-create the same
records in Netlify DNS before switching nameservers.

**3a. Sending**

1. Sign up at [resend.com](https://resend.com) → **Domains → Add domain** → `mtkcodex.tech`.
2. Resend shows the records to add. Copy each **exactly** (names and values come from Resend):
   | Type | Name (in Vercel) | Purpose |
   |---|---|---|
   | TXT | `resend._domainkey` | DKIM signature |
   | MX | `send` | Bounce handling (SPF) |
   | TXT | `send` | SPF (`v=spf1 include:… ~all`) |
3. Recommended extra record for deliverability (add yourself):
   `TXT` · name `_dmarc` · value `v=DMARC1; p=none; rua=mailto:<your email>`.
4. Wait for Resend to show **Verified** (usually minutes).
5. API Keys → create a key with **Full access** (sending + reading received mail).
6. Set `RESEND_API_KEY` and `EMAIL_FROM` = `Kashif at MTK Codex <hello@mtkcodex.tech>`.
   `CONTACT_TO_EMAIL` = where contact-form copies go (your Gmail).

**3b. Receiving (client replies land in the inbox)**

1. Resend → Domains → `mtkcodex.tech` → enable **Receiving**. Resend shows one more **MX**
   record — add it in Vercel DNS with the name and priority shown (for the root domain the
   name is `@`). The domain has no other mail provider, so there is no conflict.
2. Resend → **Webhooks → Add webhook** → URL `https://mtkcodex.tech/api/email/webhook`,
   event **`email.received`**. Copy the signing secret (`whsec_…`).
3. Set `RESEND_WEBHOOK_SECRET` = that secret and `EMAIL_REPLY_DOMAIN` = `mtkcodex.tech`.
4. Optional: `EMAIL_FORWARD_TO` = your Gmail, to also get a copy of every inbound email.

How routing works: each lead gets a private reply address `r-<token>@mtkcodex.tech`. Replies to
it, or any email from a lead's known address, go into that lead's email thread. Mail from
someone new (e.g. to `hello@mtkcodex.tech`) creates a lead with source `email`.

> If you later move company mail to Google Workspace on the root domain, switch Resend
> receiving to a subdomain such as `reply.mtkcodex.tech` and set `EMAIL_REPLY_DOMAIN` to it.

### Step 4 — Phone & desktop alerts (free)

**Push (installed app):**

1. Run `npx web-push generate-vapid-keys` once.
2. Set `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT` = `mailto:<your email>`.
3. On each device: open `/admin/settings` → **Turn on alerts**. On iPhone, first Share →
   *Add to Home Screen*, open the app from the home screen, then turn on alerts (iOS 16.4+).

**Telegram (optional backup, very reliable):**

1. In Telegram, message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Alerts fire for: new live chat (and new messages, at most every 3 minutes per chat), a chat
visitor sharing their details, WhatsApp replies, inbound emails and contact-form enquiries.
Use **Send test alert** in Settings to check.

### Step 5 — "Book a call" link (free)

Create a free booking page (Cal.com, or Google Calendar → *Appointment schedule*) for a 15-minute
video call and set `NEXT_PUBLIC_BOOKING_URL`. It appears in the live chat, the contact page and
the inbox. This is the main way US/UK clients reach you by voice until you add a phone number.

### Step 6 — WhatsApp Cloud API (optional)

Keep using the Outreach desk (wa.me from your phone) until this is set up.

1. [Meta for Developers](https://developers.facebook.com/apps) → create a **Business** app → add **WhatsApp**.
2. Register a phone number for the API. It cannot also be active in the WhatsApp phone app
   (use a second SIM, or migrate the number).
3. Business Settings → System users → create one with a **permanent token** (scopes
   `whatsapp_business_messaging`, `whatsapp_business_management`).
4. Set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET` (App settings → Basic),
   `WHATSAPP_VERIFY_TOKEN` (any random string), optionally `WHATSAPP_TEMPLATE_NAME`,
   `WHATSAPP_TEMPLATE_LANG`, `WHATSAPP_API_VERSION` (default `v23.0`). Redeploy.
5. WhatsApp → Configuration → webhook URL `https://mtkcodex.tech/api/whatsapp/webhook`, the same
   verify token, subscribe to **messages**.

Rules the inbox enforces: free-text replies only within 24 hours of the customer's last message;
outside that window only an approved template can be sent. Replying `STOP` marks the lead
do-not-contact automatically.

### Step 7 — Check it works

1. Open the site in a private window → chat bubble → **Chat with the team** → send a message.
   It appears in `/admin/inbox` with the visitor's city and local time; your phone gets an alert.
2. Reply from the inbox. With the visitor's tab closed and an email given in the chat, the reply
   is also emailed with a "continue the chat" link.
3. Submit the contact form → a starred lead appears on `/admin` with location and preferred channel.
4. Email `hello@mtkcodex.tech` from another account → it lands in the inbox as an email thread.
5. `/admin/analytics` → your visit shows on the live map.

---

## 2. How international clients reach you

| Client | First contact | Ongoing |
|---|---|---|
| Pakistan | WhatsApp (outreach desk), live chat | WhatsApp / inbox |
| UAE, Saudi, Qatar | Live chat, WhatsApp, contact form | WhatsApp or email in the inbox |
| UK / EU | Live chat, contact form | Email in the inbox, booked video calls |
| US / Canada | Live chat, contact form | Email in the inbox, booked video calls (no US number needed) |

- The chat tells visitors when you're online, and when you're away it says when you'll be back
  **in their own timezone** (office hours: Mon–Sat 10:00–19:00 Lahore, from `src/data/site.ts`).
- The contact form has a country-code picker (defaults from the visitor's timezone), a
  "best way to reach you" choice, and records their timezone.
- Every lead shows its city, region, country and **their local time**, so you reply at a sensible hour.
- A US/Canada SMS/call number (e.g. Quo or Twilio) can be added later without changing this setup.

---

## 3. Access & security

| Item | Value |
|---|---|
| Login | `/admin/login` with `ADMIN_EMAIL` + `ADMIN_PASSWORD` |
| Session | 8-hour HMAC-signed cookie, `HttpOnly`, `SameSite=Lax`, `Secure` in production |
| Writes | Session + same-origin check on every admin API call |
| Throttling | Login, contact form and chat are rate-limited in Postgres (`rate_limit_hit`), shared across serverless instances |
| Webhooks | WhatsApp (`X-Hub-Signature-256`) and Resend (Svix signature, 5-minute window) are verified on the raw body |
| Chat visitors | Hold a random token; only its SHA-256 is stored. Resume links are signed and expire in 14 days |
| Headers | CSP, HSTS, `nosniff`, frame-ancestors; `/admin` is `no-store`, `noindex` |

Rotate the password by changing `ADMIN_PASSWORD` and redeploying. Rotating
`ADMIN_SESSION_SECRET` signs everyone out and invalidates chat resume links.

Never commit lead data or credentials. Private batches and outreach logs live in `.data/`
(gitignored).

---

## 4. Storage modes

| Mode | When | Behaviour |
|---|---|---|
| `supabase` | Supabase vars set | Everything persists. Required for production. |
| `file` | No Supabase, on your own machine or server | `.data/leads.json`, `activities.json`, `messages.json`, `chats.json`… The first run seeds from `.data/leads.seed.json` if present. |
| `readonly` | No Supabase on Netlify/Vercel (serverless) | Empty, read-only CRM with a banner; live chat is hidden. |

Supabase notes: send the secret key in both `apikey` and `Authorization` (the adapter does);
values pasted into Vercel may carry whitespace (trimmed in code). Lists page through PostgREST's
1,000-row cap, so large imports show in full.

---

## 5. Data model

| Table | Purpose |
|---|---|
| `leads` | One row per business/person: profile, status, deal stage/value, tags, star, location, preferred channel, unread count |
| `lead_activities` | Timeline: created, import, status, note, follow-up, deal, message in/out, opt-out, edit |
| `messages` | Every message on every channel. `thread_key` = `web:<chat id>`, `wa:<digits>` or `email:<address>` |
| `chat_sessions` | Website chat visitors: details they shared, page, device, city/region/country/timezone, presence |
| `page_views` | Cookieless analytics incl. city/region/timezone and coordinates rounded to ~10 km |
| `push_subscriptions` | Devices that receive alerts |
| `rate_limits`, `app_state` | Shared throttles; admin "online" presence |

### Status and deals

```
new → queued → contacted → replied → interested → won
                    ↘ lost        queued/contacted → skipped (not on WhatsApp)
```

Deal stages (Deals board): `discovery → proposal → negotiation → in_progress → review → delivered`
(+ `on_hold`). Moving a deal to discovery/proposal/negotiation marks the lead **Interested**;
in progress or later marks it **Won**. A reply on any channel moves `new/queued/contacted` to
**Replied**. `do_not_contact` blocks queueing and sending everywhere and is set automatically on
`STOP` / `unsubscribe`.

---

## 6. Daily workflow

1. **Inbox first** (`/admin/inbox`): answer live chats, WhatsApp replies and emails. Keep the tab
   (or the installed app) open — that's what shows visitors you're online.
2. **Leads** (`/admin`): check *Follow-ups due* and *Hot leads*; star important ones; set the next
   follow-up from the drawer (quick buttons +2d/+3d/+1w).
3. **Outreach** (`/admin/outreach`): click-to-send cold WhatsApp from your own phone. The page
   counts first messages today against a safe ~20/day limit.
4. **Deals** (`/admin/deals`): drag work through the stages and keep values current.

Never automate bulk WhatsApp from a personal number — it gets numbers banned. The Cloud API is the
compliant route for automation.

---

## 7. Import & export

- **Import** (`/admin` → Import): upload a CSV/TSV (Excel: *Save as CSV*) or paste a Google Sheets
  link shared as "Anyone with the link can view". Columns are auto-matched (scraper names like
  `phone_e164`, `lead_score` work), with a preview. Leads are de-duplicated by id, phone and email;
  choose **Skip** or **Refresh profile** for existing ones (status, notes and history are never
  overwritten). Local numbers `0300…` become `+92300…`. Large sheets upload in chunks of 500.
- **Export**: *Export all* (server CSV), *Export these N* (current filters) or *Export* on a
  selection. Cells that would run as spreadsheet formulas are neutralised.
- `scripts/import-sent-log.mjs <sent.csv> [--apply]` reconciles a WhatsApp sent log from the
  scraper into Supabase (dry run by default, idempotent).
- Set `LEADS_SHEET_URL` to show a link to your private warehouse sheet in the admin.

---

## 8. Analytics & live locations

`/admin/analytics` shows live visitors on a world map plus a list (city, region, country, page,
device, their local time), top cities and countries, sources, pages and outreach numbers. The
strip on `/admin` lists who is on the site right now.

- Location comes free from the host's edge: Netlify `x-nf-geo`, Vercel `x-vercel-ip-*` or Cloudflare
  `cf-ip*` headers (`src/lib/geo.ts` reads whichever is present). Local development has none.
- Cookieless: the visitor id is a daily `HMAC(day, IP, user-agent, ADMIN_SESSION_SECRET)`; no
  cookies or storage. Do Not Track, Global Privacy Control and an "analytics off" choice are honoured.
- Only real public pages are recorded; bots, `/admin` and `/api` are ignored.
- Retention: run `select public.analytics_prune(180);` monthly.

---

## 9. Costs (start free, upgrade when needed)

| Service | Free tier | When to pay |
|---|---|---|
| Supabase | 500 MB database | Paid plan for daily backups / more storage |
| Resend | 3,000 emails/month, 100/day | Pro (~$20/mo) when you send more |
| Web Push, Telegram | Free | — |
| Cal.com / Google appointment schedule | Free | — |
| WhatsApp Cloud API | Replies inside the 24h window are free | Template (business-initiated) messages are billed per message |
| Netlify (hosting) | 300 credits/month, commercial use allowed; site pauses if exceeded | Pro, or move to a free VM behind Cloudflare |
| Vercel (not used) | Hobby is non-commercial only | Pro ($20/mo) if you ever move back |

Live chat polls adaptively — 3 s mid-conversation, 8 s when open but quiet, 30 s in the background
for the unread badge, and not at all after 30 quiet minutes — so function usage stays small.

---

## 10. File map

| Path | Purpose |
|---|---|
| `src/lib/leads.ts` | Lead storage (Supabase / file / read-only), patch rules, import, activity log |
| `src/lib/inbox.ts` | Unified inbox: conversations, WhatsApp + email inbound, sending from the dashboard |
| `src/lib/chat.ts` | Website live chat sessions, presence, auto-replies, resume links |
| `src/lib/message-store.ts` | Message table shared by inbox and chat |
| `src/lib/email.ts` | Resend send/receive, webhook verification, reply parsing |
| `src/lib/whatsapp.ts` | Cloud API send, webhook parsing, opt-out detection |
| `src/lib/notify.ts` | Push + Telegram alerts, admin presence |
| `src/lib/geo.ts`, `src/lib/business-hours.ts` | Visitor location (Netlify/Vercel/Cloudflare); office hours in any timezone |
| `netlify.toml` | Netlify build settings (Node 22) |
| `src/lib/lead-import.ts` | CSV parsing, column mapping, Google Sheet links |
| `src/lib/lead-types.ts` | Shared types and helpers (client-safe) |
| `src/lib/rate-limit.ts`, `src/lib/admin-auth.ts` | Throttling; sessions and `requireAdmin` |
| `src/components/bot/` | Site chat widget (instant answers + live chat) |
| `src/components/admin/` | Dashboard, inbox, deals, drawer, import, settings, live map |
| `src/app/api/chat/*` | Public chat API (start, send, poll, identify, status) |
| `src/app/api/admin/*` | Session-guarded admin API |
| `src/app/api/{email,whatsapp}/webhook` | Signed inbound webhooks |
| `src/app/admin/{manifest.webmanifest,sw.js}` | Installable admin app + push service worker |
| `supabase/migrations/` | Database schema (run in order) |
| `.data/` | Local-only private data (gitignored) |

---

## 11. Compliance

- Cold outreach: legitimate business reason, a clear opt-out in every first message, at most one
  follow-up, and honour every STOP immediately (the CRM enforces do-not-contact).
- UK/EU visitors: the privacy policy covers live chat and city-level location; chat details are
  used only to reply. Delete a lead on request from its drawer (removes its history).
- Do not use unofficial WhatsApp automation libraries against your number.
