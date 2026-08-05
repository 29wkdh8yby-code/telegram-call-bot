#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Build and start all services
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in your values."
    exit 1
fi

echo "==> Pulling latest changes..."
git pull --ff-only || true

echo "==> Building Docker images..."
docker compose build

echo "==> Running database migrations..."
docker compose run --rm migrate

echo "==> Starting services..."
docker compose up -d bot worker healthcheck

echo "==> Waiting for services to become healthy..."
sleep 5

echo "==> Checking health endpoint..."
curl -sf http://localhost:8080/health && echo " ✅ Health check passed" || echo " ⚠️  Health check failed — check logs"

echo ""
echo "==> Deployment complete!"
echo ""
echo "Useful commands:"
echo "  View bot logs:    docker compose logs -f bot"
echo "  View worker logs: docker compose logs -f worker"
echo "  Restart bot:      docker compose restart bot"
echo "  Stop all:         docker compose down"
echo ""
