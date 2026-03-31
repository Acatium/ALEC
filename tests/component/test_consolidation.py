"""Component test for consolidation — MockLLM + real Postgres, full run."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.db

from alec.agents.mock_llm import MockLLMClient
from alec.db.embeddings import MockEmbeddingService
from alec.events.bus import EventBus
from alec.events.types import ConsolidationCompleted, ConsolidationStarted
from alec.knowledge.domain import ConsolidationConfig
from alec.knowledge.repositories.consolidation import ConsolidationRepository
from alec.runtime.consolidation import ConsolidationService


@pytest.mark.asyncio
async def test_full_consolidation_run(test_engagement):
    """End-to-end: create entities + observations, run consolidation, verify results."""
    pool, eid = test_engagement
    embedder = MockEmbeddingService()

    # Set up data: 2 entities with enough observations
    async with pool.acquire() as conn:
        _entity_a = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'AuthService', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("AuthService (service)"),
        )
        _entity_b = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'UserDB', 'database', 4, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("UserDB (database)"),
        )

        # Create observations (enough for trigger + stale detection)
        for i in range(25):
            text = f"AuthService handles authentication via UserDB scenario {i}"
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type,
                     metadata)
                VALUES ($1, $2, $3, $4, $5)
                """,
                eid,
                f"source-{i % 3}",
                text,
                "entity",
                json.dumps({"entity_name": "AuthService", "impact_type": "expansion"}),
            )

    # Set up mock LLM — will be called once per stale entity
    mock_llm = MockLLMClient()
    mock_llm.add_response(
        mock_llm.make_text_response(
            "## AuthService (service)\n"
            "(Consolidated from 25 observations across 3 sources)\n\n"
            "Core authentication service managing user identity.\n\n"
            "Relationships:\n- writes_to UserDB (confidence: 0.9)"
        )
    )
    mock_llm.add_response(
        mock_llm.make_text_response(
            "## UserDB (database)\n"
            "(Consolidated from 25 observations across 3 sources)\n\n"
            "Primary user data store backing AuthService."
        )
    )

    # Track events
    events: list = []

    async def capture(event):
        events.append(event)

    event_bus = EventBus()
    event_bus.subscribe(ConsolidationStarted, capture)
    event_bus.subscribe(ConsolidationCompleted, capture)

    # Run consolidation
    repo = ConsolidationRepository(pool)
    service = ConsolidationService(
        repo=repo,
        llm=mock_llm,
        embedder=embedder,
        event_bus=event_bus,
    )

    config = ConsolidationConfig(min_new_observations=20)
    result = await service.run(eid, config)

    # Verify result
    assert result is not None
    assert result.entities_consolidated >= 2
    assert result.units_created >= 2
    assert result.errors == []

    # Verify consolidated units in DB
    async with pool.acquire() as conn:
        units = await conn.fetch(
            """
            SELECT * FROM consolidated_units
            WHERE engagement_id = $1 AND status = 'current'
            ORDER BY freshness DESC
            """,
            eid,
        )

    assert len(units) >= 2
    summaries = [u["summary"] for u in units]
    assert any("AuthService" in s for s in summaries)
    assert any("UserDB" in s for s in summaries)

    # Verify events
    assert len(events) == 2
    assert events[0].event_type == "consolidation.started"
    assert events[0].stale_entity_count >= 2
    assert events[1].event_type == "consolidation.completed"
    assert events[1].units_created >= 2

    # Verify LLM was called correctly
    assert len(mock_llm.calls) == 2
    for call in mock_llm.calls:
        assert "consolidation" in call.system.lower()


@pytest.mark.asyncio
async def test_consolidation_not_triggered_insufficient_data(test_engagement):
    """Consolidation returns None when trigger conditions aren't met."""
    pool, eid = test_engagement

    mock_llm = MockLLMClient()
    embedder = MockEmbeddingService()
    event_bus = EventBus()

    repo = ConsolidationRepository(pool)
    service = ConsolidationService(
        repo=repo,
        llm=mock_llm,
        embedder=embedder,
        event_bus=event_bus,
    )

    # No observations, trigger should fail
    result = await service.run(eid, ConsolidationConfig(min_new_observations=20))
    assert result is None
    assert len(mock_llm.calls) == 0


@pytest.mark.asyncio
async def test_consolidation_cross_link_detection(test_engagement):
    """Cross-links are detected and recorded as insight observations."""
    pool, eid = test_engagement
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        # Create two entities that co-occur but have no relationship
        _entity_x = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'ConfigManager', 'service', 4, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("ConfigManager (service)"),
        )
        _entity_y = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'FeatureFlags', 'service', 3, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("FeatureFlags (service)"),
        )

        # Create co-occurring observations (enough for trigger + co-occurrence)
        for i in range(25):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"src-{i}",
                f"ConfigManager uses FeatureFlags to control rollout {i}",
                "entity",
            )

    mock_llm = MockLLMClient()
    # Responses for each entity synthesis
    mock_llm.add_response(mock_llm.make_text_response("## ConfigManager\nManages config."))
    mock_llm.add_response(mock_llm.make_text_response("## FeatureFlags\nManages feature flags."))

    event_bus = EventBus()
    repo = ConsolidationRepository(pool)
    service = ConsolidationService(
        repo=repo,
        llm=mock_llm,
        embedder=embedder,
        event_bus=event_bus,
    )

    config = ConsolidationConfig(min_new_observations=20, co_occurrence_threshold=3)
    result = await service.run(eid, config)

    assert result is not None
    assert result.cross_links_detected >= 1

    # Verify insight observations were created
    async with pool.acquire() as conn:
        insights = await conn.fetch(
            """
            SELECT * FROM observations
            WHERE engagement_id = $1 AND observation_type = 'insight'
            """,
            eid,
        )

    assert len(insights) >= 1
    insight_texts = [r["raw_text"] for r in insights]
    assert any("ConfigManager" in t and "FeatureFlags" in t for t in insight_texts)


@pytest.mark.asyncio
async def test_consolidation_update_existing_unit(test_engagement):
    """Re-running consolidation updates existing units, marking old ones stale."""
    pool, eid = test_engagement
    embedder = MockEmbeddingService()

    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities
                (engagement_id, name, entity_type, observation_count, embedding)
            VALUES ($1, 'VersionedService', 'service', 5, $2)
            RETURNING entity_id
            """,
            eid,
            await embedder.embed("VersionedService (service)"),
        )

        for i in range(25):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"source-{i}",
                f"VersionedService does thing {i}",
                "entity",
            )

    mock_llm = MockLLMClient()
    event_bus = EventBus()
    repo = ConsolidationRepository(pool)

    # First run
    mock_llm.add_response(mock_llm.make_text_response("## VersionedService v1\nInitial."))
    service = ConsolidationService(
        repo=repo, llm=mock_llm, embedder=embedder, event_bus=event_bus,
    )
    r1 = await service.run(eid, ConsolidationConfig(min_new_observations=20))
    assert r1 is not None
    assert r1.units_created >= 1

    # Add more observations so trigger fires again
    async with pool.acquire() as conn:
        for i in range(25):
            await conn.execute(
                """
                INSERT INTO observations
                    (engagement_id, source_ref, raw_text, observation_type)
                VALUES ($1, $2, $3, $4)
                """,
                eid,
                f"new-source-{i}",
                f"VersionedService updated behavior {i}",
                "entity",
            )

    # Second run (min_interval_minutes=0 so it triggers immediately)
    mock_llm.add_response(mock_llm.make_text_response("## VersionedService v2\nUpdated."))
    r2 = await service.run(
        eid,
        ConsolidationConfig(
            min_new_observations=20, min_interval_minutes=0
        ),
    )
    assert r2 is not None
    assert r2.units_updated >= 1

    # Verify version history in DB
    async with pool.acquire() as conn:
        units = await conn.fetch(
            """
            SELECT * FROM consolidated_units
            WHERE subject_entity = $1 AND engagement_id = $2
            ORDER BY version
            """,
            entity_id,
            eid,
        )

    assert len(units) >= 2
    statuses = [u["status"] for u in units]
    assert "stale" in statuses
    assert "current" in statuses
