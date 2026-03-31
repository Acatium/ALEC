"""Smoke test — full loop with real LLM + real DB against ALEC's own docs."""

from __future__ import annotations

import os

import pytest

from alec.config.settings import Settings
from alec.runtime.supervisor import Supervisor


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_full_discovery_loop():
    """Run a real discovery loop against ALEC's own design docs.

    Requires:
    - ALEC_ANTHROPIC_API_KEY in environment
    - PostgreSQL running (docker-compose up -d)
    """
    api_key = os.environ.get("ALEC_ANTHROPIC_API_KEY", "")
    if not api_key:
        pytest.skip("ALEC_ANTHROPIC_API_KEY not set")

    settings = Settings(
        anthropic_api_key=api_key,
        max_workers=2,
        worker_max_tokens=50_000,
        worker_max_turns=15,
        log_format="console",
    )

    supervisor = Supervisor(settings)

    # Use ALEC's own design docs as source
    source_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "design")
    if not os.path.isdir(source_path):
        pytest.skip(f"Design docs not found at {source_path}")

    result = await supervisor.run(
        sources=[source_path],
        problem_statement="Discover the architecture and key components of the ALEC v5 system",
        max_cycles=2,
    )

    # Should produce some knowledge
    assert result["entities"] > 0, "Expected at least some entities"
    assert result["relationships"] > 0, "Expected at least some relationships"
    assert result["observations"] > 0, "Expected at least some observations"
    assert result["budget"]["tokens_used"] > 0, "Expected some tokens used"

    # Verify convergence_log has entries
    from alec.db.pool import close_pool, create_pool

    db_url = os.environ.get(
        "ALEC_DATABASE_URL",
        "postgresql://alec:alec-dev-password@localhost:5432/alec",
    )
    pool = await create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            log_count = await conn.fetchval(
                "SELECT COUNT(*) FROM convergence_log WHERE engagement_id = $1::uuid",
                result["engagement_id"],
            )
        assert log_count > 0, "Expected convergence_log entries for this engagement"
    finally:
        await close_pool(pool)
