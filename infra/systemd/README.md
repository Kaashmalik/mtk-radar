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
