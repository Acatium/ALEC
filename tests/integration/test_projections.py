"""Integration tests for ProjectionRepository."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.db

from alec.knowledge.domain import ConvergenceConfig, ConvergenceMetrics
from alec.knowledge.repositories.projections import ProjectionRepository


@pytest.mark.asyncio
async def test_build_projection_empty(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)

    # Create coordinator instance
    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            "INSERT INTO coordinator_instances (engagement_id) VALUES ($1) RETURNING instance_id",
            eid,
        )

    projection = await repo.build_projection(
        eid,
        cid,
        datetime(1970, 1, 1, tzinfo=timezone.utc),
    )

    assert projection.problem_statement == "Discover test knowledge"
    assert "Coverage Dashboard" in projection.coverage_dashboard
    assert projection.active_gaps == []
    assert projection.contradictions == []
    assert projection.alignment_opportunities == []


@pytest.mark.asyncio
async def test_find_gaps_unexplored_entity(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)

    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            "INSERT INTO coordinator_instances (engagement_id) VALUES ($1) RETURNING instance_id",
            eid,
        )
        # Create two entities: one explored, one referenced only
        e1 = await conn.fetchval(
            """INSERT INTO entities (engagement_id, name, entity_type, observation_count)
               VALUES ($1, 'ExploredSvc', 'service', 5) RETURNING entity_id""",
            eid,
        )
        e2 = await conn.fetchval(
            """INSERT INTO entities (engagement_id, name, entity_type, observation_count)
               VALUES ($1, 'ReferencedDB', 'database', 1) RETURNING entity_id""",
            eid,
        )
        # Create relationship so e2 is referenced
        await conn.execute(
            """INSERT INTO relationships (engagement_id, from_entity, to_entity, relationship_type)
               VALUES ($1, $2, $3, 'reads_from')""",
            eid,
            e1,
            e2,
        )

    projection = await repo.build_projection(
        eid,
        cid,
        datetime(1970, 1, 1, tzinfo=timezone.utc),
    )

    assert len(projection.active_gaps) == 1
    assert projection.active_gaps[0].name == "ReferencedDB"
    assert projection.active_gaps[0].gap_type == "unexplored_entity"


@pytest.mark.asyncio
async def test_find_gaps_unsurveyed_source(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)

    async with pool.acquire() as conn:
        cid = await conn.fetchval(
            "INSERT INTO coordinator_instances (engagement_id) VALUES ($1) RETURNING instance_id",
            eid,
        )
        await conn.execute(
            """INSERT INTO source_configs (engagement_id, source_type, config, status)
               VALUES ($1, 'local_files', $2, 'verified')""",
            eid,
            json.dumps({"base_path": "/test"}),
        )

    projection = await repo.build_projection(
        eid,
        cid,
        datetime(1970, 1, 1, tzinfo=timezone.utc),
    )

    assert any(g.gap_type == "unsurveyed_source" for g in projection.active_gaps)


@pytest.mark.asyncio
async def test_check_convergence_not_converged(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)
    config = ConvergenceConfig()

    # Add some expansion observations
    async with pool.acquire() as conn:
        for i in range(3):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'test', $2, 'entity', '{"impact_type": "expansion"}')""",
                eid,
                f"obs {i}",
            )

    converged, metrics = await repo.check_convergence(eid, 1, config)
    assert converged is False
    assert isinstance(metrics, ConvergenceMetrics)
    assert metrics.weighted_ratio < config.convergence_threshold
    assert metrics.expansion_rate == 3
    assert metrics.primary_converged is False


@pytest.mark.asyncio
async def test_check_convergence_converged(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)
    config = ConvergenceConfig(convergence_threshold=2.0, consecutive_cycles_required=2)

    # Log prior cycle with high reinforcement ratios (including weighted_ratio)
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO convergence_log
                (engagement_id, cycle_number,
                 reinforcement_count, expansion_count,
                 challenge_count, ratio, weighted_ratio,
                 expansion_rate, expansion_acceleration)
               VALUES ($1, 1, 10, 1, 0, 5.0, 5.0, 1, 0.0)""",
            eid,
        )

    # Add reinforcement observations for next check
    async with pool.acquire() as conn:
        for i in range(10):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'test', $2, 'entity', '{"impact_type": "reinforcement"}')""",
                eid,
                f"reinforcement {i}",
            )

    converged, metrics = await repo.check_convergence(eid, 2, config)
    assert isinstance(metrics, ConvergenceMetrics)
    # Weighted ratio may differ from raw due to capping and novelty decay,
    # but primary convergence should still trigger with enough reinforcement
    assert metrics.raw_ratio > 0
    assert metrics.primary_converged is True
    assert converged is True


@pytest.mark.asyncio
async def test_get_verified_sources(test_engagement):
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO source_configs (engagement_id, source_type, config, status)
               VALUES ($1, 'local_files', $2, 'verified')""",
            eid,
            json.dumps({"base_path": "/test/path"}),
        )

    sources = await repo.get_verified_sources(eid)
    assert len(sources) == 1
    assert sources[0]["source_type"] == "local_files"
    assert sources[0]["config"]["base_path"] == "/test/path"


@pytest.mark.asyncio
async def test_convergence_anti_gaming_cap(test_engagement):
    """Reinforcing a single entity 50x should be capped, not count as 50."""
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)
    config = ConvergenceConfig(max_reinforcement_per_entity_per_cycle=3)

    # Create the entity so observation_count lookup works
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO entities (engagement_id, name, entity_type, observation_count)
               VALUES ($1, 'SameEntity', 'service', 50)""",
            eid,
        )
        # Insert 50 reinforcement observations for the same entity
        for i in range(50):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'src', $2, 'entity',
                           '{"impact_type": "reinforcement", "entity_name": "SameEntity"}')""",
                eid,
                f"reinforce {i}",
            )
        # Insert 1 expansion
        await conn.execute(
            """INSERT INTO observations
                (engagement_id, source_ref, raw_text, observation_type, metadata)
               VALUES ($1, 'src', 'new thing', 'entity', '{"impact_type": "expansion"}')""",
            eid,
        )

    _, metrics = await repo.check_convergence(eid, 1, config)
    # Raw ratio = 50/(1+0+1) = 25.0, but weighted should be much lower
    assert metrics.raw_ratio == 25.0
    assert metrics.weighted_ratio < metrics.raw_ratio


@pytest.mark.asyncio
async def test_convergence_per_source_ratios(test_engagement):
    """Per-source ratios are tracked separately."""
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)
    config = ConvergenceConfig()

    async with pool.acquire() as conn:
        # Source A: all reinforcement
        for i in range(5):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'sourceA', $2, 'entity',
                           '{"impact_type": "reinforcement"}')""",
                eid,
                f"reinforce {i}",
            )
        # Source B: all expansion
        for i in range(3):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'sourceB', $2, 'entity',
                           '{"impact_type": "expansion"}')""",
                eid,
                f"expand {i}",
            )

    _, metrics = await repo.check_convergence(eid, 1, config)
    assert "sourceA" in metrics.per_source_ratios
    assert "sourceB" in metrics.per_source_ratios
    # sourceA: 5 reinforcement / (0 expansion + 1) = 5.0
    assert metrics.per_source_ratios["sourceA"] == 5.0
    # sourceB: 0 reinforcement / (3 expansion + 1) = 0.0
    assert metrics.per_source_ratios["sourceB"] == 0.0


@pytest.mark.asyncio
async def test_convergence_expected_contradiction_excluded(test_engagement):
    """Challenges marked as expected_contradiction are excluded from denominator."""
    pool, eid = test_engagement
    repo = ProjectionRepository(pool)
    config = ConvergenceConfig()

    async with pool.acquire() as conn:
        # Add reinforcements
        for i in range(10):
            await conn.execute(
                """INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type, metadata)
                   VALUES ($1, 'src', $2, 'entity',
                           '{"impact_type": "reinforcement"}')""",
                eid,
                f"reinforce {i}",
            )
        # Add expected contradiction (should be excluded)
        await conn.execute(
            """INSERT INTO observations
                (engagement_id, source_ref, raw_text, observation_type, metadata)
               VALUES ($1, 'src', 'expected', 'entity',
                       '{"impact_type": "challenge", "expected_contradiction": "true"}')""",
            eid,
        )
        # Add real challenge
        await conn.execute(
            """INSERT INTO observations
                (engagement_id, source_ref, raw_text, observation_type, metadata)
               VALUES ($1, 'src', 'real challenge', 'entity',
                       '{"impact_type": "challenge"}')""",
            eid,
        )

    _, metrics = await repo.check_convergence(eid, 1, config)
    # Raw ratio should be 10/(0+1+1) = 5.0 (only 1 real challenge counted)
    assert metrics.raw_ratio == 5.0
