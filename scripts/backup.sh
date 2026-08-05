#!/usr/bin/env bash
# =============================================================================
# backup.sh — Back up PostgreSQL database
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/opt/smsbot/backups}"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/smsbot_${TIMESTAMP}.sql.gz"

echo "==> Backing up database to $BACKUP_FILE..."
docker compose exec -T postgres pg_dump -U smsbot smsbot | gzip > "$BACKUP_FILE"

echo "==> Backup complete: $BACKUP_FILE"

# Keep only the last 30 backups
echo "==> Cleaning up old backups (keeping last 30)..."
ls -t "$BACKUP_DIR"/smsbot_*.sql.gz | tail -n +31 | xargs -r rm --

echo "==> Done."
