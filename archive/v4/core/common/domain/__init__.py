"""Domain models for shared business logic across ALEC services."""

from .agent_registry import (
    AgentCapability,
    AgentInfo,
    AgentRegistry,
    agent_registry,
)
from .assessment import AssessmentRating, BulletAssessment, TaskOutcome
from .events import (
    BaseEvent,
    BulletEffectivenessEvent,
    LLMResponseReceivedEvent,
    SessionCreatedEvent,
    TaskCompletedEvent,
)
from .scoring import (
    BulletScorer,
    BulletStats,
    ScoringMethod,
    bootstrap_confidence_interval,
    dirichlet_sample,
    prob_a_better_than_b,
    wilson_confidence_interval,
)

__all__ = [
    "AgentCapability",
    "AgentInfo",
    "AgentRegistry",
    "agent_registry",
    "AssessmentRating",
    "BulletAssessment",
    "TaskOutcome",
    "BaseEvent",
    "SessionCreatedEvent",
    "LLMResponseReceivedEvent",
    "BulletEffectivenessEvent",
    "TaskCompletedEvent",
    "BulletScorer",
    "BulletStats",
    "ScoringMethod",
    "wilson_confidence_interval",
    "dirichlet_sample",
    "prob_a_better_than_b",
    "bootstrap_confidence_interval",
]
