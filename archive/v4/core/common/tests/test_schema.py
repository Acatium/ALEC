"""
Schema validation tests.

Ensures database schema matches code expectations.
Run as part of test suite to catch schema drift early.
"""

import pytest

# Expected tables that must exist for ALEC to function
REQUIRED_TABLES = [
    "sessions",
    "session_events",
    "session_turns",
    "playbooks",
    "akus",  # v4 schema - renamed from playbook_bullets
    "problem_clusters",
    "knowledge_edges",
    "turn_clusters",
    "evaluation_experiments",
    "evaluation_task_results",
    "evaluation_checkpoints",
    "evaluation_task_outcomes",
    "service_configs",
    "schema_migrations",
]

# Required columns for critical tables
REQUIRED_COLUMNS = {
    "evaluation_experiments": [
        "id",
        "name",
        "experiment_type",
        "status",
        "config",
        "container_id",  # Added by migration 17
        "container_name",
    ],
    "akus": [  # v4 schema - renamed from playbook_bullets
        "aku_id",
        "situation",  # Problem context (≤60 chars)
        "assertion",  # Actionable advice (≤100 chars)
        "status",
        "helpful_count",
        "harmful_count",
        "neutral_count",
    ],
    "session_turns": [
        "turn_id",
        "session_id",
        "turn_number",
        "micro_outcome",
    ],
}


class TestSchemaValidation:
    """Validate database schema matches code expectations."""

    @pytest.fixture
    async def db_conn(self):
        """Get database connection."""
        import os

        import asyncpg

        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        )
        conn = await asyncpg.connect(database_url)
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_required_tables_exist(self, db_conn):
        """All required tables must exist."""
        rows = await db_conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        existing_tables = {row["table_name"] for row in rows}

        missing = set(REQUIRED_TABLES) - existing_tables
        assert not missing, f"Missing required tables: {missing}"

    @pytest.mark.asyncio
    async def test_required_columns_exist(self, db_conn):
        """Critical columns must exist in their tables."""
        for table, columns in REQUIRED_COLUMNS.items():
            rows = await db_conn.fetch("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = $1
            """, table)
            existing_columns = {row["column_name"] for row in rows}

            missing = set(columns) - existing_columns
            assert not missing, f"Table {table} missing columns: {missing}"

    @pytest.mark.asyncio
    async def test_schema_migrations_tracked(self, db_conn):
        """schema_migrations table should have entries."""
        count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM schema_migrations"
        )
        assert count > 0, "schema_migrations table is empty - migrations not tracked"

    @pytest.mark.asyncio
    async def test_no_duplicate_migrations(self, db_conn):
        """Each migration should only be recorded once."""
        rows = await db_conn.fetch("""
            SELECT migration_name, COUNT(*) as count
            FROM schema_migrations
            GROUP BY migration_name
            HAVING COUNT(*) > 1
        """)
        assert len(rows) == 0, f"Duplicate migrations found: {[r['migration_name'] for r in rows]}"
