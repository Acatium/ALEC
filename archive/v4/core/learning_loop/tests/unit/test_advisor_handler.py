"""Unit tests for ADVISOR handler.

Tests event routing, handler logic, error paths, and edge cases.
Phase 4 of gap-019: Learning System Reliability & Observability.

Test Philosophy: Real payloads, not mocks. All paths covered.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.common.kafka_client import Event
from core.learning_loop.advisor.service import AdvisorService


@pytest.fixture
def advisor_service():
    """Create AdvisorService with mocked dependencies."""
    with patch.object(AdvisorService, "__init__", lambda self: None):
        service = AdvisorService()
        service.service_name = "advisor"
        service.logger = MagicMock()
        service._pool = AsyncMock()
        service._kafka = AsyncMock()
        service._redis = AsyncMock()
        service._embedding_client = MagicMock()
        service._llm_client = MagicMock()

        # Mock BaseService methods
        service._require_pool = MagicMock(return_value=service._pool)
        service._require_kafka = MagicMock(return_value=service._kafka)
        service._require_redis = MagicMock(return_value=service._redis)
        service._record_event_drop = MagicMock()

        yield service


@pytest.fixture
def sample_event() -> Event:
    """Create a valid bullets.requested event."""
    return Event(
        event_id=str(uuid4()),
        event_type="bullets.requested",
        correlation_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload={
            "session_id": str(uuid4()),
            "turn_number": 1,
            "domain": "spotify",
            "problem_context": """You are an AI agent that completes tasks.

## Task
Find all playlists with more than 10 songs.

## User Information
Name: John Smith
""",
            "bullets_already_shown": [],
        },
        metadata={},
    )


class TestEventRouting:
    """Tests for event dispatch to correct handlers."""

    @pytest.mark.asyncio
    async def test_routes_bullets_requested_to_handler(self, advisor_service: AdvisorService, sample_event: Event):
        """bullets.requested events should route to _handle_akus_requested."""
        with patch.object(advisor_service, "_handle_akus_requested", new_callable=AsyncMock) as mock_handler:
            await advisor_service._handle_event(sample_event)
            mock_handler.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self, advisor_service: AdvisorService):
        """Unrelated event types should be ignored silently."""
        unrelated = Event(
            event_id=str(uuid4()),
            event_type="session.created",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4())},
            metadata={},
        )

        with patch.object(advisor_service, "_handle_akus_requested", new_callable=AsyncMock) as mock_handler:
            await advisor_service._handle_event(unrelated)
            mock_handler.assert_not_called()


class TestHandleAkusRequested:
    """Tests for the main handler logic."""

    @pytest.mark.asyncio
    async def test_drops_event_without_session_id(self, advisor_service: AdvisorService):
        """Events without session_id should be dropped with metric."""
        event = Event(
            event_id=str(uuid4()),
            event_type="bullets.requested",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "turn_number": 1,
                "problem_context": "Find playlists",
            },
            metadata={},
        )

        await advisor_service._handle_akus_requested(event)

        advisor_service._record_event_drop.assert_called_once_with(
            "bullets.requested", "missing_session_id"
        )

    @pytest.mark.asyncio
    async def test_writes_empty_result_on_embedding_failure(self, advisor_service: AdvisorService, sample_event: Event):
        """When embedding fails, should write empty result to Redis."""
        # Mock embedding to return None
        with patch.object(advisor_service, "_get_situation_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = None

            with patch.object(advisor_service, "_write_empty_result", new_callable=AsyncMock) as mock_write_empty:
                await advisor_service._handle_akus_requested(sample_event)

                advisor_service._record_event_drop.assert_called_once()
                mock_write_empty.assert_called_once()

    @pytest.mark.asyncio
    async def test_selects_bullets_and_writes_to_redis(self, advisor_service: AdvisorService, sample_event: Event):
        """Successful flow: embed -> select -> write to redis."""
        embedding = [0.1] * 384
        cluster_id = str(uuid4())
        bullets = [
            {"id": str(uuid4()), "situation": "When X", "assertion": "Do Y", "score": 0.9},
        ]

        with patch.object(advisor_service, "_get_situation_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = embedding

            with patch.object(advisor_service, "_find_nearest_cluster", new_callable=AsyncMock) as mock_cluster:
                mock_cluster.return_value = cluster_id

                with patch.object(advisor_service, "_select_akus", new_callable=AsyncMock) as mock_select:
                    mock_select.return_value = bullets

                    with patch.object(advisor_service, "_write_to_redis", new_callable=AsyncMock) as mock_write:
                        await advisor_service._handle_akus_requested(sample_event)

                        mock_embed.assert_called_once()
                        mock_cluster.assert_called_once()
                        mock_select.assert_called_once()
                        mock_write.assert_called_once_with(
                            session_id=sample_event.payload["session_id"],
                            turn_number=1,
                            akus=bullets,
                            cluster_id=cluster_id,
                        )

    @pytest.mark.asyncio
    async def test_uses_provided_cluster_id(self, advisor_service: AdvisorService):
        """When cluster_id is in payload, should not call _find_nearest_cluster."""
        existing_cluster = str(uuid4())
        event = Event(
            event_id=str(uuid4()),
            event_type="bullets.requested",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "session_id": str(uuid4()),
                "turn_number": 2,
                "cluster_id": existing_cluster,
                "problem_context": "Continue task",
            },
            metadata={},
        )

        with patch.object(advisor_service, "_get_situation_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384

            with patch.object(advisor_service, "_find_nearest_cluster", new_callable=AsyncMock) as mock_cluster:
                with patch.object(advisor_service, "_select_akus", new_callable=AsyncMock) as mock_select:
                    mock_select.return_value = []

                    with patch.object(advisor_service, "_write_to_redis", new_callable=AsyncMock):
                        await advisor_service._handle_akus_requested(event)

                        # Should NOT search for cluster since it was provided
                        mock_cluster.assert_not_called()


class TestTaskExtraction:
    """Tests for _extract_task method."""

    def test_extracts_task_section(self, advisor_service: AdvisorService):
        """Should extract ## Task section from AppWorld format."""
        user_input = """You are an AI agent.

## Task
Find all playlists with more than 10 songs.

## User Information
Name: John Smith
"""
        result = advisor_service._extract_task(user_input)
        assert result == "Find all playlists with more than 10 songs."

    def test_handles_missing_task_section(self, advisor_service: AdvisorService):
        """Should fallback to first 500 chars if no ## Task section."""
        user_input = "Just a simple query without sections"
        result = advisor_service._extract_task(user_input)
        assert result == user_input

    def test_returns_none_for_short_input(self, advisor_service: AdvisorService):
        """Should return None for input < 10 chars."""
        result = advisor_service._extract_task("Hi")
        assert result is None

    def test_returns_none_for_empty_input(self, advisor_service: AdvisorService):
        """Should return None for empty/None input."""
        assert advisor_service._extract_task("") is None
        assert advisor_service._extract_task(None) is None


class TestVectorSearch:
    """Tests for _vector_search method."""

    @pytest.mark.asyncio
    async def test_returns_akus_from_database(self, advisor_service: AdvisorService):
        """Should return AKUs from vector search query."""
        embedding = [0.1] * 384
        mock_rows = [
            {
                "aku_id": uuid4(),
                "situation": "When paginating",
                "assertion": "Use offset=0",
                "helpful_count": 5,
                "harmful_count": 1,
                "neutral_count": 2,
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.85,
            }
        ]

        advisor_service._pool.fetch = AsyncMock(return_value=mock_rows)

        result = await advisor_service._vector_search(embedding, [])

        assert len(result) == 1
        assert result[0]["situation"] == "When paginating"
        advisor_service._pool.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_database_error(self, advisor_service: AdvisorService):
        """Should return empty list and log warning on error."""
        advisor_service._pool.fetch = AsyncMock(side_effect=Exception("DB error"))

        result = await advisor_service._vector_search([0.1] * 384, [])

        assert result == []
        advisor_service.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_excludes_already_shown_bullets(self, advisor_service: AdvisorService):
        """Should pass exclude list to SQL query."""
        embedding = [0.1] * 384
        exclude = [str(uuid4()), str(uuid4())]

        advisor_service._pool.fetch = AsyncMock(return_value=[])

        await advisor_service._vector_search(embedding, exclude)

        # Verify exclude list was passed to query
        call_args = advisor_service._pool.fetch.call_args
        assert call_args[0][1] is not None  # embedding string
        assert call_args[0][2] == exclude  # exclude list


class TestThompsonRank:
    """Tests for _thompson_rank method."""

    def test_filters_below_floor(self, advisor_service: AdvisorService):
        """AKUs with TS sample below floor should be filtered."""
        # Create an AKU with very poor performance (high harmful, low helpful)
        candidates = [
            {
                "aku_id": uuid4(),
                "situation": "Bad AKU",
                "assertion": "Do wrong thing",
                "helpful_count": 0,
                "harmful_count": 100,  # Very harmful
                "neutral_count": 0,
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.9,
            }
        ]

        # Run many times - with high harmful count, TS sample will usually be < 0.25
        # This is probabilistic, so we run multiple times
        results_count = 0
        for _ in range(10):
            result = advisor_service._thompson_rank(candidates)
            results_count += len(result)

        # Most of the time, the bullet should be filtered
        # (with alpha=1, beta=101, expected value is ~0.01)
        assert results_count < 5  # Expect < 50% to pass floor

    def test_ranks_by_combined_score(self, advisor_service: AdvisorService):
        """AKUs should be ranked by similarity * ts_sample * age_decay."""
        candidates = [
            {
                "aku_id": uuid4(),
                "situation": "Good proven AKU",
                "assertion": "Do right thing",
                "helpful_count": 50,
                "harmful_count": 1,
                "neutral_count": 5,
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.9,
            },
            {
                "aku_id": uuid4(),
                "situation": "New untested AKU",
                "assertion": "Maybe do this",
                "helpful_count": 0,
                "harmful_count": 0,
                "neutral_count": 0,
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.9,
            },
        ]

        result = advisor_service._thompson_rank(candidates)

        # Both should pass (both have good expected scores)
        assert len(result) >= 1
        # Each result should have required fields
        for r in result:
            assert "id" in r
            assert "situation" in r
            assert "assertion" in r
            assert "score" in r
            assert 0 <= r["score"] <= 1


class TestWriteToRedis:
    """Tests for _write_to_redis method."""

    @pytest.mark.asyncio
    async def test_writes_all_required_keys(self, advisor_service: AdvisorService):
        """Should write turn-specific, cache, and ready keys."""
        session_id = str(uuid4())
        turn_number = 1
        bullets = [{"id": "1", "situation": "X", "assertion": "Y"}]
        cluster_id = str(uuid4())

        await advisor_service._write_to_redis(session_id, turn_number, bullets, cluster_id)

        # Should call redis.set 3 times (turn, cache, ready)
        assert advisor_service._redis.set.call_count == 3

        # Verify the keys
        calls = advisor_service._redis.set.call_args_list
        keys = [call[0][0] for call in calls]

        assert f"session:{session_id}:turn:{turn_number}:bullets" in keys
        assert f"session:{session_id}:bullets_cache" in keys
        assert f"session:{session_id}:turn:{turn_number}:bullets_ready" in keys

    @pytest.mark.asyncio
    async def test_includes_cluster_id_in_data(self, advisor_service: AdvisorService):
        """Data should include cluster_id for SESSION to use."""
        session_id = str(uuid4())
        cluster_id = str(uuid4())

        await advisor_service._write_to_redis(session_id, 1, [], cluster_id)

        # Get the data written to turn-specific key
        first_call = advisor_service._redis.set.call_args_list[0]
        data = json.loads(first_call[0][1])

        assert "cluster_id" in data
        assert data["cluster_id"] == cluster_id

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, advisor_service: AdvisorService):
        """Should log error but not crash on Redis failure."""
        advisor_service._redis.set = AsyncMock(side_effect=Exception("Redis down"))

        # Should not raise
        await advisor_service._write_to_redis(str(uuid4()), 1, [], None)

        advisor_service.logger.error.assert_called_once()


class TestClusterLookup:
    """Tests for _find_nearest_cluster method."""

    @pytest.mark.asyncio
    async def test_returns_cluster_id_when_found(self, advisor_service: AdvisorService):
        """Should return cluster_id when similarity exceeds threshold."""
        cluster_id = uuid4()
        advisor_service._pool.fetchrow = AsyncMock(return_value={
            "cluster_id": cluster_id,
            "similarity": 0.8,
        })

        result = await advisor_service._find_nearest_cluster([0.1] * 384)

        assert result == str(cluster_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, advisor_service: AdvisorService):
        """Should return None when no cluster exceeds threshold."""
        advisor_service._pool.fetchrow = AsyncMock(return_value=None)

        result = await advisor_service._find_nearest_cluster([0.1] * 384)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_database_error(self, advisor_service: AdvisorService):
        """Should return None and log warning on error."""
        advisor_service._pool.fetchrow = AsyncMock(side_effect=Exception("DB error"))

        result = await advisor_service._find_nearest_cluster([0.1] * 384)

        assert result is None
        advisor_service.logger.warning.assert_called_once()


class TestClusterSolutions:
    """Tests for _get_cluster_solutions method."""

    @pytest.mark.asyncio
    async def test_returns_solved_by_edges(self, advisor_service: AdvisorService):
        """Should return AKUs linked via solved_by edges."""
        cluster_id = str(uuid4())
        mock_rows = [
            {
                "aku_id": uuid4(),
                "situation": "When X",
                "assertion": "Do Y",
                "helpful_count": 10,
                "harmful_count": 0,
                "neutral_count": 1,
                "created_at": datetime.now(timezone.utc),
                "edge_weight": 0.9,
            }
        ]

        advisor_service._pool.fetch = AsyncMock(return_value=mock_rows)

        result = await advisor_service._get_cluster_solutions(cluster_id, [])

        assert len(result) == 1
        assert result[0]["similarity"] == 0.9  # edge_weight becomes similarity

    @pytest.mark.asyncio
    async def test_handles_no_edges(self, advisor_service: AdvisorService):
        """Should return empty list when no solved_by edges exist."""
        advisor_service._pool.fetch = AsyncMock(return_value=[])

        result = await advisor_service._get_cluster_solutions(str(uuid4()), [])

        assert result == []


class TestHarmfulLookup:
    """Tests for _get_harmful_for_cluster method."""

    @pytest.mark.asyncio
    async def test_returns_caused_failure_bullet_ids(self, advisor_service: AdvisorService):
        """Should return set of bullet IDs with caused_failure edges."""
        bullet_ids = [uuid4(), uuid4()]
        advisor_service._pool.fetch = AsyncMock(return_value=[
            {"target_id": bullet_ids[0]},
            {"target_id": bullet_ids[1]},
        ])

        result = await advisor_service._get_harmful_for_cluster(str(uuid4()))

        assert isinstance(result, set)
        assert len(result) == 2
        assert str(bullet_ids[0]) in result
        assert str(bullet_ids[1]) in result

    @pytest.mark.asyncio
    async def test_returns_empty_set_on_error(self, advisor_service: AdvisorService):
        """Should return empty set and log warning on error."""
        advisor_service._pool.fetch = AsyncMock(side_effect=Exception("DB error"))

        result = await advisor_service._get_harmful_for_cluster(str(uuid4()))

        assert result == set()
        advisor_service.logger.warning.assert_called_once()


class TestColdStartFallback:
    """Tests for _get_cold_start_candidates method."""

    @pytest.mark.asyncio
    async def test_returns_untested_akus(self, advisor_service: AdvisorService):
        """Should return AKUs with few trials for cold start."""
        mock_rows = [
            {
                "aku_id": uuid4(),
                "situation": "New AKU",
                "assertion": "Try this",
                "helpful_count": 0,
                "harmful_count": 0,
                "neutral_count": 0,
                "created_at": datetime.now(timezone.utc),
                "similarity": 0.5,  # Cold start default
            }
        ]

        advisor_service._pool.fetch = AsyncMock(return_value=mock_rows)

        result = await advisor_service._get_cold_start_candidates([])

        assert len(result) == 1
        assert result[0]["similarity"] == 0.5  # Default for cold start
