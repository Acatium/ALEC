"""Pydantic schemas for the API layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EngagementCreate(BaseModel):
    sources: list[str]
    problem_statement: str = ""
    max_cycles: int = 3
    name: str = ""
    summary: str = ""


class EngagementResponse(BaseModel):
    engagement_id: str
    name: str
    status: str
    entity_count: int = 0
    relationship_count: int = 0
    observation_count: int = 0
    problem_statement: str = ""
    summary: str = ""
    config: dict[str, object] = {}
    created_at: str | None = None
    updated_at: str | None = None


class EntityResponse(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    observation_count: int = 0
    properties: dict[str, object] = {}


class RelationshipResponse(BaseModel):
    relationship_id: str
    from_entity: str
    to_entity: str
    relationship_type: str
    confidence: float = 0.5


class ObservationResponse(BaseModel):
    observation_id: str
    source_ref: str
    raw_text: str
    observation_type: str
    created_at: str


class GraphNode(BaseModel):
    id: str
    name: str
    entity_type: str
    observation_count: int = 0
    community_id: int | None = None
    is_hub: bool = False
    is_bridge: bool = False


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship_type: str
    confidence: float = 0.5
    from_name: str = ""
    to_name: str = ""


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    offset: int
    limit: int


# --- Task / Timeline ---


class TaskResponse(BaseModel):
    task_id: str
    directive: str
    source_type: str
    source_ref: str
    max_scope: str = "survey"
    status: str = "queued"
    assigned_worker: str | None = None
    result_summary: dict[str, object] | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# --- Convergence ---


class ConvergenceEntry(BaseModel):
    cycle_number: int
    reinforcement_count: int = 0
    expansion_count: int = 0
    challenge_count: int = 0
    ratio: float | None = None
    weighted_ratio: float | None = None


# --- Engagement Stats ---


class SourceConfigEntry(BaseModel):
    source_type: str
    config: dict[str, object] = {}
    status: str = "pending"


class EngagementStatsResponse(BaseModel):
    entity_count: int = 0
    relationship_count: int = 0
    observation_count: int = 0
    task_count: int = 0
    cycle_count: int = 0
    entity_type_breakdown: dict[str, int] = {}
    observation_type_breakdown: dict[str, int] = {}
    task_status_breakdown: dict[str, int] = {}
    convergence_history: list[ConvergenceEntry] = []
    source_configs: list[SourceConfigEntry] = []


# --- Consolidated Units ---


class ConsolidatedUnitResponse(BaseModel):
    unit_id: str
    subject_entity_id: str | None = None
    subject_entity_name: str | None = None
    summary: str
    token_count: int = 0
    version: int = 1
    freshness: str | None = None
    status: str = "current"


# --- Entity Detail ---


class EntityObservation(BaseModel):
    observation_id: str
    source_ref: str
    raw_text: str
    observation_type: str
    created_at: str


class EntityRelationship(BaseModel):
    relationship_id: str
    entity_id: str
    entity_name: str
    relationship_type: str
    confidence: float = 0.5
    direction: str  # "outgoing" or "incoming"


class EntityDetailResponse(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    aliases: list[str] = []
    observation_count: int = 0
    properties: dict[str, object] = {}
    first_seen: str | None = None
    last_referenced: str | None = None
    observations: list[EntityObservation] = []
    relationships_outgoing: list[EntityRelationship] = []
    relationships_incoming: list[EntityRelationship] = []
    consolidated_summary: str | None = None


# --- Setup Analyzer ---


class EngagementUpdate(BaseModel):
    name: str | None = None
    problem_statement: str | None = None
    summary: str | None = None


class SourceAdd(BaseModel):
    source: str  # e.g. "web:https://..." or "./docs"


class SourceUpdate(BaseModel):
    status: str | None = None  # 'verified', 'disabled'
    priority: int | None = None  # 1-100
    trust_tier: str | None = None  # 'authoritative', 'analytical', 'reference'


class SourceConfigResponse(BaseModel):
    source_config_id: str
    source_type: str
    config: dict[str, object] = {}
    status: str = "pending"
    priority: int = 50
    trust_tier: str = "reference"


class AnnotationCreate(BaseModel):
    entity_id: str
    annotation_type: str  # 'correction', 'important', 'explore_more', 'note', 'dismiss'
    content: str = ""


class AnnotationResponse(BaseModel):
    annotation_id: str
    entity_id: str
    annotation_type: str
    content: str
    created_at: str


class EntityUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None


class EntityMergeRequest(BaseModel):
    source_entity_id: str  # entity to merge FROM (will be deleted)


class DirectiveCreate(BaseModel):
    directive: str
    source_ref: str | None = None
    max_scope: str = "focused"  # survey, focused, deep


class QuestionCreate(BaseModel):
    question_text: str


class QuestionUpdate(BaseModel):
    status: str | None = None  # 'open', 'answered', 'dismissed'
    answer: str | None = None


class QuestionResponse(BaseModel):
    question_id: str
    question_text: str
    status: str
    answer: str | None = None
    created_at: str
    answered_at: str | None = None


class SnapshotCreate(BaseModel):
    name: str
    description: str = ""


class SnapshotResponse(BaseModel):
    snapshot_id: str
    name: str
    description: str
    entity_count: int
    relationship_count: int
    observation_count: int
    cycle_count: int
    convergence_ratio: float | None = None
    created_at: str


class ReportResponse(BaseModel):
    markdown: str
    title: str
    generated_at: str


class SchemaEntryResponse(BaseModel):
    schema_entry_id: str
    kind: str
    name: str
    description: str = ""
    examples: list[str] = []
    parent_category: str | None = None
    is_active: bool = True


class SchemaEntryCreate(BaseModel):
    kind: str  # 'entity_type' or 'relationship_type'
    name: str
    description: str = ""
    examples: list[str] = []
    parent_category: str | None = None


class ApplyTemplateRequest(BaseModel):
    template_id: str


class TemplateResponse(BaseModel):
    template_id: str
    name: str
    description: str
    entity_type_count: int
    relationship_type_count: int


class SchemaProposalResponse(BaseModel):
    template_base: str = "general_discovery"
    entity_types: list[dict[str, object]] = []
    relationship_types: list[dict[str, object]] = []
    reasoning: str = ""


class AnalyzeRequest(BaseModel):
    problem_statement: str
    sources: list[str]


class TopicCoverage(BaseModel):
    topic: str
    description: str = ""
    covered_by: list[str] = []
    coverage_level: str = "none"
    importance: str = "medium"


class SuggestedSource(BaseModel):
    url: str
    title: str = ""
    reason: str = ""
    covers_topics: list[str] = []
    reachable: bool = False


class AnalyzeResponse(BaseModel):
    topics: list[TopicCoverage] = []
    gaps: list[str] = []
    suggested_sources: list[SuggestedSource] = []
    search_queries: list[str] = []
    overall_assessment: str = ""
