#!/usr/bin/env bash
# MTK RADAR — one-command host deploy (v0.32).
#
#   bash scripts/deploy.sh [--with-workers] [--with-storage]
#
# Designed for a fresh host (VPS/laptop) with Docker + docker compose plugin:
#   1. generates infra/.env on first run — strong random MTK_API_TOKEN,
#      MTK_WORKER_TOKEN, MTK_EXTENSION_TOKEN and MTK_SESSION_SECRET (secrets
#      never enter git; .env.* is gitignored);
#   2. builds + starts the stack (postgres, redis, migrate -> api, dashboard,
#      optionally all workers and S3 storage);
#   3. runs a connected end-to-end smoke check: API health, dashboard health,
#      attention endpoint authorized with the generated token;
#   4. prints exactly what to do next (open the dashboard, log in, arm
#      automation in Settings).
#
# Upgrades: re-run the same command — migrations apply only new files, images
# rebuild from the current commit, and media/postgres volumes persist.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f infra/docker/docker-compose.yml"
ENV_FILE=infra/.env
PROFILES=()

arg_has() { case " $* " in *" $1 "*) return 0;; *) return 1;; esac; }
arg_has "$@" --with-workers  && PROFILES+=(--profile workers)
arg_has "$@" --with-storage  && PROFILES+=(--profile storage)

# ---- 1) environment with strong secrets (once) --------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  if command -v openssl >/dev/null; then
    gen() { openssl rand -hex 32; }
  else
    gen() { python3 -c 'import secrets;print(secrets.token_hex(32))'; }
  fi
  set_in_env() { sed -i "s|^# \?$2=.*|$2=$3|" "$ENV_FILE"; }
  set_in_env "$ENV_FILE" MTK_API_TOKEN        "$(gen)"
  set_in_env "$ENV_FILE" MTK_WORKER_TOKEN     "$(gen)"
  set_in_env "$ENV_FILE" MTK_EXTENSION_TOKEN  "$(gen)"
  set_in_env "$ENV_FILE" MTK_SESSION_SECRET   "$(gen)"
  set_in_env "$ENV_FILE" POSTGRES_PASSWORD    "$(gen)"
  chmod 600 "$ENV_FILE"
  echo "✔ generated $ENV_FILE with fresh secrets (keep it safe; it is gitignored)"
else
  echo "✔ using existing $ENV_FILE"
fi

# ---- 2) build + boot ------------------------------------------------------
# Build the three images explicitly first: `up --build` can attempt to resolve
# images of profiled services that were never requested (e.g. minio on quay),
# which breaks deploys on hosts where a registry is unreachable. The workers
# services share one image, so building `publishing` covers them all.
$COMPOSE build api dashboard
if arg_has "$@" --with-workers; then $COMPOSE build publishing; fi
$COMPOSE "${PROFILES[@]}" up -d

# ---- 3) connected smoke check --------------------------------------------
echo "→ waiting for the API to become healthy…"
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  if [[ $i -eq 60 ]]; then
    echo "✘ API did not become healthy — recent logs:" >&2
    $COMPOSE logs --tail 40 api migrate >&2 || true
    exit 1
  fi
  sleep 2
done
echo "✔ API healthy"

TOKEN=$(sed -n 's/^MTK_API_TOKEN=//p' "$ENV_FILE")
if [[ -n "$TOKEN" ]] \
   && curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/attention >/dev/null 2>&1; then
  echo "✔ backend connected (authenticated /attention call succeeded)"
else
  echo "⚠ authenticated probe failed — check MTK_API_TOKEN in $ENV_FILE"
fi

echo "→ waiting for the dashboard…"
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1; then break; fi
  if [[ $i -eq 40 ]]; then
    echo "✘ dashboard did not become healthy — logs:" >&2
    $COMPOSE logs --tail 40 dashboard >&2 || true
    exit 1
  fi
  sleep 2
done
echo "✔ dashboard healthy"

# ---- 4) what next ---------------------------------------------------------
cat <<'EOF'

MTK RADAR is live:

  Dashboard   http://<host-ip>:3000
  API         http://127.0.0.1:8000 (loopback only — browsers proxy via the dashboard)

Next:
  1. Open the dashboard and sign in (reviewer session; secrets in infra/.env).
  2. Settings → Connections: register your platform account (credential REFERENCE).
  3. Settings → Automation: pick stages, then arm automation (or use the kill switch).
  4. Set MTK_PUBLIC_BASE_URL + MTK_CORS_ORIGINS in infra/.env before exposing HTTPS.

Re-run this script after `git pull` to upgrade (migrations apply automatically).
EOF
