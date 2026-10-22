#!/usr/bin/env bash
# Stop the MTK RADAR stack WITHOUT deleting volumes (data/captures survive).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f infra/docker/docker-compose.yml --profile workers --profile storage down
