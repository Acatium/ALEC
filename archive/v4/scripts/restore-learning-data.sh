#!/bin/bash
# ALEC Learning Data Restore
# Restores AKUs, clusters, edges, evaluations from backup
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file>"
    echo "Example: $0 /tmp/alec-learning-data-20251214-120000.dump"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "=== ALEC Learning Data Restore ==="
echo "Backup file: $BACKUP_FILE"
echo ""

# Verify postgres is running
if ! docker exec alec-postgres pg_isready -U alec > /dev/null 2>&1; then
    echo "ERROR: alec-postgres container not running or not ready"
    exit 1
fi

# Verify schema exists (check for a key table)
if ! docker exec alec-postgres psql -U alec -d alec -c "SELECT 1 FROM playbook_bullets LIMIT 1;" > /dev/null 2>&1; then
    echo "ERROR: Schema not initialized. Run 'docker-compose up -d' first to create tables."
    exit 1
fi

# Show what's in the backup
echo "Backup contents:"
docker run --rm -v "$(dirname "$BACKUP_FILE"):/backup:ro" postgres:17 \
    pg_restore --list "/backup/$(basename "$BACKUP_FILE")" 2>/dev/null | \
    grep "TABLE DATA" | awk '{print "  " $NF}' || true
echo ""

# Confirm before proceeding
read -p "This will REPLACE existing data in these tables. Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Tables to truncate (reverse dependency order)
TABLES_TO_CLEAR=(
    "turn_clusters"
    "session_outcomes"
    "session_turns"
    "evaluation_checkpoints"
    "evaluation_task_outcomes"
    "evaluation_task_results"
    "hdbscan_label_map"
    "knowledge_edges"
    "playbook_bullets"
    "evaluation_experiments"
    "sessions"
    "playbooks"
    "problem_clusters"
)

echo "Clearing existing data..."
for t in "${TABLES_TO_CLEAR[@]}"; do
    docker exec alec-postgres psql -U alec -d alec -c "TRUNCATE $t CASCADE;" 2>/dev/null || true
done

echo "Copying backup to container..."
docker cp "$BACKUP_FILE" alec-postgres:/tmp/learning-data.dump

echo "Restoring data..."
docker exec alec-postgres pg_restore -U alec -d alec \
    --no-owner \
    --no-privileges \
    --disable-triggers \
    --data-only \
    /tmp/learning-data.dump

docker exec alec-postgres rm /tmp/learning-data.dump

echo ""
echo "=== Restore Complete ==="
echo ""
echo "Verification:"
for t in problem_clusters playbook_bullets knowledge_edges evaluation_experiments; do
    COUNT=$(docker exec alec-postgres psql -U alec -d alec -t -c "SELECT COUNT(*) FROM $t;" | tr -d ' ')
    printf "  %-25s %s rows\n" "$t" "$COUNT"
done
echo ""
echo "Run 'docker-compose restart learning-loop agents' to pick up new data."
