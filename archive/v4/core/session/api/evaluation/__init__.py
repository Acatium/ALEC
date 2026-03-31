"""
Evaluation API module.

Re-exports combined router from sub-modules for backward compatibility.
"""

from fastapi import APIRouter

from .comparison import router as comparison_router
from .crud import router as crud_router
from .runner import router as runner_router

# Create combined router
router = APIRouter(tags=["evaluation"])

# Include all sub-routers
router.include_router(crud_router)
router.include_router(runner_router)
router.include_router(comparison_router)

# Re-export models for convenience (must be after router creation)
from .models import (  # noqa: E402
    BulletImpact,
    CheckpointResponse,
    ComparisonResponse,
    ComparisonSummary,
    EpochInfo,
    EpochsComparisonResponse,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentInfo,
    ExperimentResults,
    ExperimentSummary,
    ExperimentUpdate,
    MicroOutcomes,
    StatisticalSignificance,
    TaskComparison,
    TaskResultResponse,
    TaskTrajectory,
)

__all__ = [
    "router",
    # Models
    "ExperimentCreate",
    "ExperimentSummary",
    "ExperimentDetail",
    "ExperimentUpdate",
    "ExperimentInfo",
    "MicroOutcomes",
    "TaskResultResponse",
    "CheckpointResponse",
    "ExperimentResults",
    "TaskComparison",
    "ComparisonSummary",
    "StatisticalSignificance",
    "ComparisonResponse",
    "EpochInfo",
    "TaskTrajectory",
    "BulletImpact",
    "EpochsComparisonResponse",
]
