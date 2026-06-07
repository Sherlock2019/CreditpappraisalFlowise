#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="${POC_DIR:-${APP_DIR}/bank-credit-ai-poc}"
FLOWISE_PORT="${FLOWISE_PORT:-3001}"
FLOWISE_NPX_PACKAGE="${FLOWISE_NPX_PACKAGE:-flowise@3.1.2}"
FLOWISE_HOME="${FLOWISE_HOME:-${POC_DIR}/flowise/.flowise}"
FLOWISE_VERSION="${FLOWISE_VERSION:-3.1.2}"
LOCAL_FLOWISE_BIN="${APP_DIR}/.tools/flowise-${FLOWISE_VERSION}/node_modules/.bin/flowise"
LOCAL_NODE22_DIR="${APP_DIR}/.tools/node-v22.13.1-linux-x64/bin"
LOCAL_NODE20_DIR="${APP_DIR}/.tools/node-v20.18.3-linux-x64/bin"

if [[ -x "${LOCAL_NODE20_DIR}/node" ]]; then
  export PATH="${LOCAL_NODE20_DIR}:$PATH"
elif [[ -x "${LOCAL_NODE22_DIR}/node" ]]; then
  export PATH="${LOCAL_NODE22_DIR}:$PATH"
fi

mkdir -p "$FLOWISE_HOME" "${POC_DIR}/logs"

if [[ -f "${POC_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${POC_DIR}/.env"
  set +a
fi

if curl --max-time 2 -fsS "http://127.0.0.1:${FLOWISE_PORT}" >/dev/null 2>&1; then
  echo "Flowise is already reachable at http://127.0.0.1:${FLOWISE_PORT}"
  exit 0
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx was not found. Install Node.js/npm first."
  exit 1
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  echo "Flowise ${FLOWISE_NPX_PACKAGE} requires Node.js 20 or newer."
  echo "Current Node.js: $(node --version 2>/dev/null || echo not found)"
  echo "Run ./install-node20-local.sh, then retry ./start-flowise.sh"
  exit 1
fi

if [[ ! -x "$LOCAL_FLOWISE_BIN" ]]; then
  echo "Local Flowise install not found: ${LOCAL_FLOWISE_BIN}"
  echo "Run ./install-flowise-local.sh first."
  exit 1
fi

echo "Starting flowise@${FLOWISE_VERSION} on http://127.0.0.1:${FLOWISE_PORT}"
echo "Log: ${POC_DIR}/logs/flowise.log"

cd "$POC_DIR"
nohup setsid env PORT="$FLOWISE_PORT" DATABASE_PATH="$FLOWISE_HOME" "$LOCAL_FLOWISE_BIN" start >"${POC_DIR}/logs/flowise.log" 2>&1 &
FLOWISE_PID=$!

for _ in $(seq 1 90); do
  if curl --max-time 2 -fsS "http://127.0.0.1:${FLOWISE_PORT}" >/dev/null 2>&1; then
    echo "Flowise ready: http://127.0.0.1:${FLOWISE_PORT}"
    echo "$FLOWISE_PID" >"${POC_DIR}/logs/flowise.pid"
    exit 0
  fi
  if ! kill -0 "$FLOWISE_PID" 2>/dev/null; then
    echo "Flowise exited before becoming ready. Last log lines:"
    tail -40 "${POC_DIR}/logs/flowise.log" || true
    exit 1
  fi
  sleep 1
done

echo "Flowise did not become ready in time. Last log lines:"
tail -40 "${POC_DIR}/logs/flowise.log" || true
exit 1
