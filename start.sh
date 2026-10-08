#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
UI_DIR="${UI_DIR:-${APP_DIR}/creditappflowise}"
WEB_PORT="${WEB_PORT:-8080}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
FLOWISE_PORT="${FLOWISE_PORT:-3001}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
# BACKEND_URL / FASTAPI_URL are derived after the ports are resolved unless set by the caller.
BACKEND_URL="${BACKEND_URL:-}"
FASTAPI_URL="${FASTAPI_URL:-}"
# STACK_MODE: auto = Docker Compose, falling back to the local virtualenvs if Docker fails;
# docker = Docker Compose only; local = local virtualenvs only.
STACK_MODE="${STACK_MODE:-auto}"
DOCKER_STACK_TIMEOUT="${DOCKER_STACK_TIMEOUT:-1800}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_VENV_DIR="${PYTHON_VENV_DIR:-${APP_DIR}/.venv}"
INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-1}"
PRELOAD_DEMO_DATASET="${PRELOAD_DEMO_DATASET:-1}"
START_STACK="${START_STACK:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
OPEN_FASTAPI="${OPEN_FASTAPI:-1}"
START_DOCKER_FLOWISE="${START_DOCKER_FLOWISE:-0}"
START_LOCAL_FLOWISE="${START_LOCAL_FLOWISE:-1}"
RESTART_LOCAL_FLOWISE="${RESTART_LOCAL_FLOWISE:-0}"
START_DOCKER_DAEMON="${START_DOCKER_DAEMON:-1}"
START_OLLAMA="${START_OLLAMA:-1}"
OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-0}"
COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-0}"
BUILDKIT_PROGRESS="${BUILDKIT_PROGRESS:-plain}"
export DOCKER_BUILDKIT COMPOSE_DOCKER_CLI_BUILD BUILDKIT_PROGRESS OLLAMA_HOST

cd "$APP_DIR"

if [[ ! -d "$UI_DIR" ]]; then
  echo "UI directory not found: ${UI_DIR}"
  echo "Expected the single credit appraisal UI at ${APP_DIR}/creditappflowise."
  exit 1
fi

detect_public_ip() {
  if [[ -n "${PUBLIC_IP:-}" ]]; then echo "${PUBLIC_IP}"; return 0; fi
  local ip="" token=""
  token="$(curl -s --max-time 1 -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)"
  if [[ -n "${token}" ]]; then
    ip="$(curl -s --max-time 1 -H "X-aws-ec2-metadata-token: ${token}" \
      "http://169.254.169.254/latest/meta-data/public-ipv4" 2>/dev/null || true)"
  fi
  [[ -z "${ip}" ]] && ip="$(curl -s --max-time 1 "http://169.254.169.254/latest/meta-data/public-ipv4" 2>/dev/null || true)"
  [[ -z "${ip}" ]] && ip="$(curl -s --max-time 2 https://api.ipify.org 2>/dev/null || true)"
  echo "${ip}"
}

PUBLIC_HOST="$(detect_public_ip)"
[[ -z "${PUBLIC_HOST}" ]] && PUBLIC_HOST="localhost"

print_urls() {
  if [[ "${URLS_PRINTED:-0}" == "1" ]]; then return 0; fi
  URLS_PRINTED=1
  echo ""
  echo "==================== Web App URLs ===================="
  echo "Credit Appraisal UI:  http://${PUBLIC_HOST}:${WEB_PORT}"
  echo "Streamlit UI:         http://${PUBLIC_HOST}:${STREAMLIT_PORT}"
  echo "FastAPI Health:       http://${PUBLIC_HOST}:${BACKEND_PORT}/health"
  echo "FastAPI Swagger:      http://${PUBLIC_HOST}:${BACKEND_PORT}/docs"
  echo "Flowise UI:           http://${PUBLIC_HOST}:${FLOWISE_PORT}"
  echo "======================================================"
}

cleanup() {
  print_urls
  true
}

trap cleanup EXIT INT TERM

wait_for_url() {
  local url="$1"
  local name="$2"
  local attempts="${3:-60}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Warning: ${name} did not answer at ${url} yet."
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}\$"
  else
    (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null
  fi
}

# Print the first free TCP port at or above the requested one.
free_port() {
  local port="$1"
  while port_in_use "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

# Resolve a port for one of our services: keep it when it is free, otherwise move to the next
# free port so another project listening there does not block or get mistaken for this stack.
claim_port() {
  local wanted="$1"
  local name="$2"
  local port
  port="$(free_port "$wanted")"
  if [[ "$port" != "$wanted" ]]; then
    echo "Port ${wanted} is used by another process; ${name} will use port ${port} instead." >&2
  fi
  echo "$port"
}

is_flowise() {
  curl --max-time 3 -fsS "http://127.0.0.1:${1}/api/v1/ping" 2>/dev/null | grep -qi pong
}

is_backend() {
  curl --max-time 3 -fsS "http://127.0.0.1:${1}/health" >/dev/null 2>&1
}

preload_demo_dataset() {
  if [[ "$PRELOAD_DEMO_DATASET" != "1" ]]; then
    echo "Skipping demo customer document preload. PRELOAD_DEMO_DATASET=${PRELOAD_DEMO_DATASET}"
    return 0
  fi

  if [[ ! -d "${APP_DIR}/docfactor_banking_demo_dataset/customer_documents" ]]; then
    echo "Demo customer document dataset not found; skipping preload."
    return 0
  fi

  echo "Preloading demo customer documents into FastAPI..."
  if curl --max-time 120 -fsS -X POST "${BACKEND_URL}/documents/preload-demo-dataset" >/dev/null; then
    echo "Demo customer document preload complete."
  else
    echo "Warning: demo customer document preload failed. Use Recover saved in the UI or check FastAPI logs."
  fi
}

requirements_fingerprint() {
  local req_files=()
  local req_file

  for req_file in "${POC_DIR}/backend/requirements.txt" "${POC_DIR}/frontend/requirements.txt"; do
    if [[ -f "$req_file" ]]; then
      req_files+=("$req_file")
    fi
  done

  if [[ "${#req_files[@]}" -eq 0 ]]; then
    return 1
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    cat "${req_files[@]}" | sha256sum | awk '{print $1}'
  else
    stat -c '%n:%s:%Y' "${req_files[@]}" | cksum | awk '{print $1}'
  fi
}

ensure_python_requirements() {
  if [[ "$INSTALL_REQUIREMENTS" != "1" ]]; then
    echo "Skipping Python requirements install. INSTALL_REQUIREMENTS=${INSTALL_REQUIREMENTS}"
    return 0
  fi

  if [[ ! -d "$POC_DIR" ]]; then
    echo "POC directory not found: ${POC_DIR}"
    exit 1
  fi

  local req_files=()
  local req_file
  local fingerprint
  local stamp_file
  local venv_python

  for req_file in "${POC_DIR}/backend/requirements.txt" "${POC_DIR}/frontend/requirements.txt"; do
    if [[ -f "$req_file" ]]; then
      req_files+=("$req_file")
    fi
  done

  if [[ "${#req_files[@]}" -eq 0 ]]; then
    echo "No requirements.txt files found under ${POC_DIR}; skipping Python dependency install."
    return 0
  fi

  if [[ ! -d "$PYTHON_VENV_DIR" ]]; then
    echo "Creating launcher Python virtualenv: ${PYTHON_VENV_DIR}"
    "$PYTHON_BIN" -m venv "$PYTHON_VENV_DIR"
  fi

  venv_python="${PYTHON_VENV_DIR}/bin/python"
  stamp_file="${PYTHON_VENV_DIR}/.requirements.fingerprint"
  fingerprint="$(requirements_fingerprint)"

  if [[ -f "$stamp_file" ]] && [[ "$(cat "$stamp_file" 2>/dev/null || true)" == "$fingerprint" ]]; then
    echo "Python requirements already installed from requirements.txt."
    PYTHON_BIN="$venv_python"
    return 0
  fi

  echo "Installing Python packages from requirements.txt..."
  "$venv_python" -m pip install --upgrade pip setuptools wheel
  for req_file in "${req_files[@]}"; do
    echo "Installing ${req_file}"
    "$venv_python" -m pip install -r "$req_file"
  done
  printf '%s' "$fingerprint" >"$stamp_file"
  PYTHON_BIN="$venv_python"
}

open_url() {
  local url="$1"

  if command -v wslview >/dev/null 2>&1; then
    wslview "$url" >/dev/null 2>&1 || true
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  fi
}

wait_for_docker() {
  local attempts="${1:-30}"

  for _ in $(seq 1 "$attempts"); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  return 1
}

wait_for_ollama() {
  local attempts="${1:-30}"

  for _ in $(seq 1 "$attempts"); do
    if curl --max-time 2 -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  return 1
}

ensure_ollama() {
  if [[ "$START_OLLAMA" != "1" ]]; then
    return 0
  fi

  if curl --max-time 2 -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "Ollama already reachable at http://127.0.0.1:11434"
    return 0
  fi

  if ! command -v ollama >/dev/null 2>&1; then
    echo "Warning: Ollama command not found. Local LLM answers will use fallback unless another provider is selected."
    return 0
  fi

  echo "Starting Ollama on ${OLLAMA_HOST}..."
  nohup ollama serve >"${APP_DIR}/ollama.log" 2>&1 &
  echo "$!" >"${APP_DIR}/ollama.pid"

  if ! wait_for_ollama 45; then
    echo "Warning: Ollama did not answer at http://127.0.0.1:11434 yet. See ${APP_DIR}/ollama.log"
  fi
}

ensure_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if [[ "$START_DOCKER_DAEMON" != "1" ]]; then
    return 1
  fi

  echo "Docker daemon is not reachable. Attempting to start Docker inside WSL..."

  if command -v service >/dev/null 2>&1; then
    if [[ "$(id -u)" == "0" ]]; then
      service docker start >/dev/null 2>&1 || true
    elif command -v sudo >/dev/null 2>&1; then
      sudo service docker start || true
    else
      echo "sudo is required to start the Docker service."
    fi
  elif command -v systemctl >/dev/null 2>&1; then
    if [[ "$(id -u)" == "0" ]]; then
      systemctl start docker >/dev/null 2>&1 || true
    elif command -v sudo >/dev/null 2>&1; then
      sudo systemctl start docker || true
    else
      echo "sudo is required to start the Docker service."
    fi
  else
    echo "No service manager found to start Docker automatically."
  fi

  wait_for_docker 30
}

ensure_python_requirements
ensure_ollama

if [[ "$START_STACK" != "0" ]] && [[ ! -d "$POC_DIR" ]]; then
  echo "POC directory not found: ${POC_DIR}"
  exit 1
fi

mkdir -p "${POC_DIR}/logs"

# .env is gitignored, so a fresh clone (e.g. on a server) only has .env.example
if [[ ! -f "${POC_DIR}/.env" && -f "${POC_DIR}/.env.example" ]]; then
  echo "No .env found; creating ${POC_DIR}/.env from .env.example"
  cp "${POC_DIR}/.env.example" "${POC_DIR}/.env"
fi

# --- Flowise -----------------------------------------------------------------
# Started before the POC stack so a slow Docker build does not hold it back.
FLOWISE_PID_FILE="${POC_DIR}/logs/flowise.pid"
FLOWISE_PORT_FILE="${POC_DIR}/logs/flowise.port"
FLOWISE_START_LOG="${POC_DIR}/logs/flowise-start.log"

if [[ "$START_LOCAL_FLOWISE" == "1" ]]; then
  OWN_FLOWISE_PORT=""
  if [[ -f "$FLOWISE_PID_FILE" ]] && [[ -f "$FLOWISE_PORT_FILE" ]] \
    && kill -0 "$(cat "$FLOWISE_PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
    OWN_FLOWISE_PORT="$(cat "$FLOWISE_PORT_FILE" 2>/dev/null || true)"
  fi

  if [[ -n "$OWN_FLOWISE_PORT" ]]; then
    FLOWISE_PORT="$OWN_FLOWISE_PORT"
  elif ! is_flowise "$FLOWISE_PORT"; then
    FLOWISE_PORT="$(claim_port "$FLOWISE_PORT" "Flowise")"
  fi

  # A cold Flowise start can take several minutes, so it loads in the background
  # while the rest of the stack comes up.
  if [[ "$RESTART_LOCAL_FLOWISE" == "1" ]]; then
    echo "Restarting local Flowise 3.1.2 on port ${FLOWISE_PORT} in the background..."
    FLOWISE_PORT="$FLOWISE_PORT" RESTART_FLOWISE=1 "${APP_DIR}/start-flowise.sh" >"$FLOWISE_START_LOG" 2>&1 &
    FLOWISE_START_PID=$!
  elif [[ -n "$OWN_FLOWISE_PORT" ]] && ! is_flowise "$FLOWISE_PORT"; then
    echo "Local Flowise is still loading on port ${FLOWISE_PORT}."
  elif ! is_flowise "$FLOWISE_PORT"; then
    echo "Starting local Flowise 3.1.2 on port ${FLOWISE_PORT} in the background..."
    FLOWISE_PORT="$FLOWISE_PORT" "${APP_DIR}/start-flowise.sh" >"$FLOWISE_START_LOG" 2>&1 &
    FLOWISE_START_PID=$!
  else
    echo "Flowise already reachable at http://127.0.0.1:${FLOWISE_PORT}"
  fi
fi

flowise_status() {
  if [[ "$START_LOCAL_FLOWISE" != "1" ]]; then
    echo "not started by this launcher"
  elif is_flowise "$FLOWISE_PORT"; then
    echo "ready"
  elif [[ -f "$FLOWISE_PID_FILE" ]] && kill -0 "$(cat "$FLOWISE_PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
    echo "still loading (a cold start can take several minutes), see ${POC_DIR}/logs/flowise.log"
  elif [[ -n "${FLOWISE_START_PID:-}" ]] && kill -0 "$FLOWISE_START_PID" 2>/dev/null; then
    echo "starting, see ${FLOWISE_START_LOG}"
  else
    echo "NOT running, see ${FLOWISE_START_LOG} and ${POC_DIR}/logs/flowise.log"
  fi
}

# --- POC stack ports ---------------------------------------------------------
# Host port already published by one of our containers, otherwise the next free one.
stack_port() {
  local container="$1"
  local container_port="$2"
  local wanted="$3"
  local name="$4"
  local current
  current="$(docker port "$container" "${container_port}/tcp" 2>/dev/null | head -n1 | sed 's/.*://' || true)"
  if [[ -n "$current" ]]; then
    echo "$current"
  else
    claim_port "$wanted" "$name"
  fi
}

USE_DOCKER=0
if [[ "$START_STACK" != "0" ]] && [[ "$STACK_MODE" != "local" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker was not found."
  elif ! ensure_docker_daemon; then
    cat <<EOF

Docker is installed, but the daemon is not reachable. Start it manually with
"sudo service docker start" (or start Docker Desktop and enable WSL integration
for this distro). To disable automatic Docker daemon startup:

  START_DOCKER_DAEMON=0 ./start.sh

EOF
  elif [[ "$STACK_MODE" == "auto" ]] && [[ -x "${POC_DIR}/backend/.venv/bin/uvicorn" ]] && [[ -f "${POC_DIR}/.env.local" ]] \
    && ! docker image inspect bank-credit-ai-poc-backend >/dev/null 2>&1; then
    # The local environments are ready and the Docker images are not built yet: skip the long image build.
    echo "Docker images are not built yet; using the existing local Python environments (STACK_MODE=docker forces Docker)."
  else
    USE_DOCKER=1
  fi

  if [[ "$USE_DOCKER" != "1" ]] && [[ "$STACK_MODE" == "docker" ]]; then
    exit 1
  fi
fi

if [[ "$USE_DOCKER" == "1" ]]; then
  POSTGRES_HOST_PORT="$(stack_port credit_ai_postgres 5432 "$POSTGRES_HOST_PORT" "PostgreSQL")"
  BACKEND_PORT="$(stack_port credit_ai_backend 8000 "$BACKEND_PORT" "FastAPI backend")"
  STREAMLIT_PORT="$(stack_port credit_ai_frontend 8501 "$STREAMLIT_PORT" "Streamlit UI")"
elif [[ "$START_STACK" != "0" ]] && ! is_backend "$BACKEND_PORT"; then
  BACKEND_PORT="$(claim_port "$BACKEND_PORT" "FastAPI backend")"
fi
export FLOWISE_PORT BACKEND_PORT STREAMLIT_PORT POSTGRES_HOST_PORT

# --- Launcher web UI ---------------------------------------------------------
start_web_ui() {
  if [[ -f "${APP_DIR}/web.pid" ]]; then
    OLD_WEB_PID="$(cat "${APP_DIR}/web.pid" 2>/dev/null || true)"
    if [[ -n "$OLD_WEB_PID" ]] && kill -0 "$OLD_WEB_PID" 2>/dev/null; then
      echo "Stopping existing launcher web UI process ${OLD_WEB_PID}..."
      kill "$OLD_WEB_PID" 2>/dev/null || true
      sleep 1
    fi
  fi

  WEB_PORT="$(claim_port "$WEB_PORT" "Launcher web UI")"
  WEB_BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
  echo "Starting launcher web UI on http://127.0.0.1:${WEB_PORT}..."
  # detached (setsid/nohup) so the UI keeps running after Ctrl+C or logout
  setsid nohup "$PYTHON_BIN" "${APP_DIR}/web_proxy.py" --port "$WEB_PORT" --bind 0.0.0.0 --backend "$WEB_BACKEND_URL" --directory "$UI_DIR" >"${APP_DIR}/web.log" 2>&1 </dev/null &
  WEB_PID=$!
  echo "$WEB_PID" >"${APP_DIR}/web.pid"
  wait_for_url "http://127.0.0.1:${WEB_PORT}" "Launcher web UI" 20
}

start_web_ui

# --- POC stack ---------------------------------------------------------------
start_docker_stack() {
  echo "Starting credit appraisal POC stack with Docker Compose..."
  echo "The first image build can take several minutes; the launcher UI and Flowise are already up."
  if [[ "$START_DOCKER_FLOWISE" == "1" ]]; then
    COMPOSE_CMD=(docker compose --profile flowise up --build -d)
  else
    COMPOSE_CMD=(docker compose up --build -d)
  fi

  if (cd "$POC_DIR" && timeout --foreground "$DOCKER_STACK_TIMEOUT" "${COMPOSE_CMD[@]}"); then
    return 0
  fi

  cat <<EOF

Docker Compose failed or did not finish within ${DOCKER_STACK_TIMEOUT}s. If Docker
crashed with SIGBUS or a WSL integration error, restart Docker Desktop and WSL
(powershell.exe wsl --shutdown), then retry ./start.sh.

EOF
  return 1
}

start_local_stack() {
  local backend_venv="${POC_DIR}/backend/.venv"
  local frontend_venv="${POC_DIR}/frontend/.venv"
  local local_env="${POC_DIR}/.env.local"

  if [[ ! -x "${backend_venv}/bin/uvicorn" ]] || [[ ! -f "$local_env" ]]; then
    echo "Local stack is not set up (missing ${backend_venv} or ${local_env})."
    echo "Run ./start-local.sh once to install PostgreSQL and the Python environments."
    return 1
  fi

  mkdir -p "${POC_DIR}/data/uploads"

  if is_backend "$BACKEND_PORT"; then
    echo "FastAPI backend already reachable at http://127.0.0.1:${BACKEND_PORT}"
  else
    local wanted_port="$BACKEND_PORT"
    BACKEND_PORT="$(claim_port "$BACKEND_PORT" "FastAPI backend")"
    echo "Starting local FastAPI backend on http://127.0.0.1:${BACKEND_PORT}..."
    (
      cd "${POC_DIR}/backend"
      set -a
      # shellcheck disable=SC1090,SC1091
      [[ -f "${POC_DIR}/.env" ]] && source "${POC_DIR}/.env"
      # shellcheck disable=SC1090
      source "$local_env"
      FLOWISE_API_URL="http://localhost:${FLOWISE_PORT}"
      BACKEND_URL="http://localhost:${BACKEND_PORT}"
      set +a
      exec setsid nohup "${backend_venv}/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
    ) >"${POC_DIR}/logs/backend.log" 2>&1 </dev/null &
    echo "$!" >"${POC_DIR}/logs/backend.pid"
    if [[ "$BACKEND_PORT" != "$wanted_port" ]]; then
      start_web_ui
    fi
  fi

  if curl --max-time 3 -fsS "http://127.0.0.1:${STREAMLIT_PORT}/_stcore/health" >/dev/null 2>&1; then
    echo "Streamlit UI already reachable at http://127.0.0.1:${STREAMLIT_PORT}"
  elif [[ -x "${frontend_venv}/bin/streamlit" ]]; then
    STREAMLIT_PORT="$(claim_port "$STREAMLIT_PORT" "Streamlit UI")"
    echo "Starting local Streamlit UI on http://127.0.0.1:${STREAMLIT_PORT}..."
    (
      cd "${POC_DIR}/frontend"
      export BACKEND_URL="http://localhost:${BACKEND_PORT}"
      exec setsid nohup "${frontend_venv}/bin/streamlit" run streamlit_app.py --server.address=0.0.0.0 --server.port "$STREAMLIT_PORT" --server.headless true
    ) >"${POC_DIR}/logs/frontend.log" 2>&1 </dev/null &
    echo "$!" >"${POC_DIR}/logs/frontend.pid"
  else
    echo "Warning: ${frontend_venv} not found; skipping the Streamlit UI."
  fi
}

STACK_RUNNING="existing services"
if [[ "$START_STACK" == "0" ]]; then
  echo "Skipping POC stack startup. Using existing services."
elif [[ "$USE_DOCKER" == "1" ]] && start_docker_stack; then
  STACK_RUNNING="Docker Compose"
elif [[ "$STACK_MODE" == "docker" ]]; then
  exit 1
else
  echo "Starting the POC stack from the local Python environments instead of Docker..."
  if start_local_stack; then
    STACK_RUNNING="local Python environments"
  else
    echo "Warning: the FastAPI backend and Streamlit UI were not started."
  fi
fi

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
FASTAPI_URL="${FASTAPI_URL:-${BACKEND_URL}/docs}"

wait_for_url "${BACKEND_URL}/health" "FastAPI backend" 45
preload_demo_dataset

if [[ "$OPEN_BROWSER" == "1" ]]; then
  open_url "http://127.0.0.1:${WEB_PORT}"
fi
if [[ "$OPEN_FASTAPI" == "1" ]]; then
  open_url "$FASTAPI_URL"
fi

cat <<EOF

Ready.
Credit Appraisal UI:  http://${PUBLIC_HOST}:${WEB_PORT}
Streamlit UI:         http://${PUBLIC_HOST}:${STREAMLIT_PORT}
FastAPI Health:       http://${PUBLIC_HOST}:${BACKEND_PORT}/health
FastAPI Swagger:      http://${PUBLIC_HOST}:${BACKEND_PORT}/docs
Flowise UI:           http://${PUBLIC_HOST}:${FLOWISE_PORT}

POC stack: ${STACK_RUNNING}
Flowise:   $(flowise_status)

Logs:
  ${APP_DIR}/web.log
  ${POC_DIR}/logs/flowise.log
  ${POC_DIR}/logs/backend.log and frontend.log (local stack only)
  UI directory: ${UI_DIR}

Everything keeps running in the background after this script exits.
Stop the launcher web server with: kill \$(cat ${APP_DIR}/web.pid)
Stop a local stack with: kill \$(cat ${POC_DIR}/logs/backend.pid ${POC_DIR}/logs/frontend.pid)
Stop Flowise with: kill \$(cat ${POC_DIR}/logs/flowise.pid)
Use "docker compose down" in ${POC_DIR} to stop the Docker POC stack.
A port that is already taken by another program is replaced by the next free one.
STACK_MODE=local skips Docker; STACK_MODE=docker disables the local fallback.
Flowise Docker image is skipped by default. Use START_DOCKER_FLOWISE=1 to include it.
Local Flowise is started by default. Use START_LOCAL_FLOWISE=0 to skip it.
Docker daemon startup is attempted by default. Use START_DOCKER_DAEMON=0 to skip it.
Ollama startup is attempted by default. Use START_OLLAMA=0 to skip it.
Python requirements install is enabled by default. Use INSTALL_REQUIREMENTS=0 to skip it.
Demo customer document preload is enabled by default. Use PRELOAD_DEMO_DATASET=0 to skip it.
EOF
