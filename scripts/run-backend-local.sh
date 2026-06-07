#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POC_DIR="${APP_DIR}/bank-credit-ai-poc"
BACKEND_DIR="${POC_DIR}/backend"
PORT="${BACKEND_PORT:-${1:-8000}}"

cd "$BACKEND_DIR"
set -a
[[ -f "${POC_DIR}/.env.local" ]] && source "${POC_DIR}/.env.local"
[[ -f "${POC_DIR}/.env" ]] && source "${POC_DIR}/.env"
[[ -f "${POC_DIR}/.env.local" ]] && source "${POC_DIR}/.env.local"
set +a

exec "${BACKEND_DIR}/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT"
