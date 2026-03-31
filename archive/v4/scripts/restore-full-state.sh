#!/bin/bash
# Full ALEC state restore script
# Restores from backup created by backup-full-state.sh

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <backup-tarball>"
  echo "Example: $0 /tmp/alec-full-backup-20251214-120000.tar.gz"
  exit 1
fi

BACKUP_FILE="$1"
RESTORE_DIR="/tmp/alec-restore-$$"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "=== ALEC Full State Restore ==="
echo "Backup file: $BACKUP_FILE"
echo ""

# Extract backup
echo "Extracting backup..."
mkdir -p "$RESTORE_DIR"
tar xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# Stop services
echo ""
echo "Stopping ALEC services..."
docker-compose down 2>/dev/null || true

# Create volumes if they don't exist
echo "Creating volumes..."
docker volume create alec_postgres_data 2>/dev/null || true
docker volume create alec_redis_data 2>/dev/null || true
docker volume create alec_kafka_data 2>/dev/null || true
docker volume create alec_appworld-data 2>/dev/null || true

# Restore volumes
echo ""
echo "[1/4] Restoring PostgreSQL volume..."
docker run --rm \
  -v alec_postgres_data:/dest \
  -v "$RESTORE_DIR":/backup:ro \
  alpine sh -c "rm -rf /dest/* && tar xzf /backup/postgres-volume.tar.gz -C /dest"
echo "      Done"

echo "[2/4] Restoring Redis volume..."
docker run --rm \
  -v alec_redis_data:/dest \
  -v "$RESTORE_DIR":/backup:ro \
  alpine sh -c "rm -rf /dest/* && tar xzf /backup/redis-volume.tar.gz -C /dest"
echo "      Done"

echo "[3/4] Restoring Kafka volume..."
docker run --rm \
  -v alec_kafka_data:/dest \
  -v "$RESTORE_DIR":/backup:ro \
  alpine sh -c "rm -rf /dest/* && tar xzf /backup/kafka-volume.tar.gz -C /dest"
echo "      Done"

echo "[4/4] Restoring AppWorld volume..."
if [ -f "$RESTORE_DIR/appworld-volume.tar.gz" ]; then
  docker run --rm \
    -v alec_appworld-data:/dest \
    -v "$RESTORE_DIR":/backup:ro \
    alpine sh -c "rm -rf /dest/* && tar xzf /backup/appworld-volume.tar.gz -C /dest"
  echo "      Done"
else
  echo "      Skipped (not in backup)"
fi

# Cleanup
rm -rf "$RESTORE_DIR"

echo ""
echo "=== Restore Complete ==="
echo ""
echo "Next steps:"
echo "  1. Start services: docker-compose up -d"
echo "  2. Verify: docker-compose ps"
echo "  3. Check data: PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -c 'SELECT COUNT(*) FROM playbook_bullets;'"
