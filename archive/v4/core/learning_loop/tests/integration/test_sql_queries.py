"""SQL Query Validation Tests (v4).

These tests validate SQL queries against the real PostgreSQL schema
using EXPLAIN to catch column mismatches, JOIN errors, and syntax issues
that mocked tests cannot detect.

v4 Schema Changes (Dec 2025):
- playbook_bullets renamed to akus
- 14 fields: situation, assertion, embeddings, counters, status, source, cluster_id
- Removed: modality, polarity, category, domain, content, updated_at, tags
- Length constraints: situation ≤60 chars, assertion ≤100 chars

Run: pytest -v -m sql_validation core/learning_loop/tests/integration/
"""

import pytest

from .conftest import execute_explain

# =============================================================================
# ADVISOR SQL Queries (advisor/service.py)
# =============================================================================

class TestAdvisorSQLQueries:
    """Validate SQL queries in advisor/service.py."""

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_aku_retrieval_by_situation_embedding(self, db_conn, sample_embedding_str):
        """Validate retrieval query using situation_embedding.

        v4: Retrieval uses situation_embedding (problem space)
        """
        query = """
            SELECT
                aku_id::text as aku_id,
                situation,
                assertion,
                source,
                status,
                helpful_count,
                harmful_count,
                neutral_count,
                evidence_count,
                1 - (situation_embedding <=> $1::vector) as similarity
            FROM akus
            WHERE status IN ('candidate', 'active')
              AND 1 - (situation_embedding <=> $1::vector) >= $2
            ORDER BY similarity DESC
            LIMIT 50
        """
        await execute_explain(db_conn, query, [sample_embedding_str, 0.5])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_cluster_solutions_query(self, db_conn, sample_embedding_str):
        """Validate solved_by edge retrieval query.

        v4: Joins knowledge_edges with problem_clusters for cluster-based retrieval
        """
        query = """
            SELECT DISTINCT
                ke.target_id::text as aku_id,
                a.situation,
                a.assertion,
                a.helpful_count,
                a.harmful_count,
                1 - (pc.centroid <=> $1::vector) as cluster_similarity,
                ke.weight as edge_weight
            FROM knowledge_edges ke
            JOIN problem_clusters pc ON ke.source_id = pc.cluster_id
            JOIN akus a ON ke.target_id = a.aku_id
            WHERE ke.edge_type = 'solved_by'
              AND a.status IN ('candidate', 'active')
              AND 1 - (pc.centroid <=> $1::vector) >= $2
            ORDER BY cluster_similarity DESC, edge_weight DESC
            LIMIT 20
        """
        await execute_explain(db_conn, query, [sample_embedding_str, 0.5])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_caused_failure_exclusion_query(self, db_conn, sample_embedding_str):
        """Validate caused_failure edge exclusion query.

        v4: caused_failure edges exclude AKUs for similar situations
        """
        query = """
            SELECT DISTINCT ke.target_id::text as aku_id
            FROM knowledge_edges ke
            JOIN problem_clusters pc ON ke.source_id = pc.cluster_id
            WHERE ke.edge_type = 'caused_failure'
              AND 1 - (pc.centroid <=> $1::vector) >= $2
        """
        await execute_explain(db_conn, query, [sample_embedding_str, 0.65])


# =============================================================================
# CURATOR SQL Queries (curator/service.py)
# =============================================================================

class TestCuratorSQLQueries:
    """Validate SQL queries in curator/service.py."""

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_dedup_by_assertion_embedding(self, db_conn, sample_embedding_str):
        """Validate deduplication query using assertion_embedding.

        v4: Dedup uses assertion_embedding (same insight = duplicate)
        """
        query = """
            SELECT aku_id::text
            FROM akus
            WHERE 1 - (assertion_embedding <=> $1::vector) > $2
              AND status IN ('candidate', 'active')
            ORDER BY 1 - (assertion_embedding <=> $1::vector) DESC
            LIMIT 1
        """
        await execute_explain(db_conn, query, [sample_embedding_str, 0.70])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_aku_insert_columns(self, db_conn, sample_embedding_str):
        """Validate INSERT has all required columns.

        v4: simplified schema - situation/assertion/embeddings/counters
        """
        query = """
            INSERT INTO akus (
                aku_id, situation, assertion, source, status,
                situation_embedding, assertion_embedding,
                helpful_count, harmful_count, neutral_count,
                evidence_count, created_at
            ) VALUES (
                gen_random_uuid(), 'test situation', 'test assertion', 'reflector', 'candidate',
                $1::vector, $1::vector,
                0, 0, 0,
                1, NOW()
            )
            RETURNING aku_id
        """
        explain_query = f"EXPLAIN {query}"
        await db_conn.fetch(explain_query, sample_embedding_str)

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_evidence_increment(self, db_conn):
        """Validate evidence_count increment query."""
        query = """
            UPDATE akus
            SET evidence_count = evidence_count + 1
            WHERE aku_id = $1
        """
        await execute_explain(db_conn, query, ['00000000-0000-0000-0000-000000000000'])


# =============================================================================
# REFLECTOR SQL Queries (reflector/service.py)
# =============================================================================

class TestReflectorSQLQueries:
    """Validate SQL queries in reflector/service.py."""

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_counter_update_helpful(self, db_conn):
        """Validate helpful_count increment query."""
        query = """
            UPDATE akus
            SET helpful_count = helpful_count + 1
            WHERE aku_id = $1
        """
        await execute_explain(db_conn, query, ['00000000-0000-0000-0000-000000000000'])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_counter_update_harmful(self, db_conn):
        """Validate harmful_count increment query."""
        query = """
            UPDATE akus
            SET harmful_count = harmful_count + 1
            WHERE aku_id = $1
        """
        await execute_explain(db_conn, query, ['00000000-0000-0000-0000-000000000000'])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_fetch_akus_info(self, db_conn):
        """Validate AKU info fetch for LLM context."""
        query = """
            SELECT aku_id, situation, assertion
            FROM akus
            WHERE aku_id = ANY($1::uuid[])
        """
        await execute_explain(db_conn, query, [['00000000-0000-0000-0000-000000000000']])


# =============================================================================
# CLUSTERER SQL Queries (clusterer/service.py)
# =============================================================================

class TestClustererSQLQueries:
    """Validate SQL queries in clusterer/service.py."""

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_find_cluster_by_centroid(self, db_conn, sample_embedding_str):
        """Validate cluster lookup by centroid similarity."""
        query = """
            SELECT cluster_id, label, success_count, failure_count
            FROM problem_clusters
            WHERE 1 - (centroid <=> $1::vector) > $2
            ORDER BY 1 - (centroid <=> $1::vector) DESC
            LIMIT 1
        """
        await execute_explain(db_conn, query, [sample_embedding_str, 0.65])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_edge_upsert(self, db_conn):
        """Validate knowledge_edges upsert query."""
        query = """
            INSERT INTO knowledge_edges (source_type, source_id, target_type, target_id, edge_type, weight, evidence_count)
            VALUES ('cluster', $1, 'aku', $2, $3, 1.0, 1)
            ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                evidence_count = knowledge_edges.evidence_count + 1,
                weight = 1.0 - (1.0 / (knowledge_edges.evidence_count + 2)),
                updated_at = NOW()
        """
        await execute_explain(db_conn, query, [
            '00000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000',
            'solved_by'
        ])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_edge_type_constraint(self, db_conn):
        """Validate edge_type CHECK constraint allows v4 types."""
        query = """
            SELECT edge_type
            FROM knowledge_edges
            WHERE edge_type = ANY($1::text[])
            LIMIT 1
        """
        await execute_explain(db_conn, query, [['solved_by', 'caused_failure']])

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_turn_store(self, db_conn):
        """Validate session_turns INSERT."""
        query = """
            INSERT INTO session_turns (
                turn_id, session_id, turn_number, sub_task, micro_outcome,
                akus_shown, akus_helped, akus_harmed,
                user_message, assistant_response, created_at
            ) VALUES (
                gen_random_uuid(), $1, $2, $3, $4,
                $5, $6, $7,
                $8, $9, NOW()
            )
        """
        explain_query = f"EXPLAIN {query}"
        await db_conn.fetch(
            explain_query,
            '00000000-0000-0000-0000-000000000000',  # session_id
            1,  # turn_number
            'test sub task',  # sub_task
            'progress',  # micro_outcome
            [],  # akus_shown
            [],  # akus_helped
            [],  # akus_harmed
            'user message',  # user_message
            'assistant response',  # assistant_response
        )

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_cluster_counter_increment(self, db_conn):
        """Validate cluster counter increment query."""
        query = """
            UPDATE problem_clusters
            SET success_count = success_count + 1,
                updated_at = NOW()
            WHERE cluster_id = $1
        """
        await execute_explain(db_conn, query, ['00000000-0000-0000-0000-000000000000'])


# =============================================================================
# Schema Validation
# =============================================================================

class TestSchemaValidation:
    """Validate v4 schema structure."""

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_akus_v4_columns(self, db_conn):
        """Verify akus has v4 columns."""
        result = await db_conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'akus'
        """)
        columns = {r['column_name'] for r in result}

        # v4 required columns
        assert 'aku_id' in columns
        assert 'situation' in columns
        assert 'assertion' in columns
        assert 'situation_embedding' in columns
        assert 'assertion_embedding' in columns
        assert 'source' in columns
        assert 'status' in columns

        # Counter columns
        assert 'helpful_count' in columns
        assert 'harmful_count' in columns
        assert 'neutral_count' in columns
        assert 'evidence_count' in columns

        # v4: These columns removed
        assert 'modality' not in columns
        assert 'polarity' not in columns
        assert 'category' not in columns
        assert 'domain' not in columns
        assert 'content' not in columns

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_knowledge_edges_columns(self, db_conn):
        """Verify knowledge_edges has required columns."""
        result = await db_conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'knowledge_edges'
        """)
        columns = {r['column_name'] for r in result}

        assert 'edge_id' in columns
        assert 'source_id' in columns
        assert 'target_id' in columns
        assert 'edge_type' in columns
        assert 'weight' in columns
        assert 'evidence_count' in columns

    @pytest.mark.sql_validation
    @pytest.mark.asyncio
    async def test_problem_clusters_columns(self, db_conn):
        """Verify problem_clusters has required columns."""
        result = await db_conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'problem_clusters'
        """)
        columns = {r['column_name'] for r in result}

        assert 'cluster_id' in columns
        assert 'label' in columns
        assert 'centroid' in columns
        assert 'success_count' in columns
        assert 'failure_count' in columns
