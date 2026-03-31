"""Pytest configuration for agents service tests."""

import asyncio
import os

import pytest

# Set test environment variables
os.environ.setdefault("DATABASE_URL", "postgresql://alec:alec-dev-password@localhost:5432/alec")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
