# Monitor notifications — webhook and email

The monitor already logs every alert. This note adds two optional delivery
channels so an alert does not depend on somebody watching a terminal:

- **Outbound webhook** — one JSON POST per alert digest (subject to cooldown).
- **Email digest** — the same payload rendered as a plain-text + HTML email.

Both are best-effort. If the webhook or SMTP server is down, the monitor keeps
sweeping and logs the failure; it never blocks publishing or approval.

**v0.30 split:** operational failures (worker stale/missing, render/QC,
publishing failure, expiries, dead credentials) go out as an **immediate**
alert set. Pending human work (redaction reviews, offer/post approvals,
verification desk, exhausted budget) goes out as a **digest**. A tick with
both categories may deliver two messages; identical sets respect the cooldown.
The dashboard inbox at `/attention` is the current view, but the endpoint
returns at most **50 items per kind**. Per-kind `count` is exact, `returned`
says how many rows came back, and `truncated` is true when the list is capped;
the dashboard shows “showing first N” and a global note (CODE-08 fixed).

> **Where this runs:** in the existing Python `monitor` worker. It does not
> need Supabase, a serverless function, or a new service. Supabase Free is a
> database option, not the notification sender — see
> [Free Supabase: what actually fits](#free-supabase-what-actually-fits).

---

## 1. Quick start

```bash
# 1. Put the values in .env (never in git)
#    Webhook + optional email settings are in .env.example.

# 2. Send one test through every configured channel
docker compose -f infra/docker/docker-compose.yml \
  --profile workers run --rm monitor \
  python workers/monitor/main.py --test-notification

# Local Python (from the repo root, with httpx installed)
python workers/monitor/main.py --test-notification
```

The command prints a safe summary and never prints the webhook token or SMTP
password:

```json
{
  "delivery": {
    "email": "sent",
    "webhook": "sent"
  },
  "notification_config": {
    "email_configured": true,
    "email_recipients": 1,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_ssl": false,
    "smtp_starttls": true,
    "webhook_configured": true
  }
}
```

`not_configured` means the channel is blank. `failed` makes the test command
exit non-zero. Then restart the monitor:

```bash
docker compose -f infra/docker/docker-compose.yml \
  --profile workers up -d --force-recreate monitor
```

If both channels are blank, the monitor behaves exactly as before: alerts go
to its log, and no network call or email is attempted.

---

## 2. Environment variables

### Webhook

| Variable | Meaning |
| --- | --- |
| `MTK_NOTIFY_WEBHOOK_URL` | HTTPS endpoint that accepts a JSON POST. Blank disables the channel. |
| `MTK_NOTIFY_WEBHOOK_TOKEN` | Optional bearer token sent as `Authorization: Bearer …`. Use a long random value. |
| `MTK_NOTIFY_TIMEOUT_S` | Delivery timeout in seconds, default `10`. |
| `MTK_NOTIFY_COOLDOWN_S` | After a fully successful delivery, suppress the same alert set for this many seconds, default `3600`. `0` disables. |
| `MTK_NOTIFY_SUBJECT_PREFIX` | Email subject prefix, default `[MTK RADAR]`. |

### Email (SMTP)

| Variable | Meaning |
| --- | --- |
| `MTK_NOTIFY_EMAIL_TO` | One recipient, or a comma-separated list. |
| `MTK_SMTP_HOST` | SMTP server, e.g. `smtp.gmail.com`. |
| `MTK_SMTP_PORT` | Default `587` (STARTTLS) or `465` (implicit SSL). |
| `MTK_SMTP_USER` | SMTP login. |
| `MTK_SMTP_PASSWORD` | SMTP password or app password. |
| `MTK_SMTP_FROM` | From address; defaults to `MTK_SMTP_USER`. |
| `MTK_SMTP_STARTTLS` | `1` by default for port 587. Ignored when SSL is on. |
| `MTK_SMTP_SSL` | `1` for implicit SSL; defaults to `1` when port is `465`. |
| `MTK_NOTIFY_TIMEOUT_S` | Connection/send timeout, default `10` seconds. |

Email requires `MTK_NOTIFY_EMAIL_TO`, `MTK_SMTP_HOST`, and a from address. The
credentials are optional for a local relay that does not authenticate.

### Gmail example

1. Enable 2-Step Verification on the Google account.
2. Google Account → Security → **App passwords** → create one for “Mail”.
3. Set:

```bash
MTK_NOTIFY_EMAIL_TO=you@example.com
MTK_SMTP_HOST=smtp.gmail.com
MTK_SMTP_PORT=587
MTK_SMTP_USER=you@gmail.com
MTK_SMTP_PASSWORD=the-16-character-app-password
MTK_SMTP_FROM=you@gmail.com
MTK_SMTP_STARTTLS=1
MTK_SMTP_SSL=0
```

Do **not** use the normal Google account password, and do not commit the app
password. If your provider blocks SMTP, use its API-specific SMTP credentials
or point `MTK_NOTIFY_WEBHOOK_URL` at a receiver that sends mail.

---

## 3. Payload schema

Schema: **`mtk-radar.notification.v1`**. One POST per eligible digest (an
alert set after the cooldown check).

```json
{
  "schema": "mtk-radar.notification.v1",
  "source": "mtk-radar.monitor",
  "event": "monitor.digest",
  "generated_at": "2026-10-22T12:00:00+00:00",
  "host": "monitor-1",
  "severity": "error",
  "alert_count": 2,
  "dashboard_url": "https://radar.example.com",
  "alerts": [
    {
      "severity": "warning",
      "event": "platform_account.expiring",
      "message": "Token for @demo (youtube) expires in 1.0 day(s).",
      "details": {
        "platform": "youtube",
        "account_handle": "@demo",
        "expires_at": "2026-10-23T12:00:00+00:00",
        "days_remaining": 1.0
      }
    },
    {
      "severity": "error",
      "event": "metrics.missing",
      "message": "4 published post(s) have no audience metrics; the metrics worker has no access or has not run yet.",
      "details": {"published_total": 4, "posts_measured": 0}
    }
  ]
}
```

`severity` is the highest alert severity in the digest (`info`, `warning`,
`error`). `dashboard_url` is `MTK_PUBLIC_BASE_URL` when configured, otherwise
`null`.

Current alert events:

| Event | Severity | Meaning |
| --- | --- | --- |
| `offers.sweep` | warning | Expired offers and/or overdue rechecks were processed; affected scheduled posts are auto-paused. |
| `platform_account.token_expired` | error | Platform session is dead; publishing is paused until credentials are refreshed. |
| `platform_account.revoked` | error | Account access was revoked; publishing is paused. |
| `platform_account.expiring` | warning | Token expires within 3 days. |
| `metrics.missing` | error | Published posts exist but no audience metrics were ever captured. |
| `metrics.stale` | warning | The newest audience snapshot is older than 48 hours. |
| `attention.<kind>` | warning/error | One alert per non-token Needs-You category (approvals, redaction, worker health, render/publish failures, budget). Delivered immediately or as a digest by category; the table above is not the full list of kinds. |
| `monitor.test` | info | Sent only by `--test-notification`; never a production alert. |

### Webhook receiver contract

- Return any `2xx` status. A non-2xx response counts as `failed` and is logged.
- Verify `Authorization: Bearer <MTK_NOTIFY_WEBHOOK_TOKEN>` if configured.
- Treat the payload as untrusted text. Do not render `message`/`details` as
  HTML without escaping, and do not execute URLs from it.
- A webhook URL can itself be a secret. Prefer HTTPS and a random path/token.
- Delivery is **at-most-once and best effort**. There is no retry queue. The
  monitor log is still the durable record.
- After a fully successful delivery, the same alert set (event + platform +
  account + status) is suppressed for `MTK_NOTIFY_COOLDOWN_S` (default one
  hour). This prevents a persistent dead token from emailing every five-minute
  monitor tick. A partial failure is retried on the next tick.

The email is a digest, not one email per alert, and is sent only when there is
at least one alert. There is no heartbeat when everything is quiet. The
cooldown cache is in memory: restarting the monitor can send one repeat
digest.

---

## 4. What is sent (and what is not)

Sent: event names, human-readable messages, counts, platform/account handles,
token expiry timestamps, metrics freshness, and the dashboard link.

Not sent: access tokens, refresh tokens, passwords, SMTP credentials, API
tokens, capture files, or evidence excerpts. The monitor only has the alert
data it derives from the API; the notification module never reads credential
values. If you add new alert details later, keep the same rule: operational
metadata only, never secrets or unredacted customer data.

---

## 5. Free Supabase: what actually fits

The core stack is **FastAPI + Python workers + Postgres + Redis + a Next.js
dashboard**, normally on one laptop or VPS. Supabase Free cannot host that
whole stack. Use it only where its limits match the job:

| Component | On Supabase Free? | Why |
| --- | --- | --- |
| Postgres database | **Conditional pilot** | 500 MB database, 5 GB egress/month, no automatic backups, and a project pauses after one week of inactivity. Fine for a low-volume pilot; not a production home without your own backups/monitoring. |
| Outbound webhook sender | **No need** | It is a few lines in the existing monitor worker. There is nothing useful to deploy to Supabase. |
| Public webhook receiver | **Possible, not required** | An Edge Function can receive a small authenticated POST, but it is a limited serverless runtime, not a worker host. Add it only if you need a public URL; the sender remains the monitor. |
| API / publishing / metrics / render workers | **No** | Long-running processes, local files/ffmpeg, and outbound platform sessions do not fit Edge Functions' execution model. |
| Video/audio storage | **No** | Supabase Storage Free is 1 GB with a 50 MB per-file limit — far below rendered video. Keep media on S3/R2/local storage. |
| Auth | **No** | The app uses reviewer tokens stored as hashes in Postgres; Supabase Auth is not part of the trust path. |

If you do point the API at Supabase Postgres, set `DATABASE_URL` to the
Supabase connection string, run the normal migrations, and keep the laptop/VPS
running the API and workers. The notification webhook/email still runs in the
monitor. The free plan is a convenience for a pilot, not a backup: take your
own `pg_dump` and test restores (runbook §2). See
[`cost-laptop-vps-2026-10-22.md`](cost-laptop-vps-2026-10-22.md) for the full
cost and resource comparison.

### Why not n8n?

n8n is not in the stack and is not required for this webhook. The monitor
already knows when an alert exists; adding an orchestration service would add a
second scheduler, another credential store, and more failure modes without
improving the publishing gates. The webhook can still point at n8n if you
already run it, but that is an optional receiver — not part of the trusted
publishing path. See [`open-source-integrations.md`](open-source-integrations.md).

---

## 6. Troubleshooting

| Symptom | Check |
| --- | --- |
| `webhook: not_configured` | `MTK_NOTIFY_WEBHOOK_URL` is blank or not passed into the monitor container. |
| `email: not_configured` | `MTK_NOTIFY_EMAIL_TO`, `MTK_SMTP_HOST`, or a from address is missing. |
| `webhook: failed` | Receiver returned non-2xx, TLS failed, or timeout. Check the monitor log; the URL is intentionally not logged. |
| `email: failed` | SMTP host/port/TLS mismatch, wrong app password, or provider blocked SMTP. Test `--test-notification` and read the monitor log. |
| Test works, real alerts do not arrive | A digest is only sent when the sweep raises an alert. Check that the condition actually exists (expired offer, dead token, stale metrics). |
| Gmail rejects the login | Use an App Password with 2-Step Verification; normal passwords and “less secure apps” do not work. |
| Duplicate emails | The monitor is running more than once, or `--once` is being called by both a scheduler and the compose service. Run one monitor owner. |

The monitor startup log prints only `NotificationConfig.public_summary()`:
configured booleans, recipient count, SMTP host/port/TLS. It never prints the
webhook token or SMTP password.
