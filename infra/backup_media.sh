#!/usr/bin/env bash
# MTK RADAR — media backup (v0.27). Run this on the LAPTOP (pull-only), not
# on the public server: the backup destination is the machine that must keep a
# copy, and a pull cannot be triggered by a compromised server.
#
# 3-2-1 policy:
#   1. server primary (projects/ + object storage)
#   2. off-site object store / NAS (database backup + media)
#   3. operator laptop snapshot with a SHA-256 manifest
#
# Environment:
#   MTK_MEDIA_SOURCE          local mounted source (e.g. /mnt/nas/mtk/projects)
#   MTK_MEDIA_DEST            laptop backup root (e.g. /backup/mtk)
#   MTK_MEDIA_RETENTION_DAYS  snapshots to keep (default 14)
#   MTK_RCLONE_REMOTE         alternative: server:mtk-media (pulls over rclone)
#   MTK_API_URL / MTK_API_TOKEN  optional dashboard status update
#
# Example cron (03:20 every day):
#   20 3 * * * MTK_MEDIA_SOURCE=/mnt/nas/mtk/projects \
#     MTK_MEDIA_DEST=/backup/mtk /opt/mtk-radar/infra/backup_media.sh >> /var/log/mtk-media.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
KEEP="${MTK_MEDIA_RETENTION_DAYS:-14}"

ARGS=(--dest "${MTK_MEDIA_DEST:?set MTK_MEDIA_DEST to the laptop backup root}"
      --keep "$KEEP")
if [ -n "${MTK_RCLONE_REMOTE:-}" ]; then
  ARGS+=(--rclone-remote "$MTK_RCLONE_REMOTE")
else
  ARGS+=(--source "${MTK_MEDIA_SOURCE:?set MTK_MEDIA_SOURCE or MTK_RCLONE_REMOTE}")
fi
if [ -n "${MTK_API_URL:-}" ]; then
  ARGS+=(--api-url "$MTK_API_URL")
fi

python3 scripts/media_backup.py "${ARGS[@]}"

# Always verify the newest snapshot as a separate step, even if the backup
# script's inline verification was disabled by a future change.
LATEST="$(find "${MTK_MEDIA_DEST}/media" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | tail -1)"
if [ -z "$LATEST" ]; then
  echo "no snapshot found under ${MTK_MEDIA_DEST}/media" >&2
  exit 1
fi
python3 scripts/verify_media_backup.py "$LATEST"
echo "media backup verified: $LATEST"
