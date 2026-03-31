#!/bin/bash
# Full ALEC state backup script
# Creates a single tarball with all data for lab migration

set -e

BACKUP_DIR="/tmp/alec-backup-$(date +%Y%m%d-%H%M%S)"
BACKUP_NAME="alec-full-backup-$(date +%Y%m%d-%H%M%S).tar.gz"

echo "=== ALEC Full State Backup ==="
echo "Backup directory: $BACKUP_DIR"
echo ""

mkdir -p "$BACKUP_DIR"

# 1. PostgreSQL dump (most important - all learning data)
echo "[1/5] Dumping PostgreSQL database..."
docker exec alec-postgres pg_dump -U alec -d alec \
  --format=custom --compress=9 \
  -f /tmp/alec-database.dump
docker cp alec-postgres:/tmp/alec-database.dump "$BACKUP_DIR/alec-database.dump"
docker exec alec-postgres rm /tmp/alec-database.dump
echo "      Done: $(du -h "$BACKUP_DIR/alec-database.dump" | cut -f1)"

# 2. PostgreSQL volume (full data directory)
echo "[2/5] Backing up PostgreSQL volume..."
docker run --rm \
  -v alec_postgres_data:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/postgres-volume.tar.gz -C /source .
echo "      Done: $(du -h "$BACKUP_DIR/postgres-volume.tar.gz" | cut -f1)"

# 3. Redis volume (session cache)
echo "[3/5] Backing up Redis volume..."
docker exec alec-redis redis-cli BGSAVE > /dev/null 2>&1 || true
sleep 2  # Wait for background save
docker run --rm \
  -v alec_redis_data:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/redis-volume.tar.gz -C /source .
echo "      Done: $(du -h "$BACKUP_DIR/redis-volume.tar.gz" | cut -f1)"

# 4. Kafka volume (event logs)
echo "[4/5] Backing up Kafka volume..."
docker run --rm \
  -v alec_kafka_data:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/kafka-volume.tar.gz -C /source .
echo "      Done: $(du -h "$BACKUP_DIR/kafka-volume.tar.gz" | cut -f1)"

# 5. AppWorld data volume (evaluation tasks)
echo "[5/5] Backing up AppWorld volume..."
docker run --rm \
  -v alec_appworld-data:/source:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf /backup/appworld-volume.tar.gz -C /source . 2>/dev/null || echo "      (empty or not found, skipping)"
echo "      Done: $(du -h "$BACKUP_DIR/appworld-volume.tar.gz" 2>/dev/null | cut -f1 || echo "skipped")"

# Create final tarball
echo ""
echo "Creating final backup archive..."
tar czf "/tmp/$BACKUP_NAME" -C "$BACKUP_DIR" .

# Cleanup intermediate files
rm -rf "$BACKUP_DIR"

echo ""
echo "=== Backup Complete ==="
echo "File: /tmp/$BACKUP_NAME"
echo "Size: $(du -h "/tmp/$BACKUP_NAME" | cut -f1)"
echo ""
echo "To restore on target lab:"
echo "  1. Copy this file to target machine"
echo "  2. Run: ./scripts/restore-full-state.sh /path/to/$BACKUP_NAME"
