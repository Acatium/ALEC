"""Tests for consolidation prompt builder and ConsolidationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from alec.agents.mock_llm import MockLLMClient
from alec.agents.prompts.consolidation import (
    CONSOLIDATION_SYSTEM_PROMPT,
    build_consolidation_user_message,
)
from alec.db.embeddings import MockEmbeddingService
from alec.events.bus import EventBus
from alec.events.types import ConsolidationCompleted, ConsolidationStarted
from alec.knowledge.domain import (
    ConsolidationConfig,
    ConsolidationMaterial,
    CrossLink,
    StaleEntity,
)
from alec.runtime.consolidation import ConsolidationService

# ── Prompt builder tests ──────────────────────────────────────────


def test_system_prompt_not_empty():
    assert len(CONSOLIDATION_SYSTEM_PROMPT) > 100


def test_build_consolidation_user_message_basic():
    mat = ConsolidationMaterial(
        entity_id=uuid4(),
        entity_name="PaymentService",
        entity_type="service",
        aliases=["pay-svc"],
        properties={"language": "python"},
        observations=[
            {
                "raw_text": "Handles payment processing",
                "source_ref": "docs/arch.md",
                "observation_type": "entity",
            },
        ],
        relationships_outgoing=[
            {"to_name": "PaymentDB", "relationship_type": "writes_to", "confidence": 0.9},
        ],
        relationships_incoming=[
            {"from_name": "OrderService", "relationship_type": "calls", "confidence": 0.8},
        ],
        alignments=[],
    )
    msg = build_consolidation_user_message(mat)

    assert "PaymentService" in msg
    assert "service" in msg
    assert "pay-svc" in msg
    assert "language=python" in msg
    assert "Handles payment processing" in msg
    assert "docs/arch.md" in msg
    assert "PaymentDB" in msg
    assert "writes_to" in msg
    assert "OrderService" in msg
    assert "calls" in msg


def test_build_consolidation_user_message_no_optional_sections():
    mat = ConsolidationMaterial(
        entity_id=uuid4(),
        entity_name="SimpleEntity",
        entity_type="concept",
        aliases=[],
        properties={},
        observations=[
            {
                "raw_text": "A basic concept",
                "source_ref": "wiki",
                "observation_type": "entity",
            },
        ],
        relationships_outgoing=[],
        relationships_incoming=[],
        alignments=[],
    )
    msg = build_consolidation_user_message(mat)

    assert "SimpleEntity" in msg
    assert "Outgoing Relationships" not in msg
    assert "Incoming Relationships" not in msg
    assert "Cross-Model Alignments" not in msg


def test_build_consolidation_user_message_with_alignments():
    mat = ConsolidationMaterial(
        entity_id=uuid4(),
        entity_name="UserService",
        entity_type="service",
        aliases=[],
        properties={},
        observations=[],
        relationships_outgoing=[],
        relationships_incoming=[],
        alignments=[
            {
                "other_entity_name": "ProfileService",
                "model_name": "Architecture Model",
                "alignment_type": "overlaps_with",
            },
        ],
    )
    msg = build_consolidation_user_message(mat)

    assert "Cross-Model Alignments" in msg
    assert "ProfileService" in msg
    assert "overlaps_with" in msg


def test_build_consolidation_user_message_observation_count():
    observations = [
        {
            "raw_text": f"Observation {i}",
            "source_ref": f"source-{i}",
            "observation_type": "entity",
        }
        for i in range(5)
    ]
    mat = ConsolidationMaterial(
        entity_id=uuid4(),
        entity_name="MultiObsEntity",
        entity_type="service",
        aliases=[],
        properties={},
        observations=observations,
        relationships_outgoing=[],
        relationships_incoming=[],
        alignments=[],
    )
    msg = build_consolidation_user_message(mat)

    assert "Observations (5)" in msg


# ── ConsolidationService unit tests ──────────────────────────────


def _make_mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.should_consolidate = AsyncMock(return_value=True)
    repo.find_stale_entities = AsyncMock(return_value=[])
    repo.gather_material = AsyncMock()
    repo.store_consolidated_unit = AsyncMock()
    repo.detect_cross_links = AsyncMock(return_value=[])
    repo.record_cross_link_observations = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_service_skips_when_not_triggered():
    repo = _make_mock_repo()
    repo.should_consolidate = AsyncMock(return_value=False)

    llm = MockLLMClient()
    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(uuid4(), ConsolidationConfig())

    assert result is None
    repo.find_stale_entities.assert_not_called()
    assert len(llm.calls) == 0


@pytest.mark.asyncio
async def test_service_skips_when_no_stale_entities():
    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(return_value=[])

    llm = MockLLMClient()
    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(uuid4(), ConsolidationConfig())

    assert result is not None
    assert result.entities_consolidated == 0


@pytest.mark.asyncio
async def test_service_synthesizes_entity():
    entity_id = uuid4()
    engagement_id = uuid4()

    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(
        return_value=[
            StaleEntity(
                entity_id=entity_id,
                name="PaymentService",
                entity_type="service",
                observation_count=5,
                new_observations=3,
                has_existing_unit=False,
            ),
        ]
    )
    repo.gather_material = AsyncMock(
        return_value=ConsolidationMaterial(
            entity_id=entity_id,
            entity_name="PaymentService",
            entity_type="service",
            aliases=[],
            properties={},
            observations=[
                {
                    "raw_text": "Processes payments",
                    "source_ref": "docs",
                    "observation_type": "entity",
                }
            ],
            relationships_outgoing=[],
            relationships_incoming=[],
            alignments=[],
        )
    )

    llm = MockLLMClient()
    summary_text = "## PaymentService (service)\nProcesses payments."
    llm.add_response(llm.make_text_response(summary_text))

    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(engagement_id, ConsolidationConfig())

    assert result is not None
    assert result.entities_consolidated == 1
    assert result.units_created == 1
    assert result.units_updated == 0
    assert len(llm.calls) == 1
    repo.store_consolidated_unit.assert_called_once()


@pytest.mark.asyncio
async def test_service_updates_existing_unit():
    entity_id = uuid4()

    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(
        return_value=[
            StaleEntity(
                entity_id=entity_id,
                name="PaymentService",
                entity_type="service",
                observation_count=10,
                new_observations=5,
                has_existing_unit=True,
            ),
        ]
    )
    repo.gather_material = AsyncMock(
        return_value=ConsolidationMaterial(
            entity_id=entity_id,
            entity_name="PaymentService",
            entity_type="service",
            aliases=[],
            properties={},
            observations=[
                {"raw_text": "Updated info", "source_ref": "docs", "observation_type": "entity"}
            ],
            relationships_outgoing=[],
            relationships_incoming=[],
            alignments=[],
        )
    )

    llm = MockLLMClient()
    llm.add_response(llm.make_text_response("## PaymentService (service)\nUpdated."))

    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(uuid4(), ConsolidationConfig())

    assert result is not None
    assert result.units_created == 0
    assert result.units_updated == 1


@pytest.mark.asyncio
async def test_service_per_entity_error_isolation():
    eid1, eid2 = uuid4(), uuid4()

    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(
        return_value=[
            StaleEntity(
                entity_id=eid1, name="FailEntity", entity_type="service",
                observation_count=5, new_observations=3, has_existing_unit=False,
            ),
            StaleEntity(
                entity_id=eid2, name="GoodEntity", entity_type="service",
                observation_count=5, new_observations=3, has_existing_unit=False,
            ),
        ]
    )

    call_count = 0

    async def gather_side_effect(engagement_id, entity):
        nonlocal call_count
        call_count += 1
        if entity.entity_id == eid1:
            raise RuntimeError("DB connection lost")
        return ConsolidationMaterial(
            entity_id=entity.entity_id,
            entity_name=entity.name,
            entity_type=entity.entity_type,
            aliases=[], properties={},
            observations=[{"raw_text": "ok", "source_ref": "x", "observation_type": "entity"}],
            relationships_outgoing=[], relationships_incoming=[], alignments=[],
        )

    repo.gather_material = AsyncMock(side_effect=gather_side_effect)

    llm = MockLLMClient()
    llm.add_response(llm.make_text_response("## GoodEntity\nSummary."))

    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(uuid4(), ConsolidationConfig())

    assert result is not None
    assert result.entities_consolidated == 1  # Only GoodEntity succeeded
    assert result.units_created == 1
    assert len(result.errors) == 1
    assert "FailEntity" in result.errors[0]


@pytest.mark.asyncio
async def test_service_records_cross_links():
    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(return_value=[])
    repo.detect_cross_links = AsyncMock(
        return_value=[
            CrossLink(
                entity_a_id=uuid4(),
                entity_a_name="ServiceA",
                entity_b_id=uuid4(),
                entity_b_name="ServiceB",
                detection_method="co_occurrence",
                strength=5.0,
                detail="Co-appear in 5 observations",
            ),
        ]
    )

    llm = MockLLMClient()
    embedder = MockEmbeddingService()
    event_bus = EventBus()

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    result = await service.run(uuid4(), ConsolidationConfig())

    assert result is not None
    assert result.cross_links_detected == 1
    assert result.cross_links_recorded == 1
    repo.record_cross_link_observations.assert_called_once()


@pytest.mark.asyncio
async def test_service_emits_events():
    entity_id = uuid4()
    engagement_id = uuid4()

    repo = _make_mock_repo()
    repo.find_stale_entities = AsyncMock(
        return_value=[
            StaleEntity(
                entity_id=entity_id, name="Svc", entity_type="service",
                observation_count=5, new_observations=3, has_existing_unit=False,
            ),
        ]
    )
    repo.gather_material = AsyncMock(
        return_value=ConsolidationMaterial(
            entity_id=entity_id, entity_name="Svc", entity_type="service",
            aliases=[], properties={},
            observations=[{"raw_text": "x", "source_ref": "y", "observation_type": "entity"}],
            relationships_outgoing=[], relationships_incoming=[], alignments=[],
        )
    )

    llm = MockLLMClient()
    llm.add_response(llm.make_text_response("## Svc\nSummary."))

    embedder = MockEmbeddingService()
    event_bus = EventBus()

    events_received: list = []

    async def capture_event(event):
        events_received.append(event)

    event_bus.subscribe(ConsolidationStarted, capture_event)
    event_bus.subscribe(ConsolidationCompleted, capture_event)

    service = ConsolidationService(
        repo=repo,
        llm=llm,
        embedder=embedder,
        event_bus=event_bus,
    )
    await service.run(engagement_id, ConsolidationConfig())

    assert len(events_received) == 2
    assert events_received[0].event_type == "consolidation.started"
    assert events_received[1].event_type == "consolidation.completed"
