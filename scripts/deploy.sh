#!/usr/bin/env bash
# MTK RADAR — one-command host deploy (v0.32).
#
#   bash scripts/deploy.sh [--with-workers] [--with-storage]
#
# Designed for a fresh host (VPS/laptop) with Docker + docker compose plugin:
#   1. generates infra/.env on first run — strong random MTK_API_TOKEN,
#      MTK_WORKER_TOKEN, MTK_EXTENSION_TOKEN, MTK_SESSION_SECRET and
#      POSTGRES_PASSWORD (secrets never enter git; .env.* is gitignored);
#      with --with-storage it also generates the MinIO root credentials once
#      and sets MTK_STORAGE_BACKEND=s3;
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
# Compose resolves a bare .env from its PROJECT directory (the folder of the
# first -f file → infra/docker/), where no env file exists — every invocation
# must point --env-file at the generated secrets file explicitly.
ENV_FILE=infra/.env
COMPOSE="docker compose --env-file $ENV_FILE -f infra/docker/docker-compose.yml"
PROFILES=()

# Needle-first membership test: arg_has <flag> "$@". The needle must NOT be
# part of the haystack it searches — the previous form arg_has "$@" <flag>
# passed the probe flag into the function's own "$*", so every probe matched
# and every deploy silently enabled every flag (2026-11-02: --profile storage
# fired without --with-storage, aborting deploys on quay.io's gated minio
# images and appending S3 lines to infra/.env).
arg_has() {
  local needle="$1"; shift
  case " $* " in *" $needle "*) return 0 ;; *) return 1 ;; esac
}
arg_has --with-workers "$@" && PROFILES+=(--profile workers)
arg_has --with-storage "$@" && PROFILES+=(--profile storage)

# ---- 1) environment with strong secrets ----------------------------------
gen() {
  if command -v openssl >/dev/null; then openssl rand -hex 32
  else python3 -c 'import secrets;print(secrets.token_hex(32))'; fi
}
# Idempotent: uncomment the line if present, otherwise APPEND it (the .env
# template documents most vars as comments — a bare sed never adds a var
# the template does not list at all, which silently skipped POSTGRES_PASSWORD).
set_in_env() {
  sed -i "s|^# \?$2=.*|$2=$3|" "$ENV_FILE"
  grep -q "^$2=" "$ENV_FILE" || echo "$2=$3" >> "$ENV_FILE"
}
# NEVER overwrite an existing value (bucket data / volumes are keyed to it):
add_if_missing() { grep -q "^$1=" "$ENV_FILE" || echo "$1=$2" >> "$ENV_FILE"; }

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
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

# ---- 1b) storage-profile S3 credentials -----------------------------------
# compose interpolates the WHOLE file on every command: the minio/storage-init
# ${MTK_S3_*:?} guards refuse to parse without values even when the storage
# profile is not started. With --with-storage the real credentials must exist
# in $ENV_FILE (generated once here; never rotated — existing bucket data is
# keyed to them) and the clients get MTK_STORAGE_BACKEND=s3. Without the
# flag, session-scoped placeholders keep the parse valid without persisting
# anything (a storage-less deploy never writes S3 values into infra/.env).
if arg_has --with-storage "$@"; then
  if ! grep -q '^MTK_S3_ACCESS_KEY=' "$ENV_FILE"; then
    add_if_missing MTK_S3_ACCESS_KEY "$(gen)"
    echo "✔ generated MTK_S3_ACCESS_KEY in $ENV_FILE (one-time; rotate manually)"
  fi
  if ! grep -q '^MTK_S3_SECRET_KEY=' "$ENV_FILE"; then
    add_if_missing MTK_S3_SECRET_KEY "$(gen)"
    echo "✔ generated MTK_S3_SECRET_KEY in $ENV_FILE (one-time; rotate manually)"
  fi
  add_if_missing MTK_STORAGE_BACKEND s3
  add_if_missing MTK_S3_ENDPOINT     http://minio:9000
else
  if ! grep -q '^MTK_S3_ACCESS_KEY=' "$ENV_FILE"; then
    export MTK_S3_ACCESS_KEY=parse-only
    export MTK_S3_SECRET_KEY=parse-only
  fi
fi

# ---- 2) build + boot ------------------------------------------------------
# BUILD before `up`: `up` resolves a named service's image from the registry
# when no local copy exists — for the local-only :local tags that means a
# guaranteed-fail Docker Hub pull with a confusing error. The workers
# services share one image, so building `publishing` covers them all —
# except page-capture, which has its own Dockerfile and must be built
# explicitly too.
$COMPOSE build api dashboard
if arg_has --with-workers "$@"; then $COMPOSE build publishing page-capture; fi

# Name the services on `up` (belt-and-braces): compose then starts exactly
# this set, so a mistake in the profile flags can never drag in services the
# operator did not ask for (minio/storage-init sit behind quay.io's
# anonymous-pull gate, 2026-11-01). Named services still start their
# dependencies (postgres, redis, migrate) through depends_on, so boot order
# and health gating are unchanged; PROFILES keeps explicitly named profiled
# services startable. (For the record: the earlier storage-less deploys that
# aborted on the gated minio images were caused by the arg_has bug above,
# not by an unscoped `up` — this scoping merely limits the blast radius of
# any future flag-handling bug.)
CORE_SERVICES=(api dashboard)
WORKER_SERVICES=(publishing verification collectors batch render page-capture monitor metrics)
STORAGE_SERVICES=(minio storage-init)
UP_SERVICES=("${CORE_SERVICES[@]}")
arg_has --with-workers "$@" && UP_SERVICES+=("${WORKER_SERVICES[@]}")
arg_has --with-storage "$@"  && UP_SERVICES+=("${STORAGE_SERVICES[@]}")
$COMPOSE "${PROFILES[@]}" up -d "${UP_SERVICES[@]}"

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
  echo "✘ authenticated probe failed — the API is up but /attention refused the token." >&2
  echo "  Check MTK_API_TOKEN in $ENV_FILE (it must match the deployment the API booted" >&2
  echo "  with) and fix it, then re-run this script." >&2
  exit 1
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

  Dashboard   http://127.0.0.1:3000  (loopback-only publish — use an SSH tunnel
              to reach it from your laptop, or the TLS ingress below)
  API         http://127.0.0.1:8000 (loopback only — browsers proxy via the dashboard)

Next:
  1. Open the dashboard and sign in (reviewer session; secrets in infra/.env).
  2. Settings → Connections: register your platform account (credential REFERENCE).
  3. Settings → Automation: pick stages, then arm automation (or use the kill switch).
  4. To expose HTTPS, see infra/proxy/README.md (Cloudflare Tunnel profile or
     host-side Caddy), then set MTK_PUBLIC_BASE_URL + MTK_CORS_ORIGINS in
     infra/.env to the public origin.

Re-run this script after `git pull` to upgrade (migrations apply automatically).
EOF
