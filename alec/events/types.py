"""Event types for the in-process event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class Event:
    """Base event type. All events are immutable."""

    event_type: str = field(init=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to JSON-safe dict."""
        result: dict[str, Any] = {}
        for f in dc_fields(self):
            val = getattr(self, f.name)
            if isinstance(val, UUID):
                result[f.name] = str(val)
            elif isinstance(val, datetime):
                result[f.name] = val.isoformat()
            else:
                result[f.name] = val
        return result


@dataclass(frozen=True)
class EngagementStarted(Event):
    event_type: str = field(init=False, default="engagement.started")
    engagement_id: UUID = field(default_factory=UUID)
    name: str = ""


@dataclass(frozen=True)
class CycleStarted(Event):
    event_type: str = field(init=False, default="cycle.started")
    engagement_id: UUID = field(default_factory=UUID)
    cycle_number: int = 0


@dataclass(frozen=True)
class CycleCompleted(Event):
    event_type: str = field(init=False, default="cycle.completed")
    engagement_id: UUID = field(default_factory=UUID)
    cycle_number: int = 0
    convergence_ratio: float = 0.0
    directives_generated: int = 0


@dataclass(frozen=True)
class WorkerDispatched(Event):
    event_type: str = field(init=False, default="worker.dispatched")
    engagement_id: UUID = field(default_factory=UUID)
    task_id: UUID = field(default_factory=UUID)
    worker_id: str = ""
    directive: str = ""


@dataclass(frozen=True)
class WorkerProgress(Event):
    event_type: str = field(init=False, default="worker.progress")
    engagement_id: UUID = field(default_factory=UUID)
    task_id: UUID = field(default_factory=UUID)
    worker_id: str = ""
    current_action: str = ""
    entities_so_far: int = 0
    observations_so_far: int = 0
    tokens_used: int = 0


@dataclass(frozen=True)
class WorkerCompleted(Event):
    event_type: str = field(init=False, default="worker.completed")
    engagement_id: UUID = field(default_factory=UUID)
    task_id: UUID = field(default_factory=UUID)
    worker_id: str = ""
    entities_written: int = 0
    relationships_written: int = 0
    observations_written: int = 0
    scope_overflow: bool = False
    error: str | None = None


@dataclass(frozen=True)
class ConvergenceReached(Event):
    event_type: str = field(init=False, default="convergence.reached")
    engagement_id: UUID = field(default_factory=UUID)
    cycle_number: int = 0
    final_ratio: float = 0.0


@dataclass(frozen=True)
class BudgetWarning(Event):
    event_type: str = field(init=False, default="budget.warning")
    engagement_id: UUID = field(default_factory=UUID)
    tokens_used: int = 0
    tokens_remaining: int = 0
    threshold_percent: int = 80


@dataclass(frozen=True)
class CommunityDetected(Event):
    event_type: str = field(init=False, default="community.detected")
    engagement_id: UUID = field(default_factory=UUID)
    cycle_number: int = 0
    community_count: int = 0
    hub_count: int = 0
    bridge_count: int = 0


@dataclass(frozen=True)
class ConsolidationStarted(Event):
    event_type: str = field(init=False, default="consolidation.started")
    engagement_id: UUID = field(default_factory=UUID)
    stale_entity_count: int = 0


@dataclass(frozen=True)
class ConsolidationCompleted(Event):
    event_type: str = field(init=False, default="consolidation.completed")
    engagement_id: UUID = field(default_factory=UUID)
    units_created: int = 0
    units_updated: int = 0
    cross_links_detected: int = 0
