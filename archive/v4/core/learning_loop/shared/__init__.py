"""Shared infrastructure for learning loop services.

Note: KafkaClient has moved to core.common.kafka_client (Dec 2025).
Note: EmbeddingClient has moved to core.common.embedding_client (Dec 2025).
"""

from .redis_client import RedisClient

__all__ = ["RedisClient"]
