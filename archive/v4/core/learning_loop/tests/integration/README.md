# Learning Loop Integration Tests

Integration tests for the v3 Learning Loop, including turn-level attribution,
cluster-based retrieval, and edge creation.

## Test Files

### test_counter_updates.py
Tests per-turn counter updates (helpful_count, harmful_count, neutral_count).

**Key tests:**
- `test_helpful_count_incremented_for_helped_bullets` - Verify helpful++ on progress/solved
- `test_harmful_count_incremented_for_harmed_bullets` - Verify harmful++ on stuck/error
- `test_harmful_count_validates_constraints` - Constraints proven when ignored
- `test_neutral_count_incremented_for_irrelevant_bullets` - Verify neutral++ for irrelevant
- `test_counter_updates_are_per_turn` - Same bullet different attribution per turn
- `test_last_used_at_updated_on_any_counter_increment` - Timestamp tracking

### test_cluster_retrieval.py
Tests cluster-based hybrid retrieval (vector + cluster + graph).

**Key tests:**
- `test_solved_by_edges_boost_bullets` - Cluster edges boost retrieval scores
- `test_caused_failure_edges_exclude_bullets` - Harmful bullets excluded
- `test_hybrid_retrieval_combines_sources` - Vector + cluster + graph merged
- `test_cluster_similarity_scoring` - Score = cluster_sim × edge_weight
- `test_archived_bullets_excluded_from_retrieval` - Status filtering

### test_clusterer_edges.py
Tests CLUSTERER edge creation from attribution.resolved events.

**Key tests:**
- `test_solved_by_edge_created_for_helped_bullet` - Create edges for helped bullets
- `test_caused_failure_edge_created_for_harmed_bullet` - Create edges for harmed bullets
- `test_upsert_increments_evidence_count` - Edge upsert logic
- `test_cluster_statistics_updated` - Update turn/success/failure counts
- `test_turn_assignment_to_cluster` - Sub-task similarity assignment
- `test_multiple_bullets_per_turn` - Multiple edges per turn
- `test_same_bullet_can_have_both_edge_types` - solved_by + caused_failure

## Running Tests

### Prerequisites
- PostgreSQL must be running (docker-compose up -d postgres)
- Database must be migrated (latest schema)
- TEST_DATABASE_URL environment variable (defaults to dev database)

### Run all integration tests
```bash
pytest -v -m db_integration core/learning_loop/tests/integration/
```

### Run specific test file
```bash
pytest -v -m db_integration core/learning_loop/tests/integration/test_counter_updates.py
```

### Run specific test
```bash
pytest -v -m db_integration core/learning_loop/tests/integration/test_counter_updates.py::TestPerTurnCounterUpdates::test_helpful_count_incremented_for_helped_bullets
```

### Run with verbose output
```bash
pytest -vv -m db_integration core/learning_loop/tests/integration/ --tb=short
```

## Test Markers

- `@pytest.mark.db_integration` - Requires real PostgreSQL database
- `@pytest.mark.asyncio` - Async test (uses event loop)

## Fixtures

Fixtures defined in `conftest.py`:

### Session-scoped
- `db_pool` - asyncpg connection pool (reused across tests)
- `event_loop` - Event loop for async tests

### Function-scoped
- `db_conn` - Single database connection (per test)
- `clean_test_data` - Auto-cleanup test data after each test
- `sample_embedding` - 384-dimensional test embedding
- `sample_embedding_str` - PostgreSQL vector format string
- `test_bullet` - Pre-created test bullet (auto-cleanup)
- `test_problem_node` - Pre-created problem node (auto-cleanup)
- `test_problem_cluster` - Pre-created cluster (v3, auto-cleanup)
- `test_cluster_solved_by_edge` - Pre-created cluster→bullet edge
- `test_cluster_caused_failure_edge` - Pre-created harm edge

## Data Cleanup

All fixtures use `clean_test_data` to track created IDs and automatically
delete them after tests complete. This prevents database pollution.

**Cleanup order (respects foreign keys):**
1. knowledge_edges
2. problem_nodes
3. problem_clusters
4. playbook_bullets (by content prefix)

## Database Schema Requirements

Tests assume the following schema (from migrations):
- `playbook_bullets` with helpful/harmful/neutral counters
- `problem_clusters` with centroid, turn_count, success/failure counts
- `knowledge_edges` with source_type='cluster' and edge_type='solved_by'/'caused_failure'
- `problem_nodes` with embedding for graph traversal

## SQL Validation

These integration tests validate actual SQL query syntax against the real
PostgreSQL schema, catching:
- Column name mismatches
- JOIN errors
- Constraint violations
- Type mismatches

Unlike unit tests with mocked databases, these tests catch production bugs
before deployment.

## Notes

- Tests use deterministic embeddings for reproducibility
- Distance threshold for cluster assignment: 0.4 (cosine distance)
- Similarity threshold for retrieval: 0.35 (v3 high recall)
- Tests do not require Kafka or Redis (direct database operations)
