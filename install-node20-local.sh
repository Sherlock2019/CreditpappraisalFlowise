#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_VERSION="${NODE_VERSION:-20.18.3}"
NODE_DIST="node-v${NODE_VERSION}-linux-x64"
TOOLS_DIR="${APP_DIR}/.tools"
NODE_DIR="${TOOLS_DIR}/${NODE_DIST}"
ARCHIVE="${TOOLS_DIR}/${NODE_DIST}.tar.xz"
URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_DIST}.tar.xz"

mkdir -p "$TOOLS_DIR"

if [[ -x "${NODE_DIR}/bin/node" ]]; then
  echo "Node ${NODE_VERSION} already installed at ${NODE_DIR}"
else
  echo "Downloading Node.js ${NODE_VERSION}..."
  curl -fL "$URL" -o "$ARCHIVE"
  echo "Extracting Node.js ${NODE_VERSION}..."
  tar -xJf "$ARCHIVE" -C "$TOOLS_DIR"
fi

echo
"${NODE_DIR}/bin/node" --version
"${NODE_DIR}/bin/npm" --version
echo
echo "Local Node.js installed. Use:"
echo "  export PATH=${NODE_DIR}/bin:\$PATH"
