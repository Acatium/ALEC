"""Tests for post-cycle deduplication sweep logic."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from alec.knowledge.dedup import DedupResult, run_dedup_sweep


@pytest.fixture
def engagement_id():
    return uuid4()


@pytest.fixture
def mock_embedder():
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 384)
    return embedder


def _make_pool(conn):
    """Create a mock pool where acquire() returns an async context manager."""
    pool = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool


def _make_transactional_conn(fetch_results):
    """Create a mock connection that supports fetch, execute, and transaction().

    fetch_results is a list of lists — each conn.fetch() call consumes the next
    entry.  Phase 1 (alias cross-match) does one fetch, Phase 2 (embedding)
    does another, so provide at least two entries.
    """
    conn = AsyncMock()

    call_idx = 0

    async def _fetch(*args, **kwargs):
        nonlocal call_idx
        if call_idx < len(fetch_results):
            result = fetch_results[call_idx]
            call_idx += 1
            return result
        return []

    conn.fetch = _fetch
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def _transaction():
        yield

    conn.transaction = _transaction
    return conn


class TestDedupResult:
    def test_defaults(self):
        result = DedupResult()
        assert result.pairs_evaluated == 0
        assert result.auto_merged == 0
        assert result.candidates_logged == 0
        assert result.errors == []

    def test_custom_values(self):
        result = DedupResult(pairs_evaluated=10, auto_merged=3, candidates_logged=5)
        assert result.pairs_evaluated == 10
        assert result.auto_merged == 3
        assert result.candidates_logged == 5


# ---------------------------------------------------------------------------
# Phase 1: Alias cross-match tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alias_cross_match_auto_merges(engagement_id, mock_embedder):
    """When entity A's name is in entity B's aliases, auto-merge unconditionally."""
    id_a, id_b = uuid4(), uuid4()
    alias_pair = {
        "id_a": id_a, "name_a": "EU AI Act",
        "obs_a": 42,
        "id_b": id_b, "name_b": "Regulation (EU) 2024/1689",
        "obs_b": 13,
    }

    # Phase 1 returns alias pair, Phase 2 returns nothing
    conn = _make_transactional_conn([[alias_pair], []])
    pool = _make_pool(conn)

    with patch("alec.knowledge.dedup.merge_entities", new_callable=AsyncMock) as mock_merge:
        result = await run_dedup_sweep(engagement_id, pool, mock_embedder)

        assert result.auto_merged == 1
        assert result.pairs_evaluated == 1
        mock_merge.assert_awaited_once()
        merge_args = mock_merge.call_args
        # Target should be id_a (more observations)
        assert merge_args[0][2] == id_a
        assert merge_args[0][3] == id_b


@pytest.mark.asyncio
async def test_alias_cross_match_skips_already_merged(engagement_id, mock_embedder):
    """If an entity was already merged in Phase 1, Phase 2 should skip it."""
    id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
    alias_pair = {
        "id_a": id_a, "name_a": "EU AI Act",
        "obs_a": 42,
        "id_b": id_b, "name_b": "Regulation (EU) 2024/1689",
        "obs_b": 13,
    }
    # Phase 2 returns a pair involving the already-merged id_b
    embedding_pair = {
        "id_a": id_b, "name_a": "Regulation (EU) 2024/1689", "type_a": "policy",
        "aliases_a": [], "obs_a": 13,
        "id_b": id_c, "name_b": "AI Regulation", "type_b": "policy",
        "aliases_b": [], "obs_b": 5,
        "embedding_sim": 0.90,
    }

    conn = _make_transactional_conn([[alias_pair], [embedding_pair]])
    pool = _make_pool(conn)

    with patch("alec.knowledge.dedup.merge_entities", new_callable=AsyncMock) as mock_merge:
        result = await run_dedup_sweep(
            engagement_id, pool, mock_embedder, auto_merge_threshold=0.50,
        )

        # Only the alias cross-match should merge; Phase 2 pair skipped
        assert mock_merge.await_count == 1
        assert result.auto_merged == 1


@pytest.mark.asyncio
async def test_alias_cross_match_error_doesnt_crash(engagement_id, mock_embedder):
    """Errors in alias cross-match are caught and recorded."""
    alias_pair = {
        "id_a": uuid4(), "name_a": "Entity A",
        "obs_a": 5,
        "id_b": uuid4(), "name_b": "Entity B",
        "obs_b": 3,
    }

    conn = _make_transactional_conn([[alias_pair], []])
    pool = _make_pool(conn)

    with patch(
        "alec.knowledge.dedup.merge_entities",
        new_callable=AsyncMock,
        side_effect=Exception("merge failed"),
    ):
        result = await run_dedup_sweep(engagement_id, pool, mock_embedder)

    assert result.pairs_evaluated == 1
    assert len(result.errors) >= 1
    assert result.auto_merged == 0


# ---------------------------------------------------------------------------
# Phase 2: Embedding similarity tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_pairs_returns_empty_result(engagement_id, mock_embedder):
    """When no similar pairs are found in either phase, return zero counts."""
    # Phase 1 empty, Phase 2 empty
    conn = _make_transactional_conn([[], []])
    pool = _make_pool(conn)

    result = await run_dedup_sweep(engagement_id, pool, mock_embedder)

    assert result.pairs_evaluated == 0
    assert result.auto_merged == 0
    assert result.candidates_logged == 0


@pytest.mark.asyncio
async def test_high_score_pair_triggers_auto_merge(engagement_id, mock_embedder):
    """When a pair has combined score >= threshold, it should be auto-merged."""
    id_a, id_b = uuid4(), uuid4()
    pair = {
        "id_a": id_a, "name_a": "BCBS 239", "type_a": "policy",
        "aliases_a": [], "obs_a": 10,
        "id_b": id_b, "name_b": "BCBS-239", "type_b": "policy",
        "aliases_b": [], "obs_b": 3,
        "embedding_sim": 0.95,
    }

    # Phase 1 empty, Phase 2 returns the pair
    conn = _make_transactional_conn([[], [pair]])
    pool = _make_pool(conn)

    with patch("alec.knowledge.dedup.merge_entities", new_callable=AsyncMock) as mock_merge:
        result = await run_dedup_sweep(
            engagement_id, pool, mock_embedder, auto_merge_threshold=0.92,
        )

        assert result.pairs_evaluated == 1
        # BCBS 239 vs BCBS-239 after normalization are nearly identical
        # combined score should be >= 0.92
        mock_merge.assert_awaited_once()
        merge_args = mock_merge.call_args
        # Target should be id_a (more observations)
        assert merge_args[0][2] == id_a  # target_id
        assert merge_args[0][3] == id_b  # source_id
        assert result.auto_merged == 1


@pytest.mark.asyncio
async def test_low_score_pair_logged_as_candidate(engagement_id, mock_embedder):
    """When a pair has score below threshold, it should be logged for user review."""
    id_a, id_b = uuid4(), uuid4()
    pair = {
        "id_a": id_a, "name_a": "Traffic Signal", "type_a": "concept",
        "aliases_a": [], "obs_a": 5,
        "id_b": id_b, "name_b": "Traffic Control System", "type_b": "concept",
        "aliases_b": [], "obs_b": 3,
        "embedding_sim": 0.82,
    }

    # Phase 1 empty, Phase 2 returns the pair
    conn = _make_transactional_conn([[], [pair]])
    pool = _make_pool(conn)

    with patch("alec.knowledge.dedup.merge_entities", new_callable=AsyncMock) as mock_merge:
        result = await run_dedup_sweep(
            engagement_id, pool, mock_embedder, auto_merge_threshold=0.92,
        )

        assert result.pairs_evaluated == 1
        mock_merge.assert_not_awaited()
        assert result.candidates_logged == 1


@pytest.mark.asyncio
async def test_error_in_pair_processing_doesnt_crash(engagement_id, mock_embedder):
    """Errors processing individual pairs should be caught and recorded."""
    pair = {
        "id_a": uuid4(), "name_a": "Entity A", "type_a": "service",
        "aliases_a": None,
        "obs_a": 5,
        "id_b": uuid4(), "name_b": "Entity B", "type_b": "service",
        "aliases_b": None,
        "obs_b": 3,
        "embedding_sim": 0.85,
    }

    # Phase 1 empty, Phase 2 returns the pair
    conn = _make_transactional_conn([[], [pair]])
    pool = _make_pool(conn)

    with patch(
        "alec.knowledge.dedup.merge_entities",
        new_callable=AsyncMock,
        side_effect=Exception("merge failed"),
    ):
        result = await run_dedup_sweep(
            engagement_id, pool, mock_embedder, auto_merge_threshold=0.01,
        )

    assert result.pairs_evaluated == 1
    assert len(result.errors) >= 1
