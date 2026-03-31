"""Observability setup for ALEC services.

Provides structured logging via structlog and Prometheus metrics.
"""

import logging
import os

import structlog
from prometheus_client import Counter, Histogram


# Configure structlog
def setup_logging(service_name: str) -> structlog.BoundLogger:
    """Configure structured logging for a service.

    Args:
        service_name: Name of the service for log context.

    Returns:
        Configured bound logger.
    """
    log_format = os.getenv("LOG_FORMAT", "json")
    log_level = os.getenv("LOG_LEVEL", "INFO")

    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger: structlog.BoundLogger = structlog.get_logger().bind(service=service_name)
    return logger


# Prometheus metrics
EVENTS_PROCESSED = Counter(
    'alec_events_processed_total',
    'Total events processed',
    ['service', 'event_type', 'status']
)

EVENT_DURATION = Histogram(
    'alec_event_processing_seconds',
    'Event processing duration',
    ['service', 'event_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0]
)

LLM_CALLS = Counter(
    'alec_llm_calls_total',
    'Total LLM calls',
    ['service', 'status']
)

LLM_DURATION = Histogram(
    'alec_llm_call_seconds',
    'LLM call duration',
    ['service'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

AKUS_TOTAL = Counter(
    'alec_akus_total',
    'Total AKUs proposed/accepted',
    ['source', 'status']
)

BULLETS_RETRIEVED = Counter(
    'alec_bullets_retrieved_total',
    'Total bullets retrieved',
    []
)

ERRORS = Counter(
    'alec_errors_total',
    'Total errors',
    ['service', 'error_type', 'retryable']
)

EVENTS_DROPPED = Counter(
    'alec_events_dropped_total',
    'Events dropped before processing (with reason)',
    ['service', 'event_type', 'drop_reason']
)
