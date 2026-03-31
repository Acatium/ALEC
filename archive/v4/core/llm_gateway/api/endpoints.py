"""API endpoints for the LLM Gateway service."""

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.llm_gateway.infrastructure.anthropic_client import AnthropicClient
from core.llm_gateway.infrastructure.config_store import ConfigStore

logger = logging.getLogger(__name__)

router = APIRouter()

# Embedding configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIMENSION = 384

# Singleton for embedding model (set by main.py on startup)
_embedding_model = None


def init_embedding_model():
    """Initialize the embedding model. Called by main.py on startup."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def _get_embedding_model():
    """Get the embedding model (must be initialized first)."""
    if _embedding_model is None:
        raise RuntimeError("Embedding model not initialized. Call init_embedding_model() first.")
    return _embedding_model

# These will be set by main.py on startup
config_store: Optional[ConfigStore] = None
anthropic_client: Optional[AnthropicClient] = None


class MessageInput(BaseModel):
    """A single message in the conversation."""

    role: str = Field(..., description="Message role (user or assistant)")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    agent_name: str = Field(..., description="Name of the agent to use for config lookup")
    messages: list[MessageInput] = Field(..., description="Conversation messages")
    system_prompt_override: Optional[str] = None
    tools: Optional[list[dict[str, Any]]] = Field(
        default=None, description="Optional list of tool definitions for tool use"
    )


class UsageStats(BaseModel):
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    # Computed fields for compatibility with OpenAI-style naming
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ToolCallResponse(BaseModel):
    """A tool call returned by the LLM."""

    id: str = Field(..., description="Unique identifier for this tool call")
    name: str = Field(..., description="Name of the tool being called")
    input: dict[str, Any] = Field(..., description="Input arguments for the tool")


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    content: Optional[str] = Field(None, description="LLM response text (None if tool_use)")
    model: str = Field(..., description="Model used for the response")
    usage: UsageStats = Field(..., description="Token usage statistics")
    stop_reason: str = Field(default="end_turn", description="Why the LLM stopped")
    tool_calls: list[ToolCallResponse] = Field(
        default_factory=list, description="Tool calls if stop_reason is tool_use"
    )


class AgentConfigResponse(BaseModel):
    """Response containing agent configuration."""

    agent_name: str
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str


class ReloadResponse(BaseModel):
    """Response from config reload endpoint."""

    message: str
    agents_loaded: int


@router.post("/api/v1/llm/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a chat request to the LLM using agent configuration.

    Args:
        request: Chat request with agent name and messages.

    Returns:
        ChatResponse with LLM response and usage stats.

    Raises:
        HTTPException: If agent not found or API call fails.
    """
    if config_store is None or anthropic_client is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    config = config_store.get_config(request.agent_name)
    if config is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{request.agent_name}' not found"
        )

    # Extract system messages from the messages array (Anthropic API requires system as top-level param)
    system_messages = [msg.content for msg in request.messages if msg.role == "system"]
    non_system_messages = [msg for msg in request.messages if msg.role != "system"]

    # Determine system prompt: override > inline system messages > config default
    if request.system_prompt_override is not None:
        system_prompt = request.system_prompt_override
    elif system_messages:
        system_prompt = "\n\n".join(system_messages)
    else:
        system_prompt = config.system_prompt

    messages = [{"role": msg.role, "content": msg.content} for msg in non_system_messages]

    try:
        response = await anthropic_client.chat(
            model=config.model,
            messages=messages,
            system_prompt=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            agent_name=request.agent_name,
            tools=request.tools,
        )

        input_tokens = response.usage["input_tokens"]
        output_tokens = response.usage["output_tokens"]

        # Convert tool calls to response model
        tool_call_responses = [
            ToolCallResponse(id=tc.id, name=tc.name, input=tc.input)
            for tc in response.tool_calls
        ]

        return ChatResponse(
            content=response.content,
            model=response.model,
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=response.usage.get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=response.usage.get("cache_read_input_tokens", 0),
                # OpenAI-compatible fields
                total_tokens=input_tokens + output_tokens,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            ),
            stop_reason=response.stop_reason,
            tool_calls=tool_call_responses,
        )

    except Exception as e:
        logger.error(f"Chat request failed for agent '{request.agent_name}': {e}")
        raise HTTPException(status_code=500, detail=f"LLM API error: {str(e)}")


@router.post("/api/v1/reload-config", response_model=ReloadResponse)
async def reload_config() -> ReloadResponse:
    """Reload all agent configurations from the database.

    Returns:
        ReloadResponse with confirmation and count of agents loaded.

    Raises:
        HTTPException: If reload fails.
    """
    if config_store is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    try:
        await config_store.reload_configs()
        agents = config_store.list_agents()
        return ReloadResponse(
            message="Configuration reloaded successfully",
            agents_loaded=len(agents),
        )
    except Exception as e:
        logger.error(f"Config reload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reload failed: {str(e)}")


@router.get("/api/v1/agents/{agent_name}/config", response_model=AgentConfigResponse)
async def get_agent_config(agent_name: str) -> AgentConfigResponse:
    """Get the current configuration for an agent.

    Args:
        agent_name: Name of the agent.

    Returns:
        AgentConfigResponse with agent configuration.

    Raises:
        HTTPException: If agent not found.
    """
    if config_store is None:
        raise HTTPException(status_code=500, detail="Service not initialized")

    config = config_store.get_config(agent_name)
    if config is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_name}' not found"
        )

    return AgentConfigResponse(
        agent_name=config.agent_name,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        system_prompt=config.system_prompt,
    )


# ============================================================================
# Embedding endpoints
# ============================================================================


class EmbedRequest(BaseModel):
    """Request body for single text embedding."""

    text: str = Field(..., description="Text to embed")


class EmbedBatchRequest(BaseModel):
    """Request body for batch text embedding."""

    texts: list[str] = Field(..., description="List of texts to embed")


class EmbedResponse(BaseModel):
    """Response from embed endpoint."""

    embedding: list[float] = Field(..., description="384-dimensional embedding vector")
    dimension: int = Field(default=EMBEDDING_DIMENSION, description="Vector dimension")


class EmbedBatchResponse(BaseModel):
    """Response from batch embed endpoint."""

    embeddings: list[list[float]] = Field(..., description="List of embedding vectors")
    dimension: int = Field(default=EMBEDDING_DIMENSION, description="Vector dimension")
    count: int = Field(..., description="Number of embeddings returned")


@router.post("/api/v1/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest) -> EmbedResponse:
    """Generate embedding for a single text.

    Args:
        request: Request with text to embed.

    Returns:
        EmbedResponse with 384-dimensional embedding vector.
    """
    try:
        model = _get_embedding_model()

        if not request.text or not request.text.strip():
            # Return zero vector for empty text
            return EmbedResponse(
                embedding=[0.0] * EMBEDDING_DIMENSION,
                dimension=EMBEDDING_DIMENSION,
            )

        # Run blocking encode in thread pool to not block event loop
        embedding = await asyncio.to_thread(
            model.encode, request.text, normalize_embeddings=True
        )
        return EmbedResponse(
            embedding=embedding.tolist(),
            dimension=EMBEDDING_DIMENSION,
        )

    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding error: {str(e)}")


@router.post("/api/v1/embed/batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest) -> EmbedBatchResponse:
    """Generate embeddings for multiple texts.

    Args:
        request: Request with list of texts to embed.

    Returns:
        EmbedBatchResponse with list of 384-dimensional embedding vectors.
    """
    try:
        model = _get_embedding_model()

        if not request.texts:
            return EmbedBatchResponse(
                embeddings=[],
                dimension=EMBEDDING_DIMENSION,
                count=0,
            )

        # Filter non-empty texts for batch encoding
        non_empty_texts = []
        non_empty_indices = []
        for i, text in enumerate(request.texts):
            if text and text.strip():
                non_empty_texts.append(text)
                non_empty_indices.append(i)

        # Batch encode non-empty texts in thread pool
        if non_empty_texts:
            encoded = await asyncio.to_thread(
                model.encode, non_empty_texts, normalize_embeddings=True
            )
        else:
            encoded = []

        # Build result with zero vectors for empty texts
        embeddings = [[0.0] * EMBEDDING_DIMENSION] * len(request.texts)
        for idx, enc in zip(non_empty_indices, encoded):
            embeddings[idx] = enc.tolist()

        return EmbedBatchResponse(
            embeddings=embeddings,
            dimension=EMBEDDING_DIMENSION,
            count=len(embeddings),
        )

    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding error: {str(e)}")
