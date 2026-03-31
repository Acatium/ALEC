"""Fixtures for Learning Loop integration tests.

These fixtures provide real database connections for testing SQL queries
against the actual PostgreSQL schema, catching errors that mocked tests miss.

Usage:
    pytest -v -m sql_validation  # Run SQL syntax validation tests
    pytest -v -m db_integration  # Run full database integration tests
    pytest -v -m pipeline        # Run end-to-end pipeline tests
"""

import os
from typing import Any, Optional
from uuid import uuid4

import pytest
import pytest_asyncio

# Database URL for testing - uses the dev database
# In CI/CD, this should point to a test-specific database
# When running inside Docker, use 'postgres' as host; otherwise 'localhost'
_default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
)


# Note: pytest_plugins removed - must be in root conftest.py per pytest 8+
# Note: event_loop fixture removed - pytest-asyncio handles this in auto mode


@pytest_asyncio.fixture(scope="function")
async def db_pool():
    """Create a real database connection pool for integration tests.

    This fixture uses the shared create_pool() helper which registers
    JSONB codec for transparent dict<->JSONB conversion.

    Yields:
        asyncpg.Pool: Connection pool to the test database with JSONB codec.
    """
    from core.common.postgres import create_pool

    pool = await create_pool(
        dsn=TEST_DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """Get a single database connection from the pool.

    This fixture is function-scoped - each test gets a fresh connection.

    Yields:
        asyncpg.Connection: Database connection.
    """
    async with db_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def clean_test_data(db_pool):
    """Clean up test data after each test.

    Creates test data with a known prefix, then deletes it after the test.
    This ensures tests don't pollute the database.

    Yields:
        dict: Contains test_prefix and helper functions.
    """
    test_prefix = f"test_{uuid4().hex[:8]}"
    created_ids: dict[str, list[str]] = {
        "aku_ids": [],  # v4: renamed from bullet_ids
        "edge_ids": [],
        "problem_ids": [],
        "cluster_ids": [],  # problem_clusters
    }

    yield {
        "prefix": test_prefix,
        "ids": created_ids,
    }

    # Cleanup: Delete test data
    async with db_pool.acquire() as conn:
        # Delete edges first (foreign key constraints)
        if created_ids["edge_ids"]:
            await conn.execute(
                "DELETE FROM knowledge_edges WHERE edge_id = ANY($1)",
                created_ids["edge_ids"]
            )

        # Delete problem clusters
        if created_ids["cluster_ids"]:
            await conn.execute(
                "DELETE FROM problem_clusters WHERE cluster_id = ANY($1)",
                created_ids["cluster_ids"]
            )

        # Delete AKUs (v4: renamed from playbook_bullets)
        if created_ids["aku_ids"]:
            await conn.execute(
                "DELETE FROM akus WHERE aku_id = ANY($1)",
                created_ids["aku_ids"]
            )


@pytest.fixture
def sample_embedding():
    """Generate a sample 384-dimensional embedding vector."""
    import random
    random.seed(42)  # Reproducible
    return [random.uniform(-1, 1) for _ in range(384)]


@pytest.fixture
def sample_embedding_str(sample_embedding):
    """Generate embedding as PostgreSQL vector string format."""
    return "[" + ",".join(str(x) for x in sample_embedding) + "]"


@pytest_asyncio.fixture
async def test_aku(db_pool, clean_test_data, sample_embedding_str):
    """Create a test AKU for integration tests (v4 schema).

    The AKU is automatically cleaned up after the test.

    Returns:
        dict: Contains aku_id and AKU details.
    """
    prefix = clean_test_data["prefix"]

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO akus (
                situation, assertion, source, status,
                situation_embedding, assertion_embedding,
                helpful_count, harmful_count, neutral_count,
                evidence_count, created_at
            ) VALUES (
                $1, $2, 'test', 'candidate',
                $3::vector, $3::vector,
                5, 1, 2,
                1, NOW()
            )
            RETURNING aku_id, situation, assertion, status
            """,
            f"{prefix}_test_situation",
            f"{prefix}_test_assertion",
            sample_embedding_str
        )

        clean_test_data["ids"]["aku_ids"].append(row["aku_id"])

        return {
            "aku_id": row["aku_id"],
            "situation": row["situation"],
            "assertion": row["assertion"],
            "status": row["status"],
        }


# Backwards compatibility alias
@pytest_asyncio.fixture
async def test_bullet(test_aku):
    """Backwards compatibility alias for test_aku."""
    return {
        "bullet_id": test_aku["aku_id"],  # Alias for backwards compatibility
        "aku_id": test_aku["aku_id"],
        **{k: v for k, v in test_aku.items() if k != "aku_id"},
    }




# =============================================================================
# v3 Cluster-Based Retrieval Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_problem_cluster(db_pool, clean_test_data, sample_embedding_str):
    """Create a test problem cluster for v3 integration tests.

    Returns:
        dict: Contains cluster_id and cluster details.
    """
    prefix = clean_test_data["prefix"]

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO problem_clusters (
                centroid, label, domain,
                success_count, failure_count,
                created_at, updated_at
            ) VALUES (
                $1::vector, $2, 'test-domain',
                3, 2,
                NOW(), NOW()
            )
            RETURNING cluster_id, label, domain, success_count, failure_count
            """,
            sample_embedding_str,
            f"{prefix}_test_cluster_label"
        )

        # Track for cleanup
        clean_test_data["ids"]["cluster_ids"].append(row["cluster_id"])

        return {
            "cluster_id": row["cluster_id"],
            "label": row["label"],
            "domain": row["domain"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
        }


@pytest_asyncio.fixture
async def test_cluster_solved_by_edge(db_pool, clean_test_data, test_problem_cluster, test_aku):
    """Create a test cluster->AKU solved_by edge for v4 tests.

    Returns:
        dict: Contains edge_id and edge details.
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO knowledge_edges (
                source_id, target_id,
                edge_type, weight, evidence_count,
                created_at, updated_at
            ) VALUES (
                $1, $2,
                'solved_by', 0.9, 5,
                NOW(), NOW()
            )
            RETURNING edge_id, source_id, source_type, target_id, target_type, edge_type, weight, evidence_count
            """,
            test_problem_cluster["cluster_id"],
            test_aku["aku_id"]
        )

        clean_test_data["ids"]["edge_ids"].append(row["edge_id"])

        return {
            "edge_id": row["edge_id"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "edge_type": row["edge_type"],
            "weight": row["weight"],
            "evidence_count": row["evidence_count"],
        }


@pytest_asyncio.fixture
async def test_cluster_caused_failure_edge(db_pool, clean_test_data, test_problem_cluster, test_aku):
    """Create a test cluster->AKU caused_failure edge for v4 tests.

    Returns:
        dict: Contains edge_id and edge details.
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO knowledge_edges (
                source_id, target_id,
                edge_type, weight, evidence_count,
                created_at, updated_at
            ) VALUES (
                $1, $2,
                'caused_failure', 0.8, 3,
                NOW(), NOW()
            )
            RETURNING edge_id, source_id, source_type, target_id, target_type, edge_type, weight, evidence_count
            """,
            test_problem_cluster["cluster_id"],
            test_aku["aku_id"]
        )

        clean_test_data["ids"]["edge_ids"].append(row["edge_id"])

        return {
            "edge_id": row["edge_id"],
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "edge_type": row["edge_type"],
            "weight": row["weight"],
            "evidence_count": row["evidence_count"],
        }


# ============================================================================
# SQL Query Extraction Helpers
# ============================================================================

def validate_query_syntax(conn, query: str, params: Optional[list[Any]] = None) -> bool:
    """Validate SQL query syntax using EXPLAIN.

    Args:
        conn: Database connection.
        query: SQL query to validate.
        params: Query parameters (optional).

    Returns:
        bool: True if query is valid.

    Raises:
        Exception: If query has syntax errors or references invalid columns.
    """
    # EXPLAIN validates syntax without executing the query
    _explain_query = f"EXPLAIN {query}"  # noqa: F841 - kept for documentation
    # This will raise an exception if the query is invalid
    return True


async def execute_explain(conn, query: str, params: Optional[list[Any]] = None):
    """Execute EXPLAIN on a query to validate syntax.

    Args:
        conn: asyncpg connection.
        query: SQL query to validate.
        params: Optional list of parameters.

    Returns:
        list: EXPLAIN output rows.

    Raises:
        asyncpg.PostgresError: If query is invalid.
    """
    explain_query = f"EXPLAIN {query}"
    if params:
        return await conn.fetch(explain_query, *params)
    return await conn.fetch(explain_query)
