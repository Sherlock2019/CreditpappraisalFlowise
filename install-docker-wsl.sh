#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

if [[ ! -f /etc/os-release ]]; then
  echo "Cannot detect Linux distribution."
  exit 1
fi

. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "This installer expects Ubuntu. Detected: ${ID:-unknown}"
  exit 1
fi

CODENAME="${VERSION_CODENAME:-}"
if [[ -z "$CODENAME" ]]; then
  echo "Cannot detect Ubuntu codename."
  exit 1
fi

echo "Installing Docker Engine inside WSL Ubuntu (${CODENAME})."

echo "Removing conflicting distro packages if present..."
$SUDO apt-get remove -y docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc || true

echo "Installing prerequisites..."
$SUDO apt-get update
$SUDO apt-get install -y ca-certificates curl gnupg lsb-release

echo "Adding Docker official apt repository..."
$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg.tmp
$SUDO mv /etc/apt/keyrings/docker.gpg.tmp /etc/apt/keyrings/docker.gpg
$SUDO chmod a+r /etc/apt/keyrings/docker.gpg

ARCH="$(dpkg --print-architecture)"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
  | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null

echo "Installing Docker Engine, Buildx, and Compose plugin..."
$SUDO apt-get update
$SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "Adding current user to docker group..."
$SUDO groupadd -f docker
$SUDO usermod -aG docker "$USER"

echo "Starting Docker service..."
if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  $SUDO systemctl enable docker >/dev/null 2>&1 || true
  $SUDO systemctl start docker
else
  $SUDO service docker start
fi

echo
echo "Docker installed."
docker --version || true
docker compose version || true
echo
echo "If 'docker ps' says permission denied, close this WSL terminal and reopen it,"
echo "or run: newgrp docker"
echo
echo "Test with:"
echo "  docker ps"
echo "  docker run --rm hello-world"
