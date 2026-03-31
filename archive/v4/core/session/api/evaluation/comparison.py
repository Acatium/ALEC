"""
Comparison endpoints for evaluation experiments.

Provides experiment comparison and epoch analysis endpoints
for analyzing performance differences.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from core.common.observability import setup_logging

from .models import (
    BulletImpact,
    ComparisonResponse,
    ComparisonSummary,
    EpochInfo,
    EpochsComparisonResponse,
    ExperimentInfo,
    StatisticalSignificance,
    TaskComparison,
    TaskTrajectory,
)

logger = setup_logging("evaluation-comparison")

router = APIRouter()


def get_pool():
    """Get database pool from global service."""
    from core.session.main import service
    return service.pool


@router.get("/experiments/{experiment_id}/compare/{other_id}", response_model=ComparisonResponse)
async def compare_experiments(experiment_id: UUID, other_id: UUID):
    """Compare two experiments to analyze performance differences.

    Matches tasks by task_id and calculates comparison metrics including
    success rates, iterations, tokens, and statistical significance.
    """
    pool = get_pool()

    try:
        async with pool.acquire() as conn:
            # Fetch both experiments
            exp_a_row = await conn.fetchrow(
                """
                SELECT id, name, config, dataset_split, tasks_completed
                FROM evaluation_experiments
                WHERE id = $1
                """,
                experiment_id
            )

            exp_b_row = await conn.fetchrow(
                """
                SELECT id, name, config, dataset_split, tasks_completed
                FROM evaluation_experiments
                WHERE id = $1
                """,
                other_id
            )

            if not exp_a_row:
                raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")
            if not exp_b_row:
                raise HTTPException(status_code=404, detail=f"Experiment {other_id} not found")

            experiment_a = ExperimentInfo(
                id=exp_a_row["id"],
                name=exp_a_row["name"],
                dataset_split=exp_a_row["dataset_split"],
                tasks_completed=exp_a_row["tasks_completed"]
            )

            experiment_b = ExperimentInfo(
                id=exp_b_row["id"],
                name=exp_b_row["name"],
                dataset_split=exp_b_row["dataset_split"],
                tasks_completed=exp_b_row["tasks_completed"]
            )

            # Fetch task results for both experiments
            tasks_a = await conn.fetch(
                """
                SELECT task_id, success, iterations, tokens_used, task_description
                FROM evaluation_task_results
                WHERE experiment_id = $1
                """,
                experiment_id
            )

            tasks_b = await conn.fetch(
                """
                SELECT task_id, success, iterations, tokens_used, task_description
                FROM evaluation_task_results
                WHERE experiment_id = $1
                """,
                other_id
            )

            # Build lookup dicts by task_id
            tasks_a_dict = {row["task_id"]: row for row in tasks_a}
            tasks_b_dict = {row["task_id"]: row for row in tasks_b}

            # Find common tasks and unique tasks
            common_task_ids = set(tasks_a_dict.keys()) & set(tasks_b_dict.keys())
            only_in_a = set(tasks_a_dict.keys()) - set(tasks_b_dict.keys())
            only_in_b = set(tasks_b_dict.keys()) - set(tasks_a_dict.keys())

            # Build task comparisons for common tasks
            task_comparisons = []
            a_wins = 0
            b_wins = 0
            both_succeeded = 0
            both_failed = 0

            # Lists for statistical tests
            successes_a = []
            successes_b = []
            iterations_a_list = []
            iterations_b_list = []

            for task_id in sorted(common_task_ids):
                task_a = tasks_a_dict[task_id]
                task_b = tasks_b_dict[task_id]

                success_a = task_a["success"]
                success_b = task_b["success"]
                iterations_a = task_a["iterations"]
                iterations_b = task_b["iterations"]
                tokens_a = task_a["tokens_used"]
                tokens_b = task_b["tokens_used"]

                # Calculate success delta (-1, 0, or 1)
                if success_a and not success_b:
                    success_delta = -1  # A succeeded, B failed
                    a_wins += 1
                elif not success_a and success_b:
                    success_delta = 1  # B succeeded, A failed
                    b_wins += 1
                elif success_a and success_b:
                    success_delta = 0
                    both_succeeded += 1
                else:
                    success_delta = 0
                    both_failed += 1

                iterations_delta = iterations_b - iterations_a
                tokens_delta = (tokens_b - tokens_a) if (tokens_a is not None and tokens_b is not None) else None

                # Get task description (prefer A's, fall back to B's)
                task_description = task_a["task_description"] or task_b["task_description"]

                task_comparisons.append(TaskComparison(
                    task_id=task_id,
                    task_description=task_description,
                    success_a=success_a,
                    iterations_a=iterations_a,
                    tokens_a=tokens_a,
                    success_b=success_b,
                    iterations_b=iterations_b,
                    tokens_b=tokens_b,
                    success_delta=success_delta,
                    iterations_delta=iterations_delta,
                    tokens_delta=tokens_delta
                ))

                # Collect data for statistical tests
                successes_a.append(1 if success_a else 0)
                successes_b.append(1 if success_b else 0)
                iterations_a_list.append(iterations_a)
                iterations_b_list.append(iterations_b)

            # Calculate summary statistics
            tasks_compared = len(common_task_ids)

            if tasks_compared > 0:
                success_rate_a = sum(successes_a) / tasks_compared
                success_rate_b = sum(successes_b) / tasks_compared
                avg_iterations_a = sum(iterations_a_list) / tasks_compared
                avg_iterations_b = sum(iterations_b_list) / tasks_compared

                # Calculate average tokens
                tokens_a_values = [tc.tokens_a for tc in task_comparisons if tc.tokens_a is not None]
                tokens_b_values = [tc.tokens_b for tc in task_comparisons if tc.tokens_b is not None]
                avg_tokens_a = sum(tokens_a_values) / len(tokens_a_values) if tokens_a_values else 0.0
                avg_tokens_b = sum(tokens_b_values) / len(tokens_b_values) if tokens_b_values else 0.0
            else:
                success_rate_a = success_rate_b = 0.0
                avg_iterations_a = avg_iterations_b = 0.0
                avg_tokens_a = avg_tokens_b = 0.0

            summary = ComparisonSummary(
                tasks_compared=tasks_compared,
                tasks_only_in_a=len(only_in_a),
                tasks_only_in_b=len(only_in_b),
                success_rate_a=success_rate_a,
                success_rate_b=success_rate_b,
                success_rate_delta=success_rate_b - success_rate_a,
                avg_iterations_a=avg_iterations_a,
                avg_iterations_b=avg_iterations_b,
                avg_iterations_delta=avg_iterations_b - avg_iterations_a,
                avg_tokens_a=avg_tokens_a,
                avg_tokens_b=avg_tokens_b,
                avg_tokens_delta=avg_tokens_b - avg_tokens_a,
                a_wins=a_wins,
                b_wins=b_wins,
                both_succeeded=both_succeeded,
                both_failed=both_failed
            )

            # Calculate statistical significance (optional)
            statistical_significance = None
            if tasks_compared >= 10:
                try:
                    from scipy import stats

                    # McNemar's test for paired success/failure (better for paired binary data)
                    # Contingency table: [[both_succeeded, a_wins], [b_wins, both_failed]]
                    if a_wins + b_wins > 0:
                        mcnemar_result = stats.binomtest(
                            b_wins, a_wins + b_wins, p=0.5, alternative='two-sided'
                        )
                        success_p_value = mcnemar_result.pvalue
                    else:
                        success_p_value = 1.0

                    # Paired t-test for iterations
                    t_stat, iterations_p_value = stats.ttest_rel(iterations_a_list, iterations_b_list)

                    statistical_significance = StatisticalSignificance(
                        success_rate_p_value=success_p_value,
                        success_rate_significant=success_p_value < 0.05,
                        iterations_p_value=iterations_p_value,
                        iterations_significant=iterations_p_value < 0.05
                    )
                except ImportError:
                    # scipy not available
                    logger.debug("scipy not available for statistical tests")
                except Exception as e:
                    logger.warning("statistical_significance_failed", error=str(e))

            return ComparisonResponse(
                experiment_a=experiment_a,
                experiment_b=experiment_b,
                summary=summary,
                task_comparisons=task_comparisons,
                statistical_significance=statistical_significance
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("experiment_compare_failed", ids=[str(experiment_id), str(other_id)], error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compare experiments")


@router.get("/epochs")
async def compare_epochs(
    experiment_ids: str = Query(..., description="Comma-separated experiment IDs"),
):
    """Compare multiple experiments (epochs) chronologically.

    Args:
        experiment_ids: Comma-separated list of experiment UUIDs to compare

    Returns:
        Epoch-by-epoch comparison including task trajectories and bullet impact analysis.
    """
    try:
        # Parse experiment IDs
        id_list = [UUID(id.strip()) for id in experiment_ids.split(",") if id.strip()]
        if len(id_list) < 2:
            raise HTTPException(status_code=400, detail="At least 2 experiment IDs required")
        if len(id_list) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 experiments allowed")

        pool = get_pool()

        async with pool.acquire() as conn:
            # Fetch experiment metadata, ordered by creation time
            exp_rows = await conn.fetch("""
                SELECT id, name, created_at, success_rate, avg_iterations, avg_tokens, tasks_completed
                FROM evaluation_experiments
                WHERE id = ANY($1::uuid[])
                ORDER BY created_at
            """, id_list)

            if len(exp_rows) != len(id_list):
                found_ids = {row["id"] for row in exp_rows}
                missing = [str(id) for id in id_list if id not in found_ids]
                raise HTTPException(status_code=404, detail=f"Experiments not found: {missing}")

            epochs = [
                EpochInfo(
                    id=row["id"],
                    name=row["name"],
                    created_at=row["created_at"],
                    success_rate=row["success_rate"],
                    avg_iterations=row["avg_iterations"],
                    avg_tokens=row["avg_tokens"],
                    tasks_completed=row["tasks_completed"],
                )
                for row in exp_rows
            ]

            # Get ordered experiment IDs (by creation time)
            ordered_ids = [row["id"] for row in exp_rows]

            # Fetch all task results for these experiments
            task_rows = await conn.fetch("""
                SELECT experiment_id, task_id, success, task_description
                FROM evaluation_task_results
                WHERE experiment_id = ANY($1::uuid[])
            """, ordered_ids)

            # Build task trajectory data
            # task_id -> {experiment_id -> (success, description)}
            task_data: dict = {}
            for row in task_rows:
                task_id = row["task_id"]
                if task_id not in task_data:
                    task_data[task_id] = {"description": row["task_description"], "results": {}}
                task_data[task_id]["results"][row["experiment_id"]] = row["success"]

            # Build trajectories
            task_trajectories = []
            for task_id, data in task_data.items():
                results = [data["results"].get(exp_id) for exp_id in ordered_ids]

                # Determine first success epoch
                first_success = None
                for i, r in enumerate(results):
                    if r is True:
                        first_success = i
                        break

                # Determine pattern
                successes = [r for r in results if r is not None]
                if not successes:
                    pattern = "not_run"
                elif all(s for s in successes):
                    pattern = "consistent_success"
                elif not any(s for s in successes):
                    pattern = "consistent_failure"
                else:
                    # Check if improving or regressing
                    first_result = next((r for r in results if r is not None), None)
                    last_result = next((r for r in reversed(results) if r is not None), None)
                    if first_result is False and last_result is True:
                        pattern = "improved"
                    elif first_result is True and last_result is False:
                        pattern = "regressed"
                    else:
                        pattern = "intermittent"

                task_trajectories.append(TaskTrajectory(
                    task_id=task_id,
                    task_description=data["description"],
                    results=results,
                    first_success_epoch=first_success,
                    pattern=pattern,
                ))

            # Sort by pattern priority: improved first, then regressed, then others
            pattern_order = {"improved": 0, "regressed": 1, "intermittent": 2, "consistent_success": 3, "consistent_failure": 4, "not_run": 5}
            task_trajectories.sort(key=lambda t: (pattern_order.get(t.pattern, 99), t.task_id))

            # Bullet impact analysis (which bullets correlated with improvements/regressions)
            # This is a simplified version - tracks bullets used in each epoch
            bullet_impact: List[BulletImpact] = []

            # Summary statistics
            patterns: dict[str, int] = {}
            for t in task_trajectories:
                patterns[t.pattern] = patterns.get(t.pattern, 0) + 1

            summary = {
                "total_tasks": len(task_trajectories),
                "patterns": patterns,
                "success_rate_trend": [e.success_rate for e in epochs],
                "avg_iterations_trend": [e.avg_iterations for e in epochs],
            }

        return EpochsComparisonResponse(
            epochs=epochs,
            task_trajectories=task_trajectories,
            bullet_impact=bullet_impact,
            summary=summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("epochs_compare_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compare epochs")
