#!/usr/bin/env bash
# MTK RADAR — laptop-first host launcher (v0.30).
#
# Starts the API/dashboard, applies pending migrations, then starts the worker
# profile. The browser's Start Automation button only arms policy after this
# script has made the worker heartbeats healthy; it never controls Docker.
#
# Usage:
#   ./scripts/mtk-start.sh             # start and open the dashboard
#   ./scripts/mtk-start.sh --no-open   # useful from systemd
#   MTK_START_STORAGE=1 ./scripts/mtk-start.sh   # also start MinIO profile
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
COMPOSE=(docker compose -f "$REPO_ROOT/infra/docker/docker-compose.yml")
OPEN_UI=1
for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_UI=0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

command -v docker >/dev/null 2>&1 || {
  echo "docker is required (install Docker Engine/Desktop first)" >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  echo "docker compose v2 is required" >&2
  exit 1
}

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "WARNING: .env is missing. Copy .env.example to .env and set real secrets." >&2
fi

echo "→ starting PostgreSQL + Redis"
"${COMPOSE[@]}" up -d postgres redis

echo "→ starting API + dashboard (builds the API image if needed)"
"${COMPOSE[@]}" up -d --build api dashboard

echo "→ waiting for the API health check"
API_READY=0
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  sleep 2
done
if [ "$API_READY" -ne 1 ]; then
  echo "API did not become healthy. Inspect: ${COMPOSE[*]} logs api" >&2
  exit 1
fi

echo "→ applying pending database migrations"
"${COMPOSE[@]}" exec -T api python db_migrate.py

PROFILE_ARGS=(--profile workers)
if [ "${MTK_START_STORAGE:-0}" = "1" ]; then
  PROFILE_ARGS+=(--profile storage)
fi

echo "→ starting workers (heartbeats become visible at /workers)"
"${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d

cat <<'EOF'

MTK RADAR is running.
  Dashboard: http://localhost:3000
  API:       http://localhost:8000
  Needs You: http://localhost:3000/attention

Open the dashboard, paste your reviewer token (Identity), then use
Start automation. The button verifies every worker heartbeat first; it does
not start Docker. Check worker health any time at /workers or /attention.
EOF

if [ "$OPEN_UI" -eq 1 ]; then
  URL="http://localhost:3000"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  else
    echo "Open $URL in your browser."
  fi
fi
