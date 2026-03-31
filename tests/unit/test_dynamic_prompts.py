"""Tests for dynamic prompt and tool generation."""

from __future__ import annotations

from alec.agents.prompts.coordinator import (
    COORDINATOR_SYSTEM_PROMPT,
    build_coordinator_prompt,
)
from alec.agents.prompts.worker import (
    WORKER_BASE_PROMPT,
    build_worker_prompt,
)
from alec.agents.tools.graph_tools import (
    GRAPH_TOOLS,
    build_graph_tools,
)

# ---------------------------------------------------------------------------
# build_graph_tools tests
# ---------------------------------------------------------------------------


def test_build_graph_tools_default():
    """build_graph_tools() returns 4 tools with default enums."""
    tools = build_graph_tools()
    assert len(tools) == 4

    tool_names = [t["name"] for t in tools]
    assert "add_entity" in tool_names
    assert "add_relationship" in tool_names
    assert "add_observation" in tool_names
    assert "suggest_followup" in tool_names

    # Check default entity type enums
    add_entity = next(t for t in tools if t["name"] == "add_entity")
    entity_enum = add_entity["input_schema"]["properties"]["entity_type"]["enum"]
    assert "service" in entity_enum
    assert "database" in entity_enum
    assert "team" in entity_enum
    assert "api" in entity_enum

    # Check default relationship type enums
    add_rel = next(t for t in tools if t["name"] == "add_relationship")
    rel_enum = add_rel["input_schema"]["properties"]["relationship_type"]["enum"]
    assert "depends_on" in rel_enum
    assert "owned_by" in rel_enum
    assert "calls" in rel_enum
    assert "related_to" in rel_enum


def test_build_graph_tools_custom():
    """build_graph_tools with custom types returns tools with custom enums."""
    custom_entity_types = ["regulation", "obligation"]
    custom_rel_types = ["governs", "requires"]

    tools = build_graph_tools(custom_entity_types, custom_rel_types)
    assert len(tools) == 4

    add_entity = next(t for t in tools if t["name"] == "add_entity")
    entity_enum = add_entity["input_schema"]["properties"]["entity_type"]["enum"]
    assert entity_enum == ["regulation", "obligation"]
    # Default types should NOT be present
    assert "service" not in entity_enum
    assert "database" not in entity_enum

    add_rel = next(t for t in tools if t["name"] == "add_relationship")
    rel_enum = add_rel["input_schema"]["properties"]["relationship_type"]["enum"]
    assert rel_enum == ["governs", "requires"]
    # Default types should NOT be present
    assert "depends_on" not in rel_enum
    assert "owned_by" not in rel_enum


def test_build_graph_tools_does_not_mutate_defaults():
    """Calling build_graph_tools with custom types should not mutate default GRAPH_TOOLS."""
    # Capture original default enums
    original_entity_enum = GRAPH_TOOLS[0]["input_schema"]["properties"]["entity_type"]["enum"][:]
    original_rel_enum = GRAPH_TOOLS[1]["input_schema"]["properties"]["relationship_type"]["enum"][:]

    # Build with custom types
    build_graph_tools(["custom_type"], ["custom_rel"])

    # Verify defaults were not mutated
    assert (
        GRAPH_TOOLS[0]["input_schema"]["properties"]
        ["entity_type"]["enum"] == original_entity_enum
    )
    assert (
        GRAPH_TOOLS[1]["input_schema"]["properties"]
        ["relationship_type"]["enum"] == original_rel_enum
    )


# ---------------------------------------------------------------------------
# build_worker_prompt tests
# ---------------------------------------------------------------------------


def test_build_worker_prompt_default():
    """build_worker_prompt() contains default entity and relationship types."""
    prompt = build_worker_prompt()
    assert isinstance(prompt, str)

    # Default types should appear
    assert "service" in prompt
    assert "database" in prompt
    assert "depends_on" in prompt
    assert "owned_by" in prompt
    assert "related_to" in prompt

    # Should NOT contain vocabulary section when no vocabulary given
    assert "Existing Entities" not in prompt

    # Should contain standard sections
    assert "## Entity Types" in prompt
    assert "## Relationship Types" in prompt
    assert "## Impact Classification" in prompt


def test_build_worker_prompt_custom():
    """Custom types appear in output; vocabulary section present when entity_vocabulary given."""
    custom_entity_types = ["regulation", "obligation", "risk_category"]
    custom_rel_types = ["governs", "requires", "exempts"]
    entity_vocab = ["EU AI Act", "GDPR", "Data Protection Authority"]

    prompt = build_worker_prompt(
        entity_types=custom_entity_types,
        relationship_types=custom_rel_types,
        entity_vocabulary=entity_vocab,
    )

    # Custom types should appear
    assert "regulation" in prompt
    assert "obligation" in prompt
    assert "risk_category" in prompt
    assert "governs" in prompt
    assert "requires" in prompt
    assert "exempts" in prompt

    # Default types should NOT appear (they are replaced)
    assert "service, database, team" not in prompt

    # Vocabulary section should be present
    assert "Existing Entities" in prompt
    assert "EU AI Act" in prompt
    assert "GDPR" in prompt
    assert "Data Protection Authority" in prompt


def test_build_worker_prompt_vocabulary_truncated():
    """entity_vocabulary is capped at 50 entries."""
    vocab = [f"Entity_{i}" for i in range(100)]
    prompt = build_worker_prompt(entity_vocabulary=vocab)

    # First 50 should be present
    assert "Entity_0" in prompt
    assert "Entity_49" in prompt
    # Entries beyond 50 should NOT be present
    assert "Entity_50" not in prompt
    assert "Entity_99" not in prompt


# ---------------------------------------------------------------------------
# build_coordinator_prompt tests
# ---------------------------------------------------------------------------


def test_build_coordinator_prompt_default():
    """build_coordinator_prompt() does NOT contain 'Engagement Schema' section."""
    prompt = build_coordinator_prompt()
    assert isinstance(prompt, str)

    # Should NOT have schema section when no custom types
    assert "Engagement Schema" not in prompt

    # Should contain standard sections
    assert "Source Trust Tiers" in prompt
    assert "User Annotations" in prompt
    assert "Open Questions" in prompt
    assert "Output Format" in prompt


def test_build_coordinator_prompt_custom():
    """With custom types, output contains 'Engagement Schema' section with the types listed."""
    custom_entity_types = ["regulation", "obligation", "governance_body"]
    custom_rel_types = ["governs", "requires", "enforces"]

    prompt = build_coordinator_prompt(
        entity_types=custom_entity_types,
        relationship_types=custom_rel_types,
    )

    # Should contain schema section
    assert "## Engagement Schema" in prompt

    # Should contain entity types
    assert "Entity types:" in prompt
    assert "regulation" in prompt
    assert "obligation" in prompt
    assert "governance_body" in prompt

    # Should contain relationship types
    assert "Relationship types:" in prompt
    assert "governs" in prompt
    assert "requires" in prompt
    assert "enforces" in prompt

    # Standard sections should still be present
    assert "Source Trust Tiers" in prompt
    assert "Output Format" in prompt


def test_build_coordinator_prompt_entity_types_only():
    """With only entity types, schema section should include
    entity types but not relationship types."""
    prompt = build_coordinator_prompt(entity_types=["service", "database"])

    assert "## Engagement Schema" in prompt
    assert "Entity types:" in prompt
    assert "service" in prompt
    assert "database" in prompt
    # relationship_types line should not appear since none were given
    assert "Relationship types:" not in prompt


def test_build_coordinator_prompt_relationship_types_only():
    """With only relationship types, schema section should include
    relationship types but not entity types."""
    prompt = build_coordinator_prompt(relationship_types=["governs", "requires"])

    assert "## Engagement Schema" in prompt
    assert "Relationship types:" in prompt
    assert "governs" in prompt
    assert "requires" in prompt
    # entity_types line should not appear since none were given
    assert "Entity types:" not in prompt


def test_default_constants_match_builders():
    """COORDINATOR_SYSTEM_PROMPT and WORKER_BASE_PROMPT match
    their respective builders called with no args."""
    assert COORDINATOR_SYSTEM_PROMPT == build_coordinator_prompt()
    assert WORKER_BASE_PROMPT == build_worker_prompt()
    assert GRAPH_TOOLS == build_graph_tools()
