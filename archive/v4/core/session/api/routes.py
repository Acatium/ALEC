"""Core chat API routes (v3).

CRITICAL: These endpoints are used by evaluation framework.
Do not modify contracts without updating alec_client.py.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from core.common.observability import setup_logging
from core.session.api.models import (
    ChatRequest,
    ChatResponse,
    MessageResponse,
    SessionCompleteRequest,
    SessionCreate,
    SessionHistoryResponse,
    SessionListResponse,
    SessionMetadata,
    SessionMicroOutcomes,
    SessionResponse,
    SessionTurnsResponse,
    TokenUsage,
    TurnResponse,
)
from core.session.domain.conversation import USE_TOOL_SEARCH, ConversationOrchestrator
from core.session.domain.llm_client import GatewayLLMClient
from core.session.infrastructure.bullet_cache import BulletCache
from core.session.infrastructure.kafka_producer import SessionKafkaProducer
from core.session.infrastructure.session_store import SessionStore

router = APIRouter()
logger = setup_logging("chat-routes")


def get_deps():
    """Get dependencies from global service."""
    from core.session.main import service

    if not service.pool or not service.redis or not service.kafka:
        raise RuntimeError("Service not fully initialized")

    store = SessionStore(service.pool)
    bullet_cache = BulletCache(service.redis)
    kafka_producer = SessionKafkaProducer(service.kafka)
    llm_client = GatewayLLMClient()

    # Create AKU search tool if feature flag is enabled
    aku_search = None
    if USE_TOOL_SEARCH:
        from core.session.domain.aku_search import AKUSearchTool
        aku_search = AKUSearchTool(service.pool)
        logger.info("aku_search_tool_enabled")

    orchestrator = ConversationOrchestrator(
        bullet_cache=bullet_cache,
        kafka_producer=kafka_producer,
        llm_client=llm_client,
        aku_search=aku_search,
    )

    return {
        "store": store,
        "orchestrator": orchestrator,
        "kafka": kafka_producer,
    }


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest) -> ChatResponse:
    """Send a message and get response.

    CRITICAL: This endpoint is used by evaluation/appworld/runner/alec_client.py
    Request: {"message": str, "session_id": UUID, "metadata": dict}
    Response: {"session_id": UUID, "message": str, "timestamp": str, "tool_calls": list, "bullets_used": list}
    """
    deps = get_deps()
    store = deps["store"]
    orchestrator = deps["orchestrator"]
    kafka = deps["kafka"]

    # Get or create session
    if request.session_id:
        session = await store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = request.session_id
    else:
        session_id = uuid4()
        domain = request.metadata.get("domain", "general")
        session = await store.create(session_id, domain, request.metadata)

        # Emit session.created
        await kafka.emit_session_created(
            session_id=str(session_id),
            domain=domain,
            metadata=request.metadata,
        )

    # Get conversation history
    history = await store.get_history(session_id)
    history_messages = []
    for turn in history:
        if turn.get("user_message"):
            history_messages.append({"role": "user", "content": turn["user_message"]})
        if turn.get("assistant_response"):
            history_messages.append({"role": "assistant", "content": turn["assistant_response"]})

    # Get turn number
    turn_number = len(history) + 1

    # Process turn
    domain = session.get("domain", "general")
    result = await orchestrator.process_turn(
        session_id=str(session_id),
        turn_number=turn_number,
        user_message=request.message,
        history=history_messages,
        domain=domain,
    )

    # Save turn to database
    aku_ids = [UUID(b.get("id") or b.get("aku_id") or b.get("bullet_id")) for b in result.bullets_used if b.get("id") or b.get("aku_id") or b.get("bullet_id")]
    await store.save_turn(
        session_id=session_id,
        turn_number=turn_number,
        user_message=request.message,
        assistant_response=result.response,
        akus_shown=aku_ids,
    )

    # Increment message count
    await store.increment_message_count(session_id)

    # Build response
    usage = result.usage
    token_usage = TokenUsage(
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        cost_usd=usage.get("cost_usd", 0.0),
    ) if usage else None

    return ChatResponse(
        session_id=session_id,
        message=result.response,
        timestamp=datetime.now(timezone.utc),
        tool_calls=[],  # v3 doesn't use tools
        token_usage=token_usage,
        bullets_used=result.bullets_used,
    )


@router.post("/stream")
async def stream_message(request: ChatRequest):
    """Stream a message response via SSE.

    Same contract as /message but streams response chunks.
    """
    deps = get_deps()
    store = deps["store"]
    orchestrator = deps["orchestrator"]
    kafka = deps["kafka"]

    # Get or create session (same as /message)
    if request.session_id:
        session = await store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = request.session_id
    else:
        session_id = uuid4()
        domain = request.metadata.get("domain", "general")
        session = await store.create(session_id, domain, request.metadata)
        await kafka.emit_session_created(str(session_id), domain, request.metadata)

    # Get history
    history = await store.get_history(session_id)
    history_messages = []
    for turn in history:
        if turn.get("user_message"):
            history_messages.append({"role": "user", "content": turn["user_message"]})
        if turn.get("assistant_response"):
            history_messages.append({"role": "assistant", "content": turn["assistant_response"]})

    turn_number = len(history) + 1
    domain = session.get("domain", "general")

    async def event_generator():
        """Generate SSE events."""
        # For now, fall back to non-streaming
        result = await orchestrator.process_turn(
            session_id=str(session_id),
            turn_number=turn_number,
            user_message=request.message,
            history=history_messages,
            domain=domain,
        )

        # Save turn
        aku_ids = [UUID(b.get("id") or b.get("aku_id") or b.get("bullet_id")) for b in result.bullets_used if b.get("id") or b.get("aku_id") or b.get("bullet_id")]
        await store.save_turn(session_id, turn_number, request.message, result.response, aku_ids)
        await store.increment_message_count(session_id)

        # Yield response
        yield {"event": "message", "data": result.response}
        yield {"event": "done", "data": str(session_id)}

    return EventSourceResponse(event_generator())


@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreate) -> SessionResponse:
    """Create a new session.

    CRITICAL: Used by evaluation framework.
    """
    deps = get_deps()
    store = deps["store"]
    kafka = deps["kafka"]

    session_id = uuid4()
    domain = request.metadata.get("domain", "general")

    session = await store.create(session_id, domain, request.metadata)

    await kafka.emit_session_created(str(session_id), domain, request.metadata)

    return SessionResponse(
        session_id=session_id,
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        status=session["status"],
        message_count=session["message_count"],
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    bullet_id: Optional[UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> SessionListResponse:
    """List sessions with optional filters."""
    deps = get_deps()
    store = deps["store"]

    sessions, total = await store.list_sessions(
        status=status,
        domain=domain,
        bullet_id=bullet_id,
        limit=limit,
        offset=offset,
    )

    from .models import SessionMicroOutcomes

    def build_session_metadata(s: dict) -> SessionMetadata:
        micro_outcomes = None
        if s.get("solved") is not None or s.get("progress") is not None:
            micro_outcomes = SessionMicroOutcomes(
                solved=s.get("solved") or 0,
                progress=s.get("progress") or 0,
                stuck=s.get("stuck") or 0,
                error=s.get("error") or 0,
            )
        return SessionMetadata(
            session_id=s["session_id"],
            domain=s.get("domain", "general"),
            status=s["status"],
            metadata=s.get("metadata", {}),
            message_count=s.get("message_count", 0),
            duration_ms=s.get("duration_ms"),
            micro_outcomes=micro_outcomes,
            created_at=s["created_at"],
            updated_at=s["updated_at"],
        )

    return SessionListResponse(
        sessions=[build_session_metadata(s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID) -> SessionResponse:
    """Get session by ID.

    CRITICAL: Used by evaluation/appworld/runner/alec_client.py
    """
    deps = get_deps()
    store = deps["store"]

    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse(
        session_id=session["session_id"],
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        status=session["status"],
        message_count=session.get("message_count", 0),
    )


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(session_id: UUID) -> SessionHistoryResponse:
    """Get session conversation history."""
    deps = get_deps()
    store = deps["store"]

    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history = await store.get_history(session_id)

    messages = []
    for turn in history:
        if turn.get("user_message"):
            messages.append(MessageResponse(
                id=turn.get("turn_id", uuid4()),
                role="user",
                content=turn["user_message"],
                timestamp=turn.get("created_at", datetime.now(timezone.utc)),
            ))
        if turn.get("assistant_response"):
            messages.append(MessageResponse(
                id=turn.get("turn_id", uuid4()),
                role="assistant",
                content=turn["assistant_response"],
                timestamp=turn.get("created_at", datetime.now(timezone.utc)),
            ))

    return SessionHistoryResponse(
        session_id=session_id,
        title=session.get("title"),
        domain=session.get("domain"),
        status=session["status"],
        message_count=session.get("message_count", 0),
        created_at=session.get("created_at"),
        updated_at=session.get("updated_at"),
        metadata=session.get("metadata"),
        messages=messages,
        total_messages=len(messages),
    )


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: UUID,
    request: SessionCompleteRequest,
) -> SessionResponse:
    """Complete a session.

    Emits session.ended event for learning loop.
    """
    deps = get_deps()
    store = deps["store"]
    kafka = deps["kafka"]

    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Complete session
    updated = await store.complete(session_id, request.status, request.reason)

    # Emit session.ended
    success = request.status == "completed"
    await kafka.emit_session_ended(
        session_id=str(session_id),
        success=success,
        domain=session.get("domain", "general"),
        reason=request.reason,
        message_count=updated.get("message_count", 0),
    )

    return SessionResponse(
        session_id=updated["session_id"],
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        status=updated["status"],
        message_count=updated.get("message_count", 0),
    )


@router.get("/sessions/{session_id}/turns", response_model=SessionTurnsResponse)
async def get_session_turns(session_id: UUID) -> SessionTurnsResponse:
    """Get session turns with micro-outcomes."""
    deps = get_deps()
    store = deps["store"]

    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get turns from session_turns table
    turns_data = await store.get_turns(session_id)

    # Build response
    turns = []
    micro_outcomes = SessionMicroOutcomes()

    for turn in turns_data:
        outcome = turn.get("micro_outcome")
        if outcome == "solved":
            micro_outcomes.solved += 1
        elif outcome == "progress":
            micro_outcomes.progress += 1
        elif outcome == "stuck":
            micro_outcomes.stuck += 1
        elif outcome == "error":
            micro_outcomes.error += 1

        turns.append(TurnResponse(
            turn_id=turn["turn_id"],
            turn_number=turn["turn_number"],
            user_message=turn.get("user_message"),
            assistant_response=turn.get("assistant_response"),
            sub_task=turn.get("sub_task"),
            micro_outcome=outcome,
            akus_shown=turn.get("akus_shown") or [],
            akus_helped=turn.get("akus_helped") or [],
            akus_harmed=turn.get("akus_harmed") or [],
            cluster_id=turn.get("cluster_id"),
            created_at=turn["created_at"],
        ))

    return SessionTurnsResponse(
        session_id=session_id,
        turns=turns,
        micro_outcomes=micro_outcomes,
    )


@router.get("/sessions/{session_id}/bullets")
async def get_session_bullets(session_id: UUID) -> dict[str, Any]:
    """Get bullets used in a session."""
    deps = get_deps()
    store = deps["store"]

    session = await store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    bullets = await store.get_bullets_used(session_id)

    return {
        "session_id": str(session_id),
        "bullets": bullets,
        "total": len(bullets),
    }
