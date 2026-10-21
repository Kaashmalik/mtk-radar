#!/usr/bin/env bash
# MTK RADAR — database restore (week 12). Restores a dump from infra/backup.sh
# into a (by default THROWAWAY) database so drills never touch production
# (docs/runbook.md: verify restores monthly, and after every pg major upgrade).
#
# Usage:
#   ./infra/restore.sh backups/mtk_radar_XXXX.dump [TARGET_DB]
#     TARGET_DB default: mtk_radar_restore  (created if missing)
set -euo pipefail

DUMP="${1:?usage: restore.sh <dumpfile> [target_db]}"
TARGET_DB="${2:-mtk_radar_restore}"
CONTAINER="${MTK_PG_CONTAINER:-mtk-radar-postgres-1}"

[ -f "$DUMP" ] || { echo "dump not found: $DUMP" >&2; exit 1; }

# safety: db names are interpolated into SQL below — restrict the charset
if ! [[ "$TARGET_DB" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "invalid target db name: '$TARGET_DB' (allowed: letters, digits, underscore)" >&2
  exit 1
fi
# safety: refuse to drop the production database unless explicitly forced
if [ "$TARGET_DB" = "mtk_radar" ] && [ "${MTK_RESTORE_FORCE:-0}" != "1" ]; then
  echo "refusing to DROP the production database 'mtk_radar'." >&2
  echo "restore into a throwaway instead (default: mtk_radar_restore)," >&2
  echo "or set MTK_RESTORE_FORCE=1 to override (runbook §restore)." >&2
  exit 1
fi

echo "restoring $DUMP -> database '$TARGET_DB' (throwaway drill unless you know better)"
docker exec "$CONTAINER" psql -U mtk -d postgres -c "DROP DATABASE IF EXISTS $TARGET_DB"
docker exec "$CONTAINER" psql -U mtk -d postgres -c "CREATE DATABASE $TARGET_DB"
docker exec -i "$CONTAINER" pg_restore -U mtk -d "$TARGET_DB" --no-owner --exit-on-error < "$DUMP"

echo "restore OK. verify with:"
echo "  docker exec $CONTAINER psql -U mtk -d $TARGET_DB -c \\"
echo "    \"SELECT state::text, COUNT(*) FROM offers GROUP BY state;\""
echo "Promote to production ONLY after verification (runbook §restore)."
