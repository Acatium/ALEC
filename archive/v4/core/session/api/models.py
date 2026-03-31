"""Pydantic models for API requests and responses (v3).

Preserves exact contracts from v2 for evaluation compatibility.
"""

from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request to send a message in a chat session."""
    session_id: Optional[UUID] = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class ChatResponse(BaseModel):
    """Response from chat endpoint.

    CRITICAL: This contract is used by evaluation/appworld/runner/alec_client.py
    Do not modify field names without updating alec_client.py
    """
    session_id: UUID
    message: str
    timestamp: datetime
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
    bullets_used: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Bullets used in this turn's LLM call"
    )


class SessionCreate(BaseModel):
    """Request to create a new session."""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """Response containing session information.

    CRITICAL: This contract is used by evaluation/appworld/runner/alec_client.py
    """
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    status: str
    message_count: int
    token_usage: Optional[TokenUsage] = None


class SessionMicroOutcomes(BaseModel):
    """Micro-outcome counts from session turns."""
    solved: int = 0
    progress: int = 0
    stuck: int = 0
    error: int = 0


class SessionMetadata(BaseModel):
    """Metadata for a chat session."""
    session_id: UUID
    user_id: Optional[str] = None
    title: Optional[str] = None
    domain: str = "general"
    playbook_id: Optional[UUID] = None
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    token_usage: Optional[TokenUsage] = None
    duration_ms: Optional[float] = None
    micro_outcomes: Optional[SessionMicroOutcomes] = None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """Response for listing sessions with pagination."""
    sessions: List[SessionMetadata]
    total: int
    limit: int
    offset: int


class SessionCompleteRequest(BaseModel):
    """Request to complete a session."""
    status: Literal["completed", "failed"]
    reason: Optional[str] = None


class MessageResponse(BaseModel):
    """Response containing a single message."""
    id: UUID
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionHistoryResponse(BaseModel):
    """Response containing session history."""
    session_id: UUID
    title: str | None = None
    domain: str | None = None
    status: str
    message_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict | None = None
    messages: list[MessageResponse]
    total_messages: int
    token_usage: Optional[TokenUsage] = None


class TurnResponse(BaseModel):
    """Response containing turn data with micro-outcome."""
    turn_id: UUID
    turn_number: int
    user_message: str | None = None
    assistant_response: str | None = None
    sub_task: str | None = None
    micro_outcome: str | None = None
    akus_shown: list[UUID] = Field(default_factory=list)
    akus_helped: list[UUID] = Field(default_factory=list)
    akus_harmed: list[UUID] = Field(default_factory=list)
    cluster_id: UUID | None = None
    created_at: datetime


class SessionTurnsResponse(BaseModel):
    """Response containing session turns with micro-outcomes."""
    session_id: UUID
    turns: list[TurnResponse]
    micro_outcomes: SessionMicroOutcomes


class BulletUpdate(BaseModel):
    """Request to update a bullet."""
    content: Optional[str] = Field(None, min_length=1, max_length=500)
    status: Optional[Literal["candidate", "active", "archived", "banned"]] = None
    category: Optional[str] = None


class BulletResponse(BaseModel):
    """Response containing AKU information (v4 schema)."""
    id: str
    situation: str
    assertion: str
    helpful_count: int = 0
    harmful_count: int = 0
    neutral_count: int = 0
    status: str = "candidate"
    created_at: str


class BulletListResponse(BaseModel):
    """Response for listing bullets with pagination."""
    bullets: List[BulletResponse]
    total: int
    page: int
    page_size: int


# Evaluation models
class ExperimentCreate(BaseModel):
    """Request to create an evaluation experiment."""
    name: str
    description: Optional[str] = None
    dataset: str
    config: dict[str, Any] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    """Response containing experiment information."""
    id: UUID
    name: str
    description: Optional[str] = None
    dataset: str
    status: str
    config: dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tasks_total: int = 0
    tasks_completed: int = 0
    success_rate: Optional[float] = None


class ExperimentListResponse(BaseModel):
    """Response for listing experiments."""
    experiments: List[ExperimentResponse]
    total: int


class TaskResultResponse(BaseModel):
    """Response containing task result."""
    task_id: str
    status: str
    success: Optional[bool] = None
    turns: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# System models
class SystemResetRequest(BaseModel):
    """Request to reset system data."""
    target: Literal["all", "counters", "sessions", "evaluations", "redis", "bullets"]
    confirm: bool = False


class LearningStatsResponse(BaseModel):
    """Response containing learning statistics."""
    total_bullets: int
    active_bullets: int
    total_sessions: int
    successful_sessions: int
    avg_effectiveness: float
    top_bullets: list[dict[str, Any]]
    recent_changes: list[dict[str, Any]]


# Knowledge Graph models
class ClusterResponse(BaseModel):
    """Response containing problem cluster information."""
    cluster_id: str
    label: str
    description: Optional[str] = None
    turn_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    status: str = "active"
    solved_by_edges: int = 0
    caused_failure_edges: int = 0
    created_at: datetime
    updated_at: datetime


class ClusterListResponse(BaseModel):
    """Response for listing clusters with pagination."""
    clusters: List[ClusterResponse]
    total: int
    page: int
    page_size: int


class EdgeResponse(BaseModel):
    """Response containing knowledge edge information."""
    edge_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    edge_type: str
    weight: float = 0.0
    evidence_count: int = 0
    created_at: datetime


class EdgeListResponse(BaseModel):
    """Response for listing edges."""
    edges: List[EdgeResponse]
    total: int


class GraphHealthResponse(BaseModel):
    """Response containing knowledge graph health metrics."""
    total_clusters: int
    active_clusters: int
    total_edges: int
    solved_by_edges: int
    caused_failure_edges: int
    avg_cluster_success_rate: float
