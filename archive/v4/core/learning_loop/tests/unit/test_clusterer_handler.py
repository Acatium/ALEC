"""Unit tests for CLUSTERER handler.

Tests event routing, cluster assignment, edge creation, and status transitions.
Phase 4 of gap-019: Learning System Reliability & Observability.

Test Philosophy: Real payloads, not mocks. All paths covered.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.common.kafka_client import Event
from core.learning_loop.clusterer.service import (
    ClustererService,
    _extract_aku_id,
    _extract_aku_ids,
)


@pytest.fixture
def clusterer_service():
    """Create ClustererService with mocked dependencies."""
    with patch.object(ClustererService, "__init__", lambda self: None):
        service = ClustererService()
        service.service_name = "clusterer"
        service.logger = MagicMock()
        service._pool = AsyncMock()
        service._kafka = AsyncMock()
        service._embedding_client = MagicMock()

        # Mock BaseService methods
        service._require_pool = MagicMock(return_value=service._pool)
        service._require_kafka = MagicMock(return_value=service._kafka)

        yield service


@pytest.fixture
def attribution_event() -> Event:
    """Create a valid attribution.resolved event."""
    session_id = str(uuid4())
    bullet_id = str(uuid4())

    return Event(
        event_id=str(uuid4()),
        event_type="attribution.resolved",
        correlation_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload={
            "session_id": session_id,
            "domain": "spotify",
            "situation": "When iterating through paginated API responses",
            "resolved_turns": [
                {
                    "turn_number": 1,
                    "sub_task": "Get playlist items",
                    "micro_outcome": "solved",
                    "bullets_shown": [{"id": bullet_id, "situation": "X"}],
                    "bullets_helped": [bullet_id],
                    "bullets_harmed": [],
                }
            ],
        },
        metadata={},
    )


@pytest.fixture
def aku_accepted_event() -> Event:
    """Create a valid aku.accepted event."""
    return Event(
        event_id=str(uuid4()),
        event_type="aku.accepted",
        correlation_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload={
            "aku_id": str(uuid4()),
            "session_id": str(uuid4()),
            "situation": "When iterating through paginated API responses",
        },
        metadata={},
    )


class TestAkuIdExtraction:
    """Tests for helper functions extracting AKU IDs."""

    def test_extract_from_dict_with_id(self):
        """Should extract 'id' field from dict if valid UUID."""
        test_uuid = "d6aa0d04-1234-5678-9abc-def012345678"
        aku = {"id": test_uuid, "situation": "When X"}
        result = _extract_aku_id(aku)
        assert result == test_uuid

    def test_extract_from_dict_with_aku_id(self):
        """Should extract 'aku_id' field from dict if valid UUID."""
        test_uuid = "d6aa0d04-1234-5678-9abc-def012345678"
        aku = {"aku_id": test_uuid, "assertion": "Do Y"}
        result = _extract_aku_id(aku)
        assert result == test_uuid

    def test_extract_from_dict_with_bullet_id(self):
        """Should extract 'bullet_id' field from dict if valid UUID (backwards compat)."""
        test_uuid = "d6aa0d04-1234-5678-9abc-def012345678"
        aku = {"bullet_id": test_uuid, "assertion": "Do Y"}
        result = _extract_aku_id(aku)
        assert result == test_uuid

    def test_extract_from_string(self):
        """Should return string if valid UUID."""
        test_uuid = "d6aa0d04-1234-5678-9abc-def012345678"
        result = _extract_aku_id(test_uuid)
        assert result == test_uuid

    def test_extract_invalid_string_returns_none(self):
        """Should return None for invalid (non-UUID) string - GAP-021 fix."""
        result = _extract_aku_id("123-abc")
        assert result is None

    def test_extract_invalid_text_returns_none(self):
        """Should return None for text that isn't a UUID - GAP-021 fix."""
        result = _extract_aku_id("but agent didn't follow through)")
        assert result is None

    def test_extract_from_uuid(self):
        """Should convert UUID to string."""
        uid = uuid4()
        result = _extract_aku_id(uid)
        assert result == str(uid)

    def test_extract_from_none(self):
        """Should return None for None input."""
        result = _extract_aku_id(None)
        assert result is None

    def test_extract_from_empty_dict(self):
        """Should return None for dict without id fields."""
        result = _extract_aku_id({})
        assert result is None

    def test_extract_multiple(self):
        """Should extract valid UUIDs from mixed format list."""
        uuid1 = "d6aa0d04-1111-5678-9abc-def012345678"
        uuid2 = "d6aa0d04-2222-5678-9abc-def012345678"
        uuid3 = "d6aa0d04-3333-5678-9abc-def012345678"
        akus = [
            {"id": uuid1},
            {"aku_id": uuid2},
            uuid3,
            None,
            {},
            "invalid-id",  # Invalid - should be filtered
        ]
        result = _extract_aku_ids(akus)
        assert result == [uuid1, uuid2, uuid3]


class TestEventRouting:
    """Tests for event dispatch to correct handlers."""

    @pytest.mark.asyncio
    async def test_routes_attribution_resolved(self, clusterer_service: ClustererService, attribution_event: Event):
        """attribution.resolved events should route to _handle_attribution_resolved."""
        with patch.object(clusterer_service, "_handle_attribution_resolved", new_callable=AsyncMock) as mock_handler:
            await clusterer_service._handle_event(attribution_event)
            mock_handler.assert_called_once_with(attribution_event)

    @pytest.mark.asyncio
    async def test_routes_aku_accepted(self, clusterer_service: ClustererService, aku_accepted_event: Event):
        """aku.accepted events should route to _handle_aku_accepted."""
        with patch.object(clusterer_service, "_handle_aku_accepted", new_callable=AsyncMock) as mock_handler:
            await clusterer_service._handle_event(aku_accepted_event)
            mock_handler.assert_called_once_with(aku_accepted_event)

    @pytest.mark.asyncio
    async def test_routes_aku_merged(self, clusterer_service: ClustererService):
        """aku.merged events should route to _handle_aku_merged."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.merged",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"aku_id": str(uuid4())},
            metadata={},
        )

        with patch.object(clusterer_service, "_handle_aku_merged", new_callable=AsyncMock) as mock_handler:
            await clusterer_service._handle_event(event)
            mock_handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self, clusterer_service: ClustererService):
        """Unrelated event types should be ignored silently."""
        unrelated = Event(
            event_id=str(uuid4()),
            event_type="session.created",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4())},
            metadata={},
        )

        with patch.object(clusterer_service, "_handle_attribution_resolved", new_callable=AsyncMock) as mock1:
            with patch.object(clusterer_service, "_handle_aku_accepted", new_callable=AsyncMock) as mock2:
                await clusterer_service._handle_event(unrelated)
                mock1.assert_not_called()
                mock2.assert_not_called()


class TestHandleAttributionResolved:
    """Tests for _handle_attribution_resolved handler."""

    @pytest.mark.asyncio
    async def test_assigns_session_to_cluster(self, clusterer_service: ClustererService, attribution_event: Event):
        """Should assign session to cluster based on situation embedding."""
        cluster_id = str(uuid4())
        clusterer_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(clusterer_service, "_assign_to_cluster", new_callable=AsyncMock) as mock_assign:
            mock_assign.return_value = cluster_id

            with patch.object(clusterer_service, "_increment_cluster_counter", new_callable=AsyncMock):
                with patch.object(clusterer_service, "_store_turn", new_callable=AsyncMock):
                    with patch.object(clusterer_service, "_maybe_promote_aku", new_callable=AsyncMock):
                        with patch.object(clusterer_service, "_maybe_archive_aku", new_callable=AsyncMock):
                            await clusterer_service._handle_attribution_resolved(attribution_event)

            mock_assign.assert_called_once()
            call_kwargs = mock_assign.call_args[1]
            assert call_kwargs["label"] == "When iterating through paginated API responses"

    @pytest.mark.asyncio
    async def test_increments_success_counter_on_solved(self, clusterer_service: ClustererService):
        """Should increment success_count for solved turns when bullets were shown."""
        cluster_id = str(uuid4())
        test_bullet_id = "d6aa0d04-1111-5678-9abc-def012345678"
        event = Event(
            event_id=str(uuid4()),
            event_type="attribution.resolved",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "session_id": str(uuid4()),
                "situation": "When X",
                "resolved_turns": [
                    # Counter only increments when bullets_shown is non-empty (cold-start protection)
                    {"turn_number": 1, "micro_outcome": "solved", "bullets_shown": [test_bullet_id]},
                ],
            },
            metadata={},
        )

        clusterer_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(clusterer_service, "_assign_to_cluster", new_callable=AsyncMock) as mock_assign:
            mock_assign.return_value = cluster_id

            with patch.object(clusterer_service, "_increment_cluster_counter", new_callable=AsyncMock) as mock_inc:
                with patch.object(clusterer_service, "_store_turn", new_callable=AsyncMock):
                    await clusterer_service._handle_attribution_resolved(event)

                mock_inc.assert_called_once_with(cluster_id, "success_count")

    @pytest.mark.asyncio
    async def test_increments_failure_counter_on_stuck(self, clusterer_service: ClustererService):
        """Should increment failure_count for stuck turns when bullets were shown."""
        cluster_id = str(uuid4())
        test_bullet_id = "d6aa0d04-2222-5678-9abc-def012345678"
        event = Event(
            event_id=str(uuid4()),
            event_type="attribution.resolved",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "session_id": str(uuid4()),
                "situation": "When X",
                "resolved_turns": [
                    # Counter only increments when bullets_shown is non-empty (cold-start protection)
                    {"turn_number": 1, "micro_outcome": "stuck", "bullets_shown": [test_bullet_id]},
                ],
            },
            metadata={},
        )

        clusterer_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(clusterer_service, "_assign_to_cluster", new_callable=AsyncMock) as mock_assign:
            mock_assign.return_value = cluster_id

            with patch.object(clusterer_service, "_increment_cluster_counter", new_callable=AsyncMock) as mock_inc:
                with patch.object(clusterer_service, "_store_turn", new_callable=AsyncMock):
                    await clusterer_service._handle_attribution_resolved(event)

                mock_inc.assert_called_once_with(cluster_id, "failure_count")

    @pytest.mark.asyncio
    async def test_creates_semantic_bridge_when_similarity_low(self, clusterer_service: ClustererService):
        """Should create semantic bridge when similarity < threshold."""
        event = Event(
            event_id=str(uuid4()),
            event_type="attribution.resolved",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "session_id": str(uuid4()),
                "situation": "When X",
                "resolved_turns": [],
                "similarity": 0.5,  # Below BRIDGE_THRESHOLD (0.70)
                "initial_situation": "When doing Y",
                "initial_embedding": [0.2] * 384,
                "bullets_helped": [str(uuid4())],
                "bullets_harmed": [],
            },
            metadata={},
        )

        clusterer_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(clusterer_service, "_assign_to_cluster", new_callable=AsyncMock) as mock_assign:
            mock_assign.return_value = str(uuid4())

            with patch.object(clusterer_service, "_create_semantic_bridge", new_callable=AsyncMock) as mock_bridge:
                await clusterer_service._handle_attribution_resolved(event)

                mock_bridge.assert_called_once()


class TestHandleAkuAccepted:
    """Tests for _handle_aku_accepted handler."""

    @pytest.mark.asyncio
    async def test_links_aku_to_cluster(self, clusterer_service: ClustererService, aku_accepted_event: Event):
        """Should link new AKU to cluster via solved_by edge."""
        aku_id = aku_accepted_event.payload["aku_id"]
        cluster_id = str(uuid4())
        embedding = [0.1] * 384

        with patch.object(clusterer_service, "_get_aku_situation_embedding", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = embedding

            with patch.object(clusterer_service, "_assign_to_cluster", new_callable=AsyncMock) as mock_assign:
                mock_assign.return_value = cluster_id

                with patch.object(clusterer_service, "_upsert_edge", new_callable=AsyncMock) as mock_edge:
                    await clusterer_service._handle_aku_accepted(aku_accepted_event)

                    mock_edge.assert_called_once_with(cluster_id, aku_id, "solved_by")

    @pytest.mark.asyncio
    async def test_returns_early_without_aku_id(self, clusterer_service: ClustererService):
        """Should return early if no aku_id in payload."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.accepted",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4())},  # No aku_id
            metadata={},
        )

        with patch.object(clusterer_service, "_get_aku_situation_embedding", new_callable=AsyncMock) as mock_get:
            await clusterer_service._handle_aku_accepted(event)

            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_warning_without_embedding(self, clusterer_service: ClustererService, aku_accepted_event: Event):
        """Should log warning if AKU has no embedding."""
        with patch.object(clusterer_service, "_get_aku_situation_embedding", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            await clusterer_service._handle_aku_accepted(aku_accepted_event)

            clusterer_service.logger.warning.assert_called_once()
            assert "aku_embedding_missing" in str(clusterer_service.logger.warning.call_args)


class TestAssignToCluster:
    """Tests for _assign_to_cluster method."""

    @pytest.mark.asyncio
    async def test_returns_existing_cluster_when_found(self, clusterer_service: ClustererService):
        """Should return existing cluster if similarity > threshold."""
        cluster_id = uuid4()
        clusterer_service._pool.fetchrow = AsyncMock(return_value={
            "cluster_id": cluster_id,
            "similarity": 0.8,
        })

        result = await clusterer_service._assign_to_cluster([0.1] * 384)

        assert result == str(cluster_id)

    @pytest.mark.asyncio
    async def test_creates_new_cluster_when_not_found(self, clusterer_service: ClustererService):
        """Should create new cluster if no match found."""
        clusterer_service._pool.fetchrow = AsyncMock(return_value=None)

        with patch.object(clusterer_service, "_create_cluster", new_callable=AsyncMock) as mock_create:
            new_cluster_id = str(uuid4())
            mock_create.return_value = new_cluster_id

            result = await clusterer_service._assign_to_cluster([0.1] * 384, domain="spotify", label="When X")

            assert result == new_cluster_id
            mock_create.assert_called_once()


class TestCreateCluster:
    """Tests for _create_cluster method."""

    @pytest.mark.asyncio
    async def test_creates_cluster_with_label(self, clusterer_service: ClustererService):
        """Should create cluster with truncated label."""
        clusterer_service._pool.execute = AsyncMock()

        result = await clusterer_service._create_cluster([0.1] * 384, domain="spotify", label="When X")

        assert result is not None  # UUID string
        clusterer_service._pool.execute.assert_called_once()

        # Verify INSERT includes label
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "label" in call_args[0]

    @pytest.mark.asyncio
    async def test_truncates_long_labels(self, clusterer_service: ClustererService):
        """Should truncate labels > 200 chars."""
        long_label = "A" * 300
        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._create_cluster([0.1] * 384, label=long_label)

        # Verify label was truncated
        # Args: (sql, cluster_id, embedding, label, domain)
        call_args = clusterer_service._pool.execute.call_args[0]
        passed_label = call_args[3]  # Fourth positional arg is label
        assert len(passed_label) == 200


class TestUpsertEdge:
    """Tests for _upsert_edge method."""

    @pytest.mark.asyncio
    async def test_creates_edge(self, clusterer_service: ClustererService):
        """Should upsert edge with correct parameters."""
        cluster_id = str(uuid4())
        bullet_id = str(uuid4())
        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._upsert_edge(cluster_id, bullet_id, "solved_by")

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "INSERT INTO knowledge_edges" in call_args[0]
        assert "ON CONFLICT" in call_args[0]

    @pytest.mark.asyncio
    async def test_handles_database_error(self, clusterer_service: ClustererService):
        """Should log warning on error."""
        clusterer_service._pool.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await clusterer_service._upsert_edge(str(uuid4()), str(uuid4()), "solved_by")

        clusterer_service.logger.warning.assert_called_once()


class TestAkuStatusTransitions:
    """Tests for AKU promotion and archival."""

    @pytest.mark.asyncio
    async def test_promotes_aku_on_helpful_threshold(self, clusterer_service: ClustererService):
        """Should promote candidate to active when helpful_count >= threshold."""
        aku_id = str(uuid4())
        clusterer_service._pool.execute = AsyncMock(return_value="UPDATE 1")

        await clusterer_service._maybe_promote_aku(aku_id)

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "status = 'active'" in call_args[0]
        assert "status = 'candidate'" in call_args[0]

    @pytest.mark.asyncio
    async def test_archives_aku_on_harmful_ratio(self, clusterer_service: ClustererService):
        """Should archive active AKU when harmful > helpful * ratio."""
        aku_id = str(uuid4())
        clusterer_service._pool.execute = AsyncMock(return_value="UPDATE 1")

        await clusterer_service._maybe_archive_aku(aku_id)

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "status = 'archived'" in call_args[0]
        assert "status = 'active'" in call_args[0]


class TestIncrementClusterCounter:
    """Tests for _increment_cluster_counter method."""

    @pytest.mark.asyncio
    async def test_increments_success_count(self, clusterer_service: ClustererService):
        """Should increment success_count for cluster."""
        cluster_id = str(uuid4())
        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._increment_cluster_counter(cluster_id, "success_count")

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "success_count = success_count + 1" in call_args[0]

    @pytest.mark.asyncio
    async def test_increments_failure_count(self, clusterer_service: ClustererService):
        """Should increment failure_count for cluster."""
        cluster_id = str(uuid4())
        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._increment_cluster_counter(cluster_id, "failure_count")

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "failure_count = failure_count + 1" in call_args[0]

    @pytest.mark.asyncio
    async def test_handles_database_error(self, clusterer_service: ClustererService):
        """Should log warning on error."""
        clusterer_service._pool.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await clusterer_service._increment_cluster_counter(str(uuid4()), "success_count")

        clusterer_service.logger.warning.assert_called_once()


class TestStoreTurn:
    """Tests for _store_turn method."""

    @pytest.mark.asyncio
    async def test_updates_turn_with_analysis(self, clusterer_service: ClustererService):
        """Should update session_turns with analysis results."""
        bullet1 = "d6aa0d04-1111-5678-9abc-def012345678"
        bullet2 = "d6aa0d04-2222-5678-9abc-def012345678"
        turn = {
            "turn_number": 1,
            "sub_task": "Get playlist items",
            "micro_outcome": "solved",
            "bullets_helped": [{"id": bullet1}],
            "bullets_harmed": [{"id": bullet2}],
        }
        session_id = str(uuid4())
        cluster_id = str(uuid4())

        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._store_turn(turn, session_id, cluster_id)

        clusterer_service._pool.execute.assert_called_once()
        call_args = clusterer_service._pool.execute.call_args[0]
        assert "UPDATE session_turns" in call_args[0]

    @pytest.mark.asyncio
    async def test_extracts_bullet_ids_from_dicts(self, clusterer_service: ClustererService):
        """Should extract valid UUIDs from dict format, filtering invalid ones."""
        bullet1 = "d6aa0d04-1111-5678-9abc-def012345678"
        bullet2 = "d6aa0d04-2222-5678-9abc-def012345678"
        bullet3 = "d6aa0d04-3333-5678-9abc-def012345678"
        turn = {
            "turn_number": 1,
            "bullets_helped": [{"id": bullet1}, {"bullet_id": bullet2}],
            "bullets_harmed": [bullet3],
        }

        clusterer_service._pool.execute = AsyncMock()

        await clusterer_service._store_turn(turn, str(uuid4()), str(uuid4()))

        # Verify extracted IDs were passed
        call_args = clusterer_service._pool.execute.call_args[0]
        assert [bullet1, bullet2] == call_args[5]  # bullets_helped
        assert [bullet3] == call_args[6]  # bullets_harmed


class TestSemanticBridge:
    """Tests for semantic bridge creation."""

    @pytest.mark.asyncio
    async def test_creates_solved_by_edges_for_helped(self, clusterer_service: ClustererService):
        """Should create solved_by edges for bullets that helped."""
        cluster_id = str(uuid4())
        bullets_helped = [str(uuid4()), str(uuid4())]

        with patch.object(clusterer_service, "_find_or_create_bridge_cluster", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = cluster_id

            with patch.object(clusterer_service, "_upsert_edge", new_callable=AsyncMock) as mock_edge:
                await clusterer_service._create_semantic_bridge(
                    initial_situation="When Y",
                    initial_embedding=[0.2] * 384,
                    domain="spotify",
                    bullets_helped=bullets_helped,
                    bullets_harmed=[],
                )

                # Should create solved_by edges for each helped bullet
                assert mock_edge.call_count == 2
                for call in mock_edge.call_args_list:
                    assert call[0][2] == "solved_by"

    @pytest.mark.asyncio
    async def test_creates_caused_failure_edges_for_harmed(self, clusterer_service: ClustererService):
        """Should create caused_failure edges for bullets that harmed."""
        cluster_id = str(uuid4())
        bullets_harmed = [str(uuid4())]

        with patch.object(clusterer_service, "_find_or_create_bridge_cluster", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = cluster_id

            with patch.object(clusterer_service, "_upsert_edge", new_callable=AsyncMock) as mock_edge:
                await clusterer_service._create_semantic_bridge(
                    initial_situation="When Y",
                    initial_embedding=[0.2] * 384,
                    domain="spotify",
                    bullets_helped=[],
                    bullets_harmed=bullets_harmed,
                )

                mock_edge.assert_called_once()
                assert mock_edge.call_args[0][2] == "caused_failure"

    @pytest.mark.asyncio
    async def test_skips_when_no_cluster_found(self, clusterer_service: ClustererService):
        """Should skip edge creation if cluster creation fails."""
        with patch.object(clusterer_service, "_find_or_create_bridge_cluster", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = None

            with patch.object(clusterer_service, "_upsert_edge", new_callable=AsyncMock) as mock_edge:
                await clusterer_service._create_semantic_bridge(
                    initial_situation="When Y",
                    initial_embedding=[0.2] * 384,
                    domain="spotify",
                    bullets_helped=[str(uuid4())],
                    bullets_harmed=[],
                )

                mock_edge.assert_not_called()
