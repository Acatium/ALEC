"""Tests for schema proposer service."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from alec.services.schema_proposer import SchemaProposer, _fallback_proposal


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.call = AsyncMock()
    return llm


@pytest.mark.asyncio
async def test_propose_parses_valid_json(mock_llm):
    """Valid JSON response is parsed correctly."""
    proposal = {
        "template_base": "regulatory_analysis",
        "entity_types": [
            {"name": "regulation", "description": "A law", "examples": ["GDPR"]}
        ],
        "relationship_types": [
            {
                "name": "governs",
                "description": "Sets rules for",
                "examples": ["reg governs domain"],
                "parent_category": "governance",
            }
        ],
        "reasoning": "Domain is regulatory.",
    }
    response = MagicMock()
    response.text = json.dumps(proposal)
    mock_llm.call.return_value = response

    proposer = SchemaProposer(mock_llm)
    result = await proposer.propose("Analyze EU AI Act", ["web:https://example.com"])

    assert result["template_base"] == "regulatory_analysis"
    assert len(result["entity_types"]) == 1
    assert result["entity_types"][0]["name"] == "regulation"
    assert len(result["relationship_types"]) == 1
    assert result["reasoning"] == "Domain is regulatory."


@pytest.mark.asyncio
async def test_propose_extracts_json_from_text(mock_llm):
    """JSON embedded in surrounding text is extracted."""
    proposal = {
        "template_base": "general_discovery",
        "entity_types": [{"name": "concept", "description": "An idea", "examples": []}],
        "relationship_types": [],
        "reasoning": "General.",
    }
    response = MagicMock()
    response.text = f"Here is my analysis:\n{json.dumps(proposal)}\nHope this helps!"
    mock_llm.call.return_value = response

    proposer = SchemaProposer(mock_llm)
    result = await proposer.propose("Explore topic", [])

    assert result["template_base"] == "general_discovery"
    assert len(result["entity_types"]) == 1


@pytest.mark.asyncio
async def test_propose_returns_fallback_on_invalid_json(mock_llm):
    """Invalid JSON falls back to default proposal."""
    response = MagicMock()
    response.text = "I cannot generate JSON right now."
    mock_llm.call.return_value = response

    proposer = SchemaProposer(mock_llm)
    result = await proposer.propose("Anything", [])

    assert result["template_base"] == "general_discovery"
    assert result["entity_types"] == []
    assert result["relationship_types"] == []


@pytest.mark.asyncio
async def test_propose_handles_missing_fields(mock_llm):
    """Missing fields get sensible defaults."""
    response = MagicMock()
    response.text = json.dumps({"entity_types": [{"name": "x", "description": "y"}]})
    mock_llm.call.return_value = response

    proposer = SchemaProposer(mock_llm)
    result = await proposer.propose("Anything", [])

    assert result["template_base"] == "general_discovery"
    assert result["reasoning"] == ""
    assert len(result["entity_types"]) == 1


def test_fallback_proposal():
    """Fallback proposal has correct structure."""
    result = _fallback_proposal()
    assert result["template_base"] == "general_discovery"
    assert result["entity_types"] == []
    assert result["relationship_types"] == []
    assert "reasoning" in result
