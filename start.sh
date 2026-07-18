#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
UI_DIR="${UI_DIR:-${APP_DIR}/creditappflowise}"
WEB_PORT="${WEB_PORT:-8080}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FASTAPI_URL="${FASTAPI_URL:-${BACKEND_URL}/docs}"
FLOWISE_URL="${FLOWISE_URL:-http://127.0.0.1:${FLOWISE_PORT:-3001}}"
STREAMLIT_URL="${STREAMLIT_URL:-http://127.0.0.1:8501}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_VENV_DIR="${PYTHON_VENV_DIR:-${APP_DIR}/.venv}"
INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-1}"
PRELOAD_DEMO_DATASET="${PRELOAD_DEMO_DATASET:-1}"
START_STACK="${START_STACK:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-0}"
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

print_urls() {
  if [[ "${URLS_PRINTED:-0}" == "1" ]]; then return 0; fi
  URLS_PRINTED=1
  echo ""
  echo "==================== Web App URLs ===================="
  echo "Credit Appraisal UI:  http://127.0.0.1:${WEB_PORT}"
  echo "Streamlit UI:         ${STREAMLIT_URL}"
  echo "FastAPI Health:       ${BACKEND_URL}/health"
  echo "FastAPI Swagger:      ${FASTAPI_URL}"
  echo "Flowise UI:           ${FLOWISE_URL}"
  echo "======================================================"
}

cleanup() {
  print_urls
  if [[ -n "${WEB_PID:-}" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  if [[ -n "${WEB_PID:-}" ]] && [[ -f "${APP_DIR}/web.pid" ]] && [[ "$(cat "${APP_DIR}/web.pid" 2>/dev/null || true)" == "$WEB_PID" ]]; then
    rm -f "${APP_DIR}/web.pid"
  fi

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

if [[ "$START_STACK" != "0" ]]; then
  if [[ ! -d "$POC_DIR" ]]; then
    echo "POC directory not found: ${POC_DIR}"
    exit 1
  fi

  if command -v docker >/dev/null 2>&1; then
    if ! ensure_docker_daemon; then
      cat <<EOF

Docker is installed, but the daemon is not reachable.

Automatic daemon startup is disabled or did not succeed. Start Docker manually,
then retry:

  sudo service docker start
  ./start.sh

If you use Docker Desktop, start Docker Desktop and enable WSL integration for
this Ubuntu distro. To skip Docker entirely, run:

  ./start-local.sh

To disable automatic Docker daemon startup:

  START_DOCKER_DAEMON=0 ./start.sh

EOF
      exit 1
    fi

    echo "Starting credit appraisal POC stack with Docker Compose..."
    if [[ "$START_DOCKER_FLOWISE" == "1" ]]; then
      COMPOSE_CMD=(docker compose --profile flowise up --build -d)
    else
      COMPOSE_CMD=(docker compose up --build -d)
    fi

    if ! (cd "$POC_DIR" && "${COMPOSE_CMD[@]}"); then
      cat <<EOF

Docker Compose failed. If Docker crashed with SIGBUS or a WSL integration error,
restart Docker Desktop and WSL, then retry:

  powershell.exe wsl --shutdown
  ./start.sh

Non-Docker fallback:

  ./start-local.sh

If the crash happens while pulling Flowise, run the default launcher without
Docker Flowise:

  START_DOCKER_FLOWISE=0 ./start.sh

Then use Flowise later with:

  START_DOCKER_FLOWISE=1 ./start.sh

EOF
      exit 1
    fi
  else
    echo "Docker was not found. Install Docker or run with START_STACK=0 if services are already running."
    echo "Continuing without Docker stack because services appear to be running manually."
  fi
else
  echo "Skipping Docker Compose startup. Using existing services."
fi

FLOWISE_PORT="${FLOWISE_PORT:-3001}"
FLOWISE_URL="${FLOWISE_URL:-http://127.0.0.1:${FLOWISE_PORT}}"

if [[ "$START_LOCAL_FLOWISE" == "1" ]]; then
  if [[ "$RESTART_LOCAL_FLOWISE" == "1" ]]; then
    echo "Restarting local Flowise 3.1.2..."
    if ! FLOWISE_PORT="$FLOWISE_PORT" RESTART_FLOWISE=1 "${APP_DIR}/start-flowise.sh"; then
      echo "Warning: local Flowise did not restart. See ${POC_DIR}/logs/flowise.log"
    fi
  elif ! curl --max-time 2 -fsS "http://127.0.0.1:${FLOWISE_PORT}" >/dev/null 2>&1; then
    echo "Starting local Flowise 3.1.2..."
    if ! FLOWISE_PORT="$FLOWISE_PORT" "${APP_DIR}/start-flowise.sh"; then
      echo "Warning: local Flowise did not start. See ${POC_DIR}/logs/flowise.log"
    fi
  else
    echo "Flowise already reachable at http://127.0.0.1:${FLOWISE_PORT}"
  fi
fi

echo "Starting launcher web UI on http://127.0.0.1:${WEB_PORT}..."
if [[ -f "${APP_DIR}/web.pid" ]]; then
  OLD_WEB_PID="$(cat "${APP_DIR}/web.pid" 2>/dev/null || true)"
  if [[ -n "$OLD_WEB_PID" ]] && kill -0 "$OLD_WEB_PID" 2>/dev/null; then
    echo "Stopping existing launcher web UI process ${OLD_WEB_PID}..."
    kill "$OLD_WEB_PID" 2>/dev/null || true
    sleep 1
  fi
fi
"$PYTHON_BIN" "${APP_DIR}/web_proxy.py" --port "$WEB_PORT" --bind 127.0.0.1 --backend "$BACKEND_URL" --directory "$UI_DIR" >web.log 2>&1 &
WEB_PID=$!
echo "$WEB_PID" >"${APP_DIR}/web.pid"

wait_for_url "http://127.0.0.1:${WEB_PORT}" "Launcher web UI" 20
wait_for_url "${BACKEND_URL}/health" "FastAPI backend" 20
preload_demo_dataset

if [[ "$OPEN_BROWSER" == "1" ]]; then
  open_url "http://127.0.0.1:${WEB_PORT}"
  if [[ "$OPEN_FASTAPI" == "1" ]]; then
    open_url "$FASTAPI_URL"
  fi
elif [[ "$OPEN_FASTAPI" == "1" ]]; then
  open_url "$FASTAPI_URL"
fi

cat <<EOF

Ready.
Credit Appraisal UI:  http://127.0.0.1:${WEB_PORT}
Streamlit UI:         http://127.0.0.1:8501
FastAPI Health:       ${BACKEND_URL}/health
FastAPI Swagger:      ${FASTAPI_URL}
Flowise UI:           ${FLOWISE_URL}

Logs:
  ${APP_DIR}/web.log
  UI directory: ${UI_DIR}

Press Ctrl+C to stop the launcher web server.
Use "docker compose down" in ${POC_DIR} to stop the POC stack.
Flowise Docker image is skipped by default. Use START_DOCKER_FLOWISE=1 to include it.
Local Flowise is started by default. Use START_LOCAL_FLOWISE=0 to skip it.
Docker daemon startup is attempted by default. Use START_DOCKER_DAEMON=0 to skip it.
Ollama startup is attempted by default. Use START_OLLAMA=0 to skip it.
Python requirements install is enabled by default. Use INSTALL_REQUIREMENTS=0 to skip it.
Demo customer document preload is enabled by default. Use PRELOAD_DEMO_DATASET=0 to skip it.
EOF

if [[ "$OPEN_BROWSER" == "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${WEB_PORT}" >/dev/null 2>&1 || true
fi

wait
