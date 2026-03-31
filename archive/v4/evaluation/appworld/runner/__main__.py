"""Entry point for running AppWorld evaluation experiments."""

import argparse
import asyncio
import logging
import os
import sys

import asyncpg

from .experiment_runner import ExperimentConfig, ExperimentRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_existing_experiment(experiment_id: str, alec_url: str, db_url: str):
    """Run an existing experiment from the database."""
    # Fetch experiment config from database
    conn = await asyncpg.connect(db_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, name, experiment_type, dataset_split, config
            FROM evaluation_experiments
            WHERE id = $1
            """,
            experiment_id
        )

        if not row:
            logger.error(f"Experiment {experiment_id} not found")
            return 1

        import json
        config_json = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]

        config = ExperimentConfig(
            name=row["name"],
            experiment_type=row["experiment_type"],
            dataset_split=row["dataset_split"],
            task_limit=config_json.get("task_limit"),
            checkpoint_interval=config_json.get("checkpoint_interval", 25),
            turns_per_task=config_json.get("turns_per_task", 10),
            grouping_strategy=config_json.get("grouping_strategy", "none"),
        )

    finally:
        await conn.close()

    logger.info(f"Running experiment: {config.name} ({experiment_id})")
    logger.info(f"  Type: {config.experiment_type}")
    logger.info(f"  Dataset: {config.dataset_split}")

    runner = ExperimentRunner(
        alec_url=alec_url,
        db_url=db_url,
        experiment_id=experiment_id  # Use existing experiment ID
    )

    def progress_callback(completed: int, total: int, result):
        status = "✓" if result.success else "✗"
        logger.info(f"[{completed}/{total}] {status} Task {result.task_id} ({result.iterations} iterations)")

    result = await runner.run_experiment(config, progress_callback=progress_callback)

    logger.info(f"\n{'='*50}")
    logger.info(f"Experiment completed: {result.name}")
    logger.info(f"  Status: {result.status}")
    logger.info(f"  Success rate: {result.success_rate:.1%}")
    logger.info(f"  Avg iterations: {result.avg_iterations:.1f}")
    logger.info(f"  Total duration: {result.total_duration_ms / 1000:.1f}s")
    logger.info(f"{'='*50}")

    return 0 if result.status == "completed" else 1


async def create_and_run_experiment(args):
    """Create a new experiment and run it (CLI mode).

    Note: Learning is controlled via service toggles on /agents page.
    Disable learning services before running baseline experiments.
    """
    # Generate name if not provided
    name = args.name or f"{args.experiment_type.replace('_', ' ').title()} - {args.dataset}"

    config = ExperimentConfig(
        name=name,
        experiment_type=args.experiment_type,
        dataset_split=args.dataset,
        task_limit=args.task_limit,
        checkpoint_interval=args.checkpoint_interval,
        turns_per_task=args.turns_per_task,
    )

    logger.info(f"Starting experiment: {config.name}")
    logger.info(f"  Type: {config.experiment_type}")
    logger.info(f"  Dataset: {config.dataset_split}")
    logger.info("  Note: Learning controlled via /agents service toggles")

    runner = ExperimentRunner(alec_url=args.alec_url, db_url=args.db_url)

    def progress_callback(completed: int, total: int, result):
        status = "✓" if result.success else "✗"
        logger.info(f"[{completed}/{total}] {status} Task {result.task_id} ({result.iterations} iterations)")

    result = await runner.run_experiment(config, progress_callback=progress_callback)

    logger.info(f"\n{'='*50}")
    logger.info(f"Experiment completed: {result.name}")
    logger.info(f"  Status: {result.status}")
    logger.info(f"  Success rate: {result.success_rate:.1%}")
    logger.info(f"  Avg iterations: {result.avg_iterations:.1f}")
    logger.info(f"  Total duration: {result.total_duration_ms / 1000:.1f}s")
    logger.info(f"{'='*50}")

    return 0 if result.status == "completed" else 1


async def main():
    """Main entry point for the evaluation runner."""
    parser = argparse.ArgumentParser(description="Run AppWorld evaluation experiments")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run existing experiment command
    run_parser = subparsers.add_parser("run", help="Run an existing experiment by ID")
    run_parser.add_argument("experiment_id", help="UUID of the experiment to run")
    run_parser.add_argument(
        "--alec-url",
        default=os.getenv("ALEC_SESSION_URL", "http://session:8000"),
        help="ALEC session service URL",
    )
    run_parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "postgresql://alec:alec-dev-password@postgres:5432/alec"),
        help="Database URL",
    )

    # Create and run experiment command (original CLI mode)
    for exp_type in ["baseline", "learning_curve", "bullet_evolution"]:
        exp_parser = subparsers.add_parser(exp_type, help=f"Run a {exp_type} experiment")
        exp_parser.add_argument(
            "--dataset",
            default="test_normal",
            choices=["train", "dev", "test_normal", "test_challenge"],
            help="Dataset split to use",
        )
        exp_parser.add_argument(
            "--name",
            default=None,
            help="Experiment name (auto-generated if not provided)",
        )
        exp_parser.add_argument(
            "--task-limit",
            type=int,
            default=None,
            help="Limit number of tasks (default: all)",
        )
        exp_parser.add_argument(
            "--turns-per-task",
            type=int,
            default=10,
            help="Max conversation turns per task (0 = until success)",
        )
        exp_parser.add_argument(
            "--checkpoint-interval",
            type=int,
            default=25,
            help="Tasks between checkpoints",
        )
        exp_parser.add_argument(
            "--alec-url",
            default=os.getenv("ALEC_SESSION_URL", "http://session:8000"),
            help="ALEC session service URL",
        )
        exp_parser.add_argument(
            "--db-url",
            default=os.getenv("DATABASE_URL", "postgresql://alec:alec-dev-password@postgres:5432/alec"),
            help="Database URL",
        )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "run":
        return await run_existing_experiment(args.experiment_id, args.alec_url, args.db_url)
    else:
        # CLI mode - create and run
        args.experiment_type = args.command
        return await create_and_run_experiment(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
