#!/usr/bin/env bash
# Stop the MTK RADAR stack WITHOUT deleting volumes (data/captures survive).
set -euo pipefail
cd "$(dirname "$0")/.."

# Compose resolves a bare .env from its PROJECT directory (infra/docker/), not
# the repo root — pass the root .env explicitly. Tolerant: `down` still has to
# interpolate the fail-closed credentials at parse time, so a missing .env is
# bridged with throwaway values (nothing starts with them; only the project
# name and service list matter for `down`).
COMPOSE=(docker compose -f infra/docker/docker-compose.yml)
if [ -f .env ]; then
  COMPOSE+=(--env-file .env)
else
  echo "WARNING: .env is missing; using throwaway values so compose still" >&2
  echo "         resolves. Set up .env before the next start (cp .env.example .env)." >&2
  export POSTGRES_PASSWORD=stop-only
  export MTK_S3_ACCESS_KEY=stop
  export MTK_S3_SECRET_KEY=stop
fi

"${COMPOSE[@]}" --profile workers --profile storage down
