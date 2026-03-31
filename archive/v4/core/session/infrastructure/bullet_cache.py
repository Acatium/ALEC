"""Redis bullet cache with polling and fallback (v3).

Retrieves bullets from ADVISOR via Redis, with timeout fallback to cached values.
"""

import asyncio
import json
from typing import Any, Optional

import redis.asyncio as aioredis

from core.common.observability import setup_logging


class BulletCache:
    """Redis bullet retrieval with in-memory fallback."""

    def __init__(self, redis: aioredis.Redis):
        """Initialize bullet cache.

        Args:
            redis: Redis connection.
        """
        self.redis = redis
        self.logger = setup_logging("bullet-cache")
        # In-memory fallback cache per session
        self._cache: dict[str, list[dict]] = {}

    async def get_bullets(
        self,
        session_id: str,
        turn_number: int,
        timeout_ms: int = 3000,
    ) -> tuple[list[dict], Optional[str]]:
        """Poll Redis for bullets with timeout fallback.

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            timeout_ms: Maximum time to wait for bullets (default 1.5s).

        Returns:
            Tuple of (bullets list, cluster_id or None).
        """
        ready_key = f"session:{session_id}:turn:{turn_number}:bullets_ready"
        bullets_key = f"session:{session_id}:turn:{turn_number}:bullets"

        elapsed = 0
        poll_interval = 100  # ms

        while elapsed < timeout_ms:
            try:
                # Check if bullets are ready
                ready = await self.redis.get(ready_key)
                if ready:
                    data = await self.redis.get(bullets_key)
                    if data:
                        result = json.loads(data)
                        bullets = result.get("bullets", [])
                        cluster_id = result.get("cluster_id")

                        # Update fallback cache
                        if bullets:
                            self._cache[session_id] = bullets

                        self.logger.debug(
                            "bullets_retrieved",
                            session_id=session_id,
                            turn_number=turn_number,
                            count=len(bullets),
                            source="redis",
                        )

                        return bullets, cluster_id

            except Exception as e:
                self.logger.warning(
                    "redis_poll_error",
                    session_id=session_id,
                    error=str(e),
                )

            await asyncio.sleep(poll_interval / 1000)
            elapsed += poll_interval

        # Timeout - use fallback cache
        cached = self._cache.get(session_id, [])
        self.logger.info(
            "bullets_timeout_fallback",
            session_id=session_id,
            turn_number=turn_number,
            cached_count=len(cached),
        )

        return cached, None

    async def get_bullets_fallback(self, session_id: str) -> list[dict]:
        """Get bullets from 24h fallback cache.

        Args:
            session_id: Session UUID string.

        Returns:
            Cached bullets list.
        """
        cache_key = f"session:{session_id}:bullets_cache"

        try:
            data = await self.redis.get(cache_key)
            if data:
                parsed = json.loads(data)
                bullets: list[dict[Any, Any]] = parsed.get("bullets", [])
                return bullets
        except Exception as e:
            self.logger.warning(
                "fallback_cache_error",
                session_id=session_id,
                error=str(e),
            )

        return self._cache.get(session_id, [])

    def clear_session(self, session_id: str) -> None:
        """Clear in-memory cache for a session.

        Args:
            session_id: Session UUID string.
        """
        self._cache.pop(session_id, None)
