"""
Centralized Redis key management for ALEC services.

This module provides consistent key patterns across all services that interact with Redis.
Using these constants ensures:
- Consistent key naming conventions
- Easy key pattern discovery
- Single source of truth for key formats
"""


class RedisKeys:
    """Centralized Redis key management for consistent key patterns across services."""

    # Default TTLs (in seconds)
    SESSION_TTL = 86400  # 24 hours
    EFFECTIVENESS_CACHE_TTL = 3600  # 1 hour

    @staticmethod
    def session_bullets(session_id: str) -> str:
        """Key for session's bullet list.

        Stores a JSON-encoded list of bullets for a session.
        Written by: Bullet Reflector
        Read by: Session service
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session

        Returns:
            Redis key string
        """
        return f"session:{session_id}:bullets"

    @staticmethod
    def session_user_input(session_id: str) -> str:
        """Key for session's last user input.

        Stores the most recent user message for context.
        Written by: Session service
        Read by: Reflectors
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session

        Returns:
            Redis key string
        """
        return f"session:{session_id}:last_user_input"

    @staticmethod
    def session_domain(session_id: str) -> str:
        """Key for session's classified domain.

        Stores the LLM-classified domain for the session (e.g., "python-debugging").
        Written by: Bullet Reflector
        Read by: Session service, other reflectors
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session

        Returns:
            Redis key string
        """
        return f"session:{session_id}:domain"

    @staticmethod
    def session_bullets_ready(session_id: str) -> str:
        """Key to signal bullets are ready for session.

        Set to "1" when Bullet Reflector has finished generating bullets.
        Session service polls this key to know when bullets are available.
        Written by: Bullet Reflector
        Read by: Session service
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session

        Returns:
            Redis key string
        """
        return f"session:{session_id}:bullets_ready"

    @staticmethod
    def bullet_effectiveness(bullet_id: str) -> str:
        """Key for bullet's effectiveness score cache.

        Caches the computed effectiveness score for a bullet.
        Written by: Curator (Event Persister)
        Read by: Bullet Reflector (for ranking)
        TTL: 1 hour (EFFECTIVENESS_CACHE_TTL)

        Args:
            bullet_id: UUID of the bullet

        Returns:
            Redis key string
        """
        return f"bullet:{bullet_id}:effectiveness"

    @staticmethod
    def session_turn_bullets(session_id: str, turn_number: int) -> str:
        """Key for session's bullets for a specific turn.

        Stores a JSON-encoded list of bullets for a specific turn.
        Written by: Bullet Reflector (on bullets.requested)
        Read by: Session service
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session
            turn_number: Turn number (1-indexed)

        Returns:
            Redis key string
        """
        return f"session:{session_id}:turn:{turn_number}:bullets"

    @staticmethod
    def session_turn_bullets_ready(session_id: str, turn_number: int) -> str:
        """Key to signal bullets are ready for a specific turn.

        Set to "1" when Bullet Reflector has finished generating bullets for this turn.
        Session service polls this key to know when bullets are available.
        Written by: Bullet Reflector
        Read by: Session service
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session
            turn_number: Turn number (1-indexed)

        Returns:
            Redis key string
        """
        return f"session:{session_id}:turn:{turn_number}:bullets_ready"

    @staticmethod
    def session_turn_query_embedding(session_id: str, turn_number: int) -> str:
        """Key for session's query embedding for a specific turn.

        Stores the query embedding generated during bullet selection.
        Used by Effectiveness Reflector for similarity gating.
        Written by: Bullet Reflector (on bullets.requested)
        Read by: Session service (forwarded to events), Effectiveness Reflector
        TTL: 24 hours (SESSION_TTL)

        Args:
            session_id: UUID of the session
            turn_number: Turn number (1-indexed)

        Returns:
            Redis key string
        """
        return f"session:{session_id}:turn:{turn_number}:query_embedding"

    @staticmethod
    def session_pattern(session_id: str = "*") -> str:
        """Pattern for matching all keys related to a session.

        Use with Redis KEYS or SCAN commands for cleanup operations.

        Args:
            session_id: UUID of the session, or "*" for all sessions

        Returns:
            Redis key pattern string
        """
        return f"session:{session_id}:*"
