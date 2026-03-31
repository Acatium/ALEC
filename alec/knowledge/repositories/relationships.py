"""Relationship repository — async CRUD against PostgreSQL."""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import Relationship

logger = structlog.get_logger()


class RelationshipRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self,
        engagement_id: UUID,
        from_entity: UUID,
        to_entity: UUID,
        relationship_type: str,
        evidence_id: UUID,
        confidence: float = 0.7,
    ) -> UUID:
        """Insert or update a relationship. If the triple already exists,
        append evidence and bump confidence."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO relationships
                    (engagement_id, from_entity, to_entity, relationship_type,
                     evidence, confidence)
                VALUES ($1, $2, $3, $4, ARRAY[$5::uuid], $6)
                ON CONFLICT ON CONSTRAINT uq_relationship_triple DO UPDATE
                SET evidence = array_append(relationships.evidence, $5::uuid),
                    confidence = GREATEST(relationships.confidence, $6),
                    last_confirmed = NOW()
                RETURNING relationship_id
                """,
                engagement_id,
                from_entity,
                to_entity,
                relationship_type,
                evidence_id,
                confidence,
            )
        rel_id: UUID = row["relationship_id"]
        return rel_id

    async def find_by_entity(self, engagement_id: UUID, entity_id: UUID) -> list[Relationship]:
        """Find all relationships involving an entity (as source or target)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM relationships
                WHERE engagement_id = $1
                  AND (from_entity = $2 OR to_entity = $2)
                """,
                engagement_id,
                entity_id,
            )
        return [self._row_to_relationship(r) for r in rows]

    async def list_by_engagement(self, engagement_id: UUID) -> list[Relationship]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM relationships
                WHERE engagement_id = $1
                ORDER BY last_confirmed DESC
                """,
                engagement_id,
            )
        return [self._row_to_relationship(r) for r in rows]

    @staticmethod
    def _row_to_relationship(row: asyncpg.Record) -> Relationship:
        return Relationship(
            relationship_id=row["relationship_id"],
            engagement_id=row["engagement_id"],
            from_entity=row["from_entity"],
            to_entity=row["to_entity"],
            relationship_type=row["relationship_type"],
            evidence=list(row["evidence"]) if row["evidence"] else [],
            confidence=row["confidence"],
            properties=json.loads(row["properties"]) if row["properties"] else {},
        )
