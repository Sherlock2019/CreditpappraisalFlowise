#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LAUNCHER_PORT:-8080}"
BACKEND="${BACKEND_PROXY_URL:-http://127.0.0.1:8001}"

if pgrep -f "web_proxy.py --port ${PORT}" >/dev/null 2>&1; then
  pkill -f "web_proxy.py --port ${PORT}" || true
  sleep 1
fi

nohup python3 "${APP_DIR}/web_proxy.py" --port "$PORT" --bind 127.0.0.1 --backend "$BACKEND" > "${APP_DIR}/web.log" 2>&1 &
echo "$!" > "${APP_DIR}/web.pid"
echo "Web UI proxy restarted on http://127.0.0.1:${PORT} -> ${BACKEND} with pid $(cat "${APP_DIR}/web.pid")"
