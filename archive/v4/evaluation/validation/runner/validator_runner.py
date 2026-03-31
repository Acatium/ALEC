"""Validation runner that orchestrates learning loop validation."""

import logging
import os
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from domain.validator import LearningLoopValidator, ValidationReport

logger = logging.getLogger(__name__)


class ValidationRunner:
    """Orchestrates learning loop validation with standalone infrastructure."""

    def __init__(
        self,
        session_url: str = None,
        db_url: str = None,
        redis_url: str = None,
    ):
        """Initialize validation runner.

        Args:
            session_url: ALEC session service URL.
            db_url: PostgreSQL connection URL.
            redis_url: Redis connection URL.
        """
        self.session_url = session_url or os.getenv(
            "ALEC_SESSION_URL", "http://session:8008"
        )
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@postgres:5432/alec"
        )
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://redis:6379/0"
        )

        self._pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[aioredis.Redis] = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create the database connection pool."""
        if self._pool is None:
            logger.info(f"Creating database pool: {self.db_url.split('@')[1] if '@' in self.db_url else self.db_url}")
            self._pool = await asyncpg.create_pool(
                self.db_url,
                min_size=2,
                max_size=5,
                command_timeout=60
            )
        return self._pool

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create the Redis client."""
        if self._redis is None:
            logger.info(f"Creating Redis client: {self.redis_url}")
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True
            )
        return self._redis

    async def close(self) -> None:
        """Close all infrastructure connections."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def run_validation(
        self,
        test_message: str = "Help me understand Python list comprehensions",
    ) -> ValidationReport:
        """Run learning loop validation.

        Args:
            test_message: Message to send for validation test.

        Returns:
            ValidationReport with results.
        """
        pool = await self._get_pool()
        redis = await self._get_redis()

        logger.info(f"Running validation against session service: {self.session_url}")

        # Create validator with standalone infrastructure
        validator = LearningLoopValidator(
            db_pool=pool,
            redis_client=redis,
            kafka_producer=None,  # Standalone service doesn't need Kafka
            session_url=self.session_url,
        )

        return await validator.validate_learning_loop(test_message)

    async def get_health(self) -> dict[str, Any]:
        """Get system health status.

        Returns:
            Health report dictionary.
        """
        pool = await self._get_pool()
        redis = await self._get_redis()

        validator = LearningLoopValidator(
            db_pool=pool,
            redis_client=redis,
            kafka_producer=None,
            session_url=self.session_url,
        )

        return await validator.get_system_health()
