"""Unit tests for worker drift detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from alec.agents.mock_llm import MockLLMClient
from alec.events.bus import EventBus
from alec.knowledge.domain import TaskRecord, WorkerResult
from alec.runtime.budget import BudgetTracker
from alec.runtime.drift import WorkerLoopState, check_drift, hash_tool_call
from alec.runtime.worker import WorkerService

# ── hash_tool_call tests ─────────────────────────────────────


def test_hash_tool_call_deterministic():
    """Same inputs produce the same hash."""
    h1 = hash_tool_call("read", {"ref": "file.py"})
    h2 = hash_tool_call("read", {"ref": "file.py"})
    assert h1 == h2


def test_hash_tool_call_sorted_keys():
    """Key order does not affect the hash."""
    h1 = hash_tool_call("add_entity", {"a": 1, "b": 2})
    h2 = hash_tool_call("add_entity", {"b": 2, "a": 1})
    assert h1 == h2


def test_hash_tool_call_different_inputs():
    """Different inputs produce different hashes."""
    h1 = hash_tool_call("read", {"ref": "a.py"})
    h2 = hash_tool_call("read", {"ref": "b.py"})
    assert h1 != h2


def test_hash_tool_call_different_names():
    """Different tool names produce different hashes."""
    h1 = hash_tool_call("read", {"ref": "a.py"})
    h2 = hash_tool_call("search", {"ref": "a.py"})
    assert h1 != h2


# ── WorkerResult default fields ──────────────────────────────


def test_worker_result_drift_fields():
    """WorkerResult drift fields default to safe values."""
    wr = WorkerResult(
        task_id=uuid4(),
        worker_id="w-1",
        entities_written=0,
        relationships_written=0,
        observations_written=0,
        followups_suggested=0,
        scope_overflow=False,
    )
    assert wr.drift_detected is False
    assert wr.duplicate_calls_skipped == 0
    assert wr.retries_exhausted == 0


# ── WorkerLoopState ──────────────────────────────────────────


def test_worker_loop_state_defaults():
    """WorkerLoopState starts clean."""
    state = WorkerLoopState()
    assert state.tool_call_cache == {}
    assert state.tool_error_counts == {}
    assert state.duplicate_calls_skipped == 0
    assert state.retries_exhausted == 0
    assert state.drift_detected is False


# ── check_drift tests ────────────────────────────────────────


def test_check_drift_no_entities():
    """No entities discovered — not drifting."""
    state = WorkerLoopState()
    assert check_drift(state, "survey") is False


def test_check_drift_all_in_scope():
    """All entity types match scope — not drifting."""
    state = WorkerLoopState()
    state.entity_types_discovered = {"survey_result": 5, "survey_item": 3}
    assert check_drift(state, "survey") is False


def test_check_drift_majority_out_of_scope():
    """Most entity types outside scope — drifting."""
    state = WorkerLoopState()
    state.entity_types_discovered = {"database": 8, "survey": 2}
    assert check_drift(state, "survey") is True


def test_check_drift_case_insensitive():
    """Scope matching should be case-insensitive."""
    state = WorkerLoopState()
    state.entity_types_discovered = {"Survey_Report": 5}
    assert check_drift(state, "survey") is False


def test_check_drift_boundary_threshold():
    """Exactly at threshold — not drifting (> not >=)."""
    state = WorkerLoopState()
    # 50% out of scope, threshold is 0.5 → not drifting (> 0.5 required)
    state.entity_types_discovered = {"other": 1, "survey": 1}
    assert check_drift(state, "survey", threshold=0.5) is False

    # 51% out of scope → drifting
    state.entity_types_discovered = {"other": 51, "survey": 49}
    assert check_drift(state, "survey", threshold=0.5) is True


def test_check_drift_entity_type_contains_scope():
    """Entity type containing scope keyword is in-scope."""
    state = WorkerLoopState()
    state.entity_types_discovered = {"deep_analysis": 5}
    assert check_drift(state, "deep") is False


# ── WorkerLoopState new fields ───────────────────────────────


def test_worker_loop_state_new_fields():
    """WorkerLoopState has entity_types_discovered and tool_call_count."""
    state = WorkerLoopState()
    assert state.entity_types_discovered == {}
    assert state.tool_call_count == 0


# ── Integration: duplicate detection via WorkerService ───────


def _make_task() -> TaskRecord:
    return TaskRecord(
        task_id=uuid4(),
        engagement_id=uuid4(),
        coordinator_id=uuid4(),
        directive="Explore the source",
        source_type="local_files",
        source_ref="/tmp/test",
    )


def _make_mock_connector() -> MagicMock:
    connector = MagicMock()
    connector.survey = AsyncMock(return_value=[{"ref": "a.py", "type": "file"}])
    connector.read = AsyncMock(return_value="file contents")
    connector.search = AsyncMock(return_value=[])
    connector.list_children = AsyncMock(return_value=[])
    connector.source_type = MagicMock(return_value="local_files")
    connector.source_ref = MagicMock(return_value="/tmp/test")
    return connector


def _make_mock_graph() -> MagicMock:
    graph = MagicMock()
    graph.entities_written = 0
    graph.relationships_written = 0
    graph.observations_written = 0
    graph.followups_suggested = 0
    graph.execute = AsyncMock(return_value="OK")
    return graph


@pytest.mark.asyncio
async def test_duplicate_detection():
    """Worker should skip duplicate tool calls and return cached result."""
    mock_llm = MockLLMClient()

    # Turn 1: LLM calls survey
    mock_llm.add_response(
        mock_llm.make_tool_response([("tc1", "survey", {})])
    )
    # Turn 2: LLM calls survey again (duplicate)
    mock_llm.add_response(
        mock_llm.make_tool_response([("tc2", "survey", {})])
    )
    # Turn 3: LLM ends
    mock_llm.add_response(mock_llm.make_text_response("Done"))

    connector = _make_mock_connector()
    graph = _make_mock_graph()

    worker = WorkerService(
        llm=mock_llm,
        connector=connector,
        graph=graph,
        budget=BudgetTracker(max_tokens=1_000_000),
        event_bus=EventBus(),
    )

    result = await worker.run(_make_task())

    # survey() should have been called only once — the duplicate was cached
    assert connector.survey.call_count == 1
    assert result.duplicate_calls_skipped == 1


@pytest.mark.asyncio
async def test_error_retry_limit():
    """Worker should stop retrying a tool after max_retries_per_tool failures."""
    mock_llm = MockLLMClient()

    # LLM keeps calling read with the same bad ref 4 times, limit is 2
    for i in range(4):
        mock_llm.add_response(
            mock_llm.make_tool_response([(f"tc{i}", "read", {"ref": "bad.py"})])
        )
    mock_llm.add_response(mock_llm.make_text_response("Giving up"))

    connector = _make_mock_connector()
    connector.read = AsyncMock(side_effect=Exception("File not found"))

    graph = _make_mock_graph()

    worker = WorkerService(
        llm=mock_llm,
        connector=connector,
        graph=graph,
        budget=BudgetTracker(max_tokens=1_000_000),
        event_bus=EventBus(),
        max_retries_per_tool=2,
    )

    result = await worker.run(_make_task())

    # read() should have been called only 2 times (the limit),
    # remaining 2 calls should have been refused
    assert connector.read.call_count == 2
    assert result.retries_exhausted == 2
