#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
BACKEND_DIR="${POC_DIR}/backend"
FRONTEND_DIR="${POC_DIR}/frontend"
DB_SQL="${POC_DIR}/db/init.sql"
LOCAL_ENV="${POC_DIR}/.env.local"
BACKEND_VENV="${BACKEND_DIR}/.venv"
FRONTEND_VENV="${FRONTEND_DIR}/.venv"

DB_NAME="${DB_NAME:-credit_ai}"
DB_USER="${DB_USER:-credit_ai_user}"
DB_PASSWORD="${DB_PASSWORD:-credit_ai_password}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8501}"
FLOWISE_PORT="${FLOWISE_PORT:-3001}"
LAUNCHER_PORT="${LAUNCHER_PORT:-8080}"

INSTALL_POSTGRES="${INSTALL_POSTGRES:-1}"
START_FLOWISE="${START_FLOWISE:-1}"
FLOWISE_NPX_PACKAGE="${FLOWISE_NPX_PACKAGE:-flowise@3.1.2}"
FLOWISE_COMMAND="${FLOWISE_COMMAND:-}"
START_LAUNCHER="${START_LAUNCHER:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-0}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$APP_DIR"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

cleanup() {
  for pid in "${BACKEND_PID:-}" "${FRONTEND_PID:-}" "${FLOWISE_PID:-}" "${LAUNCHER_PID:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

need_command() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing command: ${cmd}"
    echo "$hint"
    exit 1
  fi
}

install_postgres_if_needed() {
  if command -v psql >/dev/null 2>&1 && pg_config --sharedir >/dev/null 2>&1; then
    return
  fi

  if [[ "$INSTALL_POSTGRES" != "1" ]]; then
    echo "PostgreSQL tools are missing. Re-run with INSTALL_POSTGRES=1 or install PostgreSQL + pgvector manually."
    exit 1
  fi

  need_command sudo "Install sudo or run this script as a user with sudo privileges."
  log "Installing PostgreSQL, contrib packages, and pgvector with apt. You may be prompted for sudo."
  sudo apt-get update
  sudo apt-get install -y postgresql postgresql-contrib postgresql-server-dev-all postgresql-16-pgvector libpq-dev build-essential
}

ensure_postgres_running() {
  if command -v service >/dev/null 2>&1; then
    sudo service postgresql start >/dev/null 2>&1 || true
  fi

  if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    echo "PostgreSQL is not reachable at ${DB_HOST}:${DB_PORT}."
    echo "Start it manually, for example: sudo service postgresql start"
    exit 1
  fi
}

ensure_database() {
  log "Creating local database/user if needed."
  sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"

  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
    || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

  sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$DB_SQL" >/dev/null
}

write_local_env() {
  log "Writing local runtime env: ${LOCAL_ENV}"
  if [[ ! -f "${POC_DIR}/.env" && -f "${POC_DIR}/.env.example" ]]; then
    cp "${POC_DIR}/.env.example" "${POC_DIR}/.env"
  fi

  cat > "$LOCAL_ENV" <<EOF
DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
FLOWISE_API_URL=http://localhost:${FLOWISE_PORT}
BACKEND_URL=http://localhost:${BACKEND_PORT}
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b-instruct
UPLOAD_DIR=${POC_DIR}/data/uploads
EOF
}

load_env_files() {
  set -a
  [[ -f "${POC_DIR}/.env" ]] && source "${POC_DIR}/.env"
  source "$LOCAL_ENV"
  set +a
}

ensure_python_env() {
  local venv_dir="$1"
  local req_file="$2"
  if [[ ! -d "$venv_dir" ]]; then
    log "Creating Python virtualenv: ${venv_dir}"
    "$PYTHON_BIN" -m venv "$venv_dir"
  fi
  log "Installing Python requirements from ${req_file}"
  "${venv_dir}/bin/python" -m pip install --upgrade pip >/dev/null
  "${venv_dir}/bin/pip" install -r "$req_file"
}

start_backend() {
  log "Starting FastAPI backend on http://localhost:${BACKEND_PORT}"
  mkdir -p "${POC_DIR}/data/uploads" "${POC_DIR}/logs"
  (
    cd "$BACKEND_DIR"
    set -a
    source "$LOCAL_ENV"
    [[ -f "${POC_DIR}/.env" ]] && source "${POC_DIR}/.env"
    source "$LOCAL_ENV"
    set +a
    "${BACKEND_VENV}/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
  ) >"${POC_DIR}/logs/backend.log" 2>&1 &
  BACKEND_PID=$!
}

start_frontend() {
  log "Starting Streamlit frontend on http://localhost:${FRONTEND_PORT}"
  (
    cd "$FRONTEND_DIR"
    set -a
    source "$LOCAL_ENV"
    [[ -f "${POC_DIR}/.env" ]] && source "${POC_DIR}/.env"
    source "$LOCAL_ENV"
    set +a
    "${FRONTEND_VENV}/bin/streamlit" run streamlit_app.py --server.address=0.0.0.0 --server.port "$FRONTEND_PORT"
  ) >"${POC_DIR}/logs/frontend.log" 2>&1 &
  FRONTEND_PID=$!
}

start_flowise() {
  if [[ "$START_FLOWISE" != "1" ]]; then
    log "Skipping Flowise startup."
    return
  fi

  if [[ -n "$FLOWISE_COMMAND" ]]; then
    log "Starting Flowise with custom command on http://localhost:${FLOWISE_PORT}"
    PORT="$FLOWISE_PORT" bash -lc "$FLOWISE_COMMAND" >"${POC_DIR}/logs/flowise.log" 2>&1 &
    FLOWISE_PID=$!
  elif [[ -x "${APP_DIR}/start-flowise.sh" ]]; then
    log "Starting local Flowise install on http://localhost:${FLOWISE_PORT}"
    FLOWISE_PORT="$FLOWISE_PORT" "${APP_DIR}/start-flowise.sh"
    if [[ -f "${POC_DIR}/logs/flowise.pid" ]]; then
      FLOWISE_PID="$(cat "${POC_DIR}/logs/flowise.pid")"
    fi
  elif command -v npx >/dev/null 2>&1; then
    log "Starting Flowise ${FLOWISE_NPX_PACKAGE} with npx on http://localhost:${FLOWISE_PORT}"
    PORT="$FLOWISE_PORT" npx --yes "$FLOWISE_NPX_PACKAGE" start >"${POC_DIR}/logs/flowise.log" 2>&1 &
    FLOWISE_PID=$!
  elif command -v flowise >/dev/null 2>&1; then
    log "Starting globally installed Flowise on http://localhost:${FLOWISE_PORT}"
    PORT="$FLOWISE_PORT" flowise start >"${POC_DIR}/logs/flowise.log" 2>&1 &
    FLOWISE_PID=$!
  else
    echo "Flowise requires either the flowise command or Node.js/npx."
    echo "Install Node.js/npm, or run with START_FLOWISE=0."
  fi
}

start_launcher() {
  if [[ "$START_LAUNCHER" != "1" ]]; then
    return
  fi
  log "Starting launcher on http://localhost:${LAUNCHER_PORT}"
  "$PYTHON_BIN" "${APP_DIR}/web_proxy.py" --port "$LAUNCHER_PORT" --bind 127.0.0.1 --backend "http://127.0.0.1:${BACKEND_PORT}" >"${APP_DIR}/web.log" 2>&1 &
  LAUNCHER_PID=$!
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local attempts="${3:-60}"
  for _ in $(seq 1 "$attempts"); do
    if curl --max-time 2 -fsS "$url" >/dev/null 2>&1; then
      log "${name} is ready: ${url}"
      return 0
    fi
    sleep 1
  done
  log "Warning: ${name} did not answer at ${url} yet."
}

need_command "$PYTHON_BIN" "Install Python 3."
need_command curl "Install curl."

install_postgres_if_needed
need_command psql "Install PostgreSQL client tools."
ensure_postgres_running
ensure_database
write_local_env
load_env_files
ensure_python_env "$BACKEND_VENV" "${BACKEND_DIR}/requirements.txt"
ensure_python_env "$FRONTEND_VENV" "${FRONTEND_DIR}/requirements.txt"
start_flowise
start_backend
start_frontend
start_launcher

wait_for_url "http://localhost:${BACKEND_PORT}/health" "FastAPI backend" 45
wait_for_url "http://localhost:${FRONTEND_PORT}" "Streamlit frontend" 45

cat <<EOF

Local POC is running.

Launcher:           http://localhost:${LAUNCHER_PORT}
Credit Appraisal:   http://localhost:${FRONTEND_PORT}
Backend Swagger:    http://localhost:${BACKEND_PORT}/docs
Flowise:            http://localhost:${FLOWISE_PORT}
PostgreSQL:         ${DB_HOST}:${DB_PORT}/${DB_NAME}

Logs:
  ${POC_DIR}/logs/backend.log
  ${POC_DIR}/logs/frontend.log
  ${POC_DIR}/logs/flowise.log

Press Ctrl+C to stop FastAPI, Streamlit, Flowise, and the launcher.
PostgreSQL remains installed/running as a local service.
EOF

if [[ "$OPEN_BROWSER" == "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:${LAUNCHER_PORT}" >/dev/null 2>&1 || true
fi

wait
