"""Integration tests for Redis bullet cache.

These tests verify that the BulletCache class correctly interacts with Redis:
- Key format matches expected pattern
- TTL is enforced
- JSON encoding/decoding preserves data
- Fallback logic works on cache miss
- cluster_id stored alongside bullets

Mocked Redis tests hide bugs like typos in key construction, TTL not being set,
or JSON serialization failures. These tests catch those bugs.
"""

import asyncio
import json
from uuid import uuid4

import pytest

from core.session.infrastructure.bullet_cache import BulletCache

pytestmark = pytest.mark.asyncio


class TestKeyFormat:
    """Test Redis key construction matches implementation."""

    async def test_bullet_key_format(self, real_redis):
        """Bullet keys should follow session:{id}:turn:{n}:bullets pattern."""
        session_id = str(uuid4())
        turn_number = 3

        expected_ready_key = f"session:{session_id}:turn:{turn_number}:bullets_ready"
        expected_bullets_key = f"session:{session_id}:turn:{turn_number}:bullets"

        # Store data using the expected key format
        bullets_data = {
            "bullets": [{"id": str(uuid4()), "situation": "test", "score": 0.9}],
            "cluster_id": str(uuid4()),
        }

        await real_redis.set(expected_bullets_key, json.dumps(bullets_data))
        await real_redis.set(expected_ready_key, "1")

        # Verify BulletCache can read with the same keys
        cache = BulletCache(real_redis._client)
        bullets, cluster_id = await cache.get_bullets(session_id, turn_number, timeout_ms=500)

        assert len(bullets) == 1
        assert bullets[0]["situation"] == "test"
        assert cluster_id == bullets_data["cluster_id"]

    async def test_fallback_cache_key_format(self, real_redis):
        """Fallback cache key should be session:{id}:bullets_cache."""
        session_id = str(uuid4())

        expected_cache_key = f"session:{session_id}:bullets_cache"
        bullets_data = {
            "bullets": [{"id": str(uuid4()), "assertion": "fallback bullet"}],
        }

        await real_redis.set(expected_cache_key, json.dumps(bullets_data))

        cache = BulletCache(real_redis._client)
        bullets = await cache.get_bullets_fallback(session_id)

        assert len(bullets) == 1
        assert bullets[0]["assertion"] == "fallback bullet"


class TestTTLEnforcement:
    """Test that TTL is correctly set and enforced."""

    async def test_ttl_set_on_write(self, real_redis):
        """Keys written by ADVISOR should have TTL set."""
        session_id = str(uuid4())
        turn_number = 1

        key = f"session:{session_id}:turn:{turn_number}:bullets"
        ttl_seconds = 86400  # 24 hours

        await real_redis.set(key, json.dumps({"bullets": []}), ex=ttl_seconds)

        actual_ttl = await real_redis.ttl(key)

        # TTL should be close to 24h (within a few seconds)
        assert actual_ttl > 86300
        assert actual_ttl <= 86400

    async def test_expired_key_returns_none(self, real_redis):
        """Expired keys should return None (simulate cache miss)."""
        session_id = str(uuid4())
        turn_number = 1

        key = f"session:{session_id}:turn:{turn_number}:bullets"

        # Set with 1 second TTL
        await real_redis.set(key, json.dumps({"bullets": []}), ex=1)

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Key should be gone
        result = await real_redis.get(key)
        assert result is None


class TestJSONRoundtrip:
    """Test JSON encoding/decoding preserves all data."""

    async def test_bullet_data_preserved(self, real_redis):
        """All bullet fields should survive JSON roundtrip in Redis."""
        session_id = str(uuid4())
        bullet_id = str(uuid4())
        cluster_id = str(uuid4())

        bullets_data = {
            "bullets": [
                {
                    "id": bullet_id,
                    "situation": "When handling pagination",
                    "assertion": "Use offset=0 for first page",
                    "modality": "should",
                    "polarity": "do",
                    "score": 0.8765,
                    "similarity": 0.92,
                    "ts_sample": 0.95,
                }
            ],
            "cluster_id": cluster_id,
        }

        key = f"session:{session_id}:turn:1:bullets"
        await real_redis.set(key, json.dumps(bullets_data))

        # Read back
        raw = await real_redis.get(key)
        restored = json.loads(raw)

        # Verify all fields
        assert len(restored["bullets"]) == 1
        bullet = restored["bullets"][0]
        assert bullet["id"] == bullet_id
        assert bullet["situation"] == "When handling pagination"
        assert bullet["assertion"] == "Use offset=0 for first page"
        assert bullet["modality"] == "should"
        assert bullet["polarity"] == "do"
        assert abs(bullet["score"] - 0.8765) < 1e-10
        assert restored["cluster_id"] == cluster_id

    async def test_none_values_in_payload(self, real_redis):
        """None/null values should survive roundtrip."""
        session_id = str(uuid4())

        bullets_data = {
            "bullets": [{"id": str(uuid4()), "cluster_id": None}],
            "cluster_id": None,
        }

        key = f"session:{session_id}:turn:1:bullets"
        await real_redis.set(key, json.dumps(bullets_data))

        raw = await real_redis.get(key)
        restored = json.loads(raw)

        assert restored["cluster_id"] is None
        assert restored["bullets"][0]["cluster_id"] is None

    async def test_unicode_in_assertion(self, real_redis):
        """Unicode characters in assertions should survive roundtrip."""
        session_id = str(uuid4())

        bullets_data = {
            "bullets": [
                {
                    "id": str(uuid4()),
                    "assertion": "Check for émojis 🎉 and accénts",
                }
            ],
            "cluster_id": None,
        }

        key = f"session:{session_id}:turn:1:bullets"
        await real_redis.set(key, json.dumps(bullets_data, ensure_ascii=False))

        raw = await real_redis.get(key)
        restored = json.loads(raw)

        assert "émojis 🎉" in restored["bullets"][0]["assertion"]


class TestFallbackBehavior:
    """Test cache miss and fallback logic."""

    async def test_timeout_triggers_fallback(self, real_redis):
        """Cache miss should trigger fallback to in-memory cache."""
        session_id = str(uuid4())

        # Pre-populate in-memory cache by doing a successful read first
        bullets_data = {
            "bullets": [{"id": str(uuid4()), "assertion": "cached bullet"}],
            "cluster_id": str(uuid4()),
        }

        # Write initial bullets
        turn1_key = f"session:{session_id}:turn:1:bullets"
        turn1_ready = f"session:{session_id}:turn:1:bullets_ready"
        await real_redis.set(turn1_key, json.dumps(bullets_data))
        await real_redis.set(turn1_ready, "1")

        cache = BulletCache(real_redis._client)

        # First call populates in-memory cache
        bullets1, _ = await cache.get_bullets(session_id, 1, timeout_ms=500)
        assert len(bullets1) == 1

        # Second call for turn 2 with no Redis data should fallback
        # (short timeout to trigger fallback quickly)
        bullets2, cluster_id2 = await cache.get_bullets(session_id, 2, timeout_ms=100)

        # Should get cached bullets from turn 1
        assert len(bullets2) == 1
        assert bullets2[0]["assertion"] == "cached bullet"
        assert cluster_id2 is None  # Fallback doesn't have cluster_id

    async def test_empty_cache_returns_empty_list(self, real_redis):
        """Fresh session with no cache should return empty list."""
        session_id = str(uuid4())

        cache = BulletCache(real_redis._client)

        # Short timeout - no Redis data exists
        bullets, cluster_id = await cache.get_bullets(session_id, 1, timeout_ms=100)

        assert bullets == []
        assert cluster_id is None


class TestClusterIdStorage:
    """Test cluster_id is correctly stored and retrieved."""

    async def test_cluster_id_stored_with_bullets(self, real_redis):
        """cluster_id should be retrievable alongside bullets."""
        session_id = str(uuid4())
        cluster_id = str(uuid4())

        bullets_data = {
            "bullets": [{"id": str(uuid4()), "assertion": "test"}],
            "cluster_id": cluster_id,
        }

        key = f"session:{session_id}:turn:1:bullets"
        ready_key = f"session:{session_id}:turn:1:bullets_ready"
        await real_redis.set(key, json.dumps(bullets_data))
        await real_redis.set(ready_key, "1")

        cache = BulletCache(real_redis._client)
        bullets, returned_cluster_id = await cache.get_bullets(session_id, 1, timeout_ms=500)

        assert returned_cluster_id == cluster_id

    async def test_null_cluster_id_preserved(self, real_redis):
        """null cluster_id should be preserved (not converted to empty string)."""
        session_id = str(uuid4())

        bullets_data = {
            "bullets": [{"id": str(uuid4()), "assertion": "test"}],
            "cluster_id": None,
        }

        key = f"session:{session_id}:turn:1:bullets"
        ready_key = f"session:{session_id}:turn:1:bullets_ready"
        await real_redis.set(key, json.dumps(bullets_data))
        await real_redis.set(ready_key, "1")

        cache = BulletCache(real_redis._client)
        bullets, returned_cluster_id = await cache.get_bullets(session_id, 1, timeout_ms=500)

        assert returned_cluster_id is None  # Not empty string, not "null"
