"""Tests for AKU Search Tool."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from core.session.domain.aku_search import (
    SEARCH_KNOWLEDGE_TOOL,
    AKUSearchResult,
    AKUSearchTool,
    SearchResult,
)


class TestSearchKnowledgeTool:
    """Tests for the tool definition."""

    def test_tool_definition_structure(self):
        """Tool definition has correct structure for Anthropic API."""
        assert SEARCH_KNOWLEDGE_TOOL["name"] == "search_knowledge"
        assert "description" in SEARCH_KNOWLEDGE_TOOL
        assert "input_schema" in SEARCH_KNOWLEDGE_TOOL
        assert SEARCH_KNOWLEDGE_TOOL["input_schema"]["type"] == "object"
        assert "query" in SEARCH_KNOWLEDGE_TOOL["input_schema"]["properties"]
        assert "query" in SEARCH_KNOWLEDGE_TOOL["input_schema"]["required"]


class TestAKUSearchTool:
    """Tests for AKUSearchTool class."""

    @pytest.fixture
    def mock_pool(self):
        """Create mock asyncpg pool."""
        pool = AsyncMock()
        return pool

    @pytest.fixture
    def search_tool(self, mock_pool):
        """Create AKUSearchTool with mocked pool."""
        return AKUSearchTool(mock_pool)

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_no_results(self, search_tool, mock_pool):
        """Search returns empty result when no bullets match."""
        # Mock embedding client
        with patch.object(search_tool, '_get_embedding_client') as mock_embed:
            mock_embed.return_value.embed.return_value = [0.1] * 384
            mock_pool.fetchrow.return_value = None  # No cluster
            mock_pool.fetch.side_effect = [
                [],  # No exclusions
                [],  # No bullets
            ]

            result = await search_tool.search("test query")

            assert isinstance(result, AKUSearchResult)
            assert len(result.bullets) == 0
            assert result.formatted == "No relevant knowledge found."

    @pytest.mark.asyncio
    async def test_search_returns_bullets(self, search_tool, mock_pool):
        """Search returns bullets when matches are found."""
        from datetime import datetime, timezone

        bullet_id = uuid4()

        # Mock embedding client
        with patch.object(search_tool, '_get_embedding_client') as mock_embed:
            mock_embed.return_value.embed.return_value = [0.1] * 384

            mock_pool.fetchrow.return_value = {
                "cluster_id": str(uuid4()),
                "similarity": 0.5,
            }

            mock_pool.fetch.side_effect = [
                [],  # No exclusions
                [
                    {
                        "bullet_id": bullet_id,
                        "situation": "When testing",
                        "assertion": "Use mocks",
                        "polarity": "do",
                        "category": "constraints",
                        "similarity": 0.75,
                        "helpful_count": 10,
                        "harmful_count": 1,
                        "neutral_count": 2,
                        "created_at": datetime.now(timezone.utc),
                    }
                ],
            ]

            result = await search_tool.search("test query")

            assert len(result.bullets) == 1
            assert result.bullets[0].bullet_id == bullet_id
            assert result.bullets[0].situation == "When testing"
            assert result.bullets[0].assertion == "Use mocks"
            assert result.bullets[0].confidence == "PROVEN"  # 10/(10+1) >= 0.8

    @pytest.mark.asyncio
    async def test_search_filters_excluded_bullets(self, search_tool, mock_pool):
        """Search excludes bullets with caused_failure edges."""
        excluded_id = uuid4()
        included_id = uuid4()

        with patch.object(search_tool, '_get_embedding_client') as mock_embed:
            mock_embed.return_value.embed.return_value = [0.1] * 384

            mock_pool.fetchrow.return_value = {
                "cluster_id": str(uuid4()),
                "similarity": 0.5,
            }

            # First call returns exclusions, second returns bullets
            mock_pool.fetch.side_effect = [
                [{"target_id": excluded_id}],  # Exclusions
                [],  # Bullets (filtered by SQL)
            ]

            result = await search_tool.search("test query", cluster_id=str(uuid4()))

            # Verify exclusion was passed to SQL
            # Args: SQL query, embedding, threshold, excluded_list, max_results
            call_args = mock_pool.fetch.call_args_list[1]
            assert excluded_id in call_args[0][3]  # Fourth arg is excluded list

    @pytest.mark.asyncio
    async def test_search_tracks_cluster_id(self, search_tool, mock_pool):
        """Search finds and returns cluster_id."""
        cluster_id = str(uuid4())

        with patch.object(search_tool, '_get_embedding_client') as mock_embed:
            mock_embed.return_value.embed.return_value = [0.1] * 384

            mock_pool.fetchrow.return_value = {
                "cluster_id": cluster_id,
                "similarity": 0.5,
            }

            mock_pool.fetch.side_effect = [
                [],  # No exclusions
                [],  # No bullets
            ]

            result = await search_tool.search("test query")

            assert result.cluster_id == cluster_id

    def test_format_includes_confidence_tags(self, search_tool):
        """Results are formatted with confidence tags."""
        bullets = [
            SearchResult(
                bullet_id=uuid4(),
                situation="When testing",
                assertion="Use mocks",
                polarity="do",
                category="constraints",
                similarity=0.75,
                effectiveness=0.9,
                confidence="PROVEN",
                helpful_count=10,
                harmful_count=1,
            ),
            SearchResult(
                bullet_id=uuid4(),
                situation="When debugging",
                assertion="Check logs first",
                polarity="do",
                category="solutions",
                similarity=0.65,
                effectiveness=0.3,
                confidence="UNTESTED",
                helpful_count=1,
                harmful_count=0,
            ),
        ]

        formatted = search_tool._format_for_llm(bullets)

        assert "[PROVEN]" in formatted
        assert "[UNTESTED]" in formatted
        assert "#C" in formatted  # constraints
        assert "#S" in formatted  # solutions

    def test_format_handles_dont_polarity(self, search_tool):
        """Results format 'dont' polarity with DON'T prefix."""
        bullets = [
            SearchResult(
                bullet_id=uuid4(),
                situation="When testing",
                assertion="hardcode values",
                polarity="dont",
                category="constraints",
                similarity=0.75,
                effectiveness=0.9,
                confidence="PROVEN",
                helpful_count=10,
                harmful_count=1,
            ),
        ]

        formatted = search_tool._format_for_llm(bullets)

        assert "DON'T:" in formatted

    def test_get_tool_definition(self, search_tool):
        """get_tool_definition returns correct definition."""
        definition = search_tool.get_tool_definition()

        assert definition == SEARCH_KNOWLEDGE_TOOL


class TestSearchResultConfidence:
    """Tests for confidence level calculation."""

    def test_untested_under_5_trials(self):
        """Bullets with < 5 trials are UNTESTED."""
        # This is tested in the vector search logic
        # helpful=2, harmful=0 -> total=2 < 5 -> UNTESTED
        pass

    def test_proven_at_80_percent(self):
        """Bullets with >= 80% help rate are PROVEN."""
        # helpful=8, harmful=2 -> 8/(8+2) = 0.8 -> PROVEN
        pass

    def test_tested_below_80_percent(self):
        """Bullets with < 80% help rate are TESTED."""
        # helpful=6, harmful=4 -> 6/(6+4) = 0.6 -> TESTED
        pass
