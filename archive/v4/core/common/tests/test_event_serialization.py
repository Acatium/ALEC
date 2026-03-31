"""Tests for Kafka event serialization.

These tests verify that the json_serializer function correctly handles
all Python types that appear in Kafka event payloads:
- UUID objects → string
- datetime objects → ISO 8601 string
- None values → null
- Nested objects with mixed types
- Embedding arrays (lists of floats)

The serializer is the ONLY place where Python objects become JSON for Kafka,
so these tests catch bugs that mocked Kafka tests would miss.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from core.common.infrastructure.kafka_producer import json_serializer


class TestUUIDSerialization:
    """Test UUID serialization in event payloads."""

    def test_uuid_serializes_to_string(self):
        """UUID should serialize to its string representation."""
        original = uuid4()
        serialized = json.dumps({"id": original}, default=json_serializer)
        restored = json.loads(serialized)

        assert restored["id"] == str(original)
        assert isinstance(restored["id"], str)

    def test_uuid_roundtrip_preserves_value(self):
        """UUID value should be reconstructable after serialization."""
        original = uuid4()
        serialized = json.dumps({"bullet_id": original}, default=json_serializer)
        restored = json.loads(serialized)

        # Can reconstruct the UUID from serialized string
        reconstructed = UUID(restored["bullet_id"])
        assert reconstructed == original

    def test_multiple_uuids_in_payload(self):
        """Multiple UUIDs in nested structure should all serialize."""
        session_id = uuid4()
        bullet_ids = [uuid4(), uuid4(), uuid4()]

        payload = {
            "session_id": session_id,
            "bullets_used": bullet_ids,
            "cluster_id": uuid4(),
        }

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert restored["session_id"] == str(session_id)
        assert len(restored["bullets_used"]) == 3
        assert all(isinstance(bid, str) for bid in restored["bullets_used"])


class TestDatetimeSerialization:
    """Test datetime serialization in event payloads."""

    def test_datetime_with_timezone_serializes_to_iso8601(self):
        """Timezone-aware datetime should serialize to ISO 8601."""
        now = datetime.now(timezone.utc)
        serialized = json.dumps({"timestamp": now}, default=json_serializer)
        restored = json.loads(serialized)

        # ISO 8601 format includes timezone
        assert "+" in restored["timestamp"] or "Z" in restored["timestamp"]
        assert "T" in restored["timestamp"]

    def test_naive_datetime_serializes(self):
        """Naive datetime should also serialize (no timezone info)."""
        naive = datetime(2025, 12, 15, 10, 30, 0)
        serialized = json.dumps({"created_at": naive}, default=json_serializer)
        restored = json.loads(serialized)

        assert "2025-12-15" in restored["created_at"]
        assert "10:30:00" in restored["created_at"]

    def test_datetime_roundtrip_preserves_precision(self):
        """Datetime microseconds should survive serialization."""
        original = datetime(2025, 12, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
        serialized = json.dumps({"timestamp": original}, default=json_serializer)
        restored = json.loads(serialized)

        # Parse back and verify microseconds
        parsed = datetime.fromisoformat(restored["timestamp"].replace("Z", "+00:00"))
        assert parsed.microsecond == 123456

    def test_datetime_with_offset_timezone(self):
        """Datetime with non-UTC timezone should serialize correctly."""
        pst = timezone(timedelta(hours=-8))
        dt = datetime(2025, 12, 15, 10, 30, 0, tzinfo=pst)
        serialized = json.dumps({"timestamp": dt}, default=json_serializer)
        restored = json.loads(serialized)

        # Should include offset info
        assert "-08:00" in restored["timestamp"]


class TestNoneValues:
    """Test None value handling in event payloads."""

    def test_none_values_serialize_to_null(self):
        """None should serialize to JSON null."""
        payload = {"cluster_id": None, "error_message": None}
        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert restored["cluster_id"] is None
        assert restored["error_message"] is None

    def test_none_in_nested_structure(self):
        """None values in nested structures should serialize."""
        payload = {
            "bullets": [
                {"id": str(uuid4()), "cluster_id": None},
                {"id": str(uuid4()), "cluster_id": str(uuid4())},
            ]
        }
        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert restored["bullets"][0]["cluster_id"] is None
        assert restored["bullets"][1]["cluster_id"] is not None


class TestEmbeddingArrays:
    """Test embedding array serialization (lists of floats)."""

    def test_embedding_array_serializes(self):
        """384-dim embedding should serialize without precision loss."""
        embedding = [0.1 + i * 0.001 for i in range(384)]
        payload = {"situation_embedding": embedding}

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert len(restored["situation_embedding"]) == 384
        # Check precision preserved to reasonable degree
        assert abs(restored["situation_embedding"][0] - 0.1) < 1e-10

    def test_embedding_with_negative_values(self):
        """Embeddings with negative values should serialize."""
        embedding = [-0.5, 0.0, 0.5, -1.0, 1.0]
        payload = {"embedding": embedding}

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert restored["embedding"] == [-0.5, 0.0, 0.5, -1.0, 1.0]

    def test_embedding_scientific_notation(self):
        """Very small embedding values should serialize correctly."""
        embedding = [1e-10, -1e-10, 0.0]
        payload = {"embedding": embedding}

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        assert abs(restored["embedding"][0] - 1e-10) < 1e-15
        assert abs(restored["embedding"][1] - (-1e-10)) < 1e-15


class TestMixedTypes:
    """Test payloads with mixed types (realistic event structures)."""

    def test_full_event_payload_roundtrip(self):
        """Complete event payload with all types should serialize."""
        session_id = uuid4()
        bullet_id = uuid4()
        now = datetime.now(timezone.utc)

        payload = {
            "event_id": uuid4(),
            "event_type": "attribution.resolved",
            "timestamp": now,
            "payload": {
                "session_id": session_id,
                "turn_number": 3,
                "bullets_helped": [bullet_id],
                "bullets_harmed": [],
                "cluster_id": None,
                "micro_outcome": "solved",
                "embedding": [0.1, 0.2, 0.3],
            },
            "metadata": {
                "source": "reflector",
                "version": "1.0.0",
            },
        }

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        # Verify structure preserved
        assert restored["event_type"] == "attribution.resolved"
        assert restored["payload"]["turn_number"] == 3
        assert restored["payload"]["micro_outcome"] == "solved"
        assert restored["payload"]["cluster_id"] is None
        assert len(restored["payload"]["bullets_helped"]) == 1
        assert restored["payload"]["bullets_helped"][0] == str(bullet_id)

    def test_nested_uuids_and_datetimes(self):
        """Deeply nested UUIDs and datetimes should serialize."""
        payload = {
            "turns": [
                {
                    "turn_id": uuid4(),
                    "created_at": datetime.now(timezone.utc),
                    "bullets": [
                        {"bullet_id": uuid4(), "last_used": datetime.now(timezone.utc)},
                    ],
                },
            ],
        }

        serialized = json.dumps(payload, default=json_serializer)
        restored = json.loads(serialized)

        # Should not raise and structure should be preserved
        assert len(restored["turns"]) == 1
        assert len(restored["turns"][0]["bullets"]) == 1
        assert isinstance(restored["turns"][0]["bullets"][0]["bullet_id"], str)


class TestErrorHandling:
    """Test serializer error handling for unsupported types."""

    def test_unsupported_type_raises_typeerror(self):
        """Custom objects without serialization support should raise TypeError."""

        class CustomObject:
            pass

        with pytest.raises(TypeError, match="not JSON serializable"):
            json.dumps({"obj": CustomObject()}, default=json_serializer)

    def test_bytes_raises_typeerror(self):
        """Bytes objects should raise TypeError (not silently converted)."""
        with pytest.raises(TypeError):
            json.dumps({"data": b"binary"}, default=json_serializer)
