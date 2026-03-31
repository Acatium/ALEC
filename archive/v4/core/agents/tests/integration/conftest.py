"""Fixtures for agents service integration tests.

Provides database connections and test data fixtures for testing
LIBRARIAN and STRATEGIST service interactions.

Usage:
    pytest -v -m db_integration core/agents/tests/integration/
"""

import os
from uuid import uuid4

import pytest
import pytest_asyncio

# Database URL - uses 'postgres' in Docker, 'localhost' outside
_default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
)


@pytest_asyncio.fixture(scope="function")
async def db_pool():
    """Create a database connection pool for integration tests."""
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
async def clean_test_data(db_pool):
    """Clean up test data after each test."""
    test_prefix = f"test_{uuid4().hex[:8]}"
    created_ids: dict[str, list] = {
        "aku_ids": [],
        "edge_ids": [],
        "cluster_ids": [],
        "turn_ids": [],
        "session_ids": [],
    }

    yield {
        "prefix": test_prefix,
        "ids": created_ids,
    }

    # Cleanup (order matters for foreign keys)
    async with db_pool.acquire() as conn:
        if created_ids["edge_ids"]:
            await conn.execute(
                "DELETE FROM knowledge_edges WHERE edge_id = ANY($1)",
                created_ids["edge_ids"]
            )
        if created_ids["turn_ids"]:
            await conn.execute(
                "DELETE FROM turn_clusters WHERE turn_id = ANY($1)",
                created_ids["turn_ids"]
            )
            await conn.execute(
                "DELETE FROM session_turns WHERE turn_id = ANY($1)",
                created_ids["turn_ids"]
            )
        if created_ids["session_ids"]:
            await conn.execute(
                "DELETE FROM evaluation_task_outcomes WHERE session_id = ANY($1)",
                created_ids["session_ids"]
            )
            await conn.execute(
                "DELETE FROM sessions WHERE session_id = ANY($1)",
                created_ids["session_ids"]
            )
        if created_ids["cluster_ids"]:
            await conn.execute(
                "DELETE FROM problem_clusters WHERE cluster_id = ANY($1)",
                created_ids["cluster_ids"]
            )
        if created_ids["aku_ids"]:
            await conn.execute(
                "DELETE FROM akus WHERE aku_id = ANY($1)",
                created_ids["aku_ids"]
            )


@pytest.fixture
def sample_embedding():
    """Generate a sample 384-dimensional embedding vector."""
    import random
    random.seed(42)
    return [random.uniform(-1, 1) for _ in range(384)]


@pytest.fixture
def sample_embedding_str(sample_embedding):
    """Generate embedding as PostgreSQL vector string format."""
    return "[" + ",".join(str(x) for x in sample_embedding) + "]"
