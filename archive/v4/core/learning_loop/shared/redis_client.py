"""Redis client for learning loop services.

Primarily used by ADVISOR to write selected bullets for session consumption.
"""

import json
import logging
import os
from collections import defaultdict
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Bullet categories for cognitive organization
BULLET_CATEGORIES = ["cheat_sheets", "constraints", "examples", "meta_prompts", "solutions"]

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
BULLET_TTL_SECONDS = 24 * 60 * 60  # 24 hours


class RedisClient:
    """Redis client for bullet storage and retrieval."""

    def __init__(self, url: str = REDIS_URL):
        """Initialize Redis client.

        Args:
            url: Redis connection URL.
        """
        self.url = url
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client is not None:
            return

        self._client = redis.from_url(self.url, decode_responses=True)
        # Test connection
        await self._client.ping()
        logger.info("Connected to Redis")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Disconnected from Redis")

    async def _ensure_connected(self) -> redis.Redis:
        """Ensure connection exists and return client."""
        if self._client is None:
            await self.connect()
        assert self._client is not None, "Redis client not connected"
        return self._client

    def _convert_to_ace_format(
        self,
        bullets: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Convert flat bullet list to ACE dict format.

        Session service expects bullets organized by ACE category:
        {"cheat_sheets": [...], "constraints": [...], etc.}

        Args:
            bullets: Flat list of bullet dicts with "category" field.

        Returns:
            Dict keyed by ACE category.
        """
        ace_bullets: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for bullet in bullets:
            category = bullet.get("category", "cheat_sheets")
            # Normalize category name
            if category not in BULLET_CATEGORIES:
                category = "cheat_sheets"
            ace_bullets[category].append(bullet)

        # Ensure all ACE categories exist (empty lists if needed)
        result = {cat: ace_bullets.get(cat, []) for cat in BULLET_CATEGORIES}
        return result

    async def write_turn_bullets(
        self,
        session_id: str,
        turn_number: int,
        bullets: list[dict[str, Any]],
    ) -> None:
        """Write bullets for a specific turn.

        Args:
            session_id: Session UUID.
            turn_number: Turn number.
            bullets: List of bullet dictionaries.
        """
        client = await self._ensure_connected()

        # Per-turn key for fresh selection
        turn_key = f"session:{session_id}:turn:{turn_number}:bullets"
        ready_key = f"session:{session_id}:turn:{turn_number}:bullets_ready"

        # Also update session-level cache for fallback
        session_key = f"session:{session_id}:bullets"

        pipe = client.pipeline()

        # Convert flat list to ACE dict format for Session compatibility
        ace_bullets = self._convert_to_ace_format(bullets)

        # Write per-turn bullets (Session expects ACE dict format)
        pipe.set(turn_key, json.dumps(ace_bullets), ex=BULLET_TTL_SECONDS)

        # Set ready signal
        pipe.set(ready_key, "1", ex=BULLET_TTL_SECONDS)

        # Update session-level cache
        if bullets:
            pipe.set(session_key, json.dumps(ace_bullets), ex=BULLET_TTL_SECONDS)

        await pipe.execute()

        logger.debug(
            f"Wrote {len(bullets)} bullets for session={session_id}, turn={turn_number}"
        )

    async def get_turn_bullets(
        self,
        session_id: str,
        turn_number: int,
    ) -> Optional[list[dict[str, Any]]]:
        """Get bullets for a specific turn.

        Args:
            session_id: Session UUID.
            turn_number: Turn number.

        Returns:
            List of bullets or None if not found.
        """
        client = await self._ensure_connected()

        turn_key = f"session:{session_id}:turn:{turn_number}:bullets"
        data = await client.get(turn_key)

        if data:
            result: list[dict[str, Any]] = json.loads(data)
            return result
        return None

    async def is_turn_ready(
        self,
        session_id: str,
        turn_number: int,
    ) -> bool:
        """Check if bullets are ready for a turn.

        Args:
            session_id: Session UUID.
            turn_number: Turn number.

        Returns:
            True if bullets are ready.
        """
        client = await self._ensure_connected()

        ready_key = f"session:{session_id}:turn:{turn_number}:bullets_ready"
        exists_result = await client.exists(ready_key)
        return bool(exists_result > 0)

    async def get_session_bullets(
        self,
        session_id: str,
    ) -> Optional[list[dict[str, Any]]]:
        """Get session-level cached bullets (fallback).

        Args:
            session_id: Session UUID.

        Returns:
            List of bullets or None if not found.
        """
        client = await self._ensure_connected()

        session_key = f"session:{session_id}:bullets"
        data = await client.get(session_key)

        if data:
            result: list[dict[str, Any]] = json.loads(data)
            return result
        return None

    async def write_hybrid_params(
        self,
        session_id: str,
        alpha: float,
        beta: float,
    ) -> None:
        """Store hybrid retrieval parameters used for a session.

        Used for Thompson Sampling feedback - when task completes, we
        look up which parameters were used and update their success/failure counts.

        Args:
            session_id: Session UUID.
            alpha: Vector similarity weight used.
            beta: Cluster similarity weight used.
        """
        client = await self._ensure_connected()

        params_key = f"session:{session_id}:hybrid_params"
        params_data = json.dumps({"alpha": alpha, "beta": beta})

        # Store with same TTL as bullets
        await client.set(params_key, params_data, ex=BULLET_TTL_SECONDS)

        logger.debug(f"Stored hybrid params for session={session_id[:8]}...: α={alpha}, β={beta}")

    async def get_hybrid_params(
        self,
        session_id: str,
    ) -> Optional[tuple[float, float]]:
        """Get hybrid retrieval parameters used for a session.

        Args:
            session_id: Session UUID.

        Returns:
            Tuple of (alpha, beta) or None if not found.
        """
        client = await self._ensure_connected()

        params_key = f"session:{session_id}:hybrid_params"
        data = await client.get(params_key)

        if data:
            params = json.loads(data)
            return (params.get("alpha", 0.7), params.get("beta", 0.3))
        return None

    # =========================================================================
    # Turn Buffer Methods (for GENERATOR conversation accumulation)
    # =========================================================================
    # These methods buffer llm.response.received events for a session.
    # On session.ended, GENERATOR reads the buffer to get full conversation.
    # This replaces the broken session_events DB query approach.
    # =========================================================================

    async def buffer_turn(
        self,
        session_id: str,
        turn_data: dict[str, Any],
    ) -> int:
        """Buffer a turn for later processing by GENERATOR.

        Appends turn data to a Redis list for the session.
        Called when llm.response.received events arrive.

        Args:
            session_id: Session UUID.
            turn_data: Turn data dict with keys:
                - turn_number: int
                - user_message: str (extracted from messages)
                - assistant_response: str
                - bullets_used: list[dict]
                - problem_context: str

        Returns:
            Current buffer length after append.
        """
        client = await self._ensure_connected()

        buffer_key = f"session:{session_id}:turn_buffer"
        turn_json = json.dumps(turn_data)

        # RPUSH to maintain order (oldest first)
        length: int = await client.rpush(buffer_key, turn_json)  # type: ignore[misc]

        # Set TTL on first push
        if length == 1:
            await client.expire(buffer_key, BULLET_TTL_SECONDS)

        logger.debug(
            f"Buffered turn {turn_data.get('turn_number', '?')} for session "
            f"{session_id[:8]}... (buffer_len={length})"
        )
        return int(length)

    async def get_buffered_turns(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Get all buffered turns for a session.

        Called by GENERATOR when session.ended arrives.

        Args:
            session_id: Session UUID.

        Returns:
            List of turn dicts, ordered by arrival (oldest first).
        """
        client = await self._ensure_connected()

        buffer_key = f"session:{session_id}:turn_buffer"
        turns_json: list[Any] = await client.lrange(buffer_key, 0, -1)  # type: ignore[misc]

        turns = []
        for turn_json in turns_json:
            try:
                turns.append(json.loads(turn_json))
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in turn buffer for {session_id[:8]}...")

        # Sort by turn_number to ensure order
        turns.sort(key=lambda t: t.get("turn_number", 0))

        logger.debug(f"Retrieved {len(turns)} buffered turns for session {session_id[:8]}...")
        return turns

    async def get_buffer_length(
        self,
        session_id: str,
    ) -> int:
        """Get the number of buffered turns for a session.

        Used to check if all expected turns have arrived before processing.

        Args:
            session_id: Session UUID.

        Returns:
            Number of buffered turns.
        """
        client = await self._ensure_connected()

        buffer_key = f"session:{session_id}:turn_buffer"
        result: int = await client.llen(buffer_key)  # type: ignore[misc]
        return result

    async def delete_turn_buffer(
        self,
        session_id: str,
    ) -> None:
        """Delete the turn buffer for a session.

        Called after GENERATOR finishes processing to clean up.

        Args:
            session_id: Session UUID.
        """
        client = await self._ensure_connected()

        buffer_key = f"session:{session_id}:turn_buffer"
        await client.delete(buffer_key)

        logger.debug(f"Deleted turn buffer for session {session_id[:8]}...")

    # =========================================================================
    # Semantic Context Pipeline (Dec 2025)
    # =========================================================================
    # ADVISOR computes semantic context (task extraction, embedding, cluster match)
    # and stores it in Redis. GENERATOR reads this context to pass to REFLECTOR
    # for game-aware attribution. This eliminates semantic drift between services.
    # =========================================================================

    async def write_semantic_context(
        self,
        session_id: str,
        turn_number: int,
        context: dict[str, Any],
    ) -> None:
        """Store ADVISOR's semantic context for GENERATOR to consume.

        The semantic context includes:
        - extracted_task: Clean task text (boilerplate removed)
        - task_embedding: 384-dim vector (stored as JSON list)
        - nearest_cluster_id: UUID of matched cluster (or None)
        - nearest_cluster_label: Human-readable label
        - cluster_similarity: How well task matched cluster (0-1)
        - retrieval_path: "vector", "cluster", "vector+cluster", or "cold_start"

        Args:
            session_id: Session UUID.
            turn_number: Turn number (typically 1 for initial context).
            context: Semantic context dict from ADVISOR.
        """
        client = await self._ensure_connected()

        context_key = f"session:{session_id}:turn:{turn_number}:semantic_context"

        # Store with same TTL as bullets
        await client.set(context_key, json.dumps(context), ex=BULLET_TTL_SECONDS)

        logger.debug(
            f"Wrote semantic context for session={session_id[:8]}..., turn={turn_number}, "
            f"cluster={context.get('nearest_cluster_label', 'none')}"
        )

    async def get_semantic_context(
        self,
        session_id: str,
        turn_number: int = 1,
    ) -> Optional[dict[str, Any]]:
        """Get ADVISOR's semantic context for GENERATOR.

        Args:
            session_id: Session UUID.
            turn_number: Turn number to read (default 1 for initial context).

        Returns:
            Semantic context dict or None if not found.
        """
        client = await self._ensure_connected()

        context_key = f"session:{session_id}:turn:{turn_number}:semantic_context"
        data = await client.get(context_key)

        if data:
            try:
                result: dict[str, Any] = json.loads(data)
                return result
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in semantic context for {session_id[:8]}...")
                return None
        return None

    async def get_session_semantic_context(
        self,
        session_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get the first available semantic context for a session.

        Scans turns 1-5 looking for semantic context. Useful when GENERATOR
        doesn't know which turn ADVISOR stored context on.

        Args:
            session_id: Session UUID.

        Returns:
            Semantic context dict or None if not found.
        """
        for turn in range(1, 6):
            context = await self.get_semantic_context(session_id, turn)
            if context:
                return context
        return None
