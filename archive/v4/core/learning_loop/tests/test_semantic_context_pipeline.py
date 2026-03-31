"""Tests for the Semantic Context Pipeline (Dec 2025).

Tests that ADVISOR writes semantic context to Redis and GENERATOR can read it.
"""

import json
from unittest.mock import AsyncMock

import pytest


class TestSemanticContextPipeline:
    """Test the semantic context pipeline between ADVISOR and GENERATOR."""

    @pytest.mark.asyncio
    async def test_redis_write_semantic_context(self):
        """Test that write_semantic_context stores data correctly."""
        from core.learning_loop.shared.redis_client import RedisClient

        client = RedisClient()

        # Mock the Redis connection
        mock_redis = AsyncMock()
        client._client = mock_redis

        context = {
            "extracted_task": "Get all playlist songs",
            "task_embedding": [0.1, 0.2, 0.3],
            "nearest_cluster_id": "cluster-123",
            "nearest_cluster_label": "API pagination",
            "cluster_similarity": 0.85,
            "retrieval_path": "vector+cluster",
        }

        await client.write_semantic_context(
            session_id="session-abc",
            turn_number=1,
            context=context,
        )

        # Verify the call was made with correct key
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "session:session-abc:turn:1:semantic_context" in str(call_args)

        # Verify JSON encoding
        stored_data = json.loads(call_args[0][1])
        assert stored_data["nearest_cluster_label"] == "API pagination"
        assert stored_data["cluster_similarity"] == 0.85

    @pytest.mark.asyncio
    async def test_redis_get_semantic_context(self):
        """Test that get_semantic_context retrieves data correctly."""
        from core.learning_loop.shared.redis_client import RedisClient

        client = RedisClient()

        # Mock the Redis connection with stored data
        mock_redis = AsyncMock()
        stored_context = {
            "extracted_task": "Get all playlist songs",
            "nearest_cluster_label": "API pagination",
            "cluster_similarity": 0.85,
        }
        mock_redis.get.return_value = json.dumps(stored_context)
        client._client = mock_redis

        result = await client.get_semantic_context("session-abc", turn_number=1)

        assert result is not None
        assert result["nearest_cluster_label"] == "API pagination"
        assert result["cluster_similarity"] == 0.85
        mock_redis.get.assert_called_once_with(
            "session:session-abc:turn:1:semantic_context"
        )

    @pytest.mark.asyncio
    async def test_redis_get_semantic_context_not_found(self):
        """Test that get_semantic_context returns None when no data."""
        from core.learning_loop.shared.redis_client import RedisClient

        client = RedisClient()

        # Mock the Redis connection with no data
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        client._client = mock_redis

        result = await client.get_semantic_context("session-xyz", turn_number=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_get_session_semantic_context_scans_turns(self):
        """Test that get_session_semantic_context scans multiple turns."""
        from core.learning_loop.shared.redis_client import RedisClient

        client = RedisClient()

        # Mock Redis to return None for turns 1-2, data for turn 3
        mock_redis = AsyncMock()

        async def mock_get(key):
            if "turn:3" in key:
                return json.dumps({"nearest_cluster_label": "Found on turn 3"})
            return None

        mock_redis.get = mock_get
        client._client = mock_redis

        result = await client.get_session_semantic_context("session-abc")

        assert result is not None
        assert result["nearest_cluster_label"] == "Found on turn 3"


# v3: Removed TestSelectorClusterClassification and TestReflectorPromptGameContext
# These tested v2 modules (advisor.selector, generator.service) that don't exist in v3
# In v3:
# - ADVISOR is a BaseService subclass in advisor/service.py
# - REFLECTOR is a separate service in reflector/service.py
# - Game context concept was replaced by turn-level analysis
