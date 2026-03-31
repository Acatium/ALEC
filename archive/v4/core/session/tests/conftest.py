"""Shared test fixtures for SESSION v3 tests."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

# Test database URL
_default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"
)


@pytest.fixture(scope="function")
def event_loop():
    """Create a new event loop for each test function."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.ping = AsyncMock()
    redis.flushdb = AsyncMock()
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_kafka():
    """Create a mock Kafka client."""
    kafka = MagicMock()
    kafka.publish_event = AsyncMock()
    kafka.start_producer = AsyncMock()
    kafka.close = AsyncMock()
    return kafka


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=(
        "Test response from LLM",
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    ))
    client.stream = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_bullets():
    """Sample bullets in v3 format."""
    return [
        {
            "id": str(uuid4()),
            "situation": "When handling API pagination",
            "assertion": "Use offset=0 for the first page",
            "modality": "should",
            "polarity": "do",
            "score": 0.85,
        },
        {
            "id": str(uuid4()),
            "situation": "When parsing JSON responses",
            "assertion": "Check for null values before accessing nested fields",
            "modality": "must",
            "polarity": "dont",
            "score": 0.75,
        },
        {
            "id": str(uuid4()),
            "situation": "When querying user data",
            "assertion": "API rate limit is 100 requests per minute",
            "modality": "should",
            "polarity": "know",
            "score": 0.65,
        },
    ]


@pytest.fixture
def sample_history():
    """Sample conversation history."""
    return [
        {"role": "user", "content": "How do I paginate API results?"},
        {"role": "assistant", "content": "You can use offset and limit parameters."},
        {"role": "user", "content": "What's the default offset?"},
        {"role": "assistant", "content": "The default offset is usually 0."},
    ]


@pytest_asyncio.fixture
async def db_pool():
    """Create a real database connection pool for integration tests."""
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
    """Fixture to clean up test data after each test."""
    test_prefix = f"test_{uuid4().hex[:8]}"
    created_ids: dict[str, list[str]] = {
        "session_ids": [],
        "bullet_ids": [],
    }

    yield {
        "prefix": test_prefix,
        "ids": created_ids,
    }

    # Cleanup
    async with db_pool.acquire() as conn:
        if created_ids["session_ids"]:
            await conn.execute(
                "DELETE FROM session_turns WHERE session_id = ANY($1)",
                created_ids["session_ids"]
            )
            await conn.execute(
                "DELETE FROM sessions WHERE session_id = ANY($1)",
                created_ids["session_ids"]
            )

        if created_ids["bullet_ids"]:
            await conn.execute(
                "DELETE FROM playbook_bullets WHERE bullet_id = ANY($1)",
                created_ids["bullet_ids"]
            )


# Redis URL for testing - uses the dev Redis instance
_redis_host = "redis" if os.path.exists("/.dockerenv") else "localhost"
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", f"redis://{_redis_host}:6379/0")


@pytest_asyncio.fixture
async def real_redis():
    """Create a real Redis connection for integration tests.

    Uses a test-specific key prefix to avoid collisions with production data.
    Cleans up all test keys after the test completes.
    """
    import redis.asyncio as aioredis

    client = await aioredis.from_url(TEST_REDIS_URL)

    # Track keys created during test for cleanup
    test_prefix = f"test:{uuid4().hex[:8]}:"
    created_keys: list[str] = []

    class TrackedRedis:
        """Redis wrapper that tracks keys for cleanup."""

        def __init__(self, client: aioredis.Redis, prefix: str):
            self._client = client
            self._prefix = prefix
            self._keys: list[str] = created_keys

        async def get(self, key: str) -> bytes | None:
            return await self._client.get(key)

        async def set(
            self, key: str, value: str | bytes, ex: int | None = None
        ) -> bool:
            self._keys.append(key)
            return await self._client.set(key, value, ex=ex)

        async def delete(self, *keys: str) -> int:
            return await self._client.delete(*keys)

        async def ttl(self, key: str) -> int:
            return await self._client.ttl(key)

        async def ping(self) -> bool:
            return await self._client.ping()

        @property
        def prefix(self) -> str:
            return self._prefix

    tracked = TrackedRedis(client, test_prefix)

    yield tracked

    # Cleanup: delete all keys created during test
    if created_keys:
        await client.delete(*created_keys)

    await client.aclose()
