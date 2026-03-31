"""Observation repository — append-only writes against PostgreSQL."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import Observation

logger = structlog.get_logger()


class ObservationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        engagement_id: UUID,
        source_ref: str,
        raw_text: str,
        observation_type: str,
        worker_id: str | None = None,
        session_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        """Append an observation. Returns observation_id."""
        async with self._pool.acquire() as conn:
            obs_id: UUID = await conn.fetchval(
                """
                INSERT INTO observations
                    (engagement_id, session_id, worker_id, source_ref,
                     raw_text, observation_type, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING observation_id
                """,
                engagement_id,
                session_id,
                worker_id,
                source_ref,
                raw_text,
                observation_type,
                json.dumps(metadata or {}),
            )
        return obs_id

    async def find_by_engagement(
        self,
        engagement_id: UUID,
        observation_type: str | None = None,
        limit: int = 100,
    ) -> list[Observation]:
        async with self._pool.acquire() as conn:
            if observation_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM observations
                    WHERE engagement_id = $1 AND observation_type = $2
                    ORDER BY created_at DESC LIMIT $3
                    """,
                    engagement_id,
                    observation_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM observations
                    WHERE engagement_id = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    engagement_id,
                    limit,
                )
        return [self._row_to_observation(r) for r in rows]

    @staticmethod
    def _row_to_observation(row: asyncpg.Record) -> Observation:
        return Observation(
            observation_id=row["observation_id"],
            engagement_id=row["engagement_id"],
            source_ref=row["source_ref"],
            raw_text=row["raw_text"],
            observation_type=row["observation_type"],
            worker_id=row["worker_id"],
            session_id=row["session_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )
