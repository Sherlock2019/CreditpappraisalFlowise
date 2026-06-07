#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOWISE_VERSION="${FLOWISE_VERSION:-3.1.2}"
NODE20_BIN="${APP_DIR}/.tools/node-v20.18.3-linux-x64/bin"
NODE22_BIN="${APP_DIR}/.tools/node-v22.13.1-linux-x64/bin"
FLOWISE_DIR="${APP_DIR}/.tools/flowise-${FLOWISE_VERSION}"
UUID_CJS_DIR="${APP_DIR}/.tools/uuid-cjs"

if [[ -x "${NODE20_BIN}/node" ]]; then
  export PATH="${NODE20_BIN}:$PATH"
elif [[ -x "${NODE22_BIN}/node" ]]; then
  export PATH="${NODE22_BIN}:$PATH"
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  echo "Flowise ${FLOWISE_VERSION} needs Node.js 20 for the cleanest install."
  echo "Run ./install-node20-local.sh first."
  exit 1
fi

mkdir -p "$FLOWISE_DIR"
cd "$FLOWISE_DIR"

if [[ ! -f package.json ]]; then
  npm init -y >/dev/null
fi

echo "Installing flowise@${FLOWISE_VERSION} into ${FLOWISE_DIR}"
echo "This can take several minutes the first time because sqlite3/native packages may compile."
export CYPRESS_INSTALL_BINARY=0
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
export PUPPETEER_SKIP_DOWNLOAD=true

npm install \
  --legacy-peer-deps \
  --no-audit \
  --no-fund \
  --prefer-offline \
  "flowise@${FLOWISE_VERSION}" \
  "sqlite3@5.1.7"

echo "Pinning nested uuid@13 packages to a CommonJS-compatible version."
mkdir -p "$UUID_CJS_DIR"
if [[ ! -f "${UUID_CJS_DIR}/package.json" ]]; then
  npm init --prefix "$UUID_CJS_DIR" -y >/dev/null
fi
npm install \
  --prefix "$UUID_CJS_DIR" \
  --no-audit \
  --no-fund \
  --prefer-offline \
  "uuid@9.0.1"

while IFS= read -r uuid_package_json; do
  uuid_dir="$(dirname "$uuid_package_json")"
  uuid_major="$(node -e 'const fs=require("fs"); const p=process.argv[1]; const v=JSON.parse(fs.readFileSync(p,"utf8")).version || "0"; console.log(v.split(".")[0]);' "$uuid_package_json")"
  if [[ "$uuid_major" -ge 13 ]]; then
    echo "Replacing ${uuid_dir}"
    rm -rf "$uuid_dir"
    cp -a "${UUID_CJS_DIR}/node_modules/uuid" "$uuid_dir"
  fi
done < <(find node_modules -path '*/uuid/package.json' -print)

echo
echo "Flowise local install complete."
"${FLOWISE_DIR}/node_modules/.bin/flowise" --version || true
