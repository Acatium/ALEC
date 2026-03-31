"""Kafka client for ALEC services.

Provides both consumer and producer functionality with consistent
event schema and error handling.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError

from core.common.kafka_admin import KafkaTopicManager

logger = logging.getLogger(__name__)

# Consumer startup timeout
CONSUMER_START_TIMEOUT_SECONDS = 30

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

# P2 FIX: Increased timeouts to prevent heartbeat failures during LLM calls (Dec 2025)
# LLM calls (REFLECTOR + CURATOR) can take 15-20 seconds, which exceeds default timeouts.
# session_timeout_ms: Max time between heartbeats before consumer is removed from group
# heartbeat_interval_ms: Frequency of heartbeat messages to coordinator
# max_poll_interval_ms: Max time between poll() calls (must exceed longest processing time)
KAFKA_SESSION_TIMEOUT_MS = int(os.getenv("KAFKA_SESSION_TIMEOUT_MS", "60000"))  # 60s
KAFKA_HEARTBEAT_INTERVAL_MS = int(os.getenv("KAFKA_HEARTBEAT_INTERVAL_MS", "20000"))  # 20s
KAFKA_MAX_POLL_INTERVAL_MS = int(os.getenv("KAFKA_MAX_POLL_INTERVAL_MS", "300000"))  # 5min


@dataclass
class Event:
    """Standard event schema for Kafka messages."""

    event_id: str
    event_type: str
    timestamp: str
    correlation_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Create Event from dictionary."""
        return cls(
            event_id=data.get("event_id", str(uuid4())),
            event_type=data.get("event_type", "unknown"),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            correlation_id=data.get("correlation_id", str(uuid4())),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }


class KafkaClient:
    """Unified Kafka client for consumer and producer operations."""

    def __init__(
        self,
        service_name: str,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
    ):
        """Initialize Kafka client.

        Args:
            service_name: Name of the service using this client (for group_id).
            bootstrap_servers: Kafka bootstrap servers.
        """
        self.service_name = service_name
        self.bootstrap_servers = bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumers: dict[str, AIOKafkaConsumer] = {}
        self._running = False

    async def ensure_topics_exist(
        self,
        topics: Optional[list[str]] = None,
    ) -> list[str]:
        """Ensure all required Kafka topics exist.

        Call this before starting consumers to avoid 'Topic not found' errors.

        Args:
            topics: Topics to ensure (defaults to REQUIRED_TOPICS)

        Returns:
            List of topics that were created
        """
        manager = KafkaTopicManager(self.bootstrap_servers)
        try:
            created = await manager.ensure_topics_exist(topics)
            if created:
                logger.info(f"Created Kafka topics: {created}")
            return created
        finally:
            await manager.close()

    async def start_producer(self) -> None:
        """Start the Kafka producer."""
        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info(f"Kafka producer started for {self.service_name}")

    async def stop_producer(self) -> None:
        """Stop the Kafka producer."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info(f"Kafka producer stopped for {self.service_name}")

    async def publish_event(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: Optional[str] = None,
        key: Optional[str] = None,
    ) -> None:
        """Publish an event to Kafka.

        Args:
            topic: Kafka topic to publish to.
            event_type: Type of event (e.g., 'signal.detected').
            payload: Event payload data.
            correlation_id: Optional correlation ID for tracing.
            key: Optional message key for partitioning.
        """
        if self._producer is None:
            await self.start_producer()

        # After start_producer, _producer is guaranteed to be set
        assert self._producer is not None, "Producer failed to initialize"

        event = Event(
            event_id=str(uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation_id=correlation_id or str(uuid4()),
            payload=payload,
            metadata={
                "source": self.service_name,
                "version": "1.0.0",
            },
        )

        try:
            await self._producer.send(
                topic=topic,
                value=event.to_dict(),
                key=key,
            )
            logger.debug(f"Published {event_type} event to {topic}")
        except KafkaError as e:
            logger.error(f"Failed to publish event to {topic}: {e}")
            raise

    async def start_consumer(
        self,
        topics: list[str],
        handler: Callable[[Event], Any],
        group_id: Optional[str] = None,
    ) -> None:
        """Start consuming from topics.

        Args:
            topics: List of topics to consume from.
            handler: Async function to handle each event.
            group_id: Consumer group ID (defaults to service_name).
        """
        consumer_id = ",".join(sorted(topics))
        if consumer_id in self._consumers:
            logger.warning(f"Consumer for {topics} already running")
            return

        group = group_id or f"{self.service_name}-consumer"

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            # P2 FIX: Increased timeouts to prevent heartbeat failures during LLM calls
            session_timeout_ms=KAFKA_SESSION_TIMEOUT_MS,
            heartbeat_interval_ms=KAFKA_HEARTBEAT_INTERVAL_MS,
            max_poll_interval_ms=KAFKA_MAX_POLL_INTERVAL_MS,
        )

        self._consumers[consumer_id] = consumer

        # Start consumer with timeout to prevent hanging
        try:
            await asyncio.wait_for(
                consumer.start(),
                timeout=CONSUMER_START_TIMEOUT_SECONDS
            )
            logger.info(f"Started consumer for {topics} (group={group})")
        except asyncio.TimeoutError:
            del self._consumers[consumer_id]
            logger.error(
                f"Consumer subscription timeout for {topics} "
                f"(timeout={CONSUMER_START_TIMEOUT_SECONDS}s)"
            )
            raise RuntimeError(
                f"Failed to start Kafka consumer for {topics}: subscription timeout"
            )

        self._running = True

        try:
            async for message in consumer:
                if not self._running:
                    break

                try:
                    event = Event.from_dict(message.value)
                    await handler(event)
                except Exception as e:
                    logger.error(
                        f"Error processing message from {message.topic}: {e}",
                        exc_info=True,
                    )
        finally:
            await consumer.stop()
            del self._consumers[consumer_id]
            logger.info(f"Stopped consumer for {topics}")

    async def stop_consumers(self) -> None:
        """Stop all consumers."""
        self._running = False
        for consumer in list(self._consumers.values()):
            await consumer.stop()
        self._consumers.clear()
        logger.info(f"All consumers stopped for {self.service_name}")

    async def close(self) -> None:
        """Close all connections."""
        await self.stop_consumers()
        await self.stop_producer()
