"""Pure domain types for the knowledge layer. No DB imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


@dataclass
class Entity:
    entity_id: UUID
    engagement_id: UUID
    name: str
    entity_type: str
    model_id: UUID | None = None
    aliases: list[str] = field(default_factory=list)
    observation_count: int = 0
    status: str = "active"
    properties: dict[str, Any] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_referenced: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SchemaEntry:
    """A type definition in an engagement's dynamic ontology."""

    schema_entry_id: UUID | None = None
    engagement_id: UUID | None = None
    kind: str = ""  # 'entity_type' or 'relationship_type'
    name: str = ""
    description: str = ""
    examples: list[str] = field(default_factory=list)
    parent_category: str | None = None
    is_active: bool = True


@dataclass
class Relationship:
    relationship_id: UUID
    engagement_id: UUID
    from_entity: UUID
    to_entity: UUID
    relationship_type: str
    evidence: list[UUID] = field(default_factory=list)
    confidence: float = 0.5
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    observation_id: UUID
    engagement_id: UUID
    source_ref: str
    raw_text: str
    observation_type: str
    worker_id: str | None = None
    session_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Gap:
    """A knowledge gap detected by projection queries."""

    entity_id: UUID
    name: str
    entity_type: str
    model_id: UUID | None
    model_name: str | None
    observation_count: int
    reference_count: int
    gap_type: str  # 'unexplored_entity', 'unaligned_model', 'unsurveyed_source'


@dataclass
class Contradiction:
    """A contradiction detected between sources."""

    from_entity: UUID
    from_name: str
    to_entity: UUID
    to_name: str
    type_a: str
    type_b: str
    evidence_a: list[UUID]
    evidence_b: list[UUID]
    confidence_a: float
    confidence_b: float
    contradiction_type: str


@dataclass
class AlignmentOpp:
    """An alignment opportunity between entities in different models."""

    entity_a_id: UUID
    entity_a_name: str
    entity_a_type: str
    model_a_name: str
    model_a_purpose: str | None
    entity_b_id: UUID
    entity_b_name: str
    entity_b_type: str
    model_b_name: str
    model_b_purpose: str | None
    similarity: float


@dataclass
class RankedIssue:
    """An issue ranked for coordinator attention."""

    issue_type: str  # 'gap', 'contradiction', 'alignment_opportunity'
    score: float
    data: Gap | Contradiction | AlignmentOpp


@dataclass
class CoordinatorProjection:
    """Bounded view of the knowledge graph for one coordinator cycle."""

    problem_statement: str
    coverage_dashboard: str
    active_gaps: list[Gap]
    contradictions: list[Contradiction]
    alignment_opportunities: list[AlignmentOpp]
    recent_findings: str
    recent_decisions: str
    model_summary: str
    community_summary: str | None = None


@dataclass
class TaskRecord:
    """A worker task from the tasks table."""

    task_id: UUID
    engagement_id: UUID
    coordinator_id: UUID | None
    directive: str
    source_type: str
    source_ref: str
    max_scope: str = "survey"
    relevant_context: str | None = None
    status: str = "queued"
    assigned_worker: str | None = None
    result_summary: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class CycleStats:
    cycle_number: int
    convergence_ratio: float
    gaps_found: int
    contradictions_found: int
    directives_generated: int = 0


@dataclass
class CycleResult:
    """Result of one coordinator cycle."""

    directives: list[TaskRecord]
    convergence_signal: bool
    cycle_stats: CycleStats


@dataclass
class WorkerResult:
    """Result of one worker execution."""

    task_id: UUID
    worker_id: str
    entities_written: int
    relationships_written: int
    observations_written: int
    followups_suggested: int
    scope_overflow: bool
    error: str | None = None
    tokens_used: int = 0
    drift_detected: bool = False
    duplicate_calls_skipped: int = 0
    retries_exhausted: int = 0


@dataclass
class ConvergenceConfig:
    convergence_threshold: float = 3.0
    consecutive_cycles_required: int = 3
    novelty_decay: bool = True
    max_reinforcement_per_entity_per_cycle: int = 3
    expansion_deceleration_cycles: int = 4
    source_dominance_threshold: float = 0.6


@dataclass
class ConvergenceMetrics:
    """Multi-signal convergence measurement."""

    raw_ratio: float
    weighted_ratio: float
    expansion_rate: int
    expansion_acceleration: float
    per_source_ratios: dict[str, float]
    primary_converged: bool
    secondary_converged: bool


@dataclass
class ConsolidationConfig:
    """Configuration for the consolidation process."""

    min_new_observations: int = 20
    min_interval_minutes: int = 15
    max_interval_minutes: int = 120
    max_entities_per_run: int = 30
    co_occurrence_threshold: int = 3
    embedding_similarity_threshold: float = 0.6


@dataclass
class StaleEntity:
    """An entity that needs (re-)consolidation."""

    entity_id: UUID
    name: str
    entity_type: str
    observation_count: int
    new_observations: int
    has_existing_unit: bool


@dataclass
class ConsolidationMaterial:
    """All material gathered for one entity's consolidation."""

    entity_id: UUID
    entity_name: str
    entity_type: str
    aliases: list[str]
    properties: dict[str, Any]
    observations: list[dict[str, Any]]
    relationships_outgoing: list[dict[str, Any]]
    relationships_incoming: list[dict[str, Any]]
    alignments: list[dict[str, Any]]


@dataclass
class CrossLink:
    """A detected but unrecorded connection between two entities."""

    entity_a_id: UUID
    entity_a_name: str
    entity_b_id: UUID
    entity_b_name: str
    detection_method: str  # 'co_occurrence' or 'embedding_similarity'
    strength: float  # co-occurrence count or similarity score
    detail: str


@dataclass
class CommunityResult:
    """Result of community detection on the knowledge graph."""

    engagement_id: UUID | None = None
    cycle_number: int = 0
    algorithm: str = "louvain"
    entity_count: int = 0
    community_count: int = 0
    modularity: float | None = None
    communities: dict[int, list[str]] = field(default_factory=dict)
    hub_entities: list[str] = field(default_factory=list)
    bridge_entities: list[str] = field(default_factory=list)
    isolated_entities: list[str] = field(default_factory=list)


@dataclass
class ConsolidationResult:
    """Result of one consolidation run."""

    entities_consolidated: int
    units_created: int
    units_updated: int
    cross_links_detected: int
    cross_links_recorded: int
    errors: list[str]
