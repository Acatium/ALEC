"""Error classification for ALEC services.

Provides base error classes with retryable/fatal classification
for proper error handling and metrics.
"""


class ALECError(Exception):
    """Base error for ALEC services."""
    retryable: bool = False


class RetryableError(ALECError):
    """Error that should be retried (connection issues, timeouts)."""
    retryable = True


class FatalError(ALECError):
    """Error that should not be retried (validation, logic errors)."""
    retryable = False


class LLMTimeoutError(RetryableError):
    """LLM call timed out."""
    pass


class LLMMalformedResponseError(FatalError):
    """LLM returned unparseable response."""
    pass


class EmbeddingServiceError(RetryableError):
    """Embedding service unavailable."""
    pass


class ValidationError(FatalError):
    """Input validation failed."""
    pass


class DatabaseError(RetryableError):
    """Database connection or query error."""
    pass


class KafkaPublishError(RetryableError):
    """Failed to publish to Kafka."""
    pass
