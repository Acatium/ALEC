"""Unit tests for LibrarianService.

Tests event routing, gap detection, struggling detection, and auto-archive.
Enhanced as part of gap-019 Phase 4: Learning System Reliability.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.agents.librarian.service import LibrarianService
from core.common.kafka_client import Event


class TestLibrarianService:
    """Tests for LibrarianService gap detection and hygiene."""

    @pytest.fixture
    def mock_pool(self):
        """Create mock database pool."""
        pool = AsyncMock()
        pool.fetch = AsyncMock(return_value=[])
        pool.fetchval = AsyncMock(return_value=None)
        pool.execute = AsyncMock(return_value="UPDATE 0")
        return pool

    @pytest.fixture
    def mock_kafka(self):
        """Create mock Kafka client."""
        kafka = AsyncMock()
        kafka.publish_event = AsyncMock()
        return kafka

    @pytest.fixture
    def service(self, mock_pool, mock_kafka):
        """Create service with mocked dependencies."""
        svc = LibrarianService()
        svc.pool = mock_pool
        svc.kafka = mock_kafka
        svc.logger = MagicMock()
        return svc

    @pytest.mark.asyncio
    async def test_detect_gaps_no_gaps(self, service, mock_pool):
        """Test gap detection when no gaps exist."""
        mock_pool.fetch.return_value = []

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        await service._detect_gaps(event)

        # Should query for gaps but not publish any events
        mock_pool.fetch.assert_called_once()
        service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_gaps_with_gap(self, service, mock_pool, mock_kafka):
        """Test gap detection when gaps exist."""
        # Mock a gap cluster
        gap = {
            "cluster_id": "test-cluster-id",
            "label": "API pagination issues",
            "failure_count": 5,
            "success_count": 0,
            "domain": "test",
        }
        mock_pool.fetch.side_effect = [
            [gap],  # First call returns the gap
            [],     # Second call (sample turns) returns empty
        ]

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        await service._detect_gaps(event)

        # Should publish gap.detected event
        mock_kafka.publish_event.assert_called_once()
        call_args = mock_kafka.publish_event.call_args
        assert call_args.kwargs["topic"] == "library.gap.detected"
        assert call_args.kwargs["payload"]["cluster_id"] == "test-cluster-id"

    @pytest.mark.asyncio
    async def test_auto_archive_harmful_no_bullets(self, service, mock_pool):
        """Test auto-archive when no harmful bullets exist."""
        mock_pool.execute.return_value = "UPDATE 0"

        await service._auto_archive_harmful()

        mock_pool.execute.assert_called_once()
        # Logger should not log archived count
        service.logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_archive_harmful_with_bullets(self, service, mock_pool):
        """Test auto-archive when harmful bullets exist."""
        mock_pool.execute.return_value = "UPDATE 3"

        await service._auto_archive_harmful()

        mock_pool.execute.assert_called_once()
        service.logger.info.assert_called_once_with(
            "harmful_bullets_archived", count=3
        )

    @pytest.mark.asyncio
    async def test_get_sample_turns_with_outcome_filter(self, service, mock_pool):
        """Test sample turns retrieval with outcome filter."""
        mock_pool.fetch.return_value = [
            {
                "turn_id": "turn-1",
                "session_id": "session-1",
                "sub_task": "Test task",
                "micro_outcome": "error",
                "user_message": "Help me",
                "assistant_response": "Sorry, I can't",
            }
        ]

        result = await service._get_sample_turns(
            "cluster-id", outcome="error", limit=3
        )

        assert len(result) == 1
        assert result[0]["micro_outcome"] == "error"
        # Verify parameterized query (limit is a parameter, not f-string)
        call_args = mock_pool.fetch.call_args
        assert call_args[0][0].count("$") == 3  # cluster_id, outcome, limit

    @pytest.mark.asyncio
    async def test_cooldown_prevents_repeated_analysis(self, service):
        """Test that cooldown prevents rapid repeated analysis."""
        event = MagicMock()
        event.payload = {"domain": "test"}

        # First analysis should run
        service._last_analysis = None
        with patch.object(service, '_detect_gaps', new_callable=AsyncMock) as mock_detect:
            with patch.object(service, '_detect_struggling', new_callable=AsyncMock):
                with patch.object(service, '_auto_archive_harmful', new_callable=AsyncMock):
                    await service._maybe_run_analysis(event)
                    mock_detect.assert_called_once()

        # Second immediate call should be skipped (cooldown)
        service._last_analysis = datetime.now(timezone.utc)
        with patch.object(service, '_detect_gaps', new_callable=AsyncMock) as mock_detect:
            await service._maybe_run_analysis(event)
            mock_detect.assert_not_called()


class TestEventRouting:
    """Tests for event dispatch to handlers."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._last_analysis = None
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.mark.asyncio
    async def test_routes_attribution_resolved(self, service: LibrarianService):
        """attribution.resolved events should trigger analysis."""
        event = Event(
            event_id=str(uuid4()),
            event_type="attribution.resolved",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4()), "domain": "spotify"},
            metadata={},
        )

        with patch.object(service, "_maybe_run_analysis", new_callable=AsyncMock) as mock_analysis:
            await service._handle_event(event)
            mock_analysis.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self, service: LibrarianService):
        """Unrelated event types should be ignored."""
        event = Event(
            event_id=str(uuid4()),
            event_type="session.created",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4())},
            metadata={},
        )

        with patch.object(service, "_maybe_run_analysis", new_callable=AsyncMock) as mock_analysis:
            await service._handle_event(event)
            mock_analysis.assert_not_called()


class TestDetectStruggling:
    """Tests for _detect_struggling method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.mark.asyncio
    async def test_detect_struggling_no_clusters(self, service: LibrarianService):
        """Should not emit events when no struggling clusters."""
        service.pool.fetch.return_value = []

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        await service._detect_struggling(event)

        service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_struggling_with_cluster(self, service: LibrarianService):
        """Should emit events for struggling clusters."""
        struggling = {
            "cluster_id": "test-cluster-id",
            "label": "Date formatting",
            "success_count": 2,
            "failure_count": 8,
            "success_rate": 0.2,
        }

        service.pool.fetch.side_effect = [
            [struggling],  # First call: struggling clusters
            [],            # Second call: existing solutions
            [],            # Third call: sample failures
        ]

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        await service._detect_struggling(event)

        service.kafka.publish_event.assert_called_once()
        call_kwargs = service.kafka.publish_event.call_args[1]
        assert call_kwargs["topic"] == "library.cluster.struggling"
        assert call_kwargs["payload"]["cluster_id"] == "test-cluster-id"
        assert call_kwargs["payload"]["success_rate"] == 0.2

    @pytest.mark.asyncio
    async def test_detect_struggling_handles_error(self, service: LibrarianService):
        """Should log error and continue on database error."""
        service.pool.fetch.side_effect = Exception("DB error")

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        # Should not raise
        await service._detect_struggling(event)

        service.logger.error.assert_called_once()


class TestGetClusterSolutions:
    """Tests for _get_cluster_solutions helper."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.logger = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            return svc

    @pytest.mark.asyncio
    async def test_returns_solutions(self, service: LibrarianService):
        """Should return formatted solutions."""
        service.pool.fetch.return_value = [
            {
                "bullet_id": uuid4(),
                "situation": "When paginating",
                "assertion": "Use offset=0" + "x" * 300,  # Long assertion
            }
        ]

        result = await service._get_cluster_solutions(str(uuid4()))

        assert len(result) == 1
        assert "bullet_id" in result[0]
        assert "situation" in result[0]
        assert len(result[0]["assertion"]) == 200  # Truncated

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, service: LibrarianService):
        """Should return empty list and log warning on error."""
        service.pool.fetch.side_effect = Exception("DB error")

        result = await service._get_cluster_solutions(str(uuid4()))

        assert result == []
        service.logger.warning.assert_called_once()


class TestMaybeRunAnalysis:
    """Tests for _maybe_run_analysis cooldown logic."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._last_analysis = None
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.mark.asyncio
    async def test_runs_all_analysis_types(self, service: LibrarianService):
        """Should run gap, struggling, and archive analysis."""
        event = MagicMock()
        event.payload = {"domain": "test"}

        with patch.object(service, "_detect_gaps", new_callable=AsyncMock) as mock_gaps:
            with patch.object(service, "_detect_struggling", new_callable=AsyncMock) as mock_struggling:
                with patch.object(service, "_auto_archive_harmful", new_callable=AsyncMock) as mock_archive:
                    await service._maybe_run_analysis(event)

                    mock_gaps.assert_called_once()
                    mock_struggling.assert_called_once()
                    mock_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_last_analysis_timestamp(self, service: LibrarianService):
        """Should update _last_analysis after running."""
        event = MagicMock()
        event.payload = {"domain": "test"}

        assert service._last_analysis is None

        with patch.object(service, "_detect_gaps", new_callable=AsyncMock):
            with patch.object(service, "_detect_struggling", new_callable=AsyncMock):
                with patch.object(service, "_auto_archive_harmful", new_callable=AsyncMock):
                    await service._maybe_run_analysis(event)

        assert service._last_analysis is not None


class TestAutoArchiveHarmful:
    """Tests for _auto_archive_harmful method."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.logger = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            return svc

    @pytest.mark.asyncio
    async def test_handles_non_update_result(self, service: LibrarianService):
        """Should handle result without UPDATE."""
        service.pool.execute.return_value = "COMMAND"

        await service._auto_archive_harmful()

        # Should not log (no count to extract)
        service.logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_database_error(self, service: LibrarianService):
        """Should log error on database failure."""
        service.pool.execute.side_effect = Exception("DB error")

        # Should not raise
        await service._auto_archive_harmful()

        service.logger.error.assert_called_once()


class TestDetectGapsErrors:
    """Tests for error handling in _detect_gaps."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.kafka = AsyncMock()
            svc.logger = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            svc._require_kafka = MagicMock(return_value=svc.kafka)
            return svc

    @pytest.mark.asyncio
    async def test_handles_database_error(self, service: LibrarianService):
        """Should log error and continue on database failure."""
        service.pool.fetch.side_effect = Exception("DB error")

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        # Should not raise
        await service._detect_gaps(event)

        service.logger.error.assert_called_once()
        service.kafka.publish_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_multiple_gaps(self, service: LibrarianService):
        """Should publish event for each detected gap."""
        gaps = [
            {
                "cluster_id": "cluster-1",
                "label": "Gap 1",
                "failure_count": 5,
                "success_count": 0,
                "domain": "test",
            },
            {
                "cluster_id": "cluster-2",
                "label": "Gap 2",
                "failure_count": 10,
                "success_count": 0,
                "domain": "test",
            },
        ]

        service.pool.fetch.side_effect = [
            gaps,  # First call: gaps query
            [],    # Second call: sample turns for gap 1
            [],    # Third call: sample turns for gap 2
        ]

        event = MagicMock()
        event.payload = {"domain": "test"}
        event.correlation_id = "test-123"

        await service._detect_gaps(event)

        assert service.kafka.publish_event.call_count == 2


class TestGetSampleTurns:
    """Tests for _get_sample_turns helper."""

    @pytest.fixture
    def service(self):
        """Create service with mocked dependencies."""
        with patch.object(LibrarianService, "__init__", lambda self: None):
            svc = LibrarianService()
            svc.service_name = "librarian"
            svc.pool = AsyncMock()
            svc.logger = MagicMock()
            svc._require_pool = MagicMock(return_value=svc.pool)
            return svc

    @pytest.mark.asyncio
    async def test_returns_formatted_turns(self, service: LibrarianService):
        """Should return formatted turn data."""
        service.pool.fetch.return_value = [
            {
                "turn_id": uuid4(),
                "session_id": uuid4(),
                "turn_number": 1,
                "sub_task": "Get playlist",
                "micro_outcome": "error",
                "user_message": "Get my playlist",
                "assistant_response": "Error getting playlist",
            }
        ]

        result = await service._get_sample_turns(str(uuid4()))

        assert len(result) == 1
        assert result[0]["sub_task"] == "Get playlist"
        assert result[0]["micro_outcome"] == "error"

    @pytest.mark.asyncio
    async def test_truncates_long_messages(self, service: LibrarianService):
        """Should truncate long user messages and responses."""
        service.pool.fetch.return_value = [
            {
                "turn_id": uuid4(),
                "session_id": uuid4(),
                "turn_number": 1,
                "sub_task": "Test",
                "micro_outcome": "error",
                "user_message": "X" * 3000,  # Exceeds 2000 limit
                "assistant_response": "Y" * 4000,  # Exceeds 3000 limit
            }
        ]

        result = await service._get_sample_turns(str(uuid4()))

        # Truncation limits: user_message=2000, assistant_response=3000
        assert len(result[0]["user_message"]) == 2000
        assert len(result[0]["assistant_response"]) == 3000

    @pytest.mark.asyncio
    async def test_handles_null_messages(self, service: LibrarianService):
        """Should handle null user messages and responses."""
        service.pool.fetch.return_value = [
            {
                "turn_id": uuid4(),
                "session_id": uuid4(),
                "turn_number": 1,
                "sub_task": "Test",
                "micro_outcome": "error",
                "user_message": None,
                "assistant_response": None,
            }
        ]

        result = await service._get_sample_turns(str(uuid4()))

        assert result[0]["user_message"] is None
        assert result[0]["assistant_response"] is None

    @pytest.mark.asyncio
    async def test_respects_outcome_filter(self, service: LibrarianService):
        """Should add outcome filter to query when provided."""
        service.pool.fetch.return_value = []

        await service._get_sample_turns(str(uuid4()), outcome="error", limit=5)

        # Verify parameterized query was called
        call_args = service.pool.fetch.call_args[0]
        assert "micro_outcome" in call_args[0]
        assert call_args[1] is not None  # cluster_id
        assert call_args[2] == "error"
        assert call_args[3] == 5
