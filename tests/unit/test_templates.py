"""Tests for engagement schema templates."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from alec.knowledge.templates import (
    TEMPLATES,
    get_template,
    list_templates,
    populate_schema,
)

TEMPLATE_IDS = [
    "general_discovery",
    "enterprise_architecture",
    "research_synthesis",
    "regulatory_analysis",
]


def test_list_templates():
    """list_templates returns all 4 templates with correct metadata."""
    templates = list_templates()
    assert len(templates) == 4

    ids = [t["template_id"] for t in templates]
    for tid in TEMPLATE_IDS:
        assert tid in ids

    for t in templates:
        assert "template_id" in t
        assert "name" in t
        assert "description" in t
        assert "entity_type_count" in t
        assert "relationship_type_count" in t
        assert isinstance(t["name"], str)
        assert isinstance(t["description"], str)
        assert t["entity_type_count"] > 0
        assert t["relationship_type_count"] > 0


def test_get_template_valid():
    """get_template returns correct template data for each known ID."""
    for tid in TEMPLATE_IDS:
        result = get_template(tid)
        assert result is not None, f"Template {tid} should exist"
        assert "name" in result
        assert "description" in result
        assert "entity_types" in result
        assert "relationship_types" in result
        assert len(result["entity_types"]) > 0
        assert len(result["relationship_types"]) > 0

        # Each entity type entry should have name, description, examples
        for et in result["entity_types"]:
            assert "name" in et
            assert "description" in et
            assert "examples" in et

        # Each relationship type entry should have name, description, examples, parent_category
        for rt in result["relationship_types"]:
            assert "name" in rt
            assert "description" in rt
            assert "examples" in rt
            assert "parent_category" in rt

    # Verify specific template contents
    general = get_template("general_discovery")
    assert general["name"] == "General Discovery"

    enterprise = get_template("enterprise_architecture")
    assert enterprise["name"] == "Enterprise Architecture"

    research = get_template("research_synthesis")
    assert research["name"] == "Research Synthesis"

    regulatory = get_template("regulatory_analysis")
    assert regulatory["name"] == "Regulatory Analysis"


def test_get_template_invalid():
    """get_template returns None for unknown template IDs."""
    assert get_template("nonexistent_template") is None
    assert get_template("") is None
    assert get_template("GENERAL_DISCOVERY") is None  # case-sensitive


@pytest.mark.asyncio
async def test_populate_schema():
    """populate_schema executes correct SQL calls for entity_types and relationship_types."""
    engagement_id = uuid4()
    template_id = "general_discovery"
    template = TEMPLATES[template_id]

    expected_entity_count = len(template["entity_types"])
    expected_rel_count = len(template["relationship_types"])
    expected_total = expected_entity_count + expected_rel_count

    # Build mock asyncpg pool with async context manager for acquire()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_pool = MagicMock()
    mock_acquire_ctx = AsyncMock()
    mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

    count = await populate_schema(mock_pool, engagement_id, template_id)

    assert count == expected_total

    # Verify conn.execute was called once per entity type + relationship type
    assert mock_conn.execute.await_count == expected_total

    # Check that entity_type inserts pass the right arguments
    entity_calls = []
    rel_calls = []
    for call in mock_conn.execute.call_args_list:
        sql = call[0][0]
        if "'entity_type'" in sql:
            entity_calls.append(call)
        elif "'relationship_type'" in sql:
            rel_calls.append(call)

    assert len(entity_calls) == expected_entity_count
    assert len(rel_calls) == expected_rel_count

    # Verify first entity type call has correct arguments
    first_et = template["entity_types"][0]
    first_call_args = entity_calls[0][0]
    assert first_call_args[1] == engagement_id
    assert first_call_args[2] == first_et["name"]
    assert first_call_args[3] == first_et["description"]
    assert first_call_args[4] == first_et.get("examples", [])

    # Verify first relationship type call has correct arguments including parent_category
    first_rt = template["relationship_types"][0]
    first_rel_args = rel_calls[0][0]
    assert first_rel_args[1] == engagement_id
    assert first_rel_args[2] == first_rt["name"]
    assert first_rel_args[3] == first_rt["description"]
    assert first_rel_args[4] == first_rt.get("examples", [])
    assert first_rel_args[5] == first_rt.get("parent_category")


@pytest.mark.asyncio
async def test_populate_schema_invalid_template():
    """populate_schema raises ValueError for an unknown template ID."""
    mock_pool = MagicMock()

    with pytest.raises(ValueError, match="Unknown template"):
        await populate_schema(mock_pool, uuid4(), "nonexistent_template")
