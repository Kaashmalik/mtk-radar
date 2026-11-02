# Backup & restore-drill automation (systemd timers)

Week-12 exit criterion: backups are scheduled, not remembered.

## Install (deploy host, repo at /opt/mtk-radar)

```bash
# copy only what runs HERE: the media-backup pair belongs on the laptop
# (see below); copying it anyway is harmless because nothing enables it.
sudo cp infra/systemd/mtk-radar-{backup,restore-drill}.{service,timer} \
     infra/systemd/mtk-radar-backup-failed.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mtk-radar-backup.timer mtk-radar-restore-drill.timer
systemctl list-timers | grep mtk-radar
```

| Unit | Schedule | Does |
| --- | --- | --- |
| `mtk-radar-backup.timer` → `.service` | daily 03:00 host time, `Persistent=true` | `./infra/backup.sh 14` — `pg_dump -Fc` of the compose Postgres, atomic temp-file write, 14-day retention prune, off-site copy when `MTK_S3_*` is set |
| `mtk-radar-restore-drill.timer` → `.service` | monthly, 1st 04:00, `Persistent=true` | restores the NEWEST dump into a throwaway database (`restore.sh`); refuses to run when no dump exists |
| `mtk-radar-media-backup.timer` → `.service` | daily 03:20, `Persistent=true` (LAPTOP) | runs `./infra/backup_media.sh` on the laptop: pulls media from the NAS mount / rclone remote and verifies the newest snapshot |
| `mtk-radar-verify.timer` → `.service` | nightly 03:30, `Persistent=true` (optional, home/CI box) | interim CI while Actions is billing-locked: `scripts/record_verify_evidence.py` runs `scripts/verify.sh` and writes `docs/evidence/verify-pnpm-<date>.{log,json}` (never commits; review and commit them). Enable with `sudo systemctl enable --now mtk-radar-verify.timer` after copying both files |

Notes:
- The drill failing (unit red) means **backups are unusable** — treat like a
  failed backup: `systemctl status mtk-radar-restore-drill.service`.
- `WorkingDirectory` is baked to `/opt/mtk-radar`; adjust if the checkout
  lives elsewhere (the `EnvironmentFile=` lines follow the same convention).
  Timers use host time — confirm the deploy host is PKT or shift `OnCalendar`
  accordingly.
- **`EnvironmentFile=/opt/mtk-radar/infra/.env` is REQUIRED for off-site
  copies.** The file (written by `scripts/deploy.sh`) carries the `MTK_S3_*`
  variables that arm `backup.sh`'s off-site copy — without it the nightly
  dumps would silently stay on the same disk as the database, defeating the
  3-2-1 policy. The backup and drill units therefore fail loudly when the
  file is missing instead of degrading quietly. `MTK_S3_ENDPOINT` must be
  reachable from the **host**: the compose MinIO is internal-only
  (`expose: 9000`, no published port), so point the variable at the real
  off-site store (or publish the port for a single-box lab setup) — not at
  `http://minio:9000`.
- **Failures page.** `mtk-radar-backup.service` and
  `mtk-radar-restore-drill.service` both wire
  `OnFailure=mtk-radar-backup-failed.service`, a dependency-free oneshot
  that writes a `daemon.alert` entry to journal/syslog; when
  `MTK_NOTIFY_WEBHOOK_URL` is set (and curl is installed) it also POSTs the
  same `mtk-radar.notification.v1` payload the monitor uses
  ([`notifications.md`](../../docs/notifications.md)). Delivery is
  best-effort — the journal stays the durable record.
- cron alternative: `0 3 * * * cd /opt/mtk-radar && ./infra/backup.sh 14 >> backups/backup.log 2>&1`
  plus the monthly drill line — the timers exist because cron has no
  Persistent catch-up and no failure state you can alert on.

## Media backup timer (laptop, pull side)

`mtk-radar-media-backup.timer` runs on the **laptop** — the machine that must
keep the copy (a pull copy cannot be triggered by a compromised server). It
runs `./infra/backup_media.sh`, which snapshots the NAS mount
(`MTK_MEDIA_SOURCE`) or pulls over rclone (`MTK_RCLONE_REMOTE`) into
`MTK_MEDIA_DEST` and then verifies the newest snapshot (SHA-256 manifest).
The env file is optional here: the unit starts even without `infra/.env` so
that `backup_media.sh` can print its own setup guidance into the journal.

```bash
sudo cp infra/systemd/mtk-radar-media-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mtk-radar-media-backup.timer
sudo systemctl status mtk-radar-media-backup.service   # first-run guidance when the vars are unset
```


## Laptop launcher (v0.30)

The one-click dashboard Start button is only a policy arm. The host launcher
starts Docker and then the workers:

```bash
./scripts/mtk-start.sh          # start everything and open the dashboard
./scripts/mtk-start.sh --no-open
./scripts/mtk-stop.sh           # stop, keep volumes
```

Run it at login with a systemd user unit:

```bash
mkdir -p ~/.config/systemd/user
cp infra/systemd/mtk-radar.service ~/.config/systemd/user/
# edit WorkingDirectory/ExecStart if the checkout is not ~/mtk-radar
systemctl --user daemon-reload
systemctl --user enable --now mtk-radar.service
systemctl --user status mtk-radar.service
loginctl enable-linger "$USER"   # optional: start before login
```

A desktop shortcut is in `infra/desktop/mtk-radar.desktop`; update its path if
needed and copy it to `~/.local/share/applications/`.

The browser never receives Docker control. `GET /automation/preflight` reads
worker heartbeats and refuses to arm autopilot when a worker is stale or no
alert channel is configured.
