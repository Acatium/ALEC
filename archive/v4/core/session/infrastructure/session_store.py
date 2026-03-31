"""PostgreSQL session store (v3).

Minimal CRUD operations for sessions using asyncpg directly.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import asyncpg

from core.common.observability import setup_logging


class SessionStore:
    """PostgreSQL session CRUD operations."""

    def __init__(self, pool: asyncpg.Pool):
        """Initialize store.

        Args:
            pool: asyncpg connection pool.
        """
        self.pool = pool
        self.logger = setup_logging("session-store")

    async def create(
        self,
        session_id: UUID,
        domain: str = "general",
        metadata: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Create a new session.

        Args:
            session_id: Session UUID.
            domain: Session domain.
            metadata: Optional session metadata.

        Returns:
            Created session as dict.
        """
        now = datetime.now(timezone.utc)

        row = await self.pool.fetchrow(
            """
            INSERT INTO sessions (
                session_id, domain, status, metadata,
                message_count, created_at, updated_at
            ) VALUES ($1, $2, 'active', $3, 0, $4, $4)
            RETURNING session_id, domain, status, metadata,
                      message_count, created_at, updated_at
            """,
            session_id,
            domain,
            metadata or {},
            now,
        )

        self.logger.debug("session_created", session_id=str(session_id))

        return dict(row)

    async def get(self, session_id: UUID) -> Optional[dict[str, Any]]:
        """Get session by ID.

        Args:
            session_id: Session UUID.

        Returns:
            Session dict or None if not found.
        """
        row = await self.pool.fetchrow(
            """
            SELECT session_id, domain, status, metadata,
                   message_count, created_at, updated_at, completed_at
            FROM sessions WHERE session_id = $1
            """,
            session_id,
        )

        return dict(row) if row else None

    async def get_history(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get conversation history from session_turns.

        Args:
            session_id: Session UUID.
            limit: Maximum turns to return.

        Returns:
            List of turn dicts with user_message and assistant_response.
        """
        rows = await self.pool.fetch(
            """
            SELECT turn_id, turn_number, user_message, assistant_response, created_at
            FROM session_turns
            WHERE session_id = $1
            ORDER BY turn_number ASC
            LIMIT $2
            """,
            session_id,
            limit,
        )

        return [dict(row) for row in rows]

    async def get_turns(
        self,
        session_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get turns with full data including micro_outcome and attribution.

        Args:
            session_id: Session UUID.
            limit: Maximum turns to return.

        Returns:
            List of turn dicts with all fields.
        """
        rows = await self.pool.fetch(
            """
            SELECT turn_id, turn_number, user_message, assistant_response,
                   sub_task, micro_outcome, akus_shown, akus_helped,
                   akus_harmed, cluster_id, created_at
            FROM session_turns
            WHERE session_id = $1
            ORDER BY turn_number ASC
            LIMIT $2
            """,
            session_id,
            limit,
        )

        return [dict(row) for row in rows]

    async def list_sessions(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        bullet_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List sessions with optional filters.

        Args:
            status: Filter by status.
            domain: Filter by domain.
            bullet_id: Filter by sessions that used this bullet.
            limit: Maximum sessions to return.
            offset: Pagination offset.

        Returns:
            Tuple of (sessions list, total count).
        """
        # Build WHERE clause
        conditions: list[str] = []
        params: list[Any] = []
        param_idx = 1

        if status:
            conditions.append(f"s.status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if domain:
            conditions.append(f"s.domain = ${param_idx}")
            params.append(domain)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Subquery for micro_outcomes aggregation
        outcomes_subquery = """
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE micro_outcome = 'solved') as solved,
                    COUNT(*) FILTER (WHERE micro_outcome = 'progress') as progress,
                    COUNT(*) FILTER (WHERE micro_outcome = 'stuck') as stuck,
                    COUNT(*) FILTER (WHERE micro_outcome = 'error') as error
                FROM session_turns st
                WHERE st.session_id = s.session_id
            ) mo ON true
        """

        # If bullet_id filter, use JOIN
        if bullet_id:
            query = f"""
                SELECT DISTINCT s.session_id, s.domain, s.status, s.metadata,
                       s.message_count, s.created_at, s.updated_at,
                       EXTRACT(EPOCH FROM (s.updated_at - s.created_at)) * 1000 as duration_ms,
                       mo.solved, mo.progress, mo.stuck, mo.error
                FROM sessions s
                JOIN session_turns st ON s.session_id = st.session_id
                {outcomes_subquery}
                WHERE ${param_idx} = ANY(st.akus_shown)
                {" AND " + " AND ".join(conditions) if conditions else ""}
                ORDER BY s.updated_at DESC
                LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
            """
            params = [bullet_id] + params + [limit, offset]

            count_query = f"""
                SELECT COUNT(DISTINCT s.session_id)
                FROM sessions s
                JOIN session_turns st ON s.session_id = st.session_id
                WHERE ${1} = ANY(st.akus_shown)
                {" AND " + " AND ".join([c.replace(f"${i+2}", f"${i+2}") for i, c in enumerate(conditions)]) if conditions else ""}
            """
            count_params: list[Any] = [bullet_id] + params[:len(conditions)]
        else:
            query = f"""
                SELECT s.session_id, s.domain, s.status, s.metadata,
                       s.message_count, s.created_at, s.updated_at,
                       EXTRACT(EPOCH FROM (s.updated_at - s.created_at)) * 1000 as duration_ms,
                       mo.solved, mo.progress, mo.stuck, mo.error
                FROM sessions s
                {outcomes_subquery}
                {where_clause}
                ORDER BY s.updated_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])

            count_query = f"SELECT COUNT(*) FROM sessions s {where_clause}"
            count_params = params[:len(conditions)]

        rows = await self.pool.fetch(query, *params)
        count_row = await self.pool.fetchval(count_query, *count_params) if count_params else await self.pool.fetchval(count_query)

        return [dict(row) for row in rows], count_row or 0

    async def increment_message_count(self, session_id: UUID) -> Optional[int]:
        """Increment message count for session.

        Args:
            session_id: Session UUID.

        Returns:
            New message count or None if not found.
        """
        row = await self.pool.fetchrow(
            """
            UPDATE sessions
            SET message_count = message_count + 1,
                updated_at = $2
            WHERE session_id = $1
            RETURNING message_count
            """,
            session_id,
            datetime.now(timezone.utc),
        )

        return row["message_count"] if row else None

    async def complete(
        self,
        session_id: UUID,
        status: str,
        reason: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Complete a session.

        Args:
            session_id: Session UUID.
            status: New status ('completed' or 'failed').
            reason: Optional reason for completion.

        Returns:
            Updated session dict or None if not found.
        """
        now = datetime.now(timezone.utc)

        row = await self.pool.fetchrow(
            """
            UPDATE sessions
            SET status = $2,
                completed_at = $3,
                updated_at = $3,
                metadata = metadata || $4
            WHERE session_id = $1
            RETURNING session_id, domain, status, metadata,
                      message_count, created_at, updated_at, completed_at
            """,
            session_id,
            status,
            now,
            {"completion_reason": reason} if reason else {},
        )

        if row:
            self.logger.info(
                "session_completed",
                session_id=str(session_id),
                status=status,
            )

        return dict(row) if row else None

    async def save_turn(
        self,
        session_id: UUID,
        turn_number: int,
        user_message: str,
        assistant_response: str,
        akus_shown: list[UUID],
    ) -> UUID:
        """Save a conversation turn.

        Args:
            session_id: Session UUID.
            turn_number: Turn number.
            user_message: User's message.
            assistant_response: Assistant's response.
            akus_shown: UUIDs of AKUs shown in this turn.

        Returns:
            Turn UUID.
        """
        row = await self.pool.fetchrow(
            """
            INSERT INTO session_turns (
                session_id, turn_number, user_message, assistant_response,
                akus_shown, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING turn_id
            """,
            session_id,
            turn_number,
            user_message,
            assistant_response,
            akus_shown,
            datetime.now(timezone.utc),
        )

        assert row is not None, "Failed to insert turn"
        turn_id: UUID = row["turn_id"]
        return turn_id

    async def get_bullets_used(
        self,
        session_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get all bullets used in a session.

        Args:
            session_id: Session UUID.

        Returns:
            List of bullet dicts with usage info.
        """
        rows = await self.pool.fetch(
            """
            SELECT DISTINCT a.aku_id, a.situation, a.assertion,
                   a.helpful_count, a.harmful_count, a.neutral_count, a.status
            FROM session_turns st
            JOIN akus a ON a.aku_id = ANY(st.akus_shown)
            WHERE st.session_id = $1
            """,
            session_id,
        )

        return [dict(row) for row in rows]
