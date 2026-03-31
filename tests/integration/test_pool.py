"""Integration tests for database pool."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.db


@pytest.mark.asyncio
async def test_pool_connects(db_pool):
    async with db_pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1


@pytest.mark.asyncio
async def test_pgvector_extension(db_pool):
    async with db_pool.acquire() as conn:
        result = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    assert result == "vector"


@pytest.mark.asyncio
async def test_tables_exist(db_pool):
    expected_tables = {
        "engagements",
        "models",
        "observations",
        "entities",
        "relationships",
        "alignments",
        "knowledge_items",
        "consolidated_units",
        "agent_types",
        "prompt_versions",
        "prompt_proposals",
        "coordinator_instances",
        "tasks",
        "convergence_log",
        "source_configs",
        "code_assets",
        "code_executions",
    }
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    actual = {r["tablename"] for r in rows}
    missing = expected_tables - actual
    assert not missing, f"Missing tables: {missing}"
