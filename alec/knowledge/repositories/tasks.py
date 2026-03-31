"""Task repository — CRUD for coordinator directives."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import TaskRecord

logger = structlog.get_logger()


class TaskRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        engagement_id: UUID,
        coordinator_id: UUID | None,
        directive: str,
        source_type: str,
        source_ref: str,
        max_scope: str = "survey",
        relevant_context: str | None = None,
    ) -> UUID:
        async with self._pool.acquire() as conn:
            task_id: UUID = await conn.fetchval(
                """
                INSERT INTO tasks
                    (engagement_id, coordinator_id, directive, source_type,
                     source_ref, max_scope, relevant_context)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING task_id
                """,
                engagement_id,
                coordinator_id,
                directive,
                source_type,
                source_ref,
                max_scope,
                relevant_context,
            )
        return task_id

    async def assign(self, task_id: UUID, worker_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = 'assigned', assigned_worker = $1, started_at = NOW()
                WHERE task_id = $2
                """,
                worker_id,
                task_id,
            )

    async def start(self, task_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks SET status = 'running', started_at = NOW()
                WHERE task_id = $1
                """,
                task_id,
            )

    async def complete(self, task_id: UUID, result_summary: dict[str, Any] | None = None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = 'completed', completed_at = NOW(),
                    result_summary = $1
                WHERE task_id = $2
                """,
                json.dumps(result_summary or {}),
                task_id,
            )

    async def fail(self, task_id: UUID, error: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                SET status = 'failed', completed_at = NOW(),
                    result_summary = $1
                WHERE task_id = $2
                """,
                json.dumps({"error": error}),
                task_id,
            )

    async def find_by_id(self, task_id: UUID) -> TaskRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE task_id = $1", task_id)
        if row is None:
            return None
        return self._row_to_task(row)

    async def find_queued(self, engagement_id: UUID) -> list[TaskRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE engagement_id = $1 AND status = 'queued'
                ORDER BY created_at
                """,
                engagement_id,
            )
        return [self._row_to_task(r) for r in rows]

    @staticmethod
    def _row_to_task(row: asyncpg.Record) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            engagement_id=row["engagement_id"],
            coordinator_id=row["coordinator_id"],
            directive=row["directive"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            max_scope=row["max_scope"] or "survey",
            relevant_context=row["relevant_context"],
            status=row["status"],
            assigned_worker=row["assigned_worker"],
            result_summary=(json.loads(row["result_summary"]) if row["result_summary"] else None),
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
