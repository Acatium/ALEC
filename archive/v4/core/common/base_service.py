"""Base service class for all ALEC services.

Provides common infrastructure: PostgreSQL, Kafka, Redis, logging, metrics.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Optional

import asyncpg
import redis.asyncio as aioredis
from prometheus_client import start_http_server

from core.common.errors import RetryableError
from core.common.kafka_client import Event, KafkaClient
from core.common.observability import (
    ERRORS,
    EVENT_DURATION,
    EVENTS_DROPPED,
    EVENTS_PROCESSED,
    setup_logging,
)


class BaseService(ABC):
    """Base class for services with PostgreSQL + Kafka + observability."""

    def __init__(self, service_name: str):
        """Initialize base service.

        Args:
            service_name: Name of the service for logging/metrics.
        """
        self.service_name = service_name
        self.pool: Optional[asyncpg.Pool] = None
        self.kafka: Optional[KafkaClient] = None
        self.redis: Optional[aioredis.Redis] = None
        self.logger = setup_logging(service_name)

    async def _init_postgres(self) -> None:
        """Initialize PostgreSQL connection pool with JSONB codec."""
        from core.common.postgres import create_pool
        self.pool = await create_pool()
        self.logger.info("postgres_connected")

    async def _init_kafka(self) -> None:
        """Initialize Kafka client with topic pre-creation."""
        self.kafka = KafkaClient(service_name=self.service_name)

        # Pre-create topics to avoid race conditions at startup
        try:
            created = await self.kafka.ensure_topics_exist()
            if created:
                self.logger.info("kafka_topics_created", topics=created)
        except Exception as e:
            self.logger.warning("kafka_topic_precreation_failed", error=str(e))
            # Continue anyway - topics might already exist or auto-create is enabled

        await self.kafka.start_producer()
        self.logger.info("kafka_connected")

    async def _init_redis(self) -> None:
        """Initialize Redis client. Call explicitly if needed."""
        self.redis = await aioredis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379")
        )
        self.logger.info("redis_connected")

    def _start_metrics_server(self, port: Optional[int] = None) -> None:
        """Start Prometheus metrics endpoint."""
        port = port or int(os.getenv("METRICS_PORT", "9090"))
        try:
            start_http_server(port)
            self.logger.info("metrics_server_started", port=port)
        except OSError:
            # Port already in use (another service in same process)
            self.logger.debug("metrics_server_already_running", port=port)

    async def start(self) -> None:
        """Start the service."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()

        # After _init_kafka, kafka is guaranteed to be set
        assert self.kafka is not None, "Kafka client failed to initialize"

        await self.kafka.start_consumer(
            topics=self._get_topics(),
            handler=self._handle_event_wrapper,
            group_id=f"{self.service_name}-events",
        )
        self.logger.info("service_started")

    async def stop(self) -> None:
        """Stop the service."""
        self.logger.info("service_stopping")
        if self.kafka:
            await self.kafka.close()
        if self.pool:
            await self.pool.close()
        if self.redis:
            await self.redis.close()
        self.logger.info("service_stopped")

    async def _handle_event_wrapper(self, event: Event) -> None:
        """Wrap event handling with logging and metrics."""
        start_time = time.time()
        session_id = event.payload.get("session_id", "unknown")

        self.logger.info(
            "event_received",
            event_type=event.event_type,
            session_id=session_id
        )

        try:
            await self._handle_event(event)
            duration = time.time() - start_time

            EVENTS_PROCESSED.labels(
                service=self.service_name,
                event_type=event.event_type,
                status="success"
            ).inc()
            EVENT_DURATION.labels(
                service=self.service_name,
                event_type=event.event_type
            ).observe(duration)

            self.logger.info(
                "event_processed",
                event_type=event.event_type,
                session_id=session_id,
                duration_ms=int(duration * 1000)
            )

        except RetryableError as e:
            EVENTS_PROCESSED.labels(
                service=self.service_name,
                event_type=event.event_type,
                status="retry"
            ).inc()
            ERRORS.labels(
                service=self.service_name,
                error_type=type(e).__name__,
                retryable="true"
            ).inc()
            self.logger.warning(
                "event_processing_failed",
                event_type=event.event_type,
                session_id=session_id,
                error_type=type(e).__name__,
                error_retryable=True,
                error_message=str(e)
            )
            raise

        except Exception as e:
            EVENTS_PROCESSED.labels(
                service=self.service_name,
                event_type=event.event_type,
                status="error"
            ).inc()
            ERRORS.labels(
                service=self.service_name,
                error_type=type(e).__name__,
                retryable="false"
            ).inc()
            self.logger.error(
                "event_processing_failed",
                event_type=event.event_type,
                session_id=session_id,
                error_type=type(e).__name__,
                error_retryable=False,
                error_message=str(e)
            )
            raise

    async def health_check(self) -> dict:
        """Return health status."""
        checks = {}

        # PostgreSQL
        if self.pool is None:
            checks["postgres"] = "not_initialized"
        else:
            try:
                await self.pool.fetchval("SELECT 1")
                checks["postgres"] = "ok"
            except (asyncpg.PostgresError, OSError) as e:
                self.logger.warning("health_check_postgres_failed", error=str(e))
                checks["postgres"] = "error"

        # Kafka
        checks["kafka"] = "ok" if self.kafka else "not_initialized"

        # Redis (if initialized)
        if self.redis:
            try:
                await self.redis.ping()
                checks["redis"] = "ok"
            except (aioredis.RedisError, OSError) as e:
                self.logger.warning("health_check_redis_failed", error=str(e))
                checks["redis"] = "error"

        status = "healthy" if all(v == "ok" for v in checks.values()) else "unhealthy"

        return {
            "status": status,
            "checks": checks,
            "service": self.service_name
        }

    def _record_event_drop(
        self,
        event_type: str,
        drop_reason: str,
        session_id: str = "unknown"
    ) -> None:
        """Record a dropped event for observability.

        Call this when an event is not processed due to validation failure,
        missing data, or other pre-processing issues.

        Args:
            event_type: The Kafka event type (e.g., 'bullets.requested')
            drop_reason: Why the event was dropped (e.g., 'missing_session_id')
            session_id: Session ID if available, 'unknown' otherwise
        """
        EVENTS_DROPPED.labels(
            service=self.service_name,
            event_type=event_type,
            drop_reason=drop_reason
        ).inc()
        self.logger.warning(
            "event_dropped",
            event_type=event_type,
            session_id=session_id,
            drop_reason=drop_reason
        )

    def _require_pool(self) -> asyncpg.Pool:
        """Get pool or raise if not initialized."""
        if self.pool is None:
            raise RuntimeError(f"{self.service_name}: Database pool not initialized")
        return self.pool

    def _require_kafka(self) -> KafkaClient:
        """Get Kafka client or raise if not initialized."""
        if self.kafka is None:
            raise RuntimeError(f"{self.service_name}: Kafka client not initialized")
        return self.kafka

    def _require_redis(self) -> aioredis.Redis:
        """Get Redis client or raise if not initialized."""
        if self.redis is None:
            raise RuntimeError(f"{self.service_name}: Redis client not initialized")
        return self.redis

    @abstractmethod
    def _get_topics(self) -> list[str]:
        """Return list of Kafka topics to consume."""
        pass

    @abstractmethod
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming event."""
        pass
