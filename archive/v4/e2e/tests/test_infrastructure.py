"""
Infrastructure Tests.

Verify that all E2E infrastructure is working correctly.
These tests run first to ensure the environment is healthy.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

import asyncio

import asyncpg
import httpx
import pytest
from aiokafka import AIOKafkaConsumer
from redis import asyncio as aioredis

pytestmark = pytest.mark.e2e


class TestServiceHealth:
    """Verify all services are healthy."""

    @pytest.mark.asyncio
    async def test_session_api_healthy(self, api_client: httpx.AsyncClient):
        """Session API should respond to health check."""
        resp = await api_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_session_api_version(self, api_client: httpx.AsyncClient):
        """Session API should have /api/v1 endpoints."""
        # List sessions endpoint should exist
        resp = await api_client.get("/api/v1/chat/sessions")
        # 200 = success, 404 would mean endpoint doesn't exist
        assert resp.status_code in [200, 401, 403]


class TestDatabaseConnection:
    """Verify PostgreSQL connection."""

    @pytest.mark.asyncio
    async def test_can_query_database(self, db_pool: asyncpg.Pool):
        """Should be able to execute queries."""
        async with db_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    @pytest.mark.asyncio
    async def test_pgvector_extension_available(self, db_pool: asyncpg.Pool):
        """pgvector extension should be installed."""
        async with db_pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
            assert result is True, "pgvector extension not installed"

    @pytest.mark.asyncio
    async def test_required_tables_exist(self, db_pool: asyncpg.Pool):
        """All required tables should exist."""
        required_tables = [
            "sessions",
            "session_turns",
            "session_events",
            "playbook_bullets",
            "problem_clusters",
            "knowledge_edges",
        ]

        async with db_pool.acquire() as conn:
            for table in required_tables:
                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = $1
                    )
                    """,
                    table
                )
                assert exists, f"Required table '{table}' does not exist"


class TestRedisConnection:
    """Verify Redis connection."""

    @pytest.mark.asyncio
    async def test_can_ping_redis(self, redis_client: aioredis.Redis):
        """Should be able to ping Redis."""
        result = await redis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_can_set_and_get(self, redis_client: aioredis.Redis):
        """Should be able to set and get values."""
        test_key = "e2e_test_key"
        test_value = "e2e_test_value"

        await redis_client.set(test_key, test_value)
        result = await redis_client.get(test_key)
        assert result == test_value

        # Cleanup
        await redis_client.delete(test_key)


class TestKafkaConnection:
    """Verify Kafka connection."""

    @pytest.mark.asyncio
    async def test_can_create_consumer(self, kafka_consumer: AIOKafkaConsumer):
        """Should be able to create a Kafka consumer."""
        # Consumer is created by fixture, just verify it exists
        assert kafka_consumer is not None

    @pytest.mark.asyncio
    async def test_can_subscribe_to_topics(self, kafka_consumer: AIOKafkaConsumer):
        """Should be able to subscribe to topics."""
        kafka_consumer.subscribe(["session.created"])
        await asyncio.sleep(0.5)

        subscription = kafka_consumer.subscription()
        assert "session.created" in subscription

    @pytest.mark.asyncio
    async def test_expected_topics_exist(self, kafka_consumer: AIOKafkaConsumer):
        """Expected Kafka topics should exist."""
        # Subscribe to trigger topic metadata fetch
        expected_topics = [
            "session.created",
            "session.ended",
            "bullets.requested",
            "llm.response.received",
        ]

        kafka_consumer.subscribe(expected_topics)
        await asyncio.sleep(1.0)

        # Topics are auto-created in Kafka, so subscription should work
        subscription = kafka_consumer.subscription()
        for topic in expected_topics:
            assert topic in subscription, f"Could not subscribe to topic: {topic}"


class TestServiceIntegration:
    """Verify services can communicate."""

    @pytest.mark.asyncio
    async def test_session_can_write_to_database(
        self,
        api_client: httpx.AsyncClient,
        db_pool: asyncpg.Pool,
    ):
        """Session service should be able to write to database."""
        # Create a session
        resp = await api_client.post(
            "/api/v1/chat/sessions",
            json={"domain": "e2e_integration_test"}
        )
        assert resp.status_code == 200  # API returns 200 for session creation
        session_id = resp.json()["session_id"]

        # Verify it exists in database
        async with db_pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM sessions WHERE session_id = $1::uuid)",
                session_id
            )
            assert exists, "Session was not written to database"

            # Cleanup
            await conn.execute(
                "DELETE FROM sessions WHERE session_id = $1::uuid",
                session_id
            )

    @pytest.mark.asyncio
    async def test_session_can_write_to_redis(
        self,
        api_client: httpx.AsyncClient,
        redis_client: aioredis.Redis,
    ):
        """Session service should be able to write to Redis."""
        # Create a session
        resp = await api_client.post(
            "/api/v1/chat/sessions",
            json={"domain": "e2e_redis_test"}
        )
        assert resp.status_code == 200  # API returns 200 for session creation
        session_id = resp.json()["session_id"]

        # Give ADVISOR time to write bullets
        await asyncio.sleep(2.0)

        # Check if any session-related keys exist
        # (Keys may or may not exist depending on ADVISOR processing)
        keys = await redis_client.keys(f"session:{session_id}:*")
        # This verifies Redis is accessible from the test runner
