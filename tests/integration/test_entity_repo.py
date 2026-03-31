"""Integration tests for EntityRepository."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.db

from alec.knowledge.repositories.entities import EntityRepository


@pytest.mark.asyncio
async def test_create_and_find(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    entity_id = await repo.create(
        engagement_id=eid,
        name="TestService",
        entity_type="service",
        aliases=["test-svc"],
        properties={"port": 8080},
    )

    entity = await repo.find_by_id(entity_id)
    assert entity is not None
    assert entity.name == "TestService"
    assert entity.entity_type == "service"
    assert "test-svc" in entity.aliases
    assert entity.properties["port"] == 8080
    assert entity.observation_count == 1


@pytest.mark.asyncio
async def test_find_by_name(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    await repo.create(
        engagement_id=eid,
        name="MyService",
        entity_type="service",
    )

    # Case-insensitive match
    entity = await repo.find_by_name(eid, "myservice")
    assert entity is not None
    assert entity.name == "MyService"


@pytest.mark.asyncio
async def test_find_by_alias(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    await repo.create(
        engagement_id=eid,
        name="PaymentService",
        entity_type="service",
        aliases=["payments-svc"],
    )

    entity = await repo.find_by_name(eid, "payments-svc")
    assert entity is not None
    assert entity.name == "PaymentService"


@pytest.mark.asyncio
async def test_update_on_rediscovery(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    entity_id = await repo.create(
        engagement_id=eid,
        name="SomeService",
        entity_type="service",
    )

    await repo.update_on_rediscovery(
        entity_id=entity_id,
        aliases=["some-svc"],
        properties={"version": "2.0"},
    )

    entity = await repo.find_by_id(entity_id)
    assert entity is not None
    assert entity.observation_count == 2
    assert "some-svc" in entity.aliases


@pytest.mark.asyncio
async def test_find_nonexistent(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    entity = await repo.find_by_name(eid, "does-not-exist")
    assert entity is None


@pytest.mark.asyncio
async def test_list_by_engagement(test_engagement):
    pool, eid = test_engagement
    repo = EntityRepository(pool)

    await repo.create(engagement_id=eid, name="A", entity_type="service")
    await repo.create(engagement_id=eid, name="B", entity_type="database")

    entities = await repo.list_by_engagement(eid)
    assert len(entities) == 2
    names = {e.name for e in entities}
    assert names == {"A", "B"}
