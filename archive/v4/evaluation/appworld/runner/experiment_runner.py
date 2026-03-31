"""Experiment runner for orchestrating AppWorld evaluation experiments."""

import json
import logging
import os
import subprocess

# Import evaluation database for outcome tracking
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import asyncpg

from .alec_client import ALECClient
from .task_runner import TaskResult, TaskRunner

sys.path.insert(0, '/app/evaluation')
from database.connection import EvaluationDatabase

logger = logging.getLogger(__name__)

# Default LLM model - should match gateway_llm_manager.py
DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"


def json_serializer(obj: Any) -> str:
    """Custom JSON serializer for UUID and datetime objects.

    Args:
        obj: Object to serialize

    Returns:
        JSON string
    """
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@dataclass
class ExperimentConfig:
    """Configuration for an experiment run.

    Note: Learning is controlled via service toggles on /agents page,
    not per-request parameters. Disable learning services before running
    baseline experiments.
    """

    name: str
    experiment_type: str  # baseline, learning_curve, bullet_evolution
    dataset_split: str  # train, dev, test_normal, test_challenge
    task_limit: Optional[int] = None
    checkpoint_interval: int = 25
    turns_per_task: int = 25  # Conversation turns before giving up (0 = until success)
    grouping_strategy: str = "none"  # none, base_id, app
    specific_task_ids: Optional[list[str]] = None  # Run specific tasks instead of loading from split
    baseline_bullets: Optional[list[str]] = None  # Optional fixed bullets for baseline experiments


@dataclass
class ExperimentResult:
    """Result from running a complete experiment."""

    experiment_id: str
    name: str
    experiment_type: str
    status: str
    task_results: list[TaskResult]
    success_rate: float
    avg_iterations: float
    avg_tokens: float
    total_duration_ms: int
    started_at: datetime
    completed_at: datetime


# Type alias for progress callback
ProgressCallback = Callable[[int, int, TaskResult], None]


class ExperimentRunner:
    """Orchestrates running multiple AppWorld tasks as an experiment."""

    def __init__(
        self,
        alec_url: str = "http://localhost:8008",
        db_url: str = "postgresql://alec:alec-dev-password@localhost:5432/alec",
        experiment_id: Optional[str] = None,
    ):
        """Initialize experiment runner.

        Args:
            alec_url: Base URL for the ALEC session service.
            db_url: PostgreSQL connection URL for storing results.
            experiment_id: Optional existing experiment ID (for UI-created experiments).
        """
        self.alec_url = alec_url
        self.db_url = db_url
        self.experiment_id = experiment_id  # Use existing ID if provided
        self._pool: Optional[asyncpg.Pool] = None
        self._eval_db: Optional[EvaluationDatabase] = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create the database connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.db_url)
        return self._pool

    async def _get_eval_db(self) -> EvaluationDatabase:
        """Get or create the evaluation database connection."""
        if self._eval_db is None:
            self._eval_db = EvaluationDatabase(self.db_url)
            await self._eval_db.get_pool()  # Initialize the pool
        return self._eval_db

    async def _complete_session(
        self,
        session_id: str,
        result: TaskResult,
    ) -> None:
        """Complete session via SESSION API (emits session.ended event).

        This routes session completion through SESSION, which properly emits
        session.ended to Kafka for REFLECTOR to consume and process.

        Args:
            session_id: Session ID from ALEC.
            result: Task result with success/failure.
        """
        try:
            async with ALECClient(base_url=self.alec_url) as client:
                await client.complete_session(
                    session_id=session_id,
                    success=result.success,
                    reason="task_completed" if result.success else result.error_message,
                )
            logger.debug(f"Completed session via API: session={session_id[:8]}..., success={result.success}")
        except Exception as e:
            logger.warning(f"Failed to complete session via API: {e}")

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash.

        Returns:
            Git commit hash (40 characters) or None if not in a git repo.
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:40]
        except Exception as e:
            logger.debug(f"Could not get git commit: {e}")
        return None

    def _capture_environment_snapshot(self) -> dict[str, Any]:
        """Capture environment configuration for reproducibility.

        Returns:
            Dict containing environment variables and system info.
        """
        return {
            # Service URLs
            "alec_url": self.alec_url,
            "llm_gateway_url": os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:8000"),
            "database_url": self.db_url.split("@")[-1] if "@" in self.db_url else "masked",  # Mask credentials

            # LLM configuration
            "llm_model": os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL),

            # System info
            "python_version": os.popen("python --version 2>&1").read().strip(),
            "hostname": os.getenv("HOSTNAME", "unknown"),
        }

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._eval_db:
            await self._eval_db.close()
            self._eval_db = None

    async def _record_task_outcome(
        self,
        experiment_id: str,
        result: TaskResult,
    ) -> None:
        """Record task outcome to evaluation tracking table.

        Args:
            experiment_id: Parent experiment identifier.
            result: Task execution result.
        """
        try:
            eval_db = await self._get_eval_db()

            # Calculate turns to success (NULL if failed)
            turns_to_success = result.iterations if result.success else None

            # Build execution log for debugging
            execution_log = {
                "success": result.success,
                "iterations": result.iterations,
                "tokens_used": result.tokens_used,
                "duration_ms": result.duration_ms,
                "error_message": result.error_message,
                "test_results": result.test_results,
            }

            await eval_db.record_task_outcome(
                experiment_id=experiment_id,
                task_id=result.task_id,
                session_id=result.session_id or "unknown",
                success=result.success,
                turns_to_success=turns_to_success,
                total_turns=result.iterations,
                execution_log=execution_log,
            )

            logger.debug(
                f"Recorded outcome: task={result.task_id}, success={result.success}, "
                f"turns={turns_to_success}/{result.iterations}"
            )

        except Exception as e:
            # Non-critical: log error but don't raise
            logger.warning(f"Failed to record task outcome: {e}")

    # NOTE: session.ended events are emitted via SESSION API (_complete_session).
    # This triggers REFLECTOR for turn analysis and counter attribution.

    async def run_experiment(
        self,
        config: ExperimentConfig,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExperimentResult:
        """Run an experiment with the given configuration.

        Args:
            config: Experiment configuration.
            progress_callback: Optional callback for progress updates.

        Returns:
            ExperimentResult with aggregated metrics and individual task results.
        """
        # Use existing experiment ID or generate new one
        experiment_id = self.experiment_id or str(uuid4())
        started_at = datetime.utcnow()
        task_results: list[TaskResult] = []

        try:
            # Load task IDs from AppWorld dataset or use specific task IDs
            task_ids = await self._load_task_ids(
                config.dataset_split,
                config.task_limit,
                config.specific_task_ids
            )

            # Apply grouping strategy for cross-session learning
            if config.grouping_strategy == "base_id":
                task_ids = self._group_tasks_by_base_id(task_ids)
                logger.info("Grouped tasks by base_id for cross-session learning")
            elif config.grouping_strategy == "app":
                task_ids = self._group_tasks_by_app(task_ids)
                logger.info("Grouped tasks by app for domain-specific learning")

            if not task_ids:
                logger.warning(f"No tasks found for dataset split: {config.dataset_split}")
                if self.experiment_id:
                    await self._update_experiment_status(experiment_id, "failed", datetime.utcnow())
                return ExperimentResult(
                    experiment_id=experiment_id,
                    name=config.name,
                    experiment_type=config.experiment_type,
                    status="failed",
                    task_results=[],
                    success_rate=0.0,
                    avg_iterations=0.0,
                    avg_tokens=0.0,
                    total_duration_ms=0,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                )

            # Save experiment record or update existing one
            if self.experiment_id:
                # Update tasks_total for existing experiment
                await self._update_experiment_tasks_total(experiment_id, len(task_ids))
            else:
                # Create new experiment record
                await self._save_experiment(experiment_id, config, "running")

            # Create task runner
            # Note: Learning is controlled via service toggles on /agents page
            runner = TaskRunner(
                alec_url=self.alec_url,
                turns_per_task=config.turns_per_task,
                experiment_name=f"alec_eval_{experiment_id[:8]}",
            )

            # Run tasks sequentially
            for i, task_id in enumerate(task_ids):
                logger.info(
                    f"Running task {i + 1}/{len(task_ids)}: {task_id}"
                )

                try:
                    result = await runner.run_task(task_id)
                    task_results.append(result)

                    # Save task result to database
                    await self._save_task_result(experiment_id, result)

                    # Record task outcome to evaluation tracking table
                    await self._record_task_outcome(experiment_id, result)

                    # Complete session via SESSION API (emits session.ended for REFLECTOR)
                    await self._complete_session(result.session_id, result)

                    # Update tasks_completed in experiment table for real-time progress
                    await self._update_experiment_progress(experiment_id, i + 1, task_results)

                    # Call progress callback if provided
                    if progress_callback:
                        try:
                            progress_callback(i + 1, len(task_ids), result)
                        except Exception as e:
                            logger.warning(f"Progress callback error: {e}")

                    # Save checkpoint if interval reached
                    if (i + 1) % config.checkpoint_interval == 0:
                        checkpoint_num = (i + 1) // config.checkpoint_interval
                        await self._save_checkpoint(
                            experiment_id, checkpoint_num, i + 1, task_results
                        )
                        logger.info(
                            f"Saved checkpoint {checkpoint_num} at task {i + 1}"
                        )

                except Exception as e:
                    # Log error but continue with next task
                    logger.error(f"Task {task_id} failed with error: {e}")
                    error_result = TaskResult(
                        task_id=task_id,
                        session_id="",
                        success=False,
                        iterations=0,
                        tokens_used=0,
                        duration_ms=0,
                        error_message=str(e),
                    )
                    task_results.append(error_result)
                    await self._save_task_result(experiment_id, error_result)

                    # NOTE: No task.completed event for exceptions - no session_id available
                    # These are harness-level errors (task never ran), not agent failures

                    # Record failed task outcome
                    await self._record_task_outcome(experiment_id, error_result)

            # Calculate aggregate statistics
            completed_at = datetime.utcnow()
            success_count = sum(1 for r in task_results if r.success)
            success_rate = success_count / len(task_results) if task_results else 0.0

            total_iterations = sum(r.iterations for r in task_results)
            avg_iterations = total_iterations / len(task_results) if task_results else 0.0

            total_tokens = sum(r.tokens_used for r in task_results)
            avg_tokens = total_tokens / len(task_results) if task_results else 0.0

            total_duration_ms = sum(r.duration_ms for r in task_results)

            # Calculate assertion-level statistics
            total_assertions = 0
            passed_assertions = 0
            for r in task_results:
                if r.test_results:
                    total_assertions += r.test_results.get("num_tests", 0)
                    passed_assertions += len(r.test_results.get("passes", []))

            # Update experiment status to completed with final metrics
            await self._update_experiment_completed(
                experiment_id, "completed", completed_at,
                success_rate, avg_iterations, avg_tokens, len(task_results),
                total_assertions, passed_assertions
            )

            return ExperimentResult(
                experiment_id=experiment_id,
                name=config.name,
                experiment_type=config.experiment_type,
                status="completed",
                task_results=task_results,
                success_rate=success_rate,
                avg_iterations=avg_iterations,
                avg_tokens=avg_tokens,
                total_duration_ms=total_duration_ms,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as e:
            logger.error(f"Experiment {experiment_id} failed: {e}")
            await self._update_experiment_status(
                experiment_id, "failed", datetime.utcnow()
            )
            raise

    async def _load_task_ids(
        self,
        dataset_split: str,
        task_limit: Optional[int],
        specific_task_ids: Optional[list[str]] = None
    ) -> list[str]:
        """Load task IDs from AppWorld dataset or use specific task IDs.

        Args:
            dataset_split: The dataset split to load (train, dev, test_normal, test_challenge).
            task_limit: Optional limit on number of tasks.
            specific_task_ids: Optional list of specific task IDs to run instead of loading from split.

        Returns:
            List of task IDs.
        """
        # Use specific task IDs if provided (ignores dataset_split for loading)
        if specific_task_ids:
            task_ids = specific_task_ids
            if task_limit:
                task_ids = task_ids[:task_limit]
            logger.info(f"Using {len(task_ids)} specific task IDs")
            return task_ids

        try:
            # Import AppWorld to get task list
            from appworld.task import load_task_ids

            task_ids = load_task_ids(dataset_split)

            if task_limit:
                task_ids = task_ids[:task_limit]

            logger.info(f"Loaded {len(task_ids)} tasks from {dataset_split}")
            return task_ids

        except ImportError:
            logger.error("AppWorld not installed. Install with: pip install appworld")
            return []
        except Exception as e:
            logger.error(f"Failed to load task IDs: {e}")
            return []

    def _group_tasks_by_base_id(self, task_ids: list[str]) -> list[str]:
        """Group tasks by base ID to keep variants together for cross-session learning.

        Task IDs follow pattern: {base_id}_{variant} (e.g., 024c982_1, 024c982_2)
        Groups variants so bullets learned from variant 1 inform variant 2.

        Args:
            task_ids: List of task IDs.

        Returns:
            Reordered list with variants grouped together.
        """
        from collections import defaultdict

        groups: dict[str, list[str]] = defaultdict(list)

        for task_id in task_ids:
            # Extract base_id from task_id (format: base_id_variant)
            parts = task_id.rsplit('_', 1)
            base_id = parts[0] if len(parts) > 1 else task_id
            groups[base_id].append(task_id)

        # Flatten while preserving group order (sort by first task appearance)
        result = []
        seen_bases = []
        for task_id in task_ids:
            parts = task_id.rsplit('_', 1)
            base_id = parts[0] if len(parts) > 1 else task_id
            if base_id not in seen_bases:
                seen_bases.append(base_id)
                result.extend(sorted(groups[base_id]))

        logger.info(f"Grouped {len(task_ids)} tasks into {len(seen_bases)} base groups")
        return result

    def _group_tasks_by_app(self, task_ids: list[str]) -> list[str]:
        """Group tasks by detected app for domain-specific learning.

        Detects app from task instruction text and groups tasks by app.

        Args:
            task_ids: List of task IDs.

        Returns:
            Reordered list with tasks grouped by app.
        """
        from collections import defaultdict

        app_groups: dict[str, list[str]] = defaultdict(list)

        for task_id in task_ids:
            try:
                # Try to load task specs to detect app
                from appworld.task import load_task
                task = load_task(task_id)
                instruction = task.instruction.lower() if hasattr(task, 'instruction') else ""

                # Detect app from instruction
                app = self._detect_app(instruction)
                app_groups[app].append(task_id)
            except Exception:
                # If can't load task, put in 'other' group
                app_groups['other'].append(task_id)

        # Flatten in consistent app order
        app_order = ['venmo', 'spotify', 'amazon', 'gmail', 'todoist',
                     'simple_note', 'phone', 'file_system', 'other']

        result = []
        for app in app_order:
            if app in app_groups:
                result.extend(app_groups[app])
                logger.debug(f"App '{app}': {len(app_groups[app])} tasks")

        # Add any remaining apps not in the predefined order
        for app in app_groups:
            if app not in app_order:
                result.extend(app_groups[app])
                logger.debug(f"App '{app}': {len(app_groups[app])} tasks")

        logger.info(f"Grouped {len(task_ids)} tasks by app into {len(app_groups)} groups")
        return result

    def _detect_app(self, instruction: str) -> str:
        """Detect which app a task involves from instruction text.

        Args:
            instruction: Task instruction text (lowercase).

        Returns:
            Detected app name.
        """
        patterns = {
            'venmo': ['venmo'],
            'spotify': ['spotify', 'playlist', 'song'],
            'amazon': ['amazon', 'order', 'purchase'],
            'gmail': ['gmail', 'email', 'inbox'],
            'todoist': ['todoist', 'task', 'todo'],
            'simple_note': ['simple note', 'simplenote', 'note'],
            'phone': ['phone', 'message', 'sms', 'call'],
            'file_system': ['file', 'folder', 'directory', 'documents', 'downloads'],
        }

        for app, keywords in patterns.items():
            for keyword in keywords:
                if keyword in instruction:
                    return app

        return 'other'

    def _flatten_bullets(
        self, bullets: Optional[dict[str, list[str]]]
    ) -> list[str]:
        """Flatten bullet dict into a list.

        Args:
            bullets: Dict mapping categories to bullet lists.

        Returns:
            Flattened list of all bullets.
        """
        if not bullets:
            return []

        flattened = []
        for category_bullets in bullets.values():
            flattened.extend(category_bullets)

        return flattened

    async def _save_experiment(
        self, experiment_id: str, config: ExperimentConfig, status: str
    ) -> None:
        """Save experiment record to database with full reproducibility info.

        Args:
            experiment_id: Unique experiment identifier.
            config: Experiment configuration.
            status: Current status (pending, running, completed, failed).
        """
        pool = await self._get_pool()

        # Capture environment for reproducibility
        env_snapshot = self._capture_environment_snapshot()
        git_commit = self._get_git_commit()

        # Extended config includes all reproducibility-relevant settings
        config_json = json.dumps({
            "task_limit": config.task_limit,
            "checkpoint_interval": config.checkpoint_interval,
            "turns_per_task": config.turns_per_task,
            "baseline_bullets": config.baseline_bullets,
            "grouping_strategy": config.grouping_strategy,
            "specific_task_ids": config.specific_task_ids,
        })

        # Note: learning_mode column deprecated - service toggles control learning now
        query = """
            INSERT INTO evaluation_experiments (
                id, name, experiment_type, dataset_split, learning_mode,
                config, status, started_at,
                llm_model, llm_gateway_url, evaluation_mode, codebase_commit,
                environment_snapshot
            ) VALUES ($1, $2, $3, $4, 'disabled', $5, $6, $7, $8, $9, $10, $11, $12)
        """

        await pool.execute(
            query,
            experiment_id,
            config.name,
            config.experiment_type,
            config.dataset_split,
            config_json,
            status,
            datetime.utcnow(),
            env_snapshot.get("llm_model"),
            env_snapshot.get("llm_gateway_url"),
            env_snapshot.get("evaluation_mode"),
            git_commit,
            json.dumps(env_snapshot),
        )

    async def _update_experiment_status(
        self, experiment_id: str, status: str, completed_at: datetime
    ) -> None:
        """Update experiment status in database.

        Args:
            experiment_id: Unique experiment identifier.
            status: New status.
            completed_at: Completion timestamp.
        """
        pool = await self._get_pool()

        query = """
            UPDATE evaluation_experiments
            SET status = $2, completed_at = $3
            WHERE id = $1
        """

        await pool.execute(query, experiment_id, status, completed_at)

    async def _update_experiment_completed(
        self,
        experiment_id: str,
        status: str,
        completed_at: datetime,
        success_rate: float,
        avg_iterations: float,
        avg_tokens: float,
        tasks_completed: int,
        total_assertions: int = 0,
        passed_assertions: int = 0,
    ) -> None:
        """Update experiment with final metrics.

        Args:
            experiment_id: Unique experiment identifier.
            status: Final status.
            completed_at: Completion timestamp.
            success_rate: Final success rate.
            avg_iterations: Average iterations per task.
            avg_tokens: Average tokens per task.
            tasks_completed: Total tasks completed.
            total_assertions: Total number of assertions across all tasks.
            passed_assertions: Number of passed assertions.
        """
        pool = await self._get_pool()

        query = """
            UPDATE evaluation_experiments
            SET status = $2, completed_at = $3, success_rate = $4,
                avg_iterations = $5, avg_tokens = $6, tasks_completed = $7,
                total_assertions = $8, passed_assertions = $9
            WHERE id = $1
        """

        await pool.execute(
            query, experiment_id, status, completed_at,
            success_rate, avg_iterations, avg_tokens, tasks_completed,
            total_assertions, passed_assertions
        )

    async def _update_experiment_tasks_total(
        self, experiment_id: str, tasks_total: int
    ) -> None:
        """Update experiment tasks_total in database.

        Args:
            experiment_id: Unique experiment identifier.
            tasks_total: Total number of tasks to run.
        """
        pool = await self._get_pool()

        query = """
            UPDATE evaluation_experiments
            SET tasks_total = $2
            WHERE id = $1
        """

        await pool.execute(query, experiment_id, tasks_total)

    async def _update_experiment_progress(
        self, experiment_id: str, tasks_completed: int, task_results: list
    ) -> None:
        """Update experiment progress in database for real-time UI updates.

        Args:
            experiment_id: Unique experiment identifier.
            tasks_completed: Number of tasks completed so far.
            task_results: List of task results for calculating running metrics.
        """
        pool = await self._get_pool()

        # Calculate running success rate
        success_count = sum(1 for r in task_results if r.success)
        success_rate = success_count / len(task_results) if task_results else 0.0

        query = """
            UPDATE evaluation_experiments
            SET tasks_completed = $2, success_rate = $3
            WHERE id = $1
        """

        await pool.execute(query, experiment_id, tasks_completed, success_rate)

    async def _save_task_result(
        self, experiment_id: str, result: TaskResult
    ) -> None:
        """Save individual task result to database.

        Args:
            experiment_id: Parent experiment identifier.
            result: Task execution result.
        """
        pool = await self._get_pool()

        bullets_json = json.dumps(result.bullets_used) if result.bullets_used else None
        test_results_json = json.dumps(result.test_results) if result.test_results else None

        query = """
            INSERT INTO evaluation_task_results (
                experiment_id, task_id, session_id, success, iterations,
                tokens_used, duration_ms, bullets_used, error_message, test_results,
                task_description
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """

        session_id = result.session_id if result.session_id else None

        await pool.execute(
            query,
            experiment_id,
            result.task_id,
            session_id,
            result.success,
            result.iterations,
            result.tokens_used,
            result.duration_ms,
            bullets_json,
            result.error_message,
            test_results_json,
            result.task_description,
        )

    async def _save_checkpoint(
        self,
        experiment_id: str,
        checkpoint_num: int,
        tasks_completed: int,
        results: list[TaskResult],
    ) -> None:
        """Save experiment checkpoint to database.

        Args:
            experiment_id: Parent experiment identifier.
            checkpoint_num: Checkpoint sequence number.
            tasks_completed: Number of tasks completed at checkpoint.
            results: Results up to this checkpoint.
        """
        pool = await self._get_pool()

        # Calculate checkpoint statistics
        success_count = sum(1 for r in results if r.success)
        success_rate = success_count / len(results) if results else 0.0

        total_iterations = sum(r.iterations for r in results)
        avg_iterations = total_iterations / len(results) if results else 0.0

        total_tokens = sum(r.tokens_used for r in results)
        avg_tokens = total_tokens / len(results) if results else 0.0

        # Count unique bullets used
        all_bullets = set()
        for r in results:
            if r.bullets_used:
                for category_bullets in r.bullets_used.values():
                    if isinstance(category_bullets, list):
                        all_bullets.update(category_bullets)
        bullet_count = len(all_bullets)

        query = """
            INSERT INTO evaluation_checkpoints (
                experiment_id, checkpoint_number, tasks_completed,
                success_rate, avg_iterations, avg_tokens, bullet_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """

        await pool.execute(
            query,
            experiment_id,
            checkpoint_num,
            tasks_completed,
            success_rate,
            avg_iterations,
            avg_tokens,
            bullet_count,
        )
