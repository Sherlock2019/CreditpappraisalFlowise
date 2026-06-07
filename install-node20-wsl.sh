#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

echo "Installing Node.js 20 LTS inside WSL Ubuntu..."
$SUDO apt-get update
$SUDO apt-get install -y ca-certificates curl gnupg

curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO bash -
$SUDO apt-get install -y nodejs

echo
node --version
npm --version
echo "Node.js 20 installation complete."
