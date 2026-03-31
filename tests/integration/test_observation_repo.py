"""Integration tests for ObservationRepository."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.db

from alec.knowledge.repositories.observations import ObservationRepository


@pytest.mark.asyncio
async def test_create_and_find(test_engagement):
    pool, eid = test_engagement
    repo = ObservationRepository(pool)

    obs_id = await repo.create(
        engagement_id=eid,
        source_ref="test-file.md",
        raw_text="Service A depends on Database B",
        observation_type="relationship",
        worker_id="worker-001",
        metadata={"impact_type": "expansion"},
    )

    observations = await repo.find_by_engagement(eid)
    assert len(observations) == 1
    assert observations[0].observation_id == obs_id
    assert observations[0].raw_text == "Service A depends on Database B"
    assert observations[0].observation_type == "relationship"
    assert observations[0].metadata["impact_type"] == "expansion"


@pytest.mark.asyncio
async def test_filter_by_type(test_engagement):
    pool, eid = test_engagement
    repo = ObservationRepository(pool)

    await repo.create(
        engagement_id=eid,
        source_ref="a",
        raw_text="insight 1",
        observation_type="insight",
    )
    await repo.create(
        engagement_id=eid,
        source_ref="b",
        raw_text="gap 1",
        observation_type="gap",
    )
    await repo.create(
        engagement_id=eid,
        source_ref="c",
        raw_text="insight 2",
        observation_type="insight",
    )

    insights = await repo.find_by_engagement(eid, observation_type="insight")
    assert len(insights) == 2
    assert all(o.observation_type == "insight" for o in insights)


@pytest.mark.asyncio
async def test_limit(test_engagement):
    pool, eid = test_engagement
    repo = ObservationRepository(pool)

    for i in range(5):
        await repo.create(
            engagement_id=eid,
            source_ref=f"file-{i}",
            raw_text=f"obs {i}",
            observation_type="entity",
        )

    observations = await repo.find_by_engagement(eid, limit=3)
    assert len(observations) == 3
