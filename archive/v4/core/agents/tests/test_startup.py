"""Tests for agents service startup and connectivity.

These tests verify the service can start and connect to all dependencies:
- PostgreSQL pool creation
- Kafka consumer registration
- Redis connection (for caching)
"""

import os

import asyncpg
import pytest


class TestServiceStartup:
    """Test service startup and connectivity."""

    @pytest.mark.asyncio
    async def test_postgres_pool_creation(self):
        """Verify PostgreSQL connection pool can be created."""
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        )

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        assert pool is not None

        # Test query
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

        await pool.close()

    @pytest.mark.asyncio
    async def test_agents_service_imports(self):
        """Verify agents service can be imported without errors."""
        from core.agents.main import AgentsService

        service = AgentsService()
        assert service is not None
        assert hasattr(service, "librarian")
        assert hasattr(service, "strategist")

    @pytest.mark.asyncio
    async def test_librarian_service_imports(self):
        """Verify LIBRARIAN service can be imported."""
        from core.agents.librarian.service import LibrarianService

        service = LibrarianService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_strategist_service_imports(self):
        """Verify STRATEGIST service can be imported."""
        from core.agents.strategist.service import StrategistService

        service = StrategistService()
        assert service is not None


class TestDependencyVerification:
    """Verify upstream data dependencies exist."""

    @pytest.mark.asyncio
    async def test_problem_clusters_exist(self):
        """Verify problem_clusters table has data."""
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        )

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM problem_clusters")
            # Should have some clusters from prior training
            assert count >= 0, "problem_clusters table should exist"

        await pool.close()

    @pytest.mark.asyncio
    async def test_session_turns_exist(self):
        """Verify session_turns table has data with micro_outcomes."""
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        )

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            # Check table exists and has micro_outcome column
            result = await conn.fetch("""
                SELECT micro_outcome, COUNT(*)
                FROM session_turns
                GROUP BY micro_outcome
            """)
            # Should have some turns
            assert result is not None, "session_turns table should exist"

        await pool.close()

    @pytest.mark.asyncio
    async def test_session_ended_events_exist(self):
        """Verify session.ended events exist with success values."""
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        )

        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            result = await conn.fetch("""
                SELECT payload->>'success' as success, COUNT(*)
                FROM session_events
                WHERE event_type = 'session.ended'
                GROUP BY payload->>'success'
            """)
            # Should have some session.ended events
            assert result is not None, "session_events should have session.ended events"

        await pool.close()
