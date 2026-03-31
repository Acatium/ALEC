"""Fixtures for LLM Gateway integration tests.

Uses real PostgreSQL to catch schema mismatches and SQL errors.
"""

import os

import pytest_asyncio

# Database URL - uses real dev database
_default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
)


@pytest_asyncio.fixture(scope="function")
async def db_pool():
    """Create real database connection pool with JSONB codec."""
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
    """Get a single database connection."""
    async with db_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def clean_test_configs(db_pool):
    """Clean up test configs after each test."""
    test_service_names: list[str] = []

    yield test_service_names

    # Cleanup: delete test configs
    if test_service_names:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM service_configs WHERE service_name = ANY($1)",
                test_service_names
            )
