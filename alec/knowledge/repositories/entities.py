"""Entity repository — async CRUD against PostgreSQL."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import Entity

logger = structlog.get_logger()


class EntityRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def find_by_id(self, entity_id: UUID) -> Entity | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM entities WHERE entity_id = $1", entity_id)
        if row is None:
            return None
        return self._row_to_entity(row)

    async def find_by_name(self, engagement_id: UUID, name: str) -> Entity | None:
        """Find entity by exact name or alias match (case-insensitive)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM entities
                WHERE engagement_id = $1
                  AND (LOWER(name) = LOWER($2) OR LOWER($2) = ANY(SELECT LOWER(unnest(aliases))))
                  AND status = 'active'
                LIMIT 1
                """,
                engagement_id,
                name,
            )
        if row is None:
            return None
        return self._row_to_entity(row)

    async def create(
        self,
        engagement_id: UUID,
        name: str,
        entity_type: str,
        model_id: UUID | None = None,
        aliases: list[str] | None = None,
        embedding: list[float] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> UUID:
        """Insert a new entity and return its ID."""
        async with self._pool.acquire() as conn:
            entity_id: UUID = await conn.fetchval(
                """
                INSERT INTO entities
                    (engagement_id, model_id, name, entity_type,
                     aliases, embedding, observation_count, properties)
                VALUES ($1, $2, $3, $4, $5, $6, 1, $7)
                RETURNING entity_id
                """,
                engagement_id,
                model_id,
                name,
                entity_type,
                aliases or [],
                embedding,
                json.dumps(properties or {}),
            )
        return entity_id

    async def update_on_rediscovery(
        self,
        entity_id: UUID,
        aliases: list[str] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Update an existing entity when rediscovered."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE entities
                SET observation_count = observation_count + 1,
                    last_referenced = NOW(),
                    aliases = (
                        SELECT ARRAY(
                            SELECT DISTINCT unnest(array_cat(aliases, $1::text[]))
                        )
                    ),
                    properties = properties || $2::jsonb
                WHERE entity_id = $3
                """,
                aliases or [],
                json.dumps(properties or {}),
                entity_id,
            )

    async def find_by_normalized_prefix(
        self,
        engagement_id: UUID,
        tokens: list[str],
        limit: int = 20,
    ) -> list[Entity]:
        """Find candidate entities whose lowercased name contains any of the given tokens.

        Used as a fast pre-filter for Python-side string similarity scoring.
        """
        if not tokens:
            return []
        # Build OR conditions for each token
        conditions = " OR ".join(
            f"LOWER(name) LIKE '%' || ${i + 2} || '%'"
            for i in range(len(tokens))
        )
        query = f"""
            SELECT * FROM entities
            WHERE engagement_id = $1
              AND status = 'active'
              AND ({conditions})
            ORDER BY observation_count DESC
            LIMIT ${len(tokens) + 2}
        """  # noqa: S608
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                query,
                engagement_id,
                *tokens,
                limit,
            )
        return [self._row_to_entity(r) for r in rows]

    async def find_similar(
        self,
        engagement_id: UUID,
        embedding: list[float],
        threshold: float = 0.85,
        limit: int = 5,
    ) -> list[tuple[Entity, float]]:
        """Find entities with similar embeddings using pgvector cosine distance."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *, 1 - (embedding <=> $2::vector) AS similarity
                FROM entities
                WHERE engagement_id = $1
                  AND status = 'active'
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> $2::vector) >= $3
                ORDER BY embedding <=> $2::vector ASC
                LIMIT $4
                """,
                engagement_id,
                embedding,
                threshold,
                limit,
            )
        return [(self._row_to_entity(r), r["similarity"]) for r in rows]

    async def list_by_engagement(self, engagement_id: UUID, status: str = "active") -> list[Entity]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM entities
                WHERE engagement_id = $1 AND status = $2
                ORDER BY observation_count DESC
                """,
                engagement_id,
                status,
            )
        return [self._row_to_entity(r) for r in rows]

    @staticmethod
    def _row_to_entity(row: asyncpg.Record) -> Entity:
        return Entity(
            entity_id=row["entity_id"],
            engagement_id=row["engagement_id"],
            name=row["name"],
            entity_type=row["entity_type"],
            model_id=row["model_id"],
            aliases=list(row["aliases"]) if row["aliases"] else [],
            observation_count=row["observation_count"],
            status=row["status"],
            properties=(
                row["properties"]
                if isinstance(row["properties"], dict)
                else (
                    json.loads(row["properties"])
                    if row["properties"]
                    else {}
                )
            ),
            first_seen=row["first_seen"],
            last_referenced=row["last_referenced"],
        )
