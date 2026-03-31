"""Integration tests for GraphWriter."""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.db

from alec.db.embeddings import MockEmbeddingService
from alec.knowledge.graph_writer import GraphWriter
from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.relationships import RelationshipRepository


@pytest.mark.asyncio
async def test_add_entity(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    result = await gw.execute(
        "add_entity",
        {
            "name": "TestService",
            "entity_type": "service",
            "aliases": ["test-svc"],
        },
    )

    assert "Created" in result
    assert gw.entities_written == 1


@pytest.mark.asyncio
async def test_add_entity_dedup(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    # First add creates
    await gw.execute("add_entity", {"name": "Svc", "entity_type": "service"})
    assert gw.entities_written == 1

    # Second add updates (local cache hit)
    result = await gw.execute("add_entity", {"name": "Svc", "entity_type": "service"})
    assert "Updated" in result
    assert gw.entities_written == 1  # No new entity


@pytest.mark.asyncio
async def test_add_relationship(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    # Add entities first
    await gw.execute("add_entity", {"name": "A", "entity_type": "service"})
    await gw.execute("add_entity", {"name": "B", "entity_type": "database"})

    result = await gw.execute(
        "add_relationship",
        {
            "from_entity": "A",
            "to_entity": "B",
            "relationship_type": "reads_from",
            "evidence": "A reads from database B",
        },
    )

    assert "reads_from" in result
    assert gw.relationships_written == 1


@pytest.mark.asyncio
async def test_add_relationship_auto_creates_entities(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    # Add relationship without pre-creating entities
    result = await gw.execute(
        "add_relationship",
        {
            "from_entity": "NewA",
            "to_entity": "NewB",
            "relationship_type": "calls",
            "evidence": "NewA calls NewB",
        },
    )

    assert "calls" in result
    assert gw.entities_written == 2  # Both auto-created
    assert gw.relationships_written == 1


@pytest.mark.asyncio
async def test_add_observation(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    result = await gw.execute(
        "add_observation",
        {
            "text": "Interesting finding about the system",
            "observation_type": "insight",
            "impact_type": "expansion",
        },
    )

    assert "insight" in result
    assert gw.observations_written == 1


@pytest.mark.asyncio
async def test_suggest_followup(test_engagement):
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    result = await gw.execute(
        "suggest_followup",
        {
            "question": "What is the deployment strategy?",
            "priority": "high",
        },
    )

    assert "high" in result
    assert gw.followups_suggested == 1


# ── gap-v5-001: Convergence signal tests ─────────────────────


@pytest.mark.asyncio
async def test_new_entity_creates_expansion_observation(test_engagement):
    """New entity should create an observation with impact_type='expansion'."""
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    await gw.execute(
        "add_entity",
        {
            "name": "NewService",
            "entity_type": "service",
        },
    )

    async with pool.acquire() as conn:
        obs = await conn.fetch(
            """
            SELECT metadata FROM observations
            WHERE engagement_id = $1
              AND metadata->>'impact_type' = 'expansion'
              AND observation_type = 'entity_discovered'
            """,
            eid,
        )
    assert len(obs) == 1


@pytest.mark.asyncio
async def test_rediscovered_entity_db_creates_reinforcement(test_engagement):
    """Entity found in DB (not cache) should create reinforcement observation."""
    pool, eid = test_engagement
    obs_repo = ObservationRepository(pool)
    entity_repo = EntityRepository(pool)
    rel_repo = RelationshipRepository(pool)
    embedder = MockEmbeddingService()

    # First writer creates entity
    gw1 = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="worker-1",
        source_ref="file-1",
        entities=entity_repo,
        relationships=rel_repo,
        observations=obs_repo,
        embedder=embedder,
    )
    await gw1.execute(
        "add_entity",
        {"name": "SharedSvc", "entity_type": "service"},
    )

    # Second writer (fresh cache) rediscovers it
    gw2 = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="worker-2",
        source_ref="file-2",
        entities=entity_repo,
        relationships=rel_repo,
        observations=obs_repo,
        embedder=embedder,
    )
    await gw2.execute(
        "add_entity",
        {"name": "SharedSvc", "entity_type": "service"},
    )

    async with pool.acquire() as conn:
        obs = await conn.fetch(
            """
            SELECT metadata FROM observations
            WHERE engagement_id = $1
              AND metadata->>'impact_type' = 'reinforcement'
              AND observation_type = 'entity_discovered'
            """,
            eid,
        )
    assert len(obs) == 1


@pytest.mark.asyncio
async def test_rediscovered_entity_cache_creates_reinforcement(
    test_engagement,
):
    """Entity found in local cache creates reinforcement observation."""
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    await gw.execute(
        "add_entity",
        {"name": "CachedSvc", "entity_type": "service"},
    )
    await gw.execute(
        "add_entity",
        {"name": "CachedSvc", "entity_type": "service"},
    )

    async with pool.acquire() as conn:
        obs = await conn.fetch(
            """
            SELECT metadata FROM observations
            WHERE engagement_id = $1
              AND metadata->>'impact_type' = 'reinforcement'
              AND observation_type = 'entity_discovered'
            """,
            eid,
        )
    assert len(obs) == 1


@pytest.mark.asyncio
async def test_new_relationship_creates_expansion_observation(
    test_engagement,
):
    """New relationship evidence should have impact_type='expansion'."""
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    await gw.execute(
        "add_entity",
        {"name": "X", "entity_type": "service"},
    )
    await gw.execute(
        "add_entity",
        {"name": "Y", "entity_type": "database"},
    )
    await gw.execute(
        "add_relationship",
        {
            "from_entity": "X",
            "to_entity": "Y",
            "relationship_type": "reads_from",
            "evidence": "X reads from Y",
        },
    )

    async with pool.acquire() as conn:
        obs = await conn.fetch(
            """
            SELECT metadata FROM observations
            WHERE engagement_id = $1
              AND observation_type = 'relationship'
              AND metadata->>'impact_type' = 'expansion'
            """,
            eid,
        )
    assert len(obs) == 1


@pytest.mark.asyncio
async def test_existing_relationship_creates_reinforcement_observation(
    test_engagement,
):
    """Re-adding same relationship triple produces reinforcement."""
    pool, eid = test_engagement
    gw = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref="test-file",
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )

    await gw.execute(
        "add_entity",
        {"name": "P", "entity_type": "service"},
    )
    await gw.execute(
        "add_entity",
        {"name": "Q", "entity_type": "service"},
    )
    await gw.execute(
        "add_relationship",
        {
            "from_entity": "P",
            "to_entity": "Q",
            "relationship_type": "calls",
            "evidence": "P calls Q (first source)",
        },
    )
    await gw.execute(
        "add_relationship",
        {
            "from_entity": "P",
            "to_entity": "Q",
            "relationship_type": "calls",
            "evidence": "P calls Q (second source confirms)",
        },
    )

    async with pool.acquire() as conn:
        expansion = await conn.fetch(
            """
            SELECT 1 FROM observations
            WHERE engagement_id = $1
              AND observation_type = 'relationship'
              AND metadata->>'impact_type' = 'expansion'
            """,
            eid,
        )
        reinforcement = await conn.fetch(
            """
            SELECT 1 FROM observations
            WHERE engagement_id = $1
              AND observation_type = 'relationship'
              AND metadata->>'impact_type' = 'reinforcement'
            """,
            eid,
        )
    assert len(expansion) == 1
    assert len(reinforcement) == 1


# ── Concurrency test (P3.2) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_writers_no_duplicate_entities(test_engagement):
    """3 concurrent GraphWriter instances writing the same entity should not create duplicates."""
    pool, eid = test_engagement
    embedder = MockEmbeddingService()

    async def write_shared_entity(worker_id: str) -> None:
        gw = GraphWriter(
            engagement_id=eid,
            model_id=None,
            worker_id=worker_id,
            source_ref=f"file-{worker_id}",
            entities=EntityRepository(pool),
            relationships=RelationshipRepository(pool),
            observations=ObservationRepository(pool),
            embedder=embedder,
        )
        await gw.execute(
            "add_entity",
            {"name": "SharedEntity", "entity_type": "service"},
        )

    await asyncio.gather(
        write_shared_entity("w1"),
        write_shared_entity("w2"),
        write_shared_entity("w3"),
    )

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM entities "
            "WHERE engagement_id = $1 AND LOWER(name) = 'sharedentity'",
            eid,
        )
    assert count == 1, f"Expected 1 entity but found {count} — race condition detected"
