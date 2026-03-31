"""
Runner endpoints for evaluation experiments.

Provides start, stop, results, and streaming endpoints
for experiment execution and monitoring.
"""

import json
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import docker
from core.common.observability import setup_logging

from .models import (
    CheckpointResponse,
    ExperimentDetail,
    ExperimentResults,
    MicroOutcomes,
    TaskResultResponse,
)

logger = setup_logging("evaluation-runner")

router = APIRouter()


def _get_database_url() -> str:
    """Get database URL with warning if using default dev credentials."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    logger.warning(
        "Using default dev credentials for DATABASE_URL. "
        "Set DATABASE_URL environment variable for production."
    )
    return "postgresql://alec:alec-dev-password@postgres:5432/alec"


def get_pool():
    """Get database pool from global service."""
    from core.session.main import service
    return service.pool


def _cleanup_container(container_id: Optional[str], container_name: Optional[str]) -> bool:
    """Remove a container if it exists.

    Args:
        container_id: Docker container ID
        container_name: Docker container name

    Returns:
        True if container was removed, False otherwise
    """
    try:
        client = docker.from_env()
        container = None

        # Try to find container by ID first, then by name
        for identifier in [container_id, container_name]:
            if not identifier:
                continue
            try:
                container = client.containers.get(identifier)
                break
            except docker.errors.NotFound:
                continue

        if container:
            try:
                container.remove(force=True)
                logger.info("container_cleaned_up", id=container.id[:12])
                return True
            except docker.errors.APIError as e:
                logger.warning("container_cleanup_failed", error=str(e))
                return False

        return False
    except Exception as e:
        logger.warning("container_cleanup_error", error=str(e))
        return False


async def _check_and_update_container_status(
    conn, experiment_id: UUID, container_id: str, container_name: str
) -> tuple[str, Optional[str]]:
    """Check container status and update experiment if container crashed.

    Returns:
        Tuple of (new_status, error_message)
    """
    try:
        client = docker.from_env()
        container = None

        # Try to find container by ID first, then by name
        for identifier in [container_id, container_name]:
            if not identifier:
                continue
            try:
                container = client.containers.get(identifier)
                break
            except docker.errors.NotFound:
                continue

        if container is None:
            # Container not found - it crashed and was removed or never started
            logger.warning("container_not_found_marking_failed",
                          experiment_id=str(experiment_id))
            await conn.execute(
                """
                UPDATE evaluation_experiments
                SET status = 'failed', completed_at = NOW()
                WHERE id = $1 AND status = 'running'
                """,
                experiment_id
            )
            return "failed", "Container not found - may have crashed during startup"

        # Container exists - check its status
        container.reload()
        if container.status in ["exited", "dead"]:
            # Container exited - get logs and mark as failed
            exit_code = container.attrs.get("State", {}).get("ExitCode", -1)
            try:
                logs = container.logs(tail=50).decode("utf-8", errors="replace")
            except Exception:
                logs = "Could not retrieve logs"

            error_msg = f"Container exited with code {exit_code}"
            logger.warning("container_exited_marking_failed",
                          experiment_id=str(experiment_id),
                          exit_code=exit_code,
                          logs=logs[:500])

            await conn.execute(
                """
                UPDATE evaluation_experiments
                SET status = 'failed', completed_at = NOW()
                WHERE id = $1 AND status = 'running'
                """,
                experiment_id
            )

            # Clean up the dead container
            try:
                container.remove(force=True)
            except Exception:
                pass

            return "failed", error_msg

        # Container is still running
        return "running", None

    except Exception as e:
        logger.error("container_status_check_failed", error=str(e))
        return "running", None  # Don't change status on check error


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: UUID):
    """Start a pending experiment in background."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Check experiment exists and is pending
            row = await conn.fetchrow(
                """
                SELECT id, status, config FROM evaluation_experiments
                WHERE id = $1
                """,
                experiment_id
            )

            if not row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            if row["status"] != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Experiment is {row['status']}, can only start pending experiments"
                )

            # Update status to running
            await conn.execute(
                """
                UPDATE evaluation_experiments
                SET status = 'running', started_at = NOW()
                WHERE id = $1
                """,
                experiment_id
            )

            logger.info("experiment_starting", id=str(experiment_id))

            # Launch the appworld-eval container via Docker SDK
            try:
                client = docker.from_env()
                container_name = f"appworld-eval-{str(experiment_id)[:8]}"

                # Clean up old stopped containers with same name
                try:
                    old_container = client.containers.get(container_name)
                    if old_container.status in ["exited", "dead"]:
                        old_container.remove(force=True)
                        logger.info("container_removed", name=container_name)
                except docker.errors.NotFound:
                    pass  # No old container to clean up

                # Run the appworld-eval container
                # Note: No code volume mount - evaluation code is baked into the image
                # Only mount AppWorld data volume for task data persistence
                # Note: auto_remove=False so we can inspect crashed containers
                # Labels enable easier cleanup: docker container prune --filter "label=alec.component=evaluation"
                container = client.containers.run(
                    "alec-appworld-eval:latest",
                    command=["python", "-m", "runner", "run", str(experiment_id)],
                    detach=True,
                    remove=False,  # Keep container so we can track, stop, and inspect logs
                    auto_remove=False,  # Don't auto-remove - allows log inspection on crash
                    network="alec_alec-network",
                    environment={
                        "ALEC_SESSION_URL": "http://session:8008",
                        "DATABASE_URL": _get_database_url(),
                        "KAFKA_BOOTSTRAP_SERVERS": "kafka:29092",
                        "PYTHONUNBUFFERED": "1",
                    },
                    volumes={
                        "alec_appworld-data": {"bind": "/root/.appworld", "mode": "rw"},
                    },
                    labels={
                        "alec.component": "evaluation",
                        "alec.experiment_id": str(experiment_id),
                    },
                    name=container_name,
                )
                logger.info("container_launched",
                           container_id=container.id[:12],
                           name=container_name,
                           experiment_id=str(experiment_id))

                # Store container ID and name in database for tracking
                await conn.execute(
                    """
                    UPDATE evaluation_experiments
                    SET container_id = $1, container_name = $2
                    WHERE id = $3
                    """,
                    container.id,
                    container_name,
                    experiment_id
                )
            except docker.errors.ImageNotFound:
                logger.error("appworld_image_not_found")
                await conn.execute(
                    """
                    UPDATE evaluation_experiments
                    SET status = 'pending', started_at = NULL
                    WHERE id = $1
                    """,
                    experiment_id
                )
                raise HTTPException(status_code=500, detail="Evaluation image not found. Build with: docker-compose --profile evaluation build")
            except Exception as e:
                logger.error("container_launch_failed", error=str(e))
                # Revert status back to pending
                await conn.execute(
                    """
                    UPDATE evaluation_experiments
                    SET status = 'pending', started_at = NULL
                    WHERE id = $1
                    """,
                    experiment_id
                )
                logger.error("evaluation_launch_failed", id=str(experiment_id), error=str(e), exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to launch evaluation")

            return {"message": "Experiment started", "experiment_id": str(experiment_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_start_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start experiment")


@router.post("/experiments/{experiment_id}/stop")
async def stop_experiment(experiment_id: UUID):
    """Stop a running experiment."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Check experiment exists and is running
            row = await conn.fetchrow(
                "SELECT id, status, container_id, container_name FROM evaluation_experiments WHERE id = $1",
                experiment_id
            )

            if not row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            if row["status"] != "running":
                raise HTTPException(
                    status_code=400,
                    detail=f"Experiment is {row['status']}, can only stop running experiments"
                )

            # Try to kill and remove the container
            _container_cleaned = False  # noqa: F841
            try:
                client = docker.from_env()
                container = None

                # Try by container_id first (most reliable)
                if row["container_id"]:
                    try:
                        container = client.containers.get(row["container_id"])
                    except docker.errors.NotFound:
                        logger.warning("container_not_found", id=row["container_id"][:12])

                # Fallback to container_name
                if container is None and row["container_name"]:
                    try:
                        container = client.containers.get(row["container_name"])
                    except docker.errors.NotFound:
                        logger.warning("container_not_found", name=row["container_name"])

                if container:
                    # Kill if running, then remove
                    try:
                        container.kill()
                        logger.info("container_killed", id=container.id[:12])
                    except docker.errors.APIError:
                        pass  # Container may already be stopped
                    try:
                        container.remove(force=True)
                        logger.info("container_removed", id=container.id[:12])
                        _container_cleaned = True  # noqa: F841
                    except docker.errors.APIError as e:
                        logger.warning("container_remove_failed", error=str(e))
                else:
                    logger.warning("container_not_found", experiment_id=str(experiment_id))
            except Exception as e:
                logger.warning("container_cleanup_failed", error=str(e))

            # Update status to cancelled
            await conn.execute(
                """
                UPDATE evaluation_experiments
                SET status = 'cancelled', completed_at = NOW()
                WHERE id = $1
                """,
                experiment_id
            )

            logger.info("experiment_stopped", id=str(experiment_id))

            return {"message": "Experiment stopped", "experiment_id": str(experiment_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_stop_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to stop experiment")


@router.get("/experiments/{experiment_id}/results", response_model=ExperimentResults)
async def get_experiment_results(experiment_id: UUID):
    """Get full experiment results with task details and checkpoints."""
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Get experiment detail
            exp_row = await conn.fetchrow(
                """
                SELECT id, name, experiment_type, dataset_split, status,
                       config, success_rate, avg_iterations, avg_tokens,
                       tasks_completed, tasks_total, started_at, completed_at, created_at,
                       total_assertions, passed_assertions
                FROM evaluation_experiments
                WHERE id = $1
                """,
                experiment_id
            )

            if not exp_row:
                raise HTTPException(status_code=404, detail="Experiment not found")

            # asyncpg returns JSONB columns as Python dicts directly
            config = exp_row["config"] if exp_row["config"] else {}

            experiment = ExperimentDetail(
                id=exp_row["id"],
                name=exp_row["name"],
                experiment_type=exp_row["experiment_type"],
                dataset_split=exp_row["dataset_split"],
                status=exp_row["status"],
                config=config,
                success_rate=exp_row["success_rate"],
                avg_iterations=exp_row["avg_iterations"],
                avg_tokens=exp_row["avg_tokens"],
                tasks_completed=exp_row["tasks_completed"],
                tasks_total=exp_row["tasks_total"] or 0,
                started_at=exp_row["started_at"],
                completed_at=exp_row["completed_at"],
                created_at=exp_row["created_at"],
                total_assertions=exp_row["total_assertions"] or 0,
                passed_assertions=exp_row["passed_assertions"] or 0
            )

            # Get task results
            task_rows = await conn.fetch(
                """
                SELECT id, task_id, session_id, success, iterations,
                       tokens_used, duration_ms, error_message, test_results,
                       task_description, created_at
                FROM evaluation_task_results
                WHERE experiment_id = $1
                ORDER BY created_at ASC
                """,
                experiment_id
            )

            # Get micro_outcomes for all sessions in this experiment
            session_ids = [row["session_id"] for row in task_rows if row["session_id"]]
            micro_outcomes_map: dict = {}
            if session_ids:
                outcomes_rows = await conn.fetch(
                    """
                    SELECT session_id,
                           COUNT(*) FILTER (WHERE micro_outcome = 'solved') as solved,
                           COUNT(*) FILTER (WHERE micro_outcome = 'progress') as progress,
                           COUNT(*) FILTER (WHERE micro_outcome = 'stuck') as stuck,
                           COUNT(*) FILTER (WHERE micro_outcome = 'error') as error
                    FROM session_turns
                    WHERE session_id = ANY($1::uuid[])
                    GROUP BY session_id
                    """,
                    session_ids
                )
                for orow in outcomes_rows:
                    micro_outcomes_map[orow["session_id"]] = MicroOutcomes(
                        solved=orow["solved"] or 0,
                        progress=orow["progress"] or 0,
                        stuck=orow["stuck"] or 0,
                        error=orow["error"] or 0
                    )

            task_results = []
            for row in task_rows:
                # Parse test_results if it's a JSON string (asyncpg returns JSONB as strings by default)
                test_results_value = row["test_results"]
                if isinstance(test_results_value, str):
                    test_results_value = json.loads(test_results_value)

                task_results.append(TaskResultResponse(
                    id=row["id"],
                    task_id=row["task_id"],
                    session_id=row["session_id"],
                    success=row["success"],
                    iterations=row["iterations"],
                    tokens_used=row["tokens_used"],
                    duration_ms=row["duration_ms"],
                    error_message=row["error_message"],
                    test_results=test_results_value,
                    task_description=row["task_description"],
                    micro_outcomes=micro_outcomes_map.get(row["session_id"]),
                    created_at=row["created_at"]
                ))

            # Get checkpoints
            checkpoint_rows = await conn.fetch(
                """
                SELECT checkpoint_number, tasks_completed, success_rate,
                       avg_iterations, avg_tokens, bullet_count, created_at
                FROM evaluation_checkpoints
                WHERE experiment_id = $1
                ORDER BY checkpoint_number ASC
                """,
                experiment_id
            )

            checkpoints = [
                CheckpointResponse(
                    checkpoint_number=row["checkpoint_number"],
                    tasks_completed=row["tasks_completed"],
                    success_rate=row["success_rate"],
                    avg_iterations=row["avg_iterations"],
                    avg_tokens=row["avg_tokens"],
                    bullet_count=row["bullet_count"],
                    created_at=row["created_at"]
                )
                for row in checkpoint_rows
            ]

            # Calculate assertion-level metrics from test_results
            total_assertions = 0
            passed_assertions = 0
            for task in task_results:
                if task.test_results:
                    total_assertions += task.test_results.get("num_tests", 0)
                    passed_assertions += len(task.test_results.get("passes", []))

            assertion_pass_rate = (
                passed_assertions / total_assertions if total_assertions > 0 else None
            )

            return ExperimentResults(
                experiment=experiment,
                task_results=task_results,
                checkpoints=checkpoints,
                total_assertions=total_assertions,
                passed_assertions=passed_assertions,
                assertion_pass_rate=assertion_pass_rate
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_results_failed", id=str(experiment_id), error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get experiment results")


@router.get("/experiments/{experiment_id}/stream")
async def stream_experiment_progress(experiment_id: UUID):
    """SSE stream of experiment progress."""
    pool = get_pool()

    async def event_generator():
        """Generate SSE events for experiment progress."""
        import asyncio

        last_completed = -1

        while True:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT status, tasks_completed, tasks_total,
                               success_rate, avg_iterations
                        FROM evaluation_experiments
                        WHERE id = $1
                        """,
                        experiment_id
                    )

                    if not row:
                        yield f"event: error\ndata: {json.dumps({'error': 'Experiment not found'})}\n\n"
                        break

                    # Send update if progress changed
                    if row["tasks_completed"] != last_completed:
                        last_completed = row["tasks_completed"]

                        data = {
                            "status": row["status"],
                            "tasks_completed": row["tasks_completed"],
                            "tasks_total": row["tasks_total"],
                            "success_rate": row["success_rate"],
                            "avg_iterations": row["avg_iterations"],
                            "progress": (
                                row["tasks_completed"] / row["tasks_total"]
                                if row["tasks_total"] > 0 else 0
                            )
                        }

                        yield f"event: progress\ndata: {json.dumps(data)}\n\n"

                    # Stop streaming if experiment is done
                    if row["status"] in ["completed", "failed", "cancelled"]:
                        yield f"event: complete\ndata: {json.dumps({'status': row['status']})}\n\n"
                        break

            except Exception as e:
                logger.error("stream_progress_error", error=str(e))
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                break

            # Poll every 2 seconds
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
