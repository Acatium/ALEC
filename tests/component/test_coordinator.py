"""Component tests for CoordinatorService — MockLLM + real DB."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.db

from alec.agents.mock_llm import MockLLMClient
from alec.knowledge.domain import ConvergenceConfig
from alec.knowledge.repositories.projections import ProjectionRepository
from alec.knowledge.repositories.tasks import TaskRepository
from alec.runtime.coordinator import CoordinatorService


@pytest.mark.asyncio
async def test_coordinator_generates_directives(test_engagement):
    pool, eid = test_engagement
    mock_llm = MockLLMClient()

    # Register a source
    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            "INSERT INTO coordinator_instances (engagement_id) VALUES ($1) RETURNING instance_id",
            eid,
        )
        await conn.execute(
            """INSERT INTO source_configs (engagement_id, source_type, config, status)
               VALUES ($1, 'local_files', $2, 'verified')""",
            eid,
            json.dumps({"base_path": "/test/docs"}),
        )

    # Mock coordinator LLM response with directives
    directive_json = json.dumps(
        [
            {
                "source_type": "local_files",
                "source_ref": "/test/docs",
                "directive": "Survey the docs directory for architecture information",
                "max_scope": "survey",
                "relevant_context": "No data yet",
                "reason": "Initial exploration",
            }
        ]
    )
    mock_llm.add_response(mock_llm.make_text_response(directive_json))

    coordinator = CoordinatorService(
        projections=ProjectionRepository(pool),
        tasks=TaskRepository(pool),
        llm=mock_llm,
    )

    result = await coordinator.run_cycle(
        engagement_id=eid,
        coordinator_id=cid,
        cycle_number=1,
        last_cycle_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
        convergence_config=ConvergenceConfig(),
    )

    assert result.convergence_signal is False
    assert len(result.directives) == 1
    assert result.directives[0].source_type == "local_files"
    assert result.directives[0].max_scope == "survey"
    assert result.cycle_stats.directives_generated == 1

    # Verify task was persisted
    task_repo = TaskRepository(pool)
    queued = await task_repo.find_queued(eid)
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_coordinator_empty_no_sources(test_engagement):
    pool, eid = test_engagement
    mock_llm = MockLLMClient()

    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            "INSERT INTO coordinator_instances (engagement_id) VALUES ($1) RETURNING instance_id",
            eid,
        )

    # No sources, no gaps → should return empty (no LLM call needed)
    coordinator = CoordinatorService(
        projections=ProjectionRepository(pool),
        tasks=TaskRepository(pool),
        llm=mock_llm,
    )

    result = await coordinator.run_cycle(
        engagement_id=eid,
        coordinator_id=cid,
        cycle_number=1,
        last_cycle_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
        convergence_config=ConvergenceConfig(),
    )

    assert result.convergence_signal is False
    assert len(result.directives) == 0
    assert len(mock_llm.calls) == 0  # No LLM call made
