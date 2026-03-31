"""Integration tests for RelationshipRepository."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.db

from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.relationships import RelationshipRepository


@pytest.mark.asyncio
async def test_upsert_creates(test_engagement):
    pool, eid = test_engagement
    entity_repo = EntityRepository(pool)
    obs_repo = ObservationRepository(pool)
    rel_repo = RelationshipRepository(pool)

    e1 = await entity_repo.create(engagement_id=eid, name="A", entity_type="service")
    e2 = await entity_repo.create(engagement_id=eid, name="B", entity_type="database")

    obs_id = await obs_repo.create(
        engagement_id=eid,
        source_ref="test",
        raw_text="A calls B",
        observation_type="relationship",
    )

    await rel_repo.upsert(
        engagement_id=eid,
        from_entity=e1,
        to_entity=e2,
        relationship_type="calls",
        evidence_id=obs_id,
        confidence=0.9,
    )

    rels = await rel_repo.find_by_entity(eid, e1)
    assert len(rels) == 1
    assert rels[0].relationship_type == "calls"
    assert rels[0].confidence == 0.9


@pytest.mark.asyncio
async def test_upsert_appends_evidence(test_engagement):
    pool, eid = test_engagement
    entity_repo = EntityRepository(pool)
    obs_repo = ObservationRepository(pool)
    rel_repo = RelationshipRepository(pool)

    e1 = await entity_repo.create(engagement_id=eid, name="X", entity_type="service")
    e2 = await entity_repo.create(engagement_id=eid, name="Y", entity_type="service")

    obs1 = await obs_repo.create(
        engagement_id=eid,
        source_ref="test",
        raw_text="ev1",
        observation_type="relationship",
    )
    obs2 = await obs_repo.create(
        engagement_id=eid,
        source_ref="test",
        raw_text="ev2",
        observation_type="relationship",
    )

    await rel_repo.upsert(
        engagement_id=eid,
        from_entity=e1,
        to_entity=e2,
        relationship_type="depends_on",
        evidence_id=obs1,
        confidence=0.5,
    )
    await rel_repo.upsert(
        engagement_id=eid,
        from_entity=e1,
        to_entity=e2,
        relationship_type="depends_on",
        evidence_id=obs2,
        confidence=0.8,
    )

    rels = await rel_repo.find_by_entity(eid, e1)
    assert len(rels) == 1
    assert len(rels[0].evidence) == 2
    assert rels[0].confidence == 0.8  # GREATEST of 0.5, 0.8
