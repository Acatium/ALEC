"""Unit tests for CURATOR handler.

Tests event routing, quality gate, deduplication, and edge cases.
Phase 4 of gap-019: Learning System Reliability & Observability.

Test Philosophy: Real payloads, not mocks. All paths covered.
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.common.kafka_client import Event
from core.learning_loop.curator.service import CuratorService


@pytest.fixture
def curator_service():
    """Create CuratorService with mocked dependencies."""
    with patch.object(CuratorService, "__init__", lambda self: None):
        service = CuratorService()
        service.service_name = "curator"
        service.logger = MagicMock()
        service._pool = AsyncMock()
        service._kafka = AsyncMock()
        service._embedding_client = MagicMock()

        # Mock BaseService methods
        service._require_pool = MagicMock(return_value=service._pool)
        service._require_kafka = MagicMock(return_value=service._kafka)

        yield service


@pytest.fixture
def valid_aku() -> dict[str, Any]:
    """Create a valid AKU payload (v4: assertion ≤100 chars)."""
    return {
        "situation": "When iterating through paginated API responses",
        "assertion": "Use offset=0 for first page, increment by page_size until fewer items returned",
    }


@pytest.fixture
def sample_event(valid_aku: dict[str, Any]) -> Event:
    """Create a valid aku.proposed event."""
    return Event(
        event_id=str(uuid4()),
        event_type="aku.proposed",
        correlation_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload={
            "aku": valid_aku,
            "source": "reflector",
            "session_id": str(uuid4()),
            "domain": "spotify",
        },
        metadata={},
    )


class TestEventRouting:
    """Tests for event dispatch to correct handlers."""

    @pytest.mark.asyncio
    async def test_routes_aku_proposed_to_handler(self, curator_service: CuratorService, sample_event: Event):
        """aku.proposed events should route to _handle_aku_proposed."""
        with patch.object(curator_service, "_handle_aku_proposed", new_callable=AsyncMock) as mock_handler:
            await curator_service._handle_event(sample_event)
            mock_handler.assert_called_once_with(sample_event)

    @pytest.mark.asyncio
    async def test_ignores_unrelated_events(self, curator_service: CuratorService):
        """Unrelated event types should be ignored silently."""
        unrelated = Event(
            event_id=str(uuid4()),
            event_type="session.created",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={"session_id": str(uuid4())},
            metadata={},
        )

        with patch.object(curator_service, "_handle_aku_proposed", new_callable=AsyncMock) as mock_handler:
            await curator_service._handle_event(unrelated)
            mock_handler.assert_not_called()


class TestQualityCheck:
    """Tests for _quality_check method."""

    def test_accepts_valid_aku(self, curator_service: CuratorService, valid_aku: dict[str, Any]):
        """Valid AKU should pass quality check."""
        result = curator_service._quality_check(valid_aku)
        assert result is None  # None means passed

    def test_rejects_short_assertion(self, curator_service: CuratorService):
        """Assertion < 20 chars should be rejected."""
        aku = {
            "situation": "When iterating through paginated API responses",
            "assertion": "Use offset=0",  # 12 chars - too short
        }

        result = curator_service._quality_check(aku)

        assert result is not None
        assert "assertion_too_short" in result

    def test_rejects_short_situation(self, curator_service: CuratorService):
        """Situation < 10 chars should be rejected."""
        aku = {
            "situation": "When X",  # 6 chars - too short
            "assertion": "Do something very specific with the API",
        }

        result = curator_service._quality_check(aku)

        assert result is not None
        assert "situation_too_short" in result

    def test_rejects_uuid_in_situation(self, curator_service: CuratorService):
        """Situation with UUID pattern should be rejected."""
        aku = {
            "situation": "When handling task 12345678-1234-5678-1234-567812345678",
            "assertion": "Use a specific approach that works well for this",
        }

        result = curator_service._quality_check(aku)

        assert result is not None
        assert "low_quality_situation" in result

    def test_rejects_task_id_in_situation(self, curator_service: CuratorService):
        """Situation with task_id pattern should be rejected."""
        aku = {
            "situation": "When working with task_id 12345",
            "assertion": "Use a specific approach that works well for this",
        }

        result = curator_service._quality_check(aku)

        assert result is not None
        assert "low_quality_situation" in result


class TestThresholdForSource:
    """Tests for _get_threshold_for_source method."""

    def test_reflector_threshold(self, curator_service: CuratorService):
        """REFLECTOR source should use 0.70 threshold."""
        result = curator_service._get_threshold_for_source("reflector")
        assert result == 0.70

    def test_strategist_threshold(self, curator_service: CuratorService):
        """STRATEGIST source should use higher 0.90 threshold."""
        result = curator_service._get_threshold_for_source("strategist")
        assert result == 0.90

    def test_manual_threshold(self, curator_service: CuratorService):
        """Manual source should use 0.80 threshold."""
        result = curator_service._get_threshold_for_source("manual")
        assert result == 0.80

    def test_unknown_source_uses_default(self, curator_service: CuratorService):
        """Unknown source should use default 0.70 threshold."""
        result = curator_service._get_threshold_for_source("unknown")
        assert result == 0.70


class TestHandleAkuProposed:
    """Tests for the main handler logic."""

    @pytest.mark.asyncio
    async def test_logs_warning_for_missing_aku(self, curator_service: CuratorService):
        """Events without AKU should log warning."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.proposed",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "source": "reflector",
                "session_id": str(uuid4()),
            },
            metadata={},
        )

        await curator_service._handle_aku_proposed(event)

        curator_service.logger.warning.assert_called_once()
        assert "aku_missing" in str(curator_service.logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_rejects_low_quality_aku(self, curator_service: CuratorService):
        """Low quality AKU should be rejected with metric."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.proposed",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "aku": {
                    "situation": "When X",  # Too short
                    "assertion": "Do Y",  # Too short
                },
                "source": "reflector",
                "session_id": str(uuid4()),
            },
            metadata={},
        )

        await curator_service._handle_aku_proposed(event)

        curator_service.logger.info.assert_called()
        # Check for rejection log
        calls = [str(c) for c in curator_service.logger.info.call_args_list]
        assert any("aku_rejected" in c for c in calls)

    @pytest.mark.asyncio
    async def test_merges_duplicate_aku(self, curator_service: CuratorService, sample_event: Event):
        """Duplicate AKU should merge (increment evidence) not create new."""
        existing_bullet_id = str(uuid4())

        # Mock embedding client
        curator_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        # Mock dedup check to find existing bullet
        with patch.object(
            curator_service, "_check_duplicate_by_assertion", new_callable=AsyncMock
        ) as mock_dedup:
            mock_dedup.return_value = existing_bullet_id

            with patch.object(
                curator_service, "_increment_evidence", new_callable=AsyncMock
            ) as mock_increment:
                await curator_service._handle_aku_proposed(sample_event)

                mock_increment.assert_called_once_with(existing_bullet_id)

        # Should emit aku.merged, not aku.accepted
        curator_service._kafka.publish_event.assert_called_once()
        call_kwargs = curator_service._kafka.publish_event.call_args[1]
        assert call_kwargs["topic"] == "aku.merged"
        assert call_kwargs["payload"]["aku_id"] == existing_bullet_id

    @pytest.mark.asyncio
    async def test_accepts_new_aku(self, curator_service: CuratorService, sample_event: Event):
        """New unique AKU should be stored and emit aku.accepted."""
        new_bullet_id = str(uuid4())

        # Mock embedding client
        curator_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        # Mock dedup check to find no existing bullet
        with patch.object(
            curator_service, "_check_duplicate_by_assertion", new_callable=AsyncMock
        ) as mock_dedup:
            mock_dedup.return_value = None

            with patch.object(
                curator_service, "_store_aku", new_callable=AsyncMock
            ) as mock_store:
                mock_store.return_value = new_bullet_id

                await curator_service._handle_aku_proposed(sample_event)

                mock_store.assert_called_once()

        # Should emit aku.accepted
        curator_service._kafka.publish_event.assert_called_once()
        call_kwargs = curator_service._kafka.publish_event.call_args[1]
        assert call_kwargs["topic"] == "aku.accepted"
        assert call_kwargs["payload"]["aku_id"] == new_bullet_id

    @pytest.mark.asyncio
    async def test_handles_embedding_failure(self, curator_service: CuratorService, sample_event: Event):
        """Should log error and return early on embedding failure."""
        curator_service._embedding_client.embed = MagicMock(side_effect=Exception("Embed error"))

        await curator_service._handle_aku_proposed(sample_event)

        curator_service.logger.error.assert_called_once()
        curator_service._kafka.publish_event.assert_not_called()


class TestCheckDuplicate:
    """Tests for _check_duplicate_by_assertion method."""

    @pytest.mark.asyncio
    async def test_returns_aku_id_when_found(self, curator_service: CuratorService):
        """Should return aku_id when similar assertion exists."""
        aku_id = uuid4()
        curator_service._pool.fetchrow = AsyncMock(return_value={"aku_id": aku_id})

        result = await curator_service._check_duplicate_by_assertion([0.1] * 384, 0.70)

        assert result == str(aku_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, curator_service: CuratorService):
        """Should return None when no similar assertion exists."""
        curator_service._pool.fetchrow = AsyncMock(return_value=None)

        result = await curator_service._check_duplicate_by_assertion([0.1] * 384, 0.70)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_database_error(self, curator_service: CuratorService):
        """Should return None and log warning on error."""
        curator_service._pool.fetchrow = AsyncMock(side_effect=Exception("DB error"))

        result = await curator_service._check_duplicate_by_assertion([0.1] * 384, 0.70)

        assert result is None
        curator_service.logger.warning.assert_called_once()


class TestIncrementEvidence:
    """Tests for _increment_evidence method."""

    @pytest.mark.asyncio
    async def test_increments_evidence_count(self, curator_service: CuratorService):
        """Should update evidence_count in database."""
        bullet_id = str(uuid4())
        curator_service._pool.execute = AsyncMock()

        await curator_service._increment_evidence(bullet_id)

        curator_service._pool.execute.assert_called_once()
        call_args = curator_service._pool.execute.call_args[0]
        assert "evidence_count = evidence_count + 1" in call_args[0]

    @pytest.mark.asyncio
    async def test_handles_database_error(self, curator_service: CuratorService):
        """Should log warning on error."""
        curator_service._pool.execute = AsyncMock(side_effect=Exception("DB error"))

        # Should not raise
        await curator_service._increment_evidence(str(uuid4()))

        curator_service.logger.warning.assert_called_once()


class TestStoreAku:
    """Tests for _store_aku method."""

    @pytest.mark.asyncio
    async def test_stores_aku_with_both_embeddings(self, curator_service: CuratorService, valid_aku: dict[str, Any]):
        """Should store AKU with situation and assertion embeddings."""
        situation_emb = [0.1] * 384
        assertion_emb = [0.2] * 384
        curator_service._pool.execute = AsyncMock()

        result = await curator_service._store_aku(
            aku=valid_aku,
            situation_emb=situation_emb,
            assertion_emb=assertion_emb,
            source="reflector",
        )

        assert result is not None  # Should return UUID
        curator_service._pool.execute.assert_called_once()

        # Verify INSERT query includes both embeddings
        call_args = curator_service._pool.execute.call_args[0]
        assert "situation_embedding" in call_args[0]
        assert "assertion_embedding" in call_args[0]

    @pytest.mark.asyncio
    async def test_raises_on_database_error(self, curator_service: CuratorService, valid_aku: dict[str, Any]):
        """Should raise exception on database error."""
        curator_service._pool.execute = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await curator_service._store_aku(
                aku=valid_aku,
                situation_emb=[0.1] * 384,
                assertion_emb=[0.2] * 384,
                source="reflector",
            )


class TestSourceThresholdIntegration:
    """Integration tests for source-specific threshold behavior."""

    @pytest.mark.asyncio
    async def test_reflector_aku_uses_lower_threshold(self, curator_service: CuratorService, valid_aku: dict[str, Any]):
        """REFLECTOR source should use 0.70 threshold for dedup."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.proposed",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "aku": valid_aku,
                "source": "reflector",
                "session_id": str(uuid4()),
            },
            metadata={},
        )

        curator_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(
            curator_service, "_check_duplicate_by_assertion", new_callable=AsyncMock
        ) as mock_dedup:
            mock_dedup.return_value = None
            with patch.object(curator_service, "_store_aku", new_callable=AsyncMock) as mock_store:
                mock_store.return_value = str(uuid4())

                await curator_service._handle_aku_proposed(event)

                # Verify threshold passed to dedup check
                call_args = mock_dedup.call_args[0]
                assert call_args[1] == 0.70

    @pytest.mark.asyncio
    async def test_strategist_aku_uses_higher_threshold(self, curator_service: CuratorService, valid_aku: dict[str, Any]):
        """STRATEGIST source should use 0.90 threshold for dedup."""
        event = Event(
            event_id=str(uuid4()),
            event_type="aku.proposed",
            correlation_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={
                "aku": valid_aku,
                "source": "strategist",
                "session_id": str(uuid4()),
            },
            metadata={},
        )

        curator_service._embedding_client.embed = MagicMock(return_value=[0.1] * 384)

        with patch.object(
            curator_service, "_check_duplicate_by_assertion", new_callable=AsyncMock
        ) as mock_dedup:
            mock_dedup.return_value = None
            with patch.object(curator_service, "_store_aku", new_callable=AsyncMock) as mock_store:
                mock_store.return_value = str(uuid4())

                await curator_service._handle_aku_proposed(event)

                # Verify threshold passed to dedup check
                call_args = mock_dedup.call_args[0]
                assert call_args[1] == 0.90
