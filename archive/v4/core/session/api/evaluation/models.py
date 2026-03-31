"""
Pydantic models for evaluation API.

Contains request/response models for experiments, tasks, checkpoints,
comparisons, and epoch analysis.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

# =============================================================================
# Core Experiment Models
# =============================================================================

class ExperimentCreate(BaseModel):
    """Request model for creating a new experiment."""
    name: str
    experiment_type: str  # baseline, learning_curve, bullet_evolution
    dataset_split: str  # train, dev, test_normal, test_challenge
    task_limit: Optional[int] = None
    checkpoint_interval: int = 25
    turns_per_task: int = 10  # Conversation turns before giving up (0 = until success)
    grouping_strategy: str = "none"  # none, base_id, app
    specific_task_ids: Optional[List[str]] = None  # Run specific tasks instead of loading from split
    comparison_group_id: Optional[UUID] = None  # Link experiments for A/B comparison


class ExperimentSummary(BaseModel):
    """Summary view of an experiment."""
    id: UUID
    name: str
    experiment_type: str
    dataset_split: str
    status: str
    success_rate: Optional[float]
    avg_tokens: Optional[float] = None  # For cost tracking in trends
    tasks_completed: int
    tasks_total: int
    created_at: datetime
    completed_at: Optional[datetime] = None  # For filtering completed experiments
    # Assertion-level metrics
    total_assertions: int = 0
    passed_assertions: int = 0


class ExperimentDetail(BaseModel):
    """Detailed view of an experiment."""
    id: UUID
    name: str
    experiment_type: str
    dataset_split: str
    status: str
    config: dict
    success_rate: Optional[float]
    avg_iterations: Optional[float]
    avg_tokens: Optional[float]
    tasks_completed: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    tasks_total: int = 0
    # Assertion-level metrics
    total_assertions: int = 0
    passed_assertions: int = 0


class ExperimentUpdate(BaseModel):
    """Request model for updating an experiment."""
    name: Optional[str] = None


class ExperimentInfo(BaseModel):
    """Basic experiment info for comparison."""
    id: UUID
    name: str
    dataset_split: str
    tasks_completed: int


# =============================================================================
# Task Result Models
# =============================================================================

class MicroOutcomes(BaseModel):
    """Micro-outcome counts from session turns."""
    solved: int = 0
    progress: int = 0
    stuck: int = 0
    error: int = 0


class TaskResultResponse(BaseModel):
    """Response model for a single task result."""
    id: UUID
    task_id: str
    session_id: Optional[UUID]
    success: bool
    iterations: int
    tokens_used: Optional[int]
    duration_ms: Optional[int]
    error_message: Optional[str]
    test_results: Optional[dict] = None  # AppWorld ground truth (passes, failures, num_tests)
    task_description: Optional[str] = None  # Human-readable task instruction
    micro_outcomes: Optional[MicroOutcomes] = None  # Turn-level outcome breakdown
    created_at: datetime


class CheckpointResponse(BaseModel):
    """Response model for an experiment checkpoint."""
    checkpoint_number: int
    tasks_completed: int
    success_rate: float
    avg_iterations: Optional[float]
    avg_tokens: Optional[float]
    bullet_count: Optional[int]
    created_at: datetime


class ExperimentResults(BaseModel):
    """Full experiment results including tasks and checkpoints."""
    experiment: ExperimentDetail
    task_results: List[TaskResultResponse]
    checkpoints: List[CheckpointResponse]
    # Assertion-level metrics (calculated from test_results)
    total_assertions: int = 0
    passed_assertions: int = 0
    assertion_pass_rate: Optional[float] = None


# =============================================================================
# Comparison Models
# =============================================================================

class TaskComparison(BaseModel):
    """Comparison metrics for a single task across two experiments."""
    task_id: str
    task_description: Optional[str] = None
    # Experiment A results
    success_a: bool
    iterations_a: int
    tokens_a: Optional[int] = None
    # Experiment B results
    success_b: bool
    iterations_b: int
    tokens_b: Optional[int] = None
    # Deltas (B - A, positive means B is higher/worse for iterations/tokens)
    success_delta: int  # -1, 0, or 1 (1 means B succeeded where A failed)
    iterations_delta: int
    tokens_delta: Optional[int] = None


class ComparisonSummary(BaseModel):
    """Summary statistics for experiment comparison."""
    tasks_compared: int
    tasks_only_in_a: int
    tasks_only_in_b: int
    # Success rates
    success_rate_a: float
    success_rate_b: float
    success_rate_delta: float  # B - A
    # Average iterations
    avg_iterations_a: float
    avg_iterations_b: float
    avg_iterations_delta: float  # B - A
    # Average tokens
    avg_tokens_a: float
    avg_tokens_b: float
    avg_tokens_delta: float  # B - A
    # Win/loss counts
    a_wins: int  # Tasks where A succeeded and B failed
    b_wins: int  # Tasks where B succeeded and A failed
    both_succeeded: int
    both_failed: int


class StatisticalSignificance(BaseModel):
    """Statistical significance results for comparison."""
    success_rate_p_value: Optional[float] = None
    success_rate_significant: Optional[bool] = None
    iterations_p_value: Optional[float] = None
    iterations_significant: Optional[bool] = None


class ComparisonResponse(BaseModel):
    """Full comparison response between two experiments."""
    experiment_a: ExperimentInfo
    experiment_b: ExperimentInfo
    summary: ComparisonSummary
    task_comparisons: List[TaskComparison]
    statistical_significance: Optional[StatisticalSignificance] = None


# =============================================================================
# Epoch Comparison Models
# =============================================================================

class EpochInfo(BaseModel):
    """Summary of a single epoch/experiment."""
    id: UUID
    name: str
    created_at: datetime
    success_rate: Optional[float]
    avg_iterations: Optional[float]
    avg_tokens: Optional[float]
    tasks_completed: int


class TaskTrajectory(BaseModel):
    """Track a task's success across epochs."""
    task_id: str
    task_description: Optional[str]
    results: List[Optional[bool]]  # True=success, False=fail, None=not run
    first_success_epoch: Optional[int]  # Index of first success (0-based)
    pattern: str  # "improved", "regressed", "consistent_success", "consistent_failure", "intermittent"


class BulletImpact(BaseModel):
    """Track a bullet's impact across epochs."""
    bullet_id: str
    content: str
    category: str
    first_appeared_epoch: int
    tasks_improved: int
    tasks_regressed: int
    net_impact: int


class EpochsComparisonResponse(BaseModel):
    """Response for multi-epoch comparison."""
    epochs: List[EpochInfo]
    task_trajectories: List[TaskTrajectory]
    bullet_impact: List[BulletImpact]
    summary: dict
