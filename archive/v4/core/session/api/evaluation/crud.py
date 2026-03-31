"""
CRUD endpoints for evaluation experiments.

Provides create, list, get, update, and delete operations
for evaluation experiments.
"""

import json
from typing import Any, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query

from core.common.observability import setup_logging

from .models import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentSummary,
    ExperimentUpdate,
)

logger = setup_logging("evaluation-crud")

router = APIRouter()


def get_pool():
    """Get database pool from global service."""
    from core.session.main import service
    return service.pool


@router.post("/experiments", response_model=ExperimentSummary)
async def create_experiment(request_data: ExperimentCreate):
    """Create a new evaluation experiment (pending state)."""
    pool = get_pool()
    experiment_id = uuid4()

    # Map experiment_type to task_limit if not explicitly set
    task_limit = request_data.task_limit
    if not task_limit:
        if request_data.experiment_type == "quick_test":
            task_limit = 10
        # Other experiment types use full dataset

    config = {
        "task_limit": task_limit,
        "checkpoint_interval": request_data.checkpoint_interval,
        "turns_per_task": request_data.turns_per_task,
        "grouping_strategy": request_data.grouping_strategy,
        "specific_task_ids": request_data.specific_task_ids,
    }

    try:
        async with pool.acquire() as conn:
            # Task count will be determined by AppWorld runner
            # Use task_limit if provided, otherwise 0 (will be updated when experiment starts)
            tasks_total = task_limit or 0

            # Insert experiment
            # Note: learning_mode column deprecated - service toggles control learning now
            # Register JSON codec for this connection to handle dict→jsonb
            await conn.set_type_codec(
                'jsonb',
                encoder=json.dumps,
                decoder=json.loads,
                schema='pg_catalog'
            )

            row = await conn.fetchrow(
                """
                INSERT INTO evaluation_experiments (
                    id, name, experiment_type, dataset_split, learning_mode, status,
                    config, tasks_total, comparison_group_id, created_at
                )
                VALUES ($1, $2, $3, $4, 'disabled', 'pending', $5, $6, $7, NOW())
                RETURNING id, name, experiment_type, dataset_split, status,
                          tasks_completed, tasks_total, created_at
                """,
                experiment_id,
                request_data.name,
                request_data.experiment_type,
                request_data.dataset_split,
                config,  # Pass dict directly, codec handles conversion
                tasks_total,
                request_data.comparison_group_id
            )

            logger.info("experiment_created", id=str(experiment_id), name=request_data.name)

            return ExperimentSummary(
                id=row["id"],
                name=row["name"],
                experiment_type=row["experiment_type"],
                dataset_split=row["dataset_split"],
                status=row["status"],
                success_rate=None,
                tasks_completed=row["tasks_completed"],
                tasks_total=row["tasks_total"],
                created_at=row["created_at"]
            )

    except Exception as e:
        logger.error("experiment_create_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create experiment")


@router.get("/experiments", response_model=List[ExperimentSummary])
async def list_experiments(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """List all experiments with optional status filter."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT id, name, experiment_type, dataset_split, status,
                           success_rate, avg_tokens, tasks_completed, tasks_total,
                           created_at, completed_at, total_assertions, passed_assertions
                    FROM evaluation_experiments
                    WHERE status = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    status, limit, offset
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, name, experiment_type, dataset_split, status,
                           success_rate, avg_tokens, tasks_completed, tasks_total,
                           created_at, completed_at, total_assertions, passed_assertions
                    FROM evaluation_experiments
                    ORDER BY created_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit, offset
                )

            return [
                ExperimentSummary(
                    id=row["id"],
                    name=row["name"],
                    experiment_type=row["experiment_type"],
                    dataset_split=row["dataset_split"],
                    status=row["status"],
                    success_rate=row["success_rate"],
                    avg_tokens=row["avg_tokens"],
                    tasks_completed=row["tasks_completed"],
                    tasks_total=row["tasks_total"],
                    created_at=row["created_at"],
                    completed_at=row["completed_at"],
                    total_assertions=row["total_assertions"] or 0,
                    passed_assertions=row["passed_assertions"] or 0
                )
                for row in rows
            ]

    except Exception as e:
        logger.error("experiments_list_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list experiments")


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(experiment_id: UUID):
    """Get experiment details including progress.

    For running experiments, also checks if the container is still alive
    and marks as failed if container crashed. For completed experiments,
    cleans up any leftover containers.
    """
    from .runner import _check_and_update_container_status, _cleanup_container

    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, experiment_type, dataset_split, status,
                       config, success_rate, avg_iterations, avg_tokens,
                       tasks_completed, tasks_total, started_at, completed_at, created_at,
                       total_assertions, passed_assertions, container_id, container_name
                FROM evaluation_experiments
                WHERE id = $1
                """,
                experiment_id
            )

            if not row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            # For running experiments, check if container is still alive
            status = row["status"]
            if status == "running" and (row["container_id"] or row["container_name"]):
                status, _ = await _check_and_update_container_status(
                    conn, experiment_id, row["container_id"], row["container_name"]
                )
            # For finished experiments, clean up leftover containers
            elif status in ("completed", "failed", "cancelled") and (
                row["container_id"] or row["container_name"]
            ):
                _cleanup_container(row["container_id"], row["container_name"])

            # asyncpg returns JSONB columns as Python dicts directly
            config = row["config"] if row["config"] else {}

            return ExperimentDetail(
                id=row["id"],
                name=row["name"],
                experiment_type=row["experiment_type"],
                dataset_split=row["dataset_split"],
                status=status,  # Use potentially updated status
                config=config,
                success_rate=row["success_rate"],
                avg_iterations=row["avg_iterations"],
                avg_tokens=row["avg_tokens"],
                tasks_completed=row["tasks_completed"],
                tasks_total=row["tasks_total"] or 0,
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                total_assertions=row["total_assertions"] or 0,
                passed_assertions=row["passed_assertions"] or 0
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_get_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get experiment")


@router.patch("/experiments/{experiment_id}")
async def update_experiment(experiment_id: UUID, update: ExperimentUpdate):
    """Update an experiment's properties."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Check experiment exists
            row = await conn.fetchrow(
                "SELECT id FROM evaluation_experiments WHERE id = $1",
                experiment_id
            )

            if not row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            # Build update query dynamically based on provided fields
            updates: list[str] = []
            params: list[Any] = []
            param_idx = 1

            if update.name is not None:
                updates.append(f"name = ${param_idx}")
                params.append(update.name)
                param_idx += 1

            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")

            params.append(experiment_id)
            query = f"""
                UPDATE evaluation_experiments
                SET {', '.join(updates)}
                WHERE id = ${param_idx}
                RETURNING id, name
            """

            result = await conn.fetchrow(query, *params)
            logger.info("experiment_updated", id=str(experiment_id), name=result["name"])

            return {"id": str(result["id"]), "name": result["name"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_update_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update experiment")


@router.delete("/experiments/{experiment_id}")
async def delete_experiment(experiment_id: UUID):
    """Delete an experiment and its results."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Check experiment exists
            row = await conn.fetchrow(
                "SELECT id, status FROM evaluation_experiments WHERE id = $1",
                experiment_id
            )

            if not row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            if row["status"] == "running":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete running experiment"
                )

            # Delete in order due to foreign key constraints
            await conn.execute(
                "DELETE FROM evaluation_checkpoints WHERE experiment_id = $1",
                experiment_id
            )

            await conn.execute(
                "DELETE FROM evaluation_task_results WHERE experiment_id = $1",
                experiment_id
            )

            await conn.execute(
                "DELETE FROM evaluation_experiments WHERE id = $1",
                experiment_id
            )

            logger.info("experiment_deleted", id=str(experiment_id))

            return {"message": "Experiment deleted", "experiment_id": str(experiment_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_delete_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete experiment")
