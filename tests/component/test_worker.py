"""Component tests for WorkerService — MockLLM + real DB."""

from __future__ import annotations

import os
import tempfile
from uuid import uuid4

import pytest

pytestmark = pytest.mark.db

from alec.agents.mock_llm import MockLLMClient
from alec.connectors.local_files import LocalFilesConnector
from alec.db.embeddings import MockEmbeddingService
from alec.events.bus import EventBus
from alec.events.types import WorkerCompleted
from alec.knowledge.domain import TaskRecord
from alec.knowledge.graph_writer import GraphWriter
from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.relationships import RelationshipRepository
from alec.runtime.budget import BudgetTracker
from alec.runtime.worker import WorkerService


@pytest.fixture
def source_dir():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "readme.md"), "w") as f:
            f.write("# Architecture\nService A calls Service B.\nService B uses Database C.")
        with open(os.path.join(d, "api.md"), "w") as f:
            f.write("# API\nEndpoint: /users\nEndpoint: /orders")
        yield d


@pytest.mark.asyncio
async def test_worker_full_loop(test_engagement, source_dir):
    pool, eid = test_engagement
    mock_llm = MockLLMClient()
    event_bus = EventBus()
    completed_events = []

    async def on_complete(e: WorkerCompleted) -> None:
        completed_events.append(e)

    event_bus.subscribe(WorkerCompleted, on_complete)

    # Script the LLM to survey, read, add entities, then stop
    mock_llm.add_response(
        mock_llm.make_tool_response(
            [
                ("tc1", "survey", {}),
            ]
        )
    )
    mock_llm.add_response(
        mock_llm.make_tool_response(
            [
                ("tc2", "read", {"ref": "readme.md"}),
            ]
        )
    )
    mock_llm.add_response(
        mock_llm.make_tool_response(
            [
                ("tc3", "add_entity", {"name": "ServiceA", "entity_type": "service"}),
                ("tc4", "add_entity", {"name": "ServiceB", "entity_type": "service"}),
            ]
        )
    )
    mock_llm.add_response(
        mock_llm.make_tool_response(
            [
                (
                    "tc5",
                    "add_relationship",
                    {
                        "from_entity": "ServiceA",
                        "to_entity": "ServiceB",
                        "relationship_type": "calls",
                        "evidence": "readme.md says A calls B",
                    },
                ),
            ]
        )
    )
    mock_llm.add_response(mock_llm.make_text_response("Done exploring."))

    task = TaskRecord(
        task_id=uuid4(),
        engagement_id=eid,
        coordinator_id=None,
        directive="Survey the docs directory",
        source_type="local_files",
        source_ref=source_dir,
        max_scope="survey",
    )

    connector = LocalFilesConnector(source_dir)
    graph = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref=source_dir,
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )
    budget = BudgetTracker(max_tokens=100_000)

    worker = WorkerService(
        llm=mock_llm,
        connector=connector,
        graph=graph,
        budget=budget,
        event_bus=event_bus,
    )

    result = await worker.run(task)

    assert result.error is None
    assert result.entities_written == 2
    assert result.relationships_written == 1
    assert result.scope_overflow is False
    assert len(mock_llm.calls) == 5

    # Verify DB state
    entity_repo = EntityRepository(pool)
    entities = await entity_repo.list_by_engagement(eid)
    names = {e.name for e in entities}
    assert "ServiceA" in names
    assert "ServiceB" in names

    # Verify completed event emitted
    assert len(completed_events) == 1
    assert completed_events[0].entities_written == 2


@pytest.mark.asyncio
async def test_worker_budget_stop(test_engagement, source_dir):
    pool, eid = test_engagement
    mock_llm = MockLLMClient()

    # Keep making tool calls forever
    for _ in range(20):
        mock_llm.add_response(
            mock_llm.make_tool_response(
                [
                    ("tc", "survey", {}),
                ]
            )
        )

    task = TaskRecord(
        task_id=uuid4(),
        engagement_id=eid,
        coordinator_id=None,
        directive="Survey",
        source_type="local_files",
        source_ref=source_dir,
        max_scope="survey",
    )

    connector = LocalFilesConnector(source_dir)
    graph = GraphWriter(
        engagement_id=eid,
        model_id=None,
        worker_id="test-worker",
        source_ref=source_dir,
        entities=EntityRepository(pool),
        relationships=RelationshipRepository(pool),
        observations=ObservationRepository(pool),
        embedder=MockEmbeddingService(),
    )
    # Tiny budget — will exhaust quickly
    budget = BudgetTracker(max_tokens=500)

    worker = WorkerService(
        llm=mock_llm,
        connector=connector,
        graph=graph,
        budget=budget,
        event_bus=EventBus(),
    )

    result = await worker.run(task)
    assert result.scope_overflow is True
