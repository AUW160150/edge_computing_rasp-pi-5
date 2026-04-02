#!/bin/bash
# Pi Setup Script — run once on a fresh Raspberry Pi 5 (Raspberry Pi OS 64-bit)
# Usage: bash setup.sh <PI_EXECUTE_TOKEN>
# The PI_EXECUTE_TOKEN must match the value stored in GCP Secret Manager as 'pi-execute-token'.

set -e

PI_EXECUTE_TOKEN="${1:?Usage: bash setup.sh <PI_EXECUTE_TOKEN>}"

echo "==> Updating system packages"
sudo apt-get update && sudo apt-get upgrade -y

echo "==> Installing Docker"
curl -sSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"

echo "==> Installing gcloud CLI"
curl https://sdk.cloud.google.com | bash -s -- --disable-prompts
export PATH="$HOME/google-cloud-sdk/bin:$PATH"

echo "==> Installing cloudflared"
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
  -o /tmp/cloudflared
sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

echo "==> Creating pi-api directory"
mkdir -p ~/pi-api

echo "==> Writing update-tunnel-url.sh"
cat > ~/update-tunnel-url.sh << 'EOF'
#!/bin/bash
# Reads the current Cloudflare tunnel URL from cloudflared logs and saves it to GCP Secret Manager.
set -e

LOGFILE="/tmp/cloudflared.log"
PROJECT_ID="rodela-trial-project"
SECRET_ID="pi-tunnel-url"

# Wait for URL to appear in logs (up to 30s)
for i in $(seq 1 15); do
  URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGFILE" 2>/dev/null | tail -1)
  if [ -n "$URL" ]; then break; fi
  sleep 2
done

if [ -z "$URL" ]; then
  echo "ERROR: Could not find Cloudflare tunnel URL in logs"
  exit 1
fi

echo "Tunnel URL: $URL"
echo -n "$URL" | gcloud secrets versions add "$SECRET_ID" --data-file=- --project="$PROJECT_ID"
echo "Saved to Secret Manager: $SECRET_ID"
EOF
chmod +x ~/update-tunnel-url.sh

echo "==> Writing cloudflared systemd service"
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << EOF
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8080 --logfile /tmp/cloudflared.log
ExecStartPost=/bin/bash -c 'sleep 15 && /home/${USER}/update-tunnel-url.sh'
Restart=always
User=${USER}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cloudflared

echo "==> Building and starting pi-api Docker container"
# Copy pi-api source (assumes this script is run from the repo root)
cp -r "$(dirname "$0")/../pi-api" ~/pi-api

docker build -t pi-api ~/pi-api
docker run -d \
  --name pi-api \
  --restart always \
  -p 8080:8080 \
  -e PI_EXECUTE_TOKEN="$PI_EXECUTE_TOKEN" \
  pi-api

echo "==> Starting Cloudflare tunnel"
sudo systemctl start cloudflared

echo ""
echo "Setup complete. Verify with:"
echo "  docker ps"
echo "  sudo systemctl status cloudflared"
echo "  curl http://localhost:8080/ping"
