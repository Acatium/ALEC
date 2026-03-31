"""Unit tests for observability module.

Tests structured logging setup and Prometheus metrics.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from unittest.mock import patch

# ============================================================================
# Test: Structured Logging Setup
# ============================================================================


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_returns_bound_logger(self):
        """setup_logging should return a structlog BoundLogger."""
        from core.common.observability import setup_logging

        logger = setup_logging("test-service")

        assert logger is not None
        # Should have service context bound
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'warning')

    def test_binds_service_name(self):
        """Logger should have service name bound to context."""
        from core.common.observability import setup_logging

        logger = setup_logging("my-test-service")

        # The service name is bound to the logger context
        # We can verify by checking the logger's bound values
        # structlog stores context in _context
        bound_context = getattr(logger, '_context', {})
        assert bound_context.get('service') == 'my-test-service'

    @patch.dict('os.environ', {'LOG_FORMAT': 'console'})
    def test_respects_log_format_env(self):
        """Should use console format when LOG_FORMAT=console."""
        from core.common.observability import setup_logging

        # This shouldn't crash
        logger = setup_logging("test-service")
        assert logger is not None

    @patch.dict('os.environ', {'LOG_LEVEL': 'DEBUG'})
    def test_respects_log_level_env(self):
        """Should use log level from LOG_LEVEL env var."""
        from core.common.observability import setup_logging

        logger = setup_logging("test-service")
        assert logger is not None


# ============================================================================
# Test: Prometheus Metrics Definitions
# ============================================================================


class TestMetricsDefinitions:
    """Tests for Prometheus metrics existence and configuration."""

    def test_events_processed_counter_exists(self):
        """EVENTS_PROCESSED counter should be defined."""
        from core.common.observability import EVENTS_PROCESSED

        assert EVENTS_PROCESSED is not None
        # prometheus_client stores name without _total suffix internally
        assert EVENTS_PROCESSED._name == 'alec_events_processed'

    def test_events_processed_has_correct_labels(self):
        """EVENTS_PROCESSED should have service, event_type, status labels."""
        from core.common.observability import EVENTS_PROCESSED

        labels = EVENTS_PROCESSED._labelnames
        assert 'service' in labels
        assert 'event_type' in labels
        assert 'status' in labels

    def test_event_duration_histogram_exists(self):
        """EVENT_DURATION histogram should be defined."""
        from core.common.observability import EVENT_DURATION

        assert EVENT_DURATION is not None
        assert EVENT_DURATION._name == 'alec_event_processing_seconds'

    def test_event_duration_has_correct_buckets(self):
        """EVENT_DURATION should have appropriate buckets for processing time."""
        from core.common.observability import EVENT_DURATION

        # Should have buckets from 10ms to 30s
        buckets = EVENT_DURATION._upper_bounds
        assert 0.01 in buckets or min(buckets) <= 0.01  # 10ms
        assert 30.0 in buckets or max(buckets) >= 30.0  # 30s

    def test_llm_calls_counter_exists(self):
        """LLM_CALLS counter should be defined."""
        from core.common.observability import LLM_CALLS

        assert LLM_CALLS is not None
        # prometheus_client stores name without _total suffix internally
        assert LLM_CALLS._name == 'alec_llm_calls'

    def test_llm_calls_has_service_status_labels(self):
        """LLM_CALLS should have service and status labels."""
        from core.common.observability import LLM_CALLS

        labels = LLM_CALLS._labelnames
        assert 'service' in labels
        assert 'status' in labels

    def test_llm_duration_histogram_exists(self):
        """LLM_DURATION histogram should be defined."""
        from core.common.observability import LLM_DURATION

        assert LLM_DURATION is not None
        assert LLM_DURATION._name == 'alec_llm_call_seconds'

    def test_llm_duration_has_high_buckets(self):
        """LLM_DURATION should have buckets up to 120s for slow calls."""
        from core.common.observability import LLM_DURATION

        buckets = LLM_DURATION._upper_bounds
        assert max(buckets) >= 60.0  # At least 60s for long LLM calls

    def test_akus_total_counter_exists(self):
        """AKUS_TOTAL counter should be defined."""
        from core.common.observability import AKUS_TOTAL

        assert AKUS_TOTAL is not None
        # prometheus_client stores name without _total suffix internally
        assert AKUS_TOTAL._name == 'alec_akus'

    def test_akus_total_has_source_status_labels(self):
        """AKUS_TOTAL should have source and status labels."""
        from core.common.observability import AKUS_TOTAL

        labels = AKUS_TOTAL._labelnames
        assert 'source' in labels
        assert 'status' in labels

    def test_bullets_retrieved_counter_exists(self):
        """BULLETS_RETRIEVED counter should be defined."""
        from core.common.observability import BULLETS_RETRIEVED

        assert BULLETS_RETRIEVED is not None
        # prometheus_client stores name without _total suffix internally
        assert BULLETS_RETRIEVED._name == 'alec_bullets_retrieved'

    def test_errors_counter_exists(self):
        """ERRORS counter should be defined."""
        from core.common.observability import ERRORS

        assert ERRORS is not None
        # prometheus_client stores name without _total suffix internally
        assert ERRORS._name == 'alec_errors'

    def test_errors_has_correct_labels(self):
        """ERRORS should have service, error_type, retryable labels."""
        from core.common.observability import ERRORS

        labels = ERRORS._labelnames
        assert 'service' in labels
        assert 'error_type' in labels
        assert 'retryable' in labels


# ============================================================================
# Test: Metrics Usage Patterns
# ============================================================================


class TestMetricsUsage:
    """Tests for correct metrics usage patterns."""

    def test_counter_increment(self):
        """Counters should support .labels().inc() pattern."""
        from core.common.observability import EVENTS_PROCESSED

        # This pattern is used throughout services
        labeled = EVENTS_PROCESSED.labels(
            service="test",
            event_type="test.event",
            status="success"
        )
        # Should not raise
        labeled.inc()

    def test_histogram_observe(self):
        """Histograms should support .labels().observe() pattern."""
        from core.common.observability import EVENT_DURATION

        labeled = EVENT_DURATION.labels(
            service="test",
            event_type="test.event"
        )
        # Should not raise
        labeled.observe(0.5)

    def test_aku_status_values(self):
        """AKUS_TOTAL should accept expected status values."""
        from core.common.observability import AKUS_TOTAL

        # These are the status values used in code
        expected_statuses = ["proposed", "accepted", "merged", "rejected"]

        for status in expected_statuses:
            # Should not raise
            AKUS_TOTAL.labels(source="reflector", status=status).inc()

    def test_llm_call_status_values(self):
        """LLM_CALLS should accept success/error status."""
        from core.common.observability import LLM_CALLS

        # Should not raise
        LLM_CALLS.labels(service="reflector", status="success").inc()
        LLM_CALLS.labels(service="reflector", status="error").inc()


# ============================================================================
# Test: Error Classification for Metrics
# ============================================================================


class TestErrorClassification:
    """Tests for error types used in ERRORS metric."""

    def test_retryable_error_classification(self):
        """RetryableError should be classified as retryable=true."""
        from core.common.errors import RetryableError

        error = RetryableError("Test error")
        assert isinstance(error, Exception)
        # Used in BaseService to set retryable="true" label

    def test_fatal_error_classification(self):
        """FatalError should be classified as retryable=false."""
        from core.common.errors import FatalError

        error = FatalError("Test error")
        assert isinstance(error, Exception)
        # Used in BaseService to set retryable="false" label

    def test_llm_timeout_is_retryable(self):
        """LLMTimeoutError should inherit from RetryableError."""
        from core.common.errors import LLMTimeoutError, RetryableError

        error = LLMTimeoutError("Timeout")
        assert isinstance(error, RetryableError)

    def test_database_error_is_retryable(self):
        """DatabaseError should inherit from RetryableError."""
        from core.common.errors import DatabaseError, RetryableError

        error = DatabaseError("Connection failed")
        assert isinstance(error, RetryableError)
