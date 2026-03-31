"""Shared test fixtures.

Tests are engagement-scoped: each test gets its own engagement and only
its data is cleaned up on teardown.  Running tests will NOT destroy data
belonging to other engagements (e.g. live demo runs).

Set ALEC_DATABASE_URL to point to the target database, or use
SKIP_DB_TESTS=1 to skip DB-dependent tests entirely.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

# Skip DB tests if no Postgres available
SKIP_DB = os.environ.get("SKIP_DB_TESTS", "").lower() in ("1", "true", "yes")

# Tables with an engagement_id column, ordered to respect FK constraints.
_ENGAGEMENT_CHILD_TABLES = [
    "community_analysis",
    "engagement_schema",
    "user_annotations",
    "questions",
    "snapshots",
    "convergence_log",
    "prompt_proposals",
    "tasks",
    "knowledge_items",
    "consolidated_units",
    "relationships",
    "alignments",
    "observations",
    "entities",
    "models",
    "source_configs",
    "coordinator_instances",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="Run smoke tests (requires real LLM API key)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-smoke"):
        skip_smoke = pytest.mark.skip(reason="need --run-smoke to run")
        for item in items:
            if "smoke" in item.keywords:
                item.add_marker(skip_smoke)

    if SKIP_DB:
        skip_db = pytest.mark.skip(reason="DB tests skipped (SKIP_DB_TESTS=1)")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip_db)


@pytest.fixture
def engagement_id():
    return uuid4()


@pytest.fixture
def coordinator_id():
    return uuid4()


@pytest_asyncio.fixture
async def db_pool():
    """Real Postgres pool for integration tests."""
    if SKIP_DB:
        pytest.skip("DB tests skipped (SKIP_DB_TESTS=1)")

    from alec.db.pool import close_pool, create_pool

    db_url = os.environ.get(
        "ALEC_DATABASE_URL",
        "postgresql://alec:alec-dev-password@localhost:5432/alec",
    )
    pool = await create_pool(db_url, min_size=1, max_size=3)
    yield pool
    await close_pool(pool)


async def _delete_engagement_data(pool, eid: UUID) -> None:
    """Delete all data belonging to a single engagement, in FK-safe order."""
    async with pool.acquire() as conn:
        # code_executions references code_assets (not engagement_id directly)
        await conn.execute(
            "DELETE FROM code_executions WHERE asset_id IN "
            "(SELECT asset_id FROM code_assets WHERE engagement_id = $1)",
            eid,
        )
        await conn.execute(
            "DELETE FROM code_assets WHERE engagement_id = $1", eid,
        )
        for table in _ENGAGEMENT_CHILD_TABLES:
            await conn.execute(
                f"DELETE FROM {table} WHERE engagement_id = $1",  # noqa: S608
                eid,
            )
        await conn.execute("DELETE FROM engagements WHERE engagement_id = $1", eid)


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """Provide the database pool. No global cleanup — tests are engagement-scoped."""
    yield db_pool


@pytest_asyncio.fixture
async def test_engagement(db_pool):
    """Create an isolated test engagement and return (pool, engagement_id).

    Only this engagement's data is cleaned up on teardown.
    """
    pool = db_pool
    async with pool.acquire() as conn:
        eid = await conn.fetchval(
            """
            INSERT INTO engagements (name, problem_statement, status)
            VALUES ('Test Engagement', 'Discover test knowledge', 'active')
            RETURNING engagement_id
            """,
        )
    yield pool, eid
    await _delete_engagement_data(pool, eid)
