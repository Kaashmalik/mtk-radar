# Backup & restore-drill automation (systemd timers)

Week-12 exit criterion: backups are scheduled, not remembered.

## Install (deploy host, repo at /opt/mtk-radar)

```bash
sudo cp infra/systemd/mtk-radar-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mtk-radar-backup.timer mtk-radar-restore-drill.timer
systemctl list-timers | grep mtk-radar
```

| Unit | Schedule | Does |
| --- | --- | --- |
| `mtk-radar-backup.timer` → `.service` | daily 03:00 host time, `Persistent=true` | `./infra/backup.sh 14` — `pg_dump -Fc` of the compose Postgres, atomic temp-file write, 14-day retention prune |
| `mtk-radar-restore-drill.timer` → `.service` | monthly, 1st 04:00, `Persistent=true` | restores the NEWEST dump into a throwaway database (`restore.sh`); refuses to run when no dump exists |

Notes:
- The drill failing (unit red) means **backups are unusable** — treat like a
  failed backup: `systemctl status mtk-radar-restore-drill.service`.
- `WorkingDirectory` is baked to `/opt/mtk-radar`; adjust if the checkout
  lives elsewhere. Timers use host time — confirm the deploy host is PKT or
  shift `OnCalendar` accordingly.
- cron alternative: `0 3 * * * cd /opt/mtk-radar && ./infra/backup.sh 14 >> backups/backup.log 2>&1`
  plus the monthly drill line — the timers exist because cron has no
  Persistent catch-up and no failure state you can alert on.


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
