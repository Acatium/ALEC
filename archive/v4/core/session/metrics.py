"""SESSION v3 Prometheus metrics.

Consolidated metrics for the SESSION service.
"""

from prometheus_client import Counter, Gauge, Histogram

# Request metrics
SESSION_REQUESTS = Counter(
    'session_requests_total',
    'Total HTTP requests',
    ['endpoint', 'method', 'status']
)

SESSION_REQUEST_DURATION = Histogram(
    'session_request_duration_seconds',
    'Request duration',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0]
)

# Turn metrics (defined in conversation.py)
# SESSION_TURNS - Counter with status label
# SESSION_TURN_DURATION - Histogram

# Bullet metrics
SESSION_BULLETS_USED = Counter(
    'session_bullets_used_total',
    'Bullets injected into prompts',
    ['source']  # redis, fallback
)

SESSION_BULLETS_RETRIEVED = Histogram(
    'session_bullets_retrieved_count',
    'Number of bullets retrieved per turn',
    buckets=[0, 1, 2, 4, 8, 16, 32]
)

# LLM metrics (from core.common.observability)
# LLM_CALLS - Counter with service, status
# LLM_DURATION - Histogram

# Connection metrics
SESSION_ACTIVE_SESSIONS = Gauge(
    'session_active_sessions_total',
    'Currently active sessions',
)

# Error metrics
SESSION_ERRORS = Counter(
    'session_errors_total',
    'Session errors',
    ['error_type', 'endpoint']
)
