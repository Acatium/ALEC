"""Service toggle checker for enable/disable functionality.

Provides a cached check for whether a service is enabled.
Used by Kafka consumers to skip processing when disabled.
"""

import logging
import os
from typing import Optional, TypedDict

import asyncpg
import redis.asyncio as aioredis


class _ServiceDependencyInfo(TypedDict):
    depends_on: list[str]
    dependents: list[str]
    can_disable: bool

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Cache TTL in seconds
CACHE_TTL = 30


class ServiceToggleChecker:
    """Check if a service is enabled via Redis cache with DB fallback.

    Usage:
        checker = ServiceToggleChecker("learning-loop", redis_client, db_pool)
        if not await checker.is_enabled():
            logger.debug("Service disabled, skipping")
            return

    Behavior:
        - Checks Redis cache first (fast path)
        - Falls back to DB query if cache miss
        - Caches result for CACHE_TTL seconds
        - Fail-open: returns True if check fails (resilience)
    """

    def __init__(
        self,
        agent_name: str,
        redis_client: Optional[aioredis.Redis] = None,
        db_pool: Optional[asyncpg.Pool] = None,
    ):
        """Initialize the checker.

        Args:
            agent_name: Name of the agent/service (e.g., "learning-loop")
            redis_client: Redis client for caching
            db_pool: PostgreSQL connection pool for DB queries
        """
        self.agent_name = agent_name
        self.redis_client = redis_client
        self.db_pool = db_pool
        self._cache_key = f"service:toggle:{agent_name}"

    async def is_enabled(self) -> bool:
        """Check if the service is enabled.

        Returns:
            True if enabled (or if check fails), False if explicitly disabled
        """
        try:
            # Try Redis cache first
            if self.redis_client:
                cached = await self.redis_client.get(self._cache_key)
                if cached is not None:
                    return bool(cached == "active")

            # Cache miss - query database
            if self.db_pool:
                status = await self._query_db_status()

                # Cache the result
                if self.redis_client and status is not None:
                    await self.redis_client.setex(
                        self._cache_key, CACHE_TTL, status
                    )

                return status == "active"

            # No cache or DB - fail open (default enabled)
            logger.warning(
                f"No Redis/DB available to check toggle for {self.agent_name}, "
                f"defaulting to enabled"
            )
            return True

        except Exception as e:
            # Fail open - if check fails, assume enabled
            logger.warning(
                f"Failed to check toggle for {self.agent_name}: {e}, "
                f"defaulting to enabled"
            )
            return True

    async def _query_db_status(self) -> Optional[str]:
        """Query the database for agent status.

        Returns:
            Status string ("active", "inactive", "deprecated") or None
        """
        if self.db_pool is None:
            return None
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT status FROM agents WHERE name = $1",
                    self.agent_name
                )
                if row:
                    status: str = row["status"]
                    return status
                return None
        except Exception as e:
            logger.error(f"DB query failed for {self.agent_name}: {e}")
            return None

    async def invalidate_cache(self) -> None:
        """Invalidate the cached status (call after toggle change)."""
        try:
            if self.redis_client:
                await self.redis_client.delete(self._cache_key)
                logger.debug(f"Invalidated cache for {self.agent_name}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache for {self.agent_name}: {e}")


# Service dependencies map for cascade toggles
# NOTE: bullet-reflector, effectiveness-reflector, bullet-curator, agent-curator
# were removed in Dec 2025 (v3 Learning Loop replaces them)
SERVICE_DEPENDENCIES: dict[str, _ServiceDependencyInfo] = {
    "session": {
        "depends_on": [],
        "dependents": [],
        "can_disable": False,  # Session is always on
    },
    "learning-loop": {
        "depends_on": [],
        "dependents": [],
        "can_disable": True,  # Can disable for debugging
    },
}


def get_cascade_services(agent_name: str, action: str) -> list[str]:
    """Get list of services that should be cascaded with the action.

    Args:
        agent_name: The service being toggled
        action: "disable" or "enable"

    Returns:
        List of service names that should also be toggled
    """
    if agent_name not in SERVICE_DEPENDENCIES:
        return []

    deps = SERVICE_DEPENDENCIES[agent_name]

    if action == "disable":
        # When disabling, also disable dependents
        return deps.get("dependents", [])
    elif action == "enable":
        # When enabling, also enable dependencies (upstream services)
        return deps.get("depends_on", [])

    return []


def can_disable_service(agent_name: str) -> bool:
    """Check if a service can be disabled.

    Args:
        agent_name: The service name

    Returns:
        True if the service can be disabled
    """
    if agent_name not in SERVICE_DEPENDENCIES:
        return True  # Unknown services default to toggleable

    return SERVICE_DEPENDENCIES[agent_name].get("can_disable", True)
