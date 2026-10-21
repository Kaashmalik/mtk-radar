#!/usr/bin/env bash
# MTK RADAR — database backup (week 12, master plan §13 "set retention, backups,
# ... early"). Runs inside the deploy host; targets the compose postgres
# container. Custom format (-Fc) enables selective restore + compression.
#
# Usage:
#   ./infra/backup.sh [RETENTION_DAYS]     # default 14
#
# Policy (docs/runbook.md):
#   - daily backup via cron/systemd timer, KEEP_DAYS retention, oldest pruned
#   - drill: restore into a THROWAWAY database monthly and verify /health
#   - backups contain evidence excerpts and metadata — never raw secrets
#     (redaction gate, §11) — but treat them as sensitive anyway.
set -euo pipefail

KEEP_DAYS="${1:-14}"
CONTAINER="${MTK_PG_CONTAINER:-mtk-radar-postgres-1}"
BACKUP_DIR="${MTK_BACKUP_DIR:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/mtk_radar_$STAMP.dump"

mkdir -p "$BACKUP_DIR"

# write to a temp file first so a failed pg_dump never leaves an empty
# *.dump behind (restore drills and retention would treat it as valid)
echo "backing up postgres from $CONTAINER -> $FILE"
docker exec "$CONTAINER" pg_dump -U mtk -Fc mtk_radar > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"

# retention: prune dumps older than KEEP_DAYS
find "$BACKUP_DIR" -name 'mtk_radar_*.dump' -mtime +"$KEEP_DAYS" -delete

echo "backup complete: $FILE (retention ${KEEP_DAYS}d, $(ls "$BACKUP_DIR" | wc -l) files kept)"
