#!/bin/bash
# ALEC Learning Data Backup
# Exports AKUs, clusters, edges, evaluations, and supporting session data
set -e

BACKUP_FILE="${1:-/tmp/alec-learning-data-$(date +%Y%m%d-%H%M%S).dump}"

echo "=== ALEC Learning Data Backup ==="
echo ""

# Verify postgres is running
if ! docker exec alec-postgres pg_isready -U alec > /dev/null 2>&1; then
    echo "ERROR: alec-postgres container not running or not ready"
    exit 1
fi

# Tables to backup (in dependency order for documentation, pg_dump handles it automatically)
# Core learning:
#   - problem_clusters (no deps)
#   - playbooks (no deps)
#   - playbook_bullets (deps: problem_clusters, playbooks)
#   - knowledge_edges (deps: problem_clusters, playbook_bullets - but no FK constraints)
# Session context:
#   - sessions (no deps)
#   - session_turns (deps: problem_clusters, sessions)
#   - turn_clusters (deps: session_turns, problem_clusters)
#   - session_outcomes (deps: sessions)
# Evaluations:
#   - evaluation_experiments (no deps)
#   - evaluation_task_results (deps: evaluation_experiments)
#   - evaluation_task_outcomes (no FK but logically tied)
#   - evaluation_checkpoints (deps: evaluation_experiments)

TABLES=(
    "problem_clusters"
    "playbooks"
    "playbook_bullets"
    "knowledge_edges"
    "sessions"
    "session_turns"
    "turn_clusters"
    "session_outcomes"
    "evaluation_experiments"
    "evaluation_task_results"
    "evaluation_task_outcomes"
    "evaluation_checkpoints"
    "hdbscan_label_map"
)

# Build -t flags
TABLE_FLAGS=""
for t in "${TABLES[@]}"; do
    TABLE_FLAGS="$TABLE_FLAGS -t $t"
done

echo "Backing up tables:"
for t in "${TABLES[@]}"; do
    COUNT=$(docker exec alec-postgres psql -U alec -d alec -t -c "SELECT COUNT(*) FROM $t;" 2>/dev/null | tr -d ' ')
    printf "  %-30s %s rows\n" "$t" "$COUNT"
done
echo ""

echo "Running pg_dump..."
docker exec alec-postgres pg_dump -U alec -d alec \
    --format=custom \
    --compress=9 \
    --no-owner \
    --no-privileges \
    $TABLE_FLAGS \
    -f /tmp/learning-data.dump

docker cp alec-postgres:/tmp/learning-data.dump "$BACKUP_FILE"
docker exec alec-postgres rm /tmp/learning-data.dump

echo ""
echo "=== Backup Complete ==="
echo "File: $BACKUP_FILE"
echo "Size: $(du -h "$BACKUP_FILE" | cut -f1)"
echo ""
echo "To restore on target machine:"
echo "  ./scripts/restore-learning-data.sh $BACKUP_FILE"
