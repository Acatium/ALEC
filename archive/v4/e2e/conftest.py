"""
E2E Test Fixtures for ALEC.

These fixtures connect to the DEV environment (docker-compose.yml):
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Kafka: localhost:9092
- Session API: localhost:8008

Run with: pytest -m e2e (requires dev stack to be running)

Test Philosophy: "All correct" - tests verify behavior, not implementation.
"""

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Callable, Optional
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from aiokafka import AIOKafkaConsumer
from redis import asyncio as aioredis

# =============================================================================
# Event Loop Configuration
# =============================================================================


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for each test function (required for pytest-asyncio)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Infrastructure Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """PostgreSQL connection pool."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://alec:alec-dev-password@localhost:5432/alec"
    )
    pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=5,
        command_timeout=30
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Redis client."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = aioredis.from_url(redis_url, decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for Session API."""
    session_url = os.environ.get("SESSION_URL", "http://localhost:8008")
    async with httpx.AsyncClient(
        base_url=session_url,
        timeout=httpx.Timeout(30.0, connect=10.0)
    ) as client:
        yield client


# =============================================================================
# Kafka Consumer Fixture
# =============================================================================


@pytest_asyncio.fixture
async def kafka_consumer() -> AsyncGenerator[AIOKafkaConsumer, None]:
    """
    Kafka consumer for asserting on events.

    Each test gets its own consumer group to avoid interference.
    """
    bootstrap_servers = os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
    )
    consumer = AIOKafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=f"e2e-test-{uuid4().hex[:8]}",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        consumer_timeout_ms=1000  # Return None after 1s with no messages
    )
    await consumer.start()
    yield consumer
    await consumer.stop()


# =============================================================================
# Test Data Cleanup
# =============================================================================


@pytest_asyncio.fixture
async def clean_test_data(db_pool: asyncpg.Pool) -> AsyncGenerator[dict, None]:
    """
    Fixture that provides a unique test prefix and cleans up after the test.

    Usage:
        async def test_something(clean_test_data):
            prefix = clean_test_data["prefix"]
            # Use prefix for domain names, etc.
    """
    prefix = f"e2e_{uuid4().hex[:8]}"
    data = {
        "prefix": prefix,
        "session_ids": [],
        "bullet_ids": [],
        "cluster_ids": [],
    }

    yield data

    # Cleanup after test
    async with db_pool.acquire() as conn:
        # Delete sessions with this prefix
        await conn.execute(
            "DELETE FROM sessions WHERE domain LIKE $1",
            f"{prefix}%"
        )
        # Delete bullets with this prefix
        await conn.execute(
            "DELETE FROM playbook_bullets WHERE domain LIKE $1",
            f"{prefix}%"
        )
        # Delete clusters with this prefix
        await conn.execute(
            "DELETE FROM problem_clusters WHERE label LIKE $1",
            f"{prefix}%"
        )


# =============================================================================
# Helper Functions
# =============================================================================


async def wait_for_event(
    consumer: AIOKafkaConsumer,
    topic: str,
    filter_fn: Optional[Callable[[dict], bool]] = None,
    timeout: float = 10.0
) -> Optional[dict]:
    """
    Wait for a specific event on a Kafka topic.

    Args:
        consumer: Kafka consumer instance
        topic: Topic to subscribe to (if not already subscribed)
        filter_fn: Optional function to filter events
        timeout: Maximum time to wait in seconds

    Returns:
        The matching event, or None if timeout reached
    """
    # Ensure we're subscribed to the topic
    current_topics = consumer.subscription()
    if topic not in current_topics:
        new_topics = set(current_topics) | {topic}
        consumer.subscribe(list(new_topics))
        # Wait for partition assignment
        await asyncio.sleep(0.5)

    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        try:
            msg = await asyncio.wait_for(
                consumer.getone(),
                timeout=min(1.0, deadline - asyncio.get_event_loop().time())
            )
            if msg and msg.topic == topic:
                if filter_fn is None or filter_fn(msg.value):
                    return msg.value
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue

    return None


async def wait_for_condition(
    condition_fn: Callable[[], Any],
    timeout: float = 10.0,
    interval: float = 0.5
) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition_fn: Async function that returns truthy when condition is met
        timeout: Maximum time to wait
        interval: Time between checks

    Returns:
        True if condition was met, False if timeout
    """
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        try:
            result = await condition_fn()
            if result:
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)

    return False


# =============================================================================
# Service Health Check
# =============================================================================


@pytest_asyncio.fixture(autouse=True)
async def wait_for_services(api_client: httpx.AsyncClient):
    """Wait for session service to be healthy before each test."""
    max_retries = 10
    retry_interval = 1.0

    for i in range(max_retries):
        try:
            response = await api_client.get("/health")
            if response.status_code == 200:
                return
        except Exception:
            pass

        if i < max_retries - 1:
            await asyncio.sleep(retry_interval)

    pytest.fail("Session service not healthy")


# Make helper functions available to tests
@pytest.fixture
def wait_for_event_helper():
    """Fixture that returns the wait_for_event helper function."""
    return wait_for_event


@pytest.fixture
def wait_for_condition_helper():
    """Fixture that returns the wait_for_condition helper function."""
    return wait_for_condition
