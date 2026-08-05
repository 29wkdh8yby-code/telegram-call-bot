#!/usr/bin/env bash
# =============================================================================
# setup.sh — First-time VPS setup for the SMTP-to-SMS Telegram Bot
# Run as root or with sudo on a fresh Ubuntu 22.04 LTS server
# =============================================================================
set -euo pipefail

echo "==> Installing Docker and Docker Compose..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release git

# Docker official repo
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "==> Enabling Docker service..."
systemctl enable --now docker

echo "==> Creating application directory..."
mkdir -p /opt/smsbot
cd /opt/smsbot

echo ""
echo "==> Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Copy the project files to /opt/smsbot/"
echo "  2. cp .env.example .env && nano .env"
echo "  3. Run: ./scripts/deploy.sh"
echo ""
