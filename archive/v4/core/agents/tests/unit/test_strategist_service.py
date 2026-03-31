"""Unit tests for StrategistService.

Tests event routing, handler logic, synthesis, deduplication, and error handling.
Enhanced as part of gap-019 Phase 4: Learning System Reliability.
Updated for information-based synthesis (no time-based cooldowns).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.agents.strategist.service import (
    StrategistService,
    SynthesisAttempt,
)
from core.common.kafka_client import Event


class TestStrategistService:
    """Tests for StrategistService synthesis logic."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        svc = StrategistService()
        svc.pool = AsyncMock()
        svc.kafka = AsyncMock()
        svc.logger = MagicMock()
        svc._llm_client = AsyncMock()
        svc._embedding_client = AsyncMock()
        svc._require_pool = MagicMock(return_value=svc.pool)
        return svc

    @pytest.mark.asyncio
    async def test_should_synthesize_no_hypothesis(self, service):
        """Test that synthesis allowed when no untested hypothesis exists."""
        service.pool.fetchval = AsyncMock(return_value=False)

        result = await service._should_synthesize("test-cluster-id")
        assert result is True

    @pytest.mark.asyncio
    async def test_should_synthesize_with_untested_hypothesis(self, service):
        """Test that synthesis skipped when untested hypothesis exists."""
        service.pool.fetchval = AsyncMock(return_value=True)

        result = await service._should_synthesize("test-cluster-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_synthesize_on_db_error(self, service):
        """Test that synthesis allowed on database error (fail open)."""
        service.pool.fetchval = AsyncMock(side_effect=Exception("DB error"))

        result = await service._should_synthesize("test-cluster-id")
        assert result is True
        service.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_event_routes_gap(self, service):
        """Test that gap events are routed correctly."""
        event = MagicMock()
        event.event_type = "library.gap.detected"

        with patch.object(service, '_handle_gap', new_callable=AsyncMock) as mock_handler:
            await service._handle_event(event)
            mock_handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_handle_event_routes_struggling(self, service):
        """Test that struggling events are routed correctly."""
        event = MagicMock()
        event.event_type = "library.cluster.struggling"

        with patch.object(service, '_handle_struggling', new_callable=AsyncMock) as mock_handler:
            await service._handle_event(event)
            mock_handler.assert_called_once_with(event)

    def test_get_topics(self, service):
        """Test that service subscribes to correct topics."""
        topics = service._get_topics()
        assert "library.gap.detected" in topics
        assert "library.cluster.struggling" in topics


class TestEmbeddingHelper:
    """Tests for embedding conversion helper."""

    def test_embedding_to_str_from_list(self):
        """Test converting list embedding to string."""
        from core.agents.strategist.service import _embedding_to_str

        result = _embedding_to_str([0.1, 0.2, 0.3])
        assert result == "[0.1,0.2,0.3]"

    def test_embedding_to_str_from_string(self):
        """Test that string embedding passes through."""
        from core.agents.strategist.service import _embedding_to_str

        result = _embedding_to_str("[0.1,0.2,0.3]")
        assert result == "[0.1,0.2,0.3]"


class TestHandleGap:
    """Tests for _handle_gap handler with real event payloads."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(StrategistService, "__init__", lambda self: None):
            svc = StrategistService()
            svc.service_name = "strategist"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._llm_client = AsyncMock()
            svc._embedding_client = MagicMock()
            svc._synthesis_attempts = {}
            svc._record_event_drop = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.fixture
    def gap_event(self) -> Event:
        """Create valid gap.detected event."""
        return Event(
            event_id=str(uuid4()),
            event_type="library.gap.detected",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "cluster_id": str(uuid4()),
                "cluster_label": "API pagination issues",
                "domain": "spotify",
                "failure_count": 10,
                "success_count": 0,
                "sample_turns": [
                    {
                        "sub_task": "Get playlist items",
                        "micro_outcome": "error",
                        "user_message": "Get all songs",
                        "assistant_response": "Error getting songs",
                    }
                ],
            },
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_drops_event_without_cluster_id(self, service: StrategistService):
        """Events without cluster_id should be dropped."""
        event = Event(
            event_id=str(uuid4()),
            event_type="library.gap.detected",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "cluster_label": "Test",
                "failure_count": 5,
            },
            metadata={},
        )

        await service._handle_gap(event)

        service._record_event_drop.assert_called_once()
        assert "missing_cluster_id" in str(service._record_event_drop.call_args)

    @pytest.mark.asyncio
    async def test_skips_synthesis_with_untested_hypothesis(self, service: StrategistService, gap_event: Event):
        """Should skip synthesis when untested hypothesis exists for cluster."""
        with patch.object(service, "_should_synthesize", new_callable=AsyncMock) as mock_should:
            mock_should.return_value = False  # Untested hypothesis exists

            await service._handle_gap(gap_event)

            service._record_event_drop.assert_called_once()
            assert "untested_hypothesis_exists" in str(service._record_event_drop.call_args)

    @pytest.mark.asyncio
    async def test_synthesizes_and_emits_aku(self, service: StrategistService, gap_event: Event):
        """Successful flow: synthesize -> check dedup -> emit aku."""
        synthesized_aku = {
            "situation": "When iterating through paginated responses",
            "assertion": "Use offset=0 for first page and increment until empty",
        }

        with patch.object(service, "_should_synthesize", new_callable=AsyncMock) as mock_should:
            mock_should.return_value = True  # No untested hypothesis

            with patch.object(service, "_synthesize", new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = synthesized_aku

                with patch.object(service, "_check_duplicate", new_callable=AsyncMock) as mock_dedup:
                    mock_dedup.return_value = False

                    await service._handle_gap(gap_event)

                    mock_synth.assert_called_once()
                    mock_dedup.assert_called_once()
                    service.kafka.publish_event.assert_called_once()

                    # Verify event structure
                    call_kwargs = service.kafka.publish_event.call_args[1]
                    assert call_kwargs["topic"] == "aku.proposed"
                    assert call_kwargs["payload"]["source"] == "strategist"
                    assert call_kwargs["payload"]["aku"] == synthesized_aku

    @pytest.mark.asyncio
    async def test_drops_on_duplicate_detected(self, service: StrategistService, gap_event: Event):
        """Should drop when duplicate assertion exists."""
        with patch.object(service, "_should_synthesize", new_callable=AsyncMock) as mock_should:
            mock_should.return_value = True

            with patch.object(service, "_synthesize", new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {
                    "situation": "When doing X with the API",
                    "assertion": "Do Y this is a longer assertion that is valid",
                }

                with patch.object(service, "_check_duplicate", new_callable=AsyncMock) as mock_dedup:
                    mock_dedup.return_value = True  # Duplicate found

                    await service._handle_gap(gap_event)

                    service._record_event_drop.assert_called_once()
                    assert "duplicate_detected" in str(service._record_event_drop.call_args)
                    service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_drops_on_synthesis_failure(self, service: StrategistService, gap_event: Event):
        """Should drop when synthesis fails."""
        with patch.object(service, "_should_synthesize", new_callable=AsyncMock) as mock_should:
            mock_should.return_value = True

            with patch.object(service, "_synthesize", new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = None

                await service._handle_gap(gap_event)

                service._record_event_drop.assert_called_once()
                assert "synthesis_failed" in str(service._record_event_drop.call_args)


class TestHandleStruggling:
    """Tests for _handle_struggling handler."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(StrategistService, "__init__", lambda self: None):
            svc = StrategistService()
            svc.service_name = "strategist"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._llm_client = AsyncMock()
            svc._embedding_client = MagicMock()
            svc._synthesis_attempts = {}
            svc._record_event_drop = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.fixture
    def struggling_event(self) -> Event:
        """Create valid struggling cluster event."""
        return Event(
            event_id=str(uuid4()),
            event_type="library.cluster.struggling",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "cluster_id": str(uuid4()),
                "cluster_label": "Date formatting issues",
                "domain": "spotify",
                "success_rate": 0.30,
                "turn_count": 20,
                "existing_solutions": [
                    {"assertion": "Use datetime.strptime for parsing"},
                ],
                "sample_failures": [
                    {
                        "sub_task": "Format date",
                        "micro_outcome": "error",
                        "user_message": "Format this date",
                        "assistant_response": "Error formatting",
                    }
                ],
            },
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_synthesizes_alternative_solution(self, service: StrategistService, struggling_event: Event):
        """Should synthesize alternative solution for struggling cluster."""
        synthesized_aku = {
            "situation": "When formatting dates from various sources",
            "assertion": "Use dateutil.parser.parse for more flexible date parsing",
        }

        with patch.object(service, "_should_synthesize", new_callable=AsyncMock) as mock_should:
            mock_should.return_value = True  # No untested hypothesis

            with patch.object(service, "_synthesize", new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = synthesized_aku

                with patch.object(service, "_check_duplicate", new_callable=AsyncMock) as mock_dedup:
                    mock_dedup.return_value = False

                    await service._handle_struggling(struggling_event)

                    mock_synth.assert_called_once()
                    service.kafka.publish_event.assert_called_once()


class TestSynthesizeMethod:
    """Tests for _synthesize LLM call method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(StrategistService, "__init__", lambda self: None):
            svc = StrategistService()
            svc.service_name = "strategist"
            svc.logger = MagicMock()
            svc._llm_client = AsyncMock()
            return svc

    @pytest.mark.asyncio
    async def test_returns_parsed_aku(self, service: StrategistService):
        """Should parse LLM response into AKU (v4 format - no modality/polarity)."""
        # v4 format: only SITUATION (≤60 chars) and ASSERTION (≤100 chars)
        llm_response = """---AKU---
SITUATION: When iterating through paginated responses
ASSERTION: Use offset=0 for first page. Loop until response length < page_size.
---END---
"""
        service._llm_client.chat = AsyncMock(return_value=llm_response)

        result = await service._synthesize("Test prompt")

        assert result is not None
        assert "situation" in result
        assert "assertion" in result
        # v4: No modality/polarity
        assert "modality" not in result
        assert "polarity" not in result

    @pytest.mark.asyncio
    async def test_returns_none_on_llm_error(self, service: StrategistService):
        """Should return None when LLM call fails."""
        service._llm_client.chat = AsyncMock(side_effect=Exception("LLM error"))

        result = await service._synthesize("Test prompt")

        assert result is None
        service.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_llm_client(self, service: StrategistService):
        """Should return None when LLM client not initialized."""
        service._llm_client = None

        result = await service._synthesize("Test prompt")

        assert result is None
        service.logger.error.assert_called_once()


class TestValidateAku:
    """Tests for _validate_aku method (v4 format)."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        svc = StrategistService()
        svc.logger = MagicMock()
        return svc

    def test_validates_correct_aku(self, service: StrategistService):
        """Should return True for valid AKU (v4 - no modality/polarity)."""
        aku = {
            "situation": "When paginating through API responses",
            "assertion": "Use offset=0 for the first page and increment by page_size",
        }

        result = service._validate_aku(aku)

        assert result is True

    def test_rejects_short_situation(self, service: StrategistService):
        """Should reject AKU with situation < 10 chars."""
        aku = {
            "situation": "When X",
            "assertion": "Do something very specific here",
        }

        result = service._validate_aku(aku)

        assert result is False

    def test_rejects_short_assertion(self, service: StrategistService):
        """Should reject AKU with assertion < 20 chars."""
        aku = {
            "situation": "When paginating through API responses",
            "assertion": "Do X",
        }

        result = service._validate_aku(aku)

        assert result is False

    def test_rejects_long_situation(self, service: StrategistService):
        """Should reject AKU with situation > 60 chars (v4 constraint)."""
        aku = {
            "situation": "When paginating through API responses with very long situation descriptions that exceed the limit",
            "assertion": "Use offset=0 for the first page and increment by page_size",
        }

        result = service._validate_aku(aku)

        assert result is False
        service.logger.warning.assert_called_once()

    def test_rejects_long_assertion(self, service: StrategistService):
        """Should reject AKU with assertion > 100 chars (v4 constraint)."""
        aku = {
            "situation": "When paginating through API responses",
            "assertion": "Use offset=0 for the first page and increment by page_size each time until you get an empty response or a response with fewer items than page_size",
        }

        result = service._validate_aku(aku)

        assert result is False
        service.logger.warning.assert_called_once()


class TestCheckDuplicate:
    """Tests for _check_duplicate deduplication method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(StrategistService, "__init__", lambda self: None):
            svc = StrategistService()
            svc.service_name = "strategist"
            svc.pool = AsyncMock()
            svc.logger = MagicMock()
            svc._embedding_client = MagicMock()
            return svc

    @pytest.mark.asyncio
    async def test_returns_true_when_duplicate_found(self, service: StrategistService):
        """Should return True when similar assertion exists."""
        service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)
        service.pool.fetchrow = AsyncMock(return_value={"bullet_id": uuid4()})

        result = await service._check_duplicate("Test assertion")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_duplicate(self, service: StrategistService):
        """Should return False when no similar assertion exists."""
        service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)
        service.pool.fetchrow = AsyncMock(return_value=None)

        result = await service._check_duplicate("Test assertion")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self, service: StrategistService):
        """Should return False and log warning on error."""
        service._embedding_client.embed = MagicMock(side_effect=Exception("Embed error"))

        result = await service._check_duplicate("Test assertion")

        assert result is False
        service.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_initialized(self, service: StrategistService):
        """Should return False when embedding client not initialized."""
        service._embedding_client = None

        result = await service._check_duplicate("Test assertion")

        assert result is False


class TestFormatTurns:
    """Tests for _format_turns helper method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return StrategistService()

    def test_formats_turns_correctly(self, service: StrategistService):
        """Should format turns with task, outcome, and content."""
        turns = [
            {
                "sub_task": "Get playlist",
                "micro_outcome": "error",
                "user_message": "Get my playlist",
                "assistant_response": "Error getting playlist",
            }
        ]

        result = service._format_turns(turns)

        assert "Get playlist" in result
        assert "error" in result
        assert "Get my playlist" in result

    def test_handles_empty_turns(self, service: StrategistService):
        """Should return placeholder for empty turns."""
        result = service._format_turns([])

        assert "No sample turns available" in result

    def test_limits_to_three_turns(self, service: StrategistService):
        """Should only format first 3 turns."""
        turns = [
            {"sub_task": f"Task {i}", "micro_outcome": "stuck"}
            for i in range(5)
        ]

        result = service._format_turns(turns)

        assert "Task 0" in result
        assert "Task 2" in result
        assert "Task 4" not in result

    def test_truncates_long_content(self, service: StrategistService):
        """Should truncate long user messages and responses."""
        turns = [
            {
                "sub_task": "Test",
                "micro_outcome": "error",
                "user_message": "X" * 3000,  # Exceeds 2000 limit
                "assistant_response": "Y" * 4000,  # Exceeds 3000 limit
            }
        ]

        result = service._format_turns(turns)

        # Should contain truncated content (2000 for user, 3000 for assistant)
        # Total: ~5000 chars for content + ~50 for labels
        assert len(result) < 5200
        assert "X" * 2000 in result
        assert "Y" * 3000 in result


class TestRecordAttempt:
    """Tests for _record_attempt tracking method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        svc = StrategistService()
        svc._synthesis_attempts = {}
        return svc

    def test_records_successful_attempt(self, service: StrategistService):
        """Should record successful synthesis attempt."""
        cluster_id = str(uuid4())

        service._record_attempt(cluster_id, success=True, failure_count=10)

        assert cluster_id in service._synthesis_attempts
        assert service._synthesis_attempts[cluster_id].success is True
        assert service._synthesis_attempts[cluster_id].failure_count_at_attempt == 10

    def test_records_failed_attempt(self, service: StrategistService):
        """Should record failed synthesis attempt."""
        cluster_id = str(uuid4())

        service._record_attempt(cluster_id, success=False, failure_count=5)

        assert cluster_id in service._synthesis_attempts
        assert service._synthesis_attempts[cluster_id].success is False

    def test_cleans_up_old_entries(self, service: StrategistService):
        """Should cleanup old entries when over 200."""
        # Add 201 entries
        for i in range(201):
            service._synthesis_attempts[str(i)] = SynthesisAttempt(
                timestamp=float(i),
                success=True,
                failure_count_at_attempt=0,
            )

        # Record new attempt (triggers cleanup)
        service._record_attempt("new-cluster", success=True, failure_count=0)

        # Should have been cleaned up to ~100 entries
        assert len(service._synthesis_attempts) <= 101


class TestHandleComparative:
    """Tests for _handle_comparative handler (cross-session task analysis)."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(StrategistService, "__init__", lambda self: None):
            svc = StrategistService()
            svc.service_name = "strategist"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._llm_client = AsyncMock()
            svc._embedding_client = MagicMock()
            svc._synthesis_attempts = {}
            svc._record_event_drop = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.fixture
    def comparative_event(self) -> Event:
        """Create valid task comparative event."""
        return Event(
            event_id=str(uuid4()),
            event_type="library.task.comparative",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "task_description": "What is the title of the least-played song in my Spotify library",
                "success_rate": 35.7,
                "successes": 5,
                "failures": 9,
                "total_sessions": 14,
                "success_snippet": "I'll use show_song() to get the GLOBAL play_count...",
                "failure_snippet": "I'll use show_song_privates() to get play_count...",
                "differential_bullets": [
                    {"bullet_id": str(uuid4()), "content": "Use show_song_privates for play_count"},
                ],
            },
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_synthesizes_clarifying_aku(self, service: StrategistService, comparative_event: Event):
        """Should synthesize clarifying AKU from comparative analysis."""
        synthesized_aku = {
            "situation": "When finding the least-played song",
            "assertion": "Use show_song() for GLOBAL play_count, not show_song_privates() for USER count",
        }

        with patch.object(service, "_synthesize_comparative", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = synthesized_aku

            with patch.object(service, "_check_duplicate", new_callable=AsyncMock) as mock_dedup:
                mock_dedup.return_value = False

                await service._handle_comparative(comparative_event)

                mock_synth.assert_called_once()
                mock_dedup.assert_called_once()
                service.kafka.publish_event.assert_called_once()

                # Verify event structure - CRITICAL: source must be "strategist" not "strategist-comparative"
                call_kwargs = service.kafka.publish_event.call_args[1]
                assert call_kwargs["topic"] == "aku.proposed"
                assert call_kwargs["payload"]["source"] == "strategist"  # Must match DB constraint
                assert call_kwargs["payload"]["aku"] == synthesized_aku

    @pytest.mark.asyncio
    async def test_drops_on_duplicate_detected(self, service: StrategistService, comparative_event: Event):
        """Should drop when duplicate assertion exists."""
        synthesized_aku = {
            "situation": "When finding least-played song in library",
            "assertion": "Use show_song() for GLOBAL play_count instead of privates",
        }

        with patch.object(service, "_synthesize_comparative", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = synthesized_aku

            with patch.object(service, "_check_duplicate", new_callable=AsyncMock) as mock_dedup:
                mock_dedup.return_value = True  # Duplicate found

                await service._handle_comparative(comparative_event)

                service._record_event_drop.assert_called_once()
                assert "duplicate_detected" in str(service._record_event_drop.call_args)
                service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_drops_on_synthesis_failure(self, service: StrategistService, comparative_event: Event):
        """Should drop when synthesis fails."""
        with patch.object(service, "_synthesize_comparative", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = None  # Synthesis failed

            await service._handle_comparative(comparative_event)

            service._record_event_drop.assert_called_once()
            assert "synthesis_failed" in str(service._record_event_drop.call_args)
            service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_drops_on_missing_task_description(self, service: StrategistService):
        """Should drop when task_description is missing."""
        event = Event(
            event_id=str(uuid4()),
            event_type="library.task.comparative",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "success_rate": 35.7,
                # Missing task_description
            },
            metadata={},
        )

        await service._handle_comparative(event)

        service._record_event_drop.assert_called_once()
        service.kafka.publish_event.assert_not_called()
