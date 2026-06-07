#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
UI_DIR="${UI_DIR:-${APP_DIR}/creditappflowise}"
WEB_PORT="${WEB_PORT:-8080}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
START_STACK="${START_STACK:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-0}"
START_DOCKER_FLOWISE="${START_DOCKER_FLOWISE:-0}"
START_LOCAL_FLOWISE="${START_LOCAL_FLOWISE:-1}"
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
  echo "Expected the credit appraisal UI at ${APP_DIR}/creditappflowise."
  exit 1
fi

cleanup() {
  if [[ -n "${WEB_PID:-}" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
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

if [[ "$START_LOCAL_FLOWISE" == "1" ]]; then
  if ! curl --max-time 2 -fsS "http://127.0.0.1:${FLOWISE_PORT}" >/dev/null 2>&1; then
    echo "Starting local Flowise 3.1.2..."
    if ! FLOWISE_PORT="$FLOWISE_PORT" "${APP_DIR}/start-flowise.sh"; then
      echo "Warning: local Flowise did not start. See ${POC_DIR}/logs/flowise.log"
    fi
  else
    echo "Flowise already reachable at http://127.0.0.1:${FLOWISE_PORT}"
  fi
fi

echo "Starting launcher web UI on http://127.0.0.1:${WEB_PORT}..."
"$PYTHON_BIN" "${APP_DIR}/web_proxy.py" --port "$WEB_PORT" --bind 127.0.0.1 --backend "http://127.0.0.1:8000" --directory "$UI_DIR" >web.log 2>&1 &
WEB_PID=$!

wait_for_url "http://127.0.0.1:${WEB_PORT}" "Launcher web UI" 20

cat <<EOF

Ready.
Credit Appraisal UI:  http://127.0.0.1:${WEB_PORT}
Streamlit UI:         http://127.0.0.1:8501
Backend Swagger:      http://127.0.0.1:8000/docs
Flowise UI:           http://127.0.0.1:${FLOWISE_PORT}

Logs:
  ${APP_DIR}/web.log
  UI directory: ${UI_DIR}

Press Ctrl+C to stop the launcher web server.
Use "docker compose down" in ${POC_DIR} to stop the POC stack.
Flowise Docker image is skipped by default. Use START_DOCKER_FLOWISE=1 to include it.
Local Flowise is started by default. Use START_LOCAL_FLOWISE=0 to skip it.
Docker daemon startup is attempted by default. Use START_DOCKER_DAEMON=0 to skip it.
Ollama startup is attempted by default. Use START_OLLAMA=0 to skip it.
EOF

if [[ "$OPEN_BROWSER" == "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${WEB_PORT}" >/dev/null 2>&1 || true
fi

wait
