"""Kafka producer for session events.

This module provides a Kafka producer for emitting session events to Kafka:
- session.steps: Step-by-step execution events for Reflector agents
- bullet.effectiveness: Bullet effectiveness tracking for learning
- token.usage: Token usage tracking for efficiency analysis
- session.completed: Session completion events for curator

Uses fire-and-forget pattern for non-blocking event emission.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SESSION_STEPS_TOPIC = "session.steps"
SESSION_COMPLETED_TOPIC = "session.completed"
TOKEN_USAGE_TOPIC = "token.usage"
BULLET_EFFECTIVENESS_TOPIC = "bullet.effectiveness"


def json_serializer(obj: Any) -> str:
    """Custom JSON serializer that handles UUID and datetime objects.

    Args:
        obj: Object to serialize

    Returns:
        JSON string
    """
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class SessionStepsProducer:
    """Kafka producer for session events.

    Emits session step and completion events to Kafka for consumption by Reflector agents:
    - Bias Detection Reflector
    - Performance Optimization Reflector
    - Pattern Learning Reflector
    - Anomaly Detection Reflector

    Uses fire-and-forget pattern for non-blocking emission.

    Example:
        producer = SessionStepsProducer()
        await producer.start()

        # Emit step event
        await producer.emit_session_step(
            session_id="660e8400-...",
            step_id="770e8400-...",
            step_number=5,
            step_type="tool_call",
            tool_or_agent_name="postgres_query",
            input_data={"query": "SELECT * FROM orders"},
            output_data={"rows": 10},
            success=True,
            duration_ms=45,
            correlation_id="550e8400-..."
        )

        # Emit completion event
        await producer.emit_session_completed(
            session_id="660e8400-...",
            domain="e-commerce",
            playbook_id="880e8400-...",
            status="completed",
            message_count=15,
            duration_seconds=120,
            tools_used=["postgres_query", "stripe_api"],
            correlation_id="550e8400-...",
            metadata={"user_satisfaction": "high"}
        )

        await producer.stop()
    """

    def __init__(
        self,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        steps_topic: str = SESSION_STEPS_TOPIC,
        completed_topic: str = SESSION_COMPLETED_TOPIC
    ):
        """Initialize session events producer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            steps_topic: Kafka topic for session steps
            completed_topic: Kafka topic for session completion
        """
        self.bootstrap_servers = bootstrap_servers
        self.steps_topic = steps_topic
        self.completed_topic = completed_topic
        self.producer: Optional[AIOKafkaProducer] = None
        self._connected = False

    async def start(self) -> None:
        """Start the Kafka producer.

        Raises:
            KafkaError: If connection fails
        """
        if self._connected:
            logger.warning("Producer already started")
            return

        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=json_serializer).encode("utf-8"),
                compression_type="gzip",
                acks="all",
            )
            await self.producer.start()
            self._connected = True
            logger.info(
                f"Session events producer started: steps_topic={self.steps_topic}, "
                f"completed_topic={self.completed_topic}, bootstrap={self.bootstrap_servers}"
            )
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self._connected = False
            raise KafkaError(f"Failed to start Kafka producer: {e}")

    async def stop(self) -> None:
        """Stop the Kafka producer and close connections."""
        if self.producer:
            await self.producer.stop()
            self._connected = False
            logger.info("Session steps producer stopped")

    async def publish_event(
        self,
        topic: str,
        event_type: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        source: str = "conversational-ai-service",
        version: str = "1.0.0",
    ) -> None:
        """Publish an event to Kafka with standard envelope.

        Args:
            topic: Kafka topic name
            event_type: Event type in past tense
            payload: Event-specific payload data
            correlation_id: Correlation ID for request tracing
            source: Service name emitting the event
            version: Event schema version

        Raises:
            KafkaError: If producer not connected
        """
        if not self.producer or not self._connected:
            raise KafkaError("Kafka producer not connected. Call start() first.")

        # Create standard event envelope
        event = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id or str(uuid4()),
            "payload": payload,
            "metadata": {
                "source": source,
                "version": version,
            },
        }

        try:
            # Send to topic (fire-and-forget with send, not send_and_wait)
            await self.producer.send(topic=topic, value=event)

            logger.debug(
                f"Published event {event['event_id']} to {topic}"
            )

        except Exception as e:
            logger.error(f"Failed to publish event to {topic}: {e}")
            raise KafkaError(f"Failed to publish to Kafka: {e}")

    async def emit_session_step(
        self,
        session_id: str,
        step_id: str,
        step_number: int,
        step_type: str,
        tool_or_agent_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        success: bool,
        duration_ms: int,
        correlation_id: str,
        corrected: bool = False,
        error_message: Optional[str] = None
    ) -> None:
        """Emit a session.steps event to Kafka (fire-and-forget).

        Event schema follows specifications/events/catalog.md:

        {
          "event_id": "UUID",
          "event_type": "session.steps",
          "timestamp": "ISO 8601 UTC",
          "correlation_id": "UUID",
          "payload": {
            "session_id": "UUID",
            "step_id": "UUID",
            "step_number": int,
            "step_type": "tool_call|agent_call|llm_call|human_intervention",
            "tool_or_agent_name": "string",
            "input": {},
            "output": {},
            "success": bool,
            "duration_ms": int,
            "corrected": bool,
            "error_message": "string (optional)"
          },
          "metadata": {
            "source": "conversational-ai-service",
            "version": "1.0.0"
          }
        }

        Args:
            session_id: Session UUID
            step_id: Step UUID
            step_number: Sequential step number
            step_type: Type of step (tool_call, agent_call, llm_call, human_intervention)
            tool_or_agent_name: Name of tool or agent used
            input_data: Input data for the step
            output_data: Output data from the step
            success: Whether step succeeded
            duration_ms: Execution time in milliseconds
            correlation_id: Correlation ID for request tracing
            corrected: Whether step was a human correction
            error_message: Optional error message if step failed

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        try:
            # Create payload following event schema
            payload = {
                "session_id": session_id,
                "step_id": step_id,
                "step_number": step_number,
                "step_type": step_type,
                "tool_or_agent_name": tool_or_agent_name,
                "input": input_data,
                "output": output_data,
                "success": success,
                "duration_ms": duration_ms,
                "corrected": corrected
            }

            # Add error message if present
            if error_message:
                payload["error_message"] = error_message

            # Emit event (fire-and-forget)
            await self.publish_event(
                topic=self.steps_topic,
                event_type="session.steps",
                payload=payload,
                correlation_id=correlation_id,
                source="conversational-ai-service",
                version="1.0.0"
            )

            logger.debug(
                f"Emitted session.steps event: session={session_id}, "
                f"step={step_number}, success={success}"
            )

        except Exception as e:
            # Fire-and-forget: log error but don't raise
            logger.error(
                f"Failed to emit session.steps event (non-blocking): {e}",
                exc_info=True
            )

    async def emit_session_completed(
        self,
        session_id: str,
        domain: str,
        playbook_id: Optional[str],
        status: str,
        message_count: int,
        duration_seconds: float,
        tools_used: list[str],
        correlation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        outcome_summary: Optional[str] = None,
        errors: Optional[list[Dict[str, Any]]] = None
    ) -> None:
        """Emit a session.completed event to Kafka (fire-and-forget).

        Event schema:

        {
          "event_id": "UUID",
          "event_type": "session.completed",
          "timestamp": "ISO 8601 UTC",
          "correlation_id": "UUID",
          "payload": {
            "session_id": "UUID",
            "domain": "string",
            "playbook_id": "UUID (optional)",
            "status": "completed|failed|timeout",
            "message_count": int,
            "duration_seconds": float,
            "tools_used": ["string"],
            "outcome_summary": "string (optional)",
            "errors": [{"step": int, "message": "string"}] (optional),
            "metadata": {} (optional)
          },
          "metadata": {
            "source": "conversational-ai-service",
            "version": "1.0.0"
          }
        }

        Args:
            session_id: Session UUID
            domain: Domain of the session
            playbook_id: Optional playbook UUID if session follows a playbook
            status: Session status (completed, failed, timeout)
            message_count: Total number of messages in session
            duration_seconds: Total session duration in seconds
            tools_used: List of tool names used during session
            correlation_id: Correlation ID for request tracing
            metadata: Optional additional metadata
            outcome_summary: Optional human-readable summary of session outcome
            errors: Optional list of errors that occurred during session

        Note:
            This is a fire-and-forget operation. Errors are logged but not raised.
        """
        try:
            # Create payload following event schema
            payload = {
                "session_id": session_id,
                "domain": domain,
                "status": status,
                "message_count": message_count,
                "duration_seconds": duration_seconds,
                "tools_used": tools_used,
            }

            # Add optional fields
            if playbook_id:
                payload["playbook_id"] = playbook_id

            if outcome_summary:
                payload["outcome_summary"] = outcome_summary

            if errors:
                payload["errors"] = errors

            if metadata:
                payload["metadata"] = metadata

            # Emit event (fire-and-forget)
            await self.publish_event(
                topic=self.completed_topic,
                event_type="session.completed",
                payload=payload,
                correlation_id=correlation_id,
                source="conversational-ai-service",
                version="1.0.0"
            )

            logger.info(
                f"Emitted session.completed event: session={session_id}, "
                f"status={status}, duration={duration_seconds}s, messages={message_count}"
            )

        except Exception as e:
            # Fire-and-forget: log error but don't raise
            logger.error(
                f"Failed to emit session.completed event (non-blocking): {e}",
                exc_info=True
            )

    async def health_check(self) -> bool:
        """Check if producer is healthy and connected.

        Returns:
            True if healthy, False otherwise
        """
        return self._connected and self.producer is not None

    @property
    def is_connected(self) -> bool:
        """Check if producer is connected."""
        return self._connected


# Singleton instance for convenience
_producer: Optional[SessionStepsProducer] = None


async def get_session_steps_producer() -> SessionStepsProducer:
    """Get or create singleton session steps producer.

    Returns:
        SessionStepsProducer instance

    Note:
        Remember to call start() on first use and stop() on shutdown.
    """
    global _producer
    if _producer is None:
        _producer = SessionStepsProducer()
    return _producer
