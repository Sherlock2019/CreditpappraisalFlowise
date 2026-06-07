#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "${APP_DIR}/index.html" ]]; then
  echo "Old dashboard index.html not found: ${APP_DIR}/index.html"
  exit 1
fi

echo "Starting full dashboard UI from ${APP_DIR}/index.html..."
UI_DIR="${APP_DIR}" exec "${APP_DIR}/start.sh"
