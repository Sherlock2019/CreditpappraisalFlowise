#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
WEB_PORT="${WEB_PORT:-8080}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
START_STACK="${START_STACK:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-0}"
START_DOCKER_FLOWISE="${START_DOCKER_FLOWISE:-0}"

cd "$APP_DIR"

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

if [[ "$START_STACK" != "0" ]]; then
  if [[ ! -d "$POC_DIR" ]]; then
    echo "POC directory not found: ${POC_DIR}"
    exit 1
  fi

  if command -v docker >/dev/null 2>&1; then
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
    exit 1
  fi
else
  echo "Skipping Docker Compose startup. Using existing services."
fi

echo "Starting launcher web UI on http://127.0.0.1:${WEB_PORT}..."
"$PYTHON_BIN" -m http.server "$WEB_PORT" --bind 127.0.0.1 >web.log 2>&1 &
WEB_PID=$!

wait_for_url "http://127.0.0.1:${WEB_PORT}" "Launcher web UI" 20

cat <<EOF

Ready.
Launcher web UI:      http://127.0.0.1:${WEB_PORT}
Credit Appraisal UI:  http://127.0.0.1:8501
Backend Swagger:      http://127.0.0.1:8000/docs
Flowise UI:           http://127.0.0.1:3000

Logs:
  ${APP_DIR}/web.log

Press Ctrl+C to stop the launcher web server.
Use "docker compose down" in ${POC_DIR} to stop the POC stack.
Flowise Docker image is skipped by default. Use START_DOCKER_FLOWISE=1 to include it.
EOF

if [[ "$OPEN_BROWSER" == "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${WEB_PORT}" >/dev/null 2>&1 || true
fi

wait
