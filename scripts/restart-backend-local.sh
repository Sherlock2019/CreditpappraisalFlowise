#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POC_DIR="${APP_DIR}/bank-credit-ai-poc"
BACKEND_DIR="${POC_DIR}/backend"
PORT="${BACKEND_PORT:-8000}"

mkdir -p "${POC_DIR}/logs"

if pgrep -f "uvicorn app.main:app .*--port ${PORT}" >/dev/null 2>&1; then
  pkill -f "uvicorn app.main:app .*--port ${PORT}" || true
  sleep 1
fi

nohup "${APP_DIR}/scripts/run-backend-local.sh" "$PORT" >"${POC_DIR}/logs/backend.log" 2>&1 &

echo "$!" > "${POC_DIR}/logs/backend.pid"
echo "FastAPI backend restarted on http://127.0.0.1:${PORT} with pid $(cat "${POC_DIR}/logs/backend.pid")"
