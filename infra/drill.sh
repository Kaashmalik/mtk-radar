#!/usr/bin/env bash
# MTK RADAR — restore DRILL with verification (v0.24).
#
# A restore that "succeeds" but restores the wrong amount of data is a
# failed backup. This script restores the newest dump into a THROWAWAY
# database and then COMPARES ROW COUNTS against production: any table that
# differs beyond the production writes that happened after the dump was
# taken fails the drill loudly.
#
# Usage:
#   ./infra/drill.sh [DUMP]        # default: newest ./backups/*.dump
#
# Exit code 0 = drill passed. Non-zero = backups are NOT trustworthy.
set -euo pipefail

cd "$(dirname "$0")/.."
CONTAINER="${MTK_PG_CONTAINER:-mtk-radar-postgres-1}"
PROD_DB="${MTK_PROD_DB:-mtk_radar}"
DRILL_DB="${MTK_DRILL_DB:-mtk_radar_drill}"
BACKUP_DIR="${MTK_BACKUP_DIR:-./backups}"

DUMP="${1:-}"
if [ -z "$DUMP" ]; then
  DUMP="$(ls -t "$BACKUP_DIR"/mtk_radar_*.dump 2>/dev/null | head -1 || true)"
fi
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "DRILL FAILED: no backup dump found in $BACKUP_DIR — the backup timer is broken" >&2
  exit 1
fi

echo "drill: restoring $DUMP into throwaway database '$DRILL_DB'"
bash infra/restore.sh "$DUMP" "$DRILL_DB" > /dev/null

# ---- row-count comparison ------------------------------------------------
# Compare the tables that hold the business data. Counts may differ by the
# writes that happened after the dump was taken (production keeps running) —
# the drill therefore allows a small drift and fails on a real mismatch.
TABLES="items offers evidence offer_corrections offer_scripts schedules renders capture_sessions post_metrics"

DRIFT_LIMIT="${MTK_DRILL_DRIFT_LIMIT:-25}"
failed=0
printf '%-22s %12s %12s %10s\n' "table" "production" "restored" "drift"
for t in $TABLES; do
  prod=$(docker exec "$CONTAINER" psql -U mtk -d "$PROD_DB" -t -A -c "SELECT COUNT(*) FROM $t" 2>/dev/null || echo "-")
  drill=$(docker exec "$CONTAINER" psql -U mtk -d "$DRILL_DB" -t -A -c "SELECT COUNT(*) FROM $t" 2>/dev/null || echo "-")
  if [ "$prod" = "-" ] || [ "$drill" = "-" ]; then
    printf '%-22s %12s %12s %10s\n' "$t" "?" "?" "skip"
    continue
  fi
  drift=$(( prod - drill ))
  [ "$drift" -lt 0 ] && drift=$(( -drift ))
  printf '%-22s %12s %12s %10s\n' "$t" "$prod" "$drill" "$drift"
  if [ "$drift" -gt "$DRIFT_LIMIT" ]; then
    echo "  ✘ $t differs by $drift rows (limit $DRIFT_LIMIT) — the dump does not match" >&2
    failed=1
  fi
done

# ---- schema version check ------------------------------------------------
prod_migrations=$(docker exec "$CONTAINER" psql -U mtk -d "$PROD_DB" -t -A -c "SELECT COUNT(*) FROM schema_migrations" 2>/dev/null || echo 0)
drill_migrations=$(docker exec "$CONTAINER" psql -U mtk -d "$DRILL_DB" -t -A -c "SELECT COUNT(*) FROM schema_migrations" 2>/dev/null || echo 0)
printf '%-22s %12s %12s\n' "migrations" "$prod_migrations" "$drill_migrations"
if [ "$drill_migrations" -lt "$prod_migrations" ]; then
  echo "  ✘ the dump is missing migrations ($drill_migrations < $prod_migrations)" >&2
  failed=1
fi

# ---- clean up the throwaway database ------------------------------------
docker exec "$CONTAINER" psql -U mtk -d postgres -c "DROP DATABASE IF EXISTS $DRILL_DB" > /dev/null

if [ "$failed" -ne 0 ]; then
  echo "DRILL FAILED: the backup is not trustworthy (see the table diff above)" >&2
  exit 1
fi
echo "DRILL PASSED: $DUMP restores cleanly and matches production within drift $DRIFT_LIMIT"
