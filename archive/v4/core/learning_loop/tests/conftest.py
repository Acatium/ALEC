"""Test fixtures for Learning Loop tests.

These fixtures provide mocked dependencies for unit testing the
v3 Learning Loop services: REFLECTOR, CURATOR, CLUSTERER, ADVISOR.

v3 Architecture (Dec 2025):
- REFLECTOR: Owns feedback loop (attribution, counters, caused_failure edges, AKU extraction)
- CURATOR: Quality gate and deduplication
- CLUSTERER: Cluster assignment and solved_by edges only
- ADVISOR: Thompson Sampling selection with cluster filtering
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@dataclass
class MockBullet:
    """Mock bullet for testing."""

    bullet_id: str
    content: str
    category: str = "cheat_sheets"
    domain: str = "general"
    signal_type: str = "success"
    status: str = "candidate"
    helpful_count: int = 0
    harmful_count: int = 0
    neutral_count: int = 0
    created_at: Optional[datetime] = None
    problem_embedding: Optional[list[float]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.problem_embedding is None:
            self.problem_embedding = [0.1] * 384


@pytest.fixture
def sample_bullets():
    """Create a set of sample bullets for testing.

    Returns a mix of proven, candidate, and unvalidated bullets
    with different effectiveness scores.
    """
    now = datetime.now(timezone.utc)
    return [
        MockBullet(
            bullet_id=str(uuid4()),
            content="Use pagination offset starting at 0",
            status="candidate",
            helpful_count=5,
            harmful_count=1,
            neutral_count=2,
            created_at=now - timedelta(days=3),
        ),
        MockBullet(
            bullet_id=str(uuid4()),
            content="Check authentication before API calls",
            status="unvalidated",
            helpful_count=0,
            harmful_count=0,
            neutral_count=0,
            created_at=now - timedelta(hours=12),
        ),
        MockBullet(
            bullet_id=str(uuid4()),
            content="Use private endpoints for user-specific data",
            status="candidate",
            helpful_count=10,
            harmful_count=2,
            neutral_count=1,
            created_at=now - timedelta(days=7),
        ),
        MockBullet(
            bullet_id=str(uuid4()),
            content="Handle empty responses gracefully",
            status="unvalidated",
            helpful_count=0,
            harmful_count=0,
            neutral_count=0,
            created_at=now,
        ),
    ]


@pytest.fixture
def mock_embedding_client():
    """Mock embedding client that returns deterministic vectors."""
    client = AsyncMock()

    def generate_embedding(text: str) -> list[float]:
        """Generate a pseudo-embedding based on text hash."""
        # Use text hash to generate consistent but different embeddings
        hash_val = hash(text) % 10000
        base = [0.1] * 384
        # Modify some dimensions based on hash
        for i in range(min(len(text), 20)):
            base[i % 384] = (hash_val + ord(text[i])) / 20000
        return base

    client.embed.side_effect = generate_embedding
    return client


@pytest.fixture
def mock_database_pool():
    """Mock asyncpg connection pool."""
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def appworld_prompt():
    """Sample AppWorld-style prompt with boilerplate."""
    return """You are an AI agent that completes tasks by writing Python code.

## User Information
Name: John Smith
Email: john.smith@example.com
User ID: user_12345

## Available Apps
- Spotify: Music streaming service
- Venmo: Payment service
- Calendar: Event management

## Task
Find all playlists created by the user that contain more than 10 songs

## Additional Context
The user prefers rock music and has been using the service since 2020.
"""


@pytest.fixture
def short_prompt():
    """Short prompt without AppWorld boilerplate."""
    return "How do I sort a list in Python?"
