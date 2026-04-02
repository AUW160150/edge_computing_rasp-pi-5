#!/bin/bash
# Pi Setup Script — run once on a fresh Raspberry Pi 5 (Raspberry Pi OS 64-bit Bookworm)
# Usage: bash setup.sh <PI_EXECUTE_TOKEN> <TAILSCALE_AUTH_KEY>
#
# PI_EXECUTE_TOKEN  — must match the value in GCP Secret Manager as 'pi-execute-token'
# TAILSCALE_AUTH_KEY — reusable auth key from https://login.tailscale.com/admin/settings/keys

set -e

PI_EXECUTE_TOKEN="${1:?Usage: bash setup.sh <PI_EXECUTE_TOKEN> <TAILSCALE_AUTH_KEY>}"
TAILSCALE_AUTH_KEY="${2:?Usage: bash setup.sh <PI_EXECUTE_TOKEN> <TAILSCALE_AUTH_KEY>}"

echo "==> Updating system packages"
sudo apt-get update && sudo apt-get upgrade -y

echo "==> Installing Docker"
curl -sSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"

echo "==> Installing Tailscale"
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey="$TAILSCALE_AUTH_KEY" --hostname=rodela-pi

echo "==> Pre-pulling sandbox image"
docker pull python:3.11-slim

echo "==> Building pi-api Docker image"
mkdir -p ~/pi-api
cp -r "$(dirname "$0")/../pi-api/." ~/pi-api/
docker build -t pi-api ~/pi-api

echo "==> Starting pi-api container"
docker run -d \
  --name pi-api \
  --restart always \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e PI_EXECUTE_TOKEN="$PI_EXECUTE_TOKEN" \
  pi-api

echo ""
echo "Setup complete. Verify with:"
echo "  docker ps"
echo "  tailscale status"
echo "  curl http://localhost:8080/ping"
