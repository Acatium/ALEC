"""
Pytest configuration and shared fixtures for ALEC testing.

This module provides:
- VCR configuration for LLM API call recording/replay
- Database setup/teardown fixtures
- HTTP client fixtures
- Test data generators
"""
import os
from typing import AsyncGenerator, Generator
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Removed imports for deleted test fixtures/utils
# from tests.utils.longitudinal_metrics import LongitudinalMetricsDB
# from tests.utils.outcome_metrics import OutcomeMetricsCollector
# from tests.fixtures.ground_truth import get_all_cities


# ============================================================================
# VCR Configuration (for LLM API recording/replay)
# ============================================================================

@pytest.fixture(scope="module")
def vcr_config():
    """Configure VCR for recording/replaying LLM API calls.

    Records API calls on first run, replays on subsequent runs.
    Redacts API keys for security.
    """
    return {
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("x-api-key", "REDACTED"),
            ("anthropic-version", None),
        ],
        "filter_post_data_parameters": [
            ("api_key", "REDACTED"),
        ],
        "record_mode": "once",  # Record once, then replay
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "cassette_library_dir": "tests/fixtures/cassettes",
        "decode_compressed_response": True,
    }


@pytest.fixture(scope="session")
def vcr_cassette_dir(tmp_path_factory):
    """Create cassette directory for VCR recordings."""
    cassette_dir = tmp_path_factory.mktemp("cassettes")
    return str(cassette_dir)


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory) -> str:
    """Create temporary SQLite database for testing."""
    db_path = tmp_path_factory.mktemp("data") / "test.db"
    return f"sqlite:///{db_path}"


@pytest.fixture(scope="session")
def test_engine(test_db_url):
    """Create SQLAlchemy engine for test database."""
    engine = create_engine(test_db_url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_engine) -> Generator[Session, None, None]:
    """Create database session with automatic rollback."""
    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


# Commented out: depends on deleted test utils
# @pytest.fixture(scope="function")
# def metrics_db(tmp_path) -> Generator[LongitudinalMetricsDB, None, None]:
#     """Create temporary longitudinal metrics database."""
#     db_path = tmp_path / "metrics.db"
#     db = LongitudinalMetricsDB(str(db_path))
#
#     try:
#         yield db
#     finally:
#         db.close()


# ============================================================================
# HTTP Client Fixtures
# ============================================================================

@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async HTTP client for API testing."""
    timeout = httpx.Timeout(120.0, connect=10.0)
    async with httpx.AsyncClient(
        base_url=os.getenv("CONVERSATIONAL_AI_URL", "http://localhost:8008"),
        timeout=timeout,
    ) as client:
        yield client


@pytest.fixture
def sync_http_client() -> Generator[httpx.Client, None, None]:
    """Create sync HTTP client for API testing."""
    timeout = httpx.Timeout(120.0, connect=10.0)
    with httpx.Client(
        base_url=os.getenv("CONVERSATIONAL_AI_URL", "http://localhost:8008"),
        timeout=timeout,
    ) as client:
        yield client


# ============================================================================
# Metrics Collection Fixtures
# ============================================================================

# Commented out: depends on deleted test utils
# @pytest.fixture
# def outcome_collector() -> OutcomeMetricsCollector:
#     """Create outcome metrics collector."""
#     return OutcomeMetricsCollector(context_window_size=128000)


# ============================================================================
# Test Data Fixtures
# ============================================================================

# Commented out: depends on deleted test fixtures/utils
# @pytest.fixture
# def test_cities() -> List[str]:
#     """Get list of test cities from ground truth."""
#     return get_all_cities()[:5]  # Use first 5 cities for faster tests


@pytest.fixture
def test_session_id() -> str:
    """Generate test session ID."""
    return str(uuid4())


# @pytest.fixture
# def test_decision_batch():
#     """Generate test decision batch."""
#     from tests.fixtures.sample_decisions import generate_consistent_sql_decisions
#     return generate_consistent_sql_decisions(count=5)


# @pytest.fixture
# def test_playbooks():
#     """Generate test playbooks."""
#     from tests.fixtures.sample_decisions import generate_diverse_playbooks
#     return generate_diverse_playbooks(count=5)


# ============================================================================
# Service Fixtures
# ============================================================================

# Commented out: references session service (uncomment if needed)
# @pytest.fixture
# async def curator():
#     """Create SessionBasedCurator instance."""
#     from core.session.domain.curator import SessionBasedCurator
#     return SessionBasedCurator(trigger_threshold=3, max_playbooks=20)


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_temp_files(tmp_path):
    """Cleanup temporary files after each test."""
    yield
    # Cleanup happens automatically with tmp_path


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables.

    This fixture configures environment for both scenarios:
    - Docker container testing: Uses container-internal addresses (postgres:5432)
    - Host-based testing: Uses localhost addresses (localhost:5432)

    Detection: If DATABASE_URL contains 'postgres:' (Docker hostname), we're in a container.
    """
    # Save original environment
    saved_env = {}

    # Detect if running inside Docker (DATABASE_URL points to Docker hostnames)
    current_db_url = os.getenv("DATABASE_URL", "")
    in_docker = "postgres:" in current_db_url or "@postgres/" in current_db_url

    if in_docker:
        # Inside Docker container - only set non-network environment
        test_overrides = {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "WARNING",
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "test-key"),
            # Keep DATABASE_URL, KAFKA_BOOTSTRAP_SERVERS, REDIS_URL as-is from docker-compose
        }
    else:
        # Running on host - force localhost addresses for port-mapped services
        test_overrides = {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "WARNING",
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "test-key"),
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "DATABASE_URL": "postgresql://alec:alec-dev-password@localhost:5432/alec",
            "REDIS_URL": "redis://localhost:6379/0",
        }

    # Apply overrides and save originals
    for key, value in test_overrides.items():
        saved_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original environment
    for key, original_value in saved_env.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


# ============================================================================
# Pytest Hooks
# ============================================================================

def pytest_collection_modifyitems(config, items):
    """Add markers based on test names and locations."""
    for item in items:
        # Add markers based on directory
        if "longitudinal" in str(item.fspath):
            item.add_marker(pytest.mark.longitudinal)
        if "benchmark" in str(item.fspath):
            item.add_marker(pytest.mark.benchmark)

        # Add async marker for async tests
        if "async" in item.name or item.function.__name__.startswith("async_"):
            item.add_marker(pytest.mark.asyncio)

        # Mark slow tests
        if any(marker.name == "slow" for marker in item.iter_markers()):
            item.add_marker(pytest.mark.slow)


def pytest_configure(config):
    """Configure pytest environment."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "vcr: mark test to use VCR for API recording"
    )
