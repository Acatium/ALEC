"""Database connection helper for evaluation tracking.

This module provides database connectivity for the evaluation harness's
own tracking tables. These tables maintain architectural separation from
ALEC core services.

Key Design:
- Same PostgreSQL database, separate tables (evaluation_task_outcomes, etc.)
- Never insert into ALEC core tables (sessions, playbook_bullets, etc.)
- Only read from core tables when necessary for analysis
- Evaluation harness is a consumer, not a producer of ALEC data
"""

import json
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Database URL configuration
# Uses same database as ALEC core but accesses separate evaluation tables
EVALUATION_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://alec:alec-dev-password@postgres:5432/alec"
)


class EvaluationDatabase:
    """Database connection manager for evaluation tracking."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize database connection manager.

        Args:
            database_url: PostgreSQL connection URL. Defaults to EVALUATION_DATABASE_URL.
        """
        self.database_url = database_url or EVALUATION_DATABASE_URL
        self._pool: Optional[asyncpg.Pool] = None

    async def get_pool(self) -> asyncpg.Pool:
        """Get or create the database connection pool.

        Returns:
            asyncpg.Pool instance.
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.database_url)
            logger.info("Evaluation database pool created")
        return self._pool

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Evaluation database pool closed")

    async def record_task_outcome(
        self,
        experiment_id: str,
        task_id: str,
        session_id: str,
        success: bool,
        turns_to_success: Optional[int],
        total_turns: int,
        execution_log: Optional[dict] = None,
    ) -> None:
        """Record a task outcome to evaluation_task_outcomes table.

        Args:
            experiment_id: Experiment UUID.
            task_id: Task identifier (e.g., "024c982_2").
            session_id: Session UUID (reference only, not inserted into sessions table).
            success: Whether task succeeded.
            turns_to_success: Number of turns to success (NULL if failed).
            total_turns: Total conversation turns.
            execution_log: Optional execution history for debugging.
        """
        pool = await self.get_pool()

        # Extract problem signature from task_id (e.g., "024c982" from "024c982_2")
        problem_signature = task_id.rsplit('_', 1)[0] if '_' in task_id else task_id

        query = """
            INSERT INTO evaluation_task_outcomes (
                experiment_id, task_id, session_id, success,
                turns_to_success, total_turns, problem_signature, execution_log
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        # Serialize execution_log to JSON string for asyncpg JSONB compatibility
        execution_log_json = json.dumps(execution_log) if execution_log else None

        await pool.execute(
            query,
            experiment_id,
            task_id,
            session_id,
            success,
            turns_to_success,
            total_turns,
            problem_signature,
            execution_log_json,
        )

        logger.debug(
            f"Recorded task outcome: task={task_id}, success={success}, "
            f"turns={turns_to_success}/{total_turns}"
        )
