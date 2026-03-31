"""Integration tests for ConsolidationRepository — real Postgres."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

pytestmark = pytest.mark.db

from alec.db.embeddings import MockEmbeddingService
from alec.knowledge.domain import ConsolidationConfig, StaleEntity
from alec.knowledge.repositories.consolidation import ConsolidationRepository


@pytest.mark.asyncio
async def test_should_consolidate_no_observations(test_engagement):
    """No observations → should not consolidate."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)

    result = await repo.should_consolidate(eid, ConsolidationConfig())
    assert result is False


@pytest.mark.asyncio
async def test_should_consolidate_enough_observations(test_engagement):
    """Enough observations and no prior consolidation → should consolidate."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)

    # Insert 20+ observations
    async with pool.acquire() as conn:
        for i in range(25):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"source-{i}",
                f"Observation {i}",
                "entity",
            )

    result = await repo.should_consolidate(eid, ConsolidationConfig())
    assert result is True


@pytest.mark.asyncio
async def test_should_consolidate_respects_min_observations(test_engagement):
    """Under threshold → should not consolidate."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)

    async with pool.acquire() as conn:
        for i in range(5):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"source-{i}",
                f"Observation {i}",
                "entity",
            )

    result = await repo.should_consolidate(eid, ConsolidationConfig(min_new_observations=20))
    assert result is False


@pytest.mark.asyncio
async def test_find_stale_entities_no_entities(test_engagement):
    """No entities → empty list."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)

    result = await repo.find_stale_entities(eid)
    assert result == []


@pytest.mark.asyncio
async def test_find_stale_entities_returns_unconsolidated(test_engagement):
    """Entity with >=2 observations and no consolidated unit → stale."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'PaymentService', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("PaymentService (service)"),
        )
        # Add observations that reference this entity
        for i in range(3):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type,
                     metadata)
                VALUES ($1, $2, $3, $4, $5)
                """,
                eid,
                f"source-{i}",
                f"PaymentService handles payment {i}",
                "entity",
                json.dumps({"entity_name": "PaymentService"}),
            )

    result = await repo.find_stale_entities(eid)
    assert len(result) >= 1
    entity = next(e for e in result if e.entity_id == entity_id)
    assert entity.name == "PaymentService"
    assert entity.has_existing_unit is False


@pytest.mark.asyncio
async def test_find_stale_entities_skips_low_observation_count(test_engagement):
    """Entity with <2 observations → not returned."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'SingleObsEntity', 'service', 1, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("SingleObsEntity"),
        )

    result = await repo.find_stale_entities(eid)
    names = [e.name for e in result]
    assert "SingleObsEntity" not in names


@pytest.mark.asyncio
async def test_gather_material(test_engagement):
    """Gather material for a specific entity."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count,
                 aliases, properties, embedding)
            VALUES ($1, 'OrderService', 'service', 5, $2, $3, $4)
            RETURNING entity_id
            """,
            eid,
            ["order-svc", "orders"],
            json.dumps({"language": "python"}),
            await embedder.embed("OrderService (service)"),
        )

        # Add another entity for relationship
        other_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'OrderDB', 'database', 3, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("OrderDB (database)"),
        )

        # Add relationship
        await conn.execute(
            """
            INSERT INTO relationships
                (engagement_id, from_entity, to_entity, relationship_type, confidence)
            VALUES ($1, $2, $3, 'writes_to', 0.9)
            """,
            eid,
            entity_id,
            other_id,
        )

        # Add observations
        await conn.execute(
            """
            INSERT INTO observations
                (engagement_id, source_ref, raw_text, observation_type)
            VALUES ($1, 'docs/arch.md', 'OrderService is the core order processor', 'entity')
            """,
            eid,
        )

    entity = StaleEntity(
        entity_id=entity_id,
        name="OrderService",
        entity_type="service",
        observation_count=5,
        new_observations=1,
        has_existing_unit=False,
    )
    material = await repo.gather_material(eid, entity)

    assert material.entity_name == "OrderService"
    assert material.entity_type == "service"
    assert "order-svc" in material.aliases
    assert material.properties.get("language") == "python"
    assert len(material.observations) >= 1
    assert len(material.relationships_outgoing) == 1
    assert material.relationships_outgoing[0]["to_name"] == "OrderDB"
    assert material.relationships_outgoing[0]["relationship_type"] == "writes_to"


@pytest.mark.asyncio
async def test_store_consolidated_unit_new(test_engagement):
    """Store a new consolidated unit."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'TestEntity', 'service', 3, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("TestEntity (service)"),
        )

    embedding = await embedder.embed("Test summary")
    unit_id = await repo.store_consolidated_unit(
        engagement_id=eid,
        entity_id=entity_id,
        summary="## TestEntity (service)\nA test entity.",
        embedding=embedding,
        source_observation_ids=[],
        token_count=10,
        is_update=False,
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM consolidated_units WHERE unit_id = $1",
            unit_id,
        )

    assert row is not None
    assert row["subject_entity"] == entity_id
    assert row["version"] == 1
    assert row["status"] == "current"
    assert "TestEntity" in row["summary"]


@pytest.mark.asyncio
async def test_store_consolidated_unit_update(test_engagement):
    """Update marks old version as stale and creates new version."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'UpdateEntity', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("UpdateEntity"),
        )

    embedding = await embedder.embed("v1 summary")
    await repo.store_consolidated_unit(
        engagement_id=eid,
        entity_id=entity_id,
        summary="v1 summary",
        embedding=embedding,
        source_observation_ids=[],
        token_count=5,
        is_update=False,
    )

    # Update
    embedding2 = await embedder.embed("v2 summary")
    unit_id_v2 = await repo.store_consolidated_unit(
        engagement_id=eid,
        entity_id=entity_id,
        summary="v2 summary with more detail",
        embedding=embedding2,
        source_observation_ids=[],
        token_count=10,
        is_update=True,
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM consolidated_units
            WHERE subject_entity = $1 AND engagement_id = $2
            ORDER BY version
            """,
            entity_id,
            eid,
        )

    assert len(rows) == 2
    assert rows[0]["status"] == "stale"
    assert rows[0]["version"] == 1
    assert rows[1]["status"] == "current"
    assert rows[1]["version"] == 2
    assert rows[1]["unit_id"] == unit_id_v2


@pytest.mark.asyncio
async def test_detect_cross_links_co_occurrence(test_engagement):
    """Detect cross-links via co-occurrence in observations."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        _entity_a = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'ServiceA', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("ServiceA"),
        )
        _entity_b = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'ServiceB', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("ServiceB"),
        )

        # Create 3+ observations mentioning both entities
        for i in range(4):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"source-{i}",
                f"ServiceA interacts with ServiceB in scenario {i}",
                "entity",
            )

    config = ConsolidationConfig(co_occurrence_threshold=3)
    cross_links = await repo.detect_cross_links(eid, config)

    # Should detect co-occurrence
    matching = [
        cl for cl in cross_links
        if cl.detection_method == "co_occurrence"
        and {cl.entity_a_name, cl.entity_b_name} == {"ServiceA", "ServiceB"}
    ]
    assert len(matching) >= 1
    assert matching[0].strength >= 3.0


@pytest.mark.asyncio
async def test_detect_cross_links_excludes_related(test_engagement):
    """Entities with existing relationship are excluded from cross-links."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_a = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'RelatedA', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("RelatedA"),
        )
        entity_b = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'RelatedB', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("RelatedB"),
        )

        # Create relationship between them
        await conn.execute(
            """
            INSERT INTO relationships
                (engagement_id, from_entity, to_entity, relationship_type, confidence)
            VALUES ($1, $2, $3, 'calls', 0.9)
            """,
            eid,
            entity_a,
            entity_b,
        )

        # Co-occurring observations
        for i in range(5):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"source-{i}",
                f"RelatedA and RelatedB work together {i}",
                "entity",
            )

    config = ConsolidationConfig(co_occurrence_threshold=3)
    cross_links = await repo.detect_cross_links(eid, config)

    matching = [
        cl for cl in cross_links
        if {cl.entity_a_name, cl.entity_b_name} == {"RelatedA", "RelatedB"}
    ]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_record_cross_link_observations(test_engagement):
    """Cross-links are recorded as insight observations."""
    pool, eid = test_engagement
    repo = ConsolidationRepository(pool)

    cross_links = [
        CrossLink(
            entity_a_id=uuid4(),
            entity_a_name="Alpha",
            entity_b_id=uuid4(),
            entity_b_name="Beta",
            detection_method="co_occurrence",
            strength=5.0,
            detail="Co-appear in 5 observations but have no explicit relationship",
        ),
    ]

    await repo.record_cross_link_observations(eid, cross_links)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM observations
            WHERE engagement_id = $1 AND observation_type = 'insight'
            """,
            eid,
        )

    assert len(rows) == 1
    assert "Alpha" in rows[0]["raw_text"]
    assert "Beta" in rows[0]["raw_text"]
    meta = json.loads(rows[0]["metadata"])
    assert meta["detection_method"] == "co_occurrence"
    assert meta["impact_type"] == "expansion"


# Import at bottom to avoid issues if not used in all tests
from alec.knowledge.domain import CrossLink  # noqa: E402
