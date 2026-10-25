#!/usr/bin/env bash
# MTK RADAR — full local verification (mirrors the CI pipeline).
#
# One command that proves the whole system is working, on the same steps CI
# runs: lint → compile → unit + integration tests against a REAL Postgres →
# typecheck → dashboard production build → compose config → CI YAML sanity →
# extension syntax.
#
# Usage:
#   ./scripts/verify.sh              # everything (starts a throwaway Postgres)
#   ./scripts/verify.sh --no-e2e     # skip the browser smoke test
#   ./scripts/verify.sh --fast       # skip the browser smoke test and the build
#
# The throwaway Postgres is started with docker (name mtk-verify-pg, port
# 55499) and removed afterwards. Nothing touches your .env or your data.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

RUN_E2E=1
RUN_BUILD=1
for arg in "$@"; do
  case "$arg" in
    --no-e2e) RUN_E2E=0 ;;
    --fast) RUN_E2E=0; RUN_BUILD=0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

PG_NAME="mtk-verify-pg"

# first free port from a start point (a busy port would make the whole run
# look broken for reasons that have nothing to do with the code)
pick_port() {
  python3 - "$1" << 'PY'
import socket, sys
start = int(sys.argv[1])
for candidate in range(start, start + 50):
    with socket.socket() as s:
        s.settimeout(0.2)
        if s.connect_ex(("127.0.0.1", candidate)) != 0:
            print(candidate)
            break
PY
}
PG_PORT="${MTK_VERIFY_PG_PORT:-$(pick_port 55499)}"
# 127.0.0.1, not localhost: some hosts resolve localhost to IPv6 ::1 first,
# while Docker publishes the port on IPv4 only — that fails as a 60s timeout.
PG_URL="postgresql://mtk:mtk@127.0.0.1:${PG_PORT}/mtk_verify"
VENV="${MTK_VERIFY_VENV:-/tmp/opencode/verify-venv}"

step() { printf '\n\033[1;36m▸ %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$1"; }
fail() { printf '\033[1;31m✘ %s\033[0m\n' "$1" >&2; exit 1; }

cleanup() {
  docker rm -f "$PG_NAME" > /dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------------------------------------------------------------- 1. lint
step "Filename portability (Windows-invalid characters, G28/EP-00)"
python3 scripts/check_filenames.py || fail "filenames"
ok "filenames portable"

step "Documentation links (relative README/docs links)"
python3 scripts/check_doc_links.py || fail "doc links"
ok "documentation links resolve"

step "Secret scan (gitleaks)"
if command -v gitleaks > /dev/null 2>&1; then
  gitleaks detect --source . --config .gitleaks.toml --redact \
    || fail "gitleaks"
  ok "no secrets in full history"
else
  printf '  gitleaks not installed; the CI secret-scan job is the gate\n'
fi

step "Python lint (ruff: syntax + undefined names)"
ruff check --select E9,F63,F7,F82,F821 services workers packages || fail "ruff"
ok "ruff clean"

step "Python compile"
python -m compileall -q services workers packages || fail "compileall"
ok "all modules compile"

# ------------------------------------------------------------ 2. tests
step "Unit + integration tests (real Postgres, real migrations)"
if ! docker info > /dev/null 2>&1; then
  fail "docker is required for the integration layer (Postgres)"
fi
cleanup
# a leftover container still holding the port would make the readiness check
# fail for reasons that have nothing to do with this run
for _ in $(seq 1 15); do
  docker run -d --rm --name "$PG_NAME" \
    -e POSTGRES_USER=mtk -e POSTGRES_PASSWORD=mtk -e POSTGRES_DB=mtk_verify \
    -p "${PG_PORT}:5432" postgres:16-alpine > /dev/null 2>&1 && break
  sleep 1
done
docker ps --filter "name=${PG_NAME}" --format "{{.Names}}" | grep -q "$PG_NAME" \
  || fail "could not start the throwaway Postgres (port ${PG_PORT} busy?)"
for _ in $(seq 1 60); do
  docker exec "$PG_NAME" pg_isready -U mtk > /dev/null 2>&1 && break || sleep 1
done
docker exec "$PG_NAME" pg_isready -U mtk > /dev/null 2>&1 \
  || { docker logs "$PG_NAME" | tail -5; fail "postgres did not start"; }

MTK_TEST_DATABASE_URL="$PG_URL" python -m pytest -q || fail "pytest"
ok "test suites green"

# ------------------------------------------------- 3. pinned deps (py3.12)
if command -v python3.12 > /dev/null 2>&1; then
  step "Pinned dependencies resolve on Python 3.12 (the CI target)"
  if [ ! -x "$VENV/bin/python" ]; then
    python3.12 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r services/api/requirements.txt \
      -r workers/requirements.txt -r workers/publishing/requirements.txt \
      -r workers/metrics/requirements.txt -r workers/batch/requirements.txt
  fi
  "$VENV/bin/python" -c "import fastapi, httpx, asyncpg, pydantic; print('  deps:', fastapi.__version__, httpx.__version__, asyncpg.__version__, pydantic.__version__)"
  ok "dependency set installs and imports"
fi

# ------------------------------------------------------------ 4. frontend
step "Typecheck (offer-schema + dashboard)"
corepack pnpm typecheck > /dev/null || fail "typecheck"
ok "typecheck clean"

if [ "$RUN_BUILD" = "1" ]; then
  step "Dashboard production build"
  corepack pnpm --dir apps/dashboard build > /tmp/mtk-dashboard-build.log 2>&1 \
    || { tail -20 /tmp/mtk-dashboard-build.log; fail "dashboard build"; }
  ok "dashboard builds"
fi

# ------------------------------------------------------------- 5. deploy
step "Compose configuration (production + dev override)"
docker compose -f infra/docker/docker-compose.yml config -q || fail "compose config"
docker compose -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.dev.yml config -q || fail "dev compose config"
ok "compose files valid"

step "CI workflow YAML"
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); print('  jobs:', ', '.join(d['jobs']))" \
  || fail "ci yaml"
ok "ci workflow parses"

step "Extension (Manifest V3) syntax + core logic tests"
node --check apps/extension/core.js || fail "extension core.js"
node --check apps/extension/background.js || fail "extension background.js"
node --check apps/extension/options.js || fail "extension options.js"
python3 -c "import json; json.load(open('apps/extension/manifest.json'))" || fail "extension manifest"
( cd apps/extension && node --test tests/*.test.js ) || fail "extension unit tests"
ok "extension clean"

# -------------------------------------------------------------- 6. e2e
if [ "$RUN_E2E" = "1" ]; then
  step "End-to-end (real API + dashboard build + Chromium)"

  # Pick free ports. The dashboard reads API_URL at runtime, but the API port
  # is still chosen before anything starts so both sides agree.
  API_PORT="$(pick_port 8000)"
  DASH_PORT="$(pick_port 3000)"
  echo "  api on ${API_PORT}, dashboard on ${DASH_PORT}"

  E2E_DB="mtk_verify_e2e"
  docker exec "$PG_NAME" createdb -U mtk "$E2E_DB" > /dev/null 2>&1 || true
  E2E_URL="postgresql://mtk:mtk@127.0.0.1:${PG_PORT}/${E2E_DB}"

  PY_BIN="$VENV/bin/python"
  [ -x "$PY_BIN" ] || PY_BIN="python"
  DATABASE_URL="$E2E_URL" "$PY_BIN" services/api/db_migrate.py > /dev/null || fail "migrations"

  # Real auth for the smoke test: a service token for Node-side reads and a
  # personal reviewer token for the browser session. Nothing is hard-coded.
  MTK_API_TOKEN="$(openssl rand -hex 24)"
  MTK_SESSION_SECRET="$(openssl rand -hex 32)"
  E2E_REVIEWER_TOKEN="$(DATABASE_URL="$E2E_URL" "$PY_BIN" \
    services/api/scripts/mint_reviewer.py --name "Verify E2E" | sed -n '2p')"
  [ -n "$E2E_REVIEWER_TOKEN" ] || fail "reviewer mint produced no token"

  MTK_API_TOKEN="$MTK_API_TOKEN" \
  MTK_CORS_ORIGINS="http://127.0.0.1:${DASH_PORT},http://localhost:${DASH_PORT}" \
    DATABASE_URL="$E2E_URL" "$PY_BIN" -m uvicorn main:app --app-dir services/api \
    --host 127.0.0.1 --port "$API_PORT" > /tmp/mtk-verify-api.log 2>&1 &
  API_PID=$!
  for _ in $(seq 1 30); do
    curl -sf "http://127.0.0.1:${API_PORT}/health" > /dev/null && break || sleep 1
  done
  curl -sf "http://127.0.0.1:${API_PORT}/health" > /dev/null \
    || { tail -20 /tmp/mtk-verify-api.log; fail "api did not start"; }

  corepack pnpm --dir apps/dashboard build > /dev/null 2>&1 || fail "dashboard build"
  API_URL="http://127.0.0.1:${API_PORT}" \
  MTK_API_TOKEN="$MTK_API_TOKEN" \
  MTK_SESSION_SECRET="$MTK_SESSION_SECRET" \
    corepack pnpm --dir apps/dashboard exec next start -p "$DASH_PORT" \
    > /tmp/mtk-verify-dashboard.log 2>&1 &
  DASH_PID=$!
  for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:${DASH_PORT}/" > /dev/null && break || sleep 2
  done
  curl -sf "http://127.0.0.1:${DASH_PORT}/" > /dev/null \
    || { tail -20 /tmp/mtk-verify-dashboard.log; fail "dashboard did not start"; }

  E2E_BASE_URL="http://127.0.0.1:${DASH_PORT}" \
  E2E_REVIEWER_TOKEN="$E2E_REVIEWER_TOKEN" \
    corepack pnpm --dir apps/dashboard exec playwright test || fail "playwright"
  kill "$API_PID" "$DASH_PID" > /dev/null 2>&1 || true
  ok "browser smoke green"
fi

printf '\n\033[1;32m✔ verification complete — the system is working\033[0m\n'
printf '  next: docs/go-live-checklist.md (add keys, connect accounts, first post)\n'
