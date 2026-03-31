"""Unit tests for conversation.py.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.session.domain.conversation import ConversationOrchestrator, TurnResult


class TestConversationOrchestrator:
    """Tests for ConversationOrchestrator class."""

    @pytest.fixture
    def orchestrator(self, mock_redis, mock_kafka, mock_llm_client):
        """Create orchestrator with mocked dependencies."""
        from core.session.infrastructure.bullet_cache import BulletCache
        from core.session.infrastructure.kafka_producer import SessionKafkaProducer

        bullet_cache = BulletCache(mock_redis)
        bullet_cache.get_bullets = AsyncMock(return_value=([], None))  # type: ignore[method-assign]

        kafka_producer = MagicMock(spec=SessionKafkaProducer)
        kafka_producer.emit_bullets_requested = AsyncMock()
        kafka_producer.emit_llm_response = AsyncMock()

        return ConversationOrchestrator(
            bullet_cache=bullet_cache,
            kafka_producer=kafka_producer,
            llm_client=mock_llm_client,
        )

    @pytest.mark.asyncio
    async def test_process_turn_emits_bullets_requested(self, orchestrator):
        """Should emit bullets.requested event."""
        session_id = str(uuid4())

        await orchestrator.process_turn(
            session_id=session_id,
            turn_number=1,
            user_message="Test message",
            history=[],
            domain="test",
        )

        orchestrator.kafka.emit_bullets_requested.assert_called_once()
        call_kwargs = orchestrator.kafka.emit_bullets_requested.call_args[1]
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["turn_number"] == 1

    @pytest.mark.asyncio
    async def test_process_turn_emits_llm_response(self, orchestrator):
        """Should emit llm.response.received event."""
        session_id = str(uuid4())

        await orchestrator.process_turn(
            session_id=session_id,
            turn_number=1,
            user_message="Test message",
            history=[],
        )

        orchestrator.kafka.emit_llm_response.assert_called_once()
        call_kwargs = orchestrator.kafka.emit_llm_response.call_args[1]
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["user_message"] == "Test message"

    @pytest.mark.asyncio
    async def test_process_turn_returns_turn_result(self, orchestrator):
        """Should return TurnResult with response and metadata."""
        result = await orchestrator.process_turn(
            session_id=str(uuid4()),
            turn_number=1,
            user_message="Test",
            history=[],
        )

        assert isinstance(result, TurnResult)
        assert result.response == "Test response from LLM"
        assert result.turn_number == 1
        assert result.duration_ms >= 0  # Can be 0ms with fast async mocks

    @pytest.mark.asyncio
    async def test_process_turn_includes_bullets_used(self, orchestrator, sample_bullets):
        """Should include bullets in result."""
        orchestrator.bullet_cache.get_bullets = AsyncMock(
            return_value=(sample_bullets, "cluster-123")
        )

        result = await orchestrator.process_turn(
            session_id=str(uuid4()),
            turn_number=1,
            user_message="Test",
            history=[],
        )

        assert result.bullets_used == sample_bullets
        assert result.cluster_id == "cluster-123"

    @pytest.mark.asyncio
    async def test_tracks_bullets_shown_per_session(self, orchestrator, sample_bullets):
        """Should track bullets shown to avoid duplicates."""
        orchestrator.bullet_cache.get_bullets = AsyncMock(
            return_value=(sample_bullets, None)
        )
        session_id = str(uuid4())

        # First turn
        await orchestrator.process_turn(session_id, 1, "First", [])

        # Second turn - should include previously shown bullets
        await orchestrator.process_turn(session_id, 2, "Second", [])

        second_call = orchestrator.kafka.emit_bullets_requested.call_args_list[1]
        bullets_shown = second_call[1]["bullets_already_shown"]
        assert len(bullets_shown) == len(sample_bullets)


class TestBuildMessages:
    """Tests for _build_messages method."""

    @pytest.fixture
    def orchestrator(self, mock_redis, mock_kafka, mock_llm_client):
        """Create orchestrator for testing."""
        from core.session.infrastructure.bullet_cache import BulletCache
        from core.session.infrastructure.kafka_producer import SessionKafkaProducer

        return ConversationOrchestrator(
            bullet_cache=BulletCache(mock_redis),
            kafka_producer=MagicMock(spec=SessionKafkaProducer),
            llm_client=mock_llm_client,
        )

    def test_includes_system_prompt(self, orchestrator):
        """System prompt should be first message."""
        messages = orchestrator._build_messages([], "Hello", [])

        assert messages[0]["role"] == "system"
        assert "helpful AI assistant" in messages[0]["content"]

    def test_includes_history(self, orchestrator, sample_history):
        """History messages should be included."""
        messages = orchestrator._build_messages(sample_history, "New message", [])

        # System + history + current
        assert len(messages) == 1 + len(sample_history) + 1

    def test_includes_current_message_last(self, orchestrator):
        """Current user message should be last."""
        messages = orchestrator._build_messages([], "Current message", [])

        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Current message"

    def test_windows_long_history(self, orchestrator):
        """Long history should be windowed to first + last turns."""
        # Create 20 messages (10 turns)
        long_history = []
        for i in range(10):
            long_history.append({"role": "user", "content": f"User message {i}"})
            long_history.append({"role": "assistant", "content": f"Assistant {i}"})

        messages = orchestrator._build_messages(long_history, "Current", [])

        # System + first 2 + last 8 + current = 12
        # (Plus bullet injection if any)
        assert len(messages) == 12

        # First turn preserved
        assert "User message 0" in messages[1]["content"]

        # Last assistant message preserved (messages[-2] is last assistant, messages[-1] is current user)
        assert "Assistant 9" in messages[-2]["content"]

    def test_injects_bullets_after_first_user_message(self, orchestrator, sample_bullets):
        """Bullets should be injected after first user message for cache efficiency."""
        history = [
            {"role": "user", "content": "First user"},
            {"role": "assistant", "content": "First assistant"},
        ]

        messages = orchestrator._build_messages(history, "Current", sample_bullets)

        # Find injected bullets by looking for category markers (not "RELEVANT KNOWLEDGE" which is in system prompt)
        bullet_idx = None
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and ("Solutions (#S):" in content or "Constraints (#C):" in content):
                bullet_idx = i
                break

        assert bullet_idx is not None, "Bullet injection should occur"
        # Should be after first user (index 1 is first user after system)
        assert bullet_idx == 2

    def test_no_bullet_injection_when_empty(self, orchestrator):
        """No bullet message when bullets list is empty."""
        messages = orchestrator._build_messages([], "Hello", [])

        # System prompt mentions "RELEVANT KNOWLEDGE" as instructional text - that's OK
        # What we're checking is that no ACTUAL bullets were injected
        for msg in messages:
            if msg.get("role") != "system":
                assert "Solutions (#S):" not in msg.get("content", ""), \
                    "No bullets should be injected when list empty"


class TestClearSession:
    """Tests for clear_session method."""

    @pytest.fixture
    def orchestrator(self, mock_redis, mock_kafka, mock_llm_client):
        """Create orchestrator for testing."""
        from core.session.infrastructure.bullet_cache import BulletCache
        from core.session.infrastructure.kafka_producer import SessionKafkaProducer

        return ConversationOrchestrator(
            bullet_cache=BulletCache(mock_redis),
            kafka_producer=MagicMock(spec=SessionKafkaProducer),
            llm_client=mock_llm_client,
        )

    def test_clears_session_state(self, orchestrator):
        """Should clear all session-specific state."""
        session_id = str(uuid4())

        # Add some state
        orchestrator._session_bullets_shown[session_id] = {"bullet-1", "bullet-2"}
        orchestrator._session_cluster_ids[session_id] = "cluster-123"

        orchestrator.clear_session(session_id)

        assert session_id not in orchestrator._session_bullets_shown
        assert session_id not in orchestrator._session_cluster_ids

    def test_handles_nonexistent_session(self, orchestrator):
        """Should not raise error for unknown session."""
        # Should not raise
        orchestrator.clear_session("nonexistent-session")
