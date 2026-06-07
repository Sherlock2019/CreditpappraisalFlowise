#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/.env.flowise" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/.env.flowise"
  set +a
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required."
  exit 1
fi

python3 "${SCRIPT_DIR}/validate-flowise-json.py"
python3 "${SCRIPT_DIR}/import-flowise-chatflow.py" "$@"

cat <<'EOF'

Next manual steps:
1. Open Flowise UI.
2. Reconnect provider credentials for OpenAI, DeepSeek, embeddings, or local Ollama as needed.
3. Confirm POC_BACKEND_BASE_URL points at the FastAPI backend.
4. Test each imported flow from the Flowise canvas.
EOF
