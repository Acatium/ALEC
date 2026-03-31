"""Core common utilities for ALEC services."""

from core.common.base_service import BaseService
from core.common.embedding_client import EmbeddingClient, embed, embed_batch
from core.common.errors import (
    ALECError,
    DatabaseError,
    EmbeddingServiceError,
    FatalError,
    KafkaPublishError,
    LLMMalformedResponseError,
    LLMTimeoutError,
    RetryableError,
    ValidationError,
)
from core.common.kafka_client import Event, KafkaClient
from core.common.observability import (
    AKUS_TOTAL,
    BULLETS_RETRIEVED,
    ERRORS,
    EVENT_DURATION,
    EVENTS_PROCESSED,
    LLM_CALLS,
    LLM_DURATION,
    setup_logging,
)

__all__ = [
    # Kafka
    "KafkaClient",
    "Event",
    # Base service
    "BaseService",
    # Embedding
    "EmbeddingClient",
    "embed",
    "embed_batch",
    # Errors
    "ALECError",
    "RetryableError",
    "FatalError",
    "LLMTimeoutError",
    "LLMMalformedResponseError",
    "EmbeddingServiceError",
    "ValidationError",
    "DatabaseError",
    "KafkaPublishError",
    # Observability
    "setup_logging",
    "EVENTS_PROCESSED",
    "EVENT_DURATION",
    "LLM_CALLS",
    "LLM_DURATION",
    "AKUS_TOTAL",
    "BULLETS_RETRIEVED",
    "ERRORS",
]
