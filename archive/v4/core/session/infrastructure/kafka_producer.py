"""Kafka event producer for SESSION (v3).

Emits events for the learning loop to consume.
"""

from typing import Any, Optional

from core.common.kafka_client import KafkaClient
from core.common.observability import setup_logging


class SessionKafkaProducer:
    """Kafka producer for session events."""

    def __init__(self, kafka: KafkaClient):
        """Initialize producer.

        Args:
            kafka: Shared Kafka client.
        """
        self.kafka = kafka
        self.logger = setup_logging("session-kafka")

    async def emit_session_created(
        self,
        session_id: str,
        domain: str,
        metadata: dict[str, Any],
    ) -> None:
        """Emit session.created event.

        Args:
            session_id: Session UUID string.
            domain: Session domain.
            metadata: Session metadata.
        """
        await self.kafka.publish_event(
            topic="session.created",
            event_type="session.created",
            payload={
                "session_id": session_id,
                "domain": domain,
                "metadata": metadata,
            },
            correlation_id=session_id,
            key=session_id,
        )

        self.logger.debug("emitted_session_created", session_id=session_id)

    async def emit_bullets_requested(
        self,
        session_id: str,
        turn_number: int,
        problem_context: str,
        domain: str,
        cluster_id: Optional[str] = None,
        bullets_already_shown: Optional[list[str]] = None,
    ) -> None:
        """Emit bullets.requested event for ADVISOR.

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            problem_context: User message / problem context (truncated).
            domain: Session domain.
            cluster_id: Optional cluster ID from previous turn.
            bullets_already_shown: IDs of bullets already shown in this session.
        """
        await self.kafka.publish_event(
            topic="bullets.requested",
            event_type="bullets.requested",
            payload={
                "session_id": session_id,
                "turn_number": turn_number,
                "problem_context": problem_context[:500],  # Truncate for embedding
                "domain": domain,
                "cluster_id": cluster_id,
                "bullets_already_shown": bullets_already_shown or [],
            },
            correlation_id=session_id,
            key=session_id,
        )

        self.logger.debug(
            "emitted_bullets_requested",
            session_id=session_id,
            turn_number=turn_number,
        )

    async def emit_llm_response(
        self,
        session_id: str,
        turn_number: int,
        user_message: str,
        assistant_response: str,
        bullets_used: list[dict[str, Any]],
        error_trace: Optional[str] = None,
    ) -> None:
        """Emit llm.response.received event for REFLECTOR.

        Args:
            session_id: Session UUID string.
            turn_number: Current turn number.
            user_message: User's input message.
            assistant_response: LLM's response.
            bullets_used: Full bullet objects used in this turn.
            error_trace: Optional error trace if turn resulted in error.
        """
        await self.kafka.publish_event(
            topic="llm.response.received",
            event_type="llm.response.received",
            payload={
                "session_id": session_id,
                "turn_number": turn_number,
                "user_message": user_message,
                "assistant_response": assistant_response,
                "bullets_used": bullets_used,
                "bullets_used_full": bullets_used,  # Backward compat
                "error_trace": error_trace,
            },
            correlation_id=session_id,
            key=session_id,
        )

        self.logger.debug(
            "emitted_llm_response",
            session_id=session_id,
            turn_number=turn_number,
            bullet_count=len(bullets_used),
        )

    async def emit_session_ended(
        self,
        session_id: str,
        success: bool,
        domain: str = "general",
        reason: Optional[str] = None,
        message_count: int = 0,
    ) -> None:
        """Emit session.ended event for REFLECTOR analysis.

        Args:
            session_id: Session UUID string.
            success: Whether session completed successfully.
            domain: Session domain for learning attribution.
            reason: Optional reason for completion.
            message_count: Total messages in session.
        """
        await self.kafka.publish_event(
            topic="session.ended",
            event_type="session.ended",
            payload={
                "session_id": session_id,
                "success": success,
                "domain": domain,
                "reason": reason,
                "message_count": message_count,
            },
            correlation_id=session_id,
            key=session_id,
        )

        self.logger.info(
            "emitted_session_ended",
            session_id=session_id,
            success=success,
        )
