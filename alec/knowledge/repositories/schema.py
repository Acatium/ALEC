"""Schema repository — CRUD for engagement_schema table."""

from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import SchemaEntry

logger = structlog.get_logger()


class SchemaRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_entity_types(
        self, engagement_id: UUID, active_only: bool = True
    ) -> list[SchemaEntry]:
        """Get entity type definitions for an engagement."""
        async with self._pool.acquire() as conn:
            query = """
                SELECT schema_entry_id, engagement_id, kind, name,
                       description, examples, parent_category, is_active
                FROM engagement_schema
                WHERE engagement_id = $1 AND kind = 'entity_type'
            """
            if active_only:
                query += " AND is_active = TRUE"
            query += " ORDER BY name"
            rows = await conn.fetch(query, engagement_id)
        return [self._row_to_entry(r) for r in rows]

    async def get_relationship_types(
        self, engagement_id: UUID, active_only: bool = True
    ) -> list[SchemaEntry]:
        """Get relationship type definitions for an engagement."""
        async with self._pool.acquire() as conn:
            query = """
                SELECT schema_entry_id, engagement_id, kind, name,
                       description, examples, parent_category, is_active
                FROM engagement_schema
                WHERE engagement_id = $1 AND kind = 'relationship_type'
            """
            if active_only:
                query += " AND is_active = TRUE"
            query += " ORDER BY name"
            rows = await conn.fetch(query, engagement_id)
        return [self._row_to_entry(r) for r in rows]

    async def get_all(
        self, engagement_id: UUID, active_only: bool = True
    ) -> list[SchemaEntry]:
        """Get all schema entries for an engagement."""
        async with self._pool.acquire() as conn:
            query = """
                SELECT schema_entry_id, engagement_id, kind, name,
                       description, examples, parent_category, is_active
                FROM engagement_schema
                WHERE engagement_id = $1
            """
            if active_only:
                query += " AND is_active = TRUE"
            query += " ORDER BY kind, name"
            rows = await conn.fetch(query, engagement_id)
        return [self._row_to_entry(r) for r in rows]

    async def add_type(
        self,
        engagement_id: UUID,
        kind: str,
        name: str,
        description: str = "",
        examples: list[str] | None = None,
        parent_category: str | None = None,
    ) -> UUID:
        """Add a type to the engagement schema. Returns the entry ID."""
        async with self._pool.acquire() as conn:
            entry_id: UUID = await conn.fetchval(
                """
                INSERT INTO engagement_schema
                    (engagement_id, kind, name, description, examples, parent_category)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (engagement_id, kind, name) DO UPDATE
                    SET description = EXCLUDED.description,
                        examples = EXCLUDED.examples,
                        parent_category = EXCLUDED.parent_category,
                        is_active = TRUE
                RETURNING schema_entry_id
                """,
                engagement_id,
                kind,
                name,
                description,
                examples or [],
                parent_category,
            )
        return entry_id

    async def deactivate_type(
        self, engagement_id: UUID, kind: str, name: str
    ) -> bool:
        """Deactivate a type. Returns True if a row was updated."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE engagement_schema
                SET is_active = FALSE
                WHERE engagement_id = $1 AND kind = $2 AND name = $3
                """,
                engagement_id,
                kind,
                name,
            )
        return bool(result != "UPDATE 0")

    async def count(self, engagement_id: UUID) -> int:
        """Count active schema entries for an engagement."""
        async with self._pool.acquire() as conn:
            count: int = await conn.fetchval(
                "SELECT COUNT(*) FROM engagement_schema "
                "WHERE engagement_id = $1 AND is_active = TRUE",
                engagement_id,
            )
            return count

    @staticmethod
    def _row_to_entry(row: asyncpg.Record) -> SchemaEntry:
        return SchemaEntry(
            schema_entry_id=row["schema_entry_id"],
            engagement_id=row["engagement_id"],
            kind=row["kind"],
            name=row["name"],
            description=row["description"],
            examples=list(row["examples"]) if row["examples"] else [],
            parent_category=row["parent_category"],
            is_active=row["is_active"],
        )
