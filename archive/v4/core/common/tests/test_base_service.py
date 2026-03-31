"""Unit tests for BaseService class.

Tests the event handling wrapper with metrics and logging.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_event():
    """Create a mock Kafka event."""
    event = MagicMock()
    event.event_type = "test.event"
    event.payload = {"session_id": "test-session-123"}
    event.correlation_id = "corr-123"
    return event


@pytest.fixture
def base_service():
    """Create a BaseService instance with mocked dependencies."""
    with patch("core.common.base_service.setup_logging") as mock_logging:
        mock_logging.return_value = MagicMock()

        from core.common.base_service import BaseService

        class TestService(BaseService):
            def _get_topics(self):
                return ["test.topic"]

            async def _handle_event(self, event):
                pass

        service = TestService("test-service")
        service.pool = AsyncMock()
        service.kafka = AsyncMock()
        yield service


# ============================================================================
# Test: Event Processing Wrapper
# ============================================================================


class TestEventProcessingWrapper:
    """Tests for _handle_event_wrapper method."""

    @pytest.mark.asyncio
    async def test_logs_event_received(self, base_service, mock_event):
        """Should log when event is received."""
        await base_service._handle_event_wrapper(mock_event)

        base_service.logger.info.assert_any_call(
            "event_received",
            event_type="test.event",
            session_id="test-session-123"
        )

    @pytest.mark.asyncio
    async def test_logs_event_processed_on_success(self, base_service, mock_event):
        """Should log when event is successfully processed."""
        await base_service._handle_event_wrapper(mock_event)

        # Find the event_processed call
        calls = [c for c in base_service.logger.info.call_args_list
                 if c[0][0] == "event_processed"]
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_includes_duration_in_success_log(self, base_service, mock_event):
        """Success log should include duration_ms."""
        await base_service._handle_event_wrapper(mock_event)

        calls = [c for c in base_service.logger.info.call_args_list
                 if c[0][0] == "event_processed"]
        assert len(calls) == 1
        assert "duration_ms" in calls[0][1]

    @pytest.mark.asyncio
    async def test_logs_warning_on_retryable_error(self, base_service, mock_event):
        """Should log warning for retryable errors."""
        from core.common.errors import RetryableError

        async def failing_handler(event):
            raise RetryableError("Temporary failure")

        base_service._handle_event = failing_handler

        with pytest.raises(RetryableError):
            await base_service._handle_event_wrapper(mock_event)

        base_service.logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_logs_error_on_fatal_error(self, base_service, mock_event):
        """Should log error for non-retryable errors."""
        async def failing_handler(event):
            raise ValueError("Fatal failure")

        base_service._handle_event = failing_handler

        with pytest.raises(ValueError):
            await base_service._handle_event_wrapper(mock_event)

        base_service.logger.error.assert_called()


# ============================================================================
# Test: Metrics Recording
# ============================================================================


class TestMetricsRecording:
    """Tests for Prometheus metrics recording in event wrapper."""

    @pytest.mark.asyncio
    async def test_increments_events_processed_on_success(self, base_service, mock_event):
        """EVENTS_PROCESSED should increment with status=success."""
        with patch("core.common.base_service.EVENTS_PROCESSED") as mock_counter:
            await base_service._handle_event_wrapper(mock_event)

            mock_counter.labels.assert_called_with(
                service="test-service",
                event_type="test.event",
                status="success"
            )
            mock_counter.labels.return_value.inc.assert_called()

    @pytest.mark.asyncio
    async def test_records_event_duration_on_success(self, base_service, mock_event):
        """EVENT_DURATION should record processing time."""
        with patch("core.common.base_service.EVENT_DURATION") as mock_histogram:
            await base_service._handle_event_wrapper(mock_event)

            mock_histogram.labels.assert_called_with(
                service="test-service",
                event_type="test.event"
            )
            mock_histogram.labels.return_value.observe.assert_called()

    @pytest.mark.asyncio
    async def test_increments_events_processed_retry_on_retryable(self, base_service, mock_event):
        """EVENTS_PROCESSED should increment with status=retry on RetryableError."""
        from core.common.errors import RetryableError

        async def failing_handler(event):
            raise RetryableError("Temporary")

        base_service._handle_event = failing_handler

        with patch("core.common.base_service.EVENTS_PROCESSED") as mock_counter:
            with pytest.raises(RetryableError):
                await base_service._handle_event_wrapper(mock_event)

            mock_counter.labels.assert_called_with(
                service="test-service",
                event_type="test.event",
                status="retry"
            )

    @pytest.mark.asyncio
    async def test_increments_events_processed_error_on_fatal(self, base_service, mock_event):
        """EVENTS_PROCESSED should increment with status=error on fatal errors."""
        async def failing_handler(event):
            raise ValueError("Fatal")

        base_service._handle_event = failing_handler

        with patch("core.common.base_service.EVENTS_PROCESSED") as mock_counter:
            with pytest.raises(ValueError):
                await base_service._handle_event_wrapper(mock_event)

            mock_counter.labels.assert_called_with(
                service="test-service",
                event_type="test.event",
                status="error"
            )

    @pytest.mark.asyncio
    async def test_increments_errors_counter_with_correct_labels(self, base_service, mock_event):
        """ERRORS counter should record error_type and retryable flag."""
        from core.common.errors import RetryableError

        async def failing_handler(event):
            raise RetryableError("Temporary")

        base_service._handle_event = failing_handler

        with patch("core.common.base_service.ERRORS") as mock_counter:
            with pytest.raises(RetryableError):
                await base_service._handle_event_wrapper(mock_event)

            mock_counter.labels.assert_called_with(
                service="test-service",
                error_type="RetryableError",
                retryable="true"
            )


# ============================================================================
# Test: Health Check
# ============================================================================


class TestHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_returns_postgres_ok_when_healthy(self, base_service):
        """Should return postgres=ok when database is healthy."""
        base_service.pool.fetchval = AsyncMock(return_value=1)

        result = await base_service.health_check()

        assert result["checks"]["postgres"] == "ok"
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_returns_postgres_error_when_unhealthy(self, base_service):
        """Should return postgres=error when database query fails."""
        import asyncpg
        base_service.pool.fetchval = AsyncMock(
            side_effect=asyncpg.PostgresError("Connection failed")
        )

        result = await base_service.health_check()

        assert result["checks"]["postgres"] == "error"
        assert result["status"] == "unhealthy"


# ============================================================================
# Test: Structured Log Fields
# ============================================================================


class TestStructuredLogFields:
    """Tests for structured log field consistency."""

    @pytest.mark.asyncio
    async def test_error_log_includes_error_type(self, base_service, mock_event):
        """Error logs should include error_type field."""
        async def failing_handler(event):
            raise ValueError("Test error")

        base_service._handle_event = failing_handler

        with pytest.raises(ValueError):
            await base_service._handle_event_wrapper(mock_event)

        # Check error log call
        error_calls = base_service.logger.error.call_args_list
        assert len(error_calls) > 0
        kwargs = error_calls[0][1]
        assert "error_type" in kwargs
        assert kwargs["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_error_log_includes_error_message(self, base_service, mock_event):
        """Error logs should include error_message field."""
        async def failing_handler(event):
            raise ValueError("Specific error message")

        base_service._handle_event = failing_handler

        with pytest.raises(ValueError):
            await base_service._handle_event_wrapper(mock_event)

        error_calls = base_service.logger.error.call_args_list
        kwargs = error_calls[0][1]
        assert "error_message" in kwargs
        assert kwargs["error_message"] == "Specific error message"

    @pytest.mark.asyncio
    async def test_all_logs_include_session_id(self, base_service, mock_event):
        """All logs should include session_id from event payload."""
        await base_service._handle_event_wrapper(mock_event)

        for call in base_service.logger.info.call_args_list:
            kwargs = call[1]
            assert kwargs.get("session_id") == "test-session-123"
