"""Graph tool JSON schemas for the Anthropic tool-use API."""

from __future__ import annotations

import copy
from typing import Any

# Default entity/relationship types (backward compat)
_DEFAULT_ENTITY_TYPES = [
    "service", "database", "team", "api", "policy", "person",
    "document", "capability", "domain", "repository", "schema", "process",
]

_DEFAULT_RELATIONSHIP_TYPES = [
    "depends_on", "owned_by", "reads_from", "writes_to", "calls",
    "governs", "implements", "contains", "supersedes", "related_to",
]

_ADD_ENTITY_TEMPLATE: dict[str, Any] = {
    "name": "add_entity",
    "description": (
        "Record a discovered entity. IMPORTANT: Before creating a new entity, "
        "check the existing entity list in the system prompt. If a matching entity "
        "exists, reuse its exact name. Put alternate names/abbreviations in "
        "aliases. Entity resolution catches some duplicates, but exact name "
        "reuse is far more reliable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The entity name as it appears in this source.",
            },
            "entity_type": {
                "type": "string",
                "enum": _DEFAULT_ENTITY_TYPES,
                "description": "The type of entity.",
            },
            "aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Alternative names seen for this entity "
                    "(e.g., 'payments-svc', 'PaymentService')."
                ),
                "default": [],
            },
            "properties": {
                "type": "object",
                "description": "Key-value properties observed about this entity.",
                "default": {},
            },
        },
        "required": ["name", "entity_type"],
    },
}

_ADD_RELATIONSHIP_TEMPLATE: dict[str, Any] = {
    "name": "add_relationship",
    "description": (
        "Record a relationship between two entities. Both entities should already "
        "exist (use add_entity first). If you reference an entity that doesn't "
        "exist yet, it will be auto-created with minimal information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "from_entity": {
                "type": "string",
                "description": "Name of the source entity.",
            },
            "to_entity": {
                "type": "string",
                "description": "Name of the target entity.",
            },
            "relationship_type": {
                "type": "string",
                "enum": _DEFAULT_RELATIONSHIP_TYPES,
                "description": "How from_entity relates to to_entity.",
            },
            "evidence": {
                "type": "string",
                "description": "Brief description of the evidence for this relationship.",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Confidence 0.0-1.0. Use 0.9+ for explicit declarations, "
                    "0.5-0.8 for inferred from context."
                ),
                "default": 0.7,
            },
        },
        "required": ["from_entity", "to_entity", "relationship_type", "evidence"],
    },
}

_ADD_OBSERVATION: dict[str, Any] = {
    "name": "add_observation",
    "description": (
        "Record a free-text observation. Use this for insights, contradictions, "
        "or information that doesn't fit neatly into entity/relationship structure."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The observation text. Be specific and cite the source.",
            },
            "observation_type": {
                "type": "string",
                "enum": ["insight", "contradiction", "gap", "alignment"],
                "description": "What kind of observation this is.",
            },
            "entities_referenced": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names of entities this observation relates to.",
                "default": [],
            },
        },
        "required": ["text", "observation_type"],
    },
}

_SUGGEST_FOLLOWUP: dict[str, Any] = {
    "name": "suggest_followup",
    "description": (
        "Suggest a follow-up exploration task. Use when you find something that "
        "needs deeper investigation but is outside your current scope."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "What should be investigated?",
            },
            "suggested_source": {
                "type": "string",
                "description": "Which source to investigate (if known).",
                "default": "",
            },
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How important is this follow-up?",
                "default": "medium",
            },
        },
        "required": ["question"],
    },
}


def build_graph_tools(
    entity_types: list[str] | None = None,
    relationship_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build graph tool schemas with provided type enums.

    If entity_types or relationship_types are None, uses the default lists.
    """
    add_entity = copy.deepcopy(_ADD_ENTITY_TEMPLATE)
    add_rel = copy.deepcopy(_ADD_RELATIONSHIP_TEMPLATE)

    if entity_types is not None:
        add_entity["input_schema"]["properties"]["entity_type"]["enum"] = entity_types

    if relationship_types is not None:
        add_rel["input_schema"]["properties"]["relationship_type"]["enum"] = relationship_types

    return [add_entity, add_rel, _ADD_OBSERVATION, _SUGGEST_FOLLOWUP]


# Default tools for backward compatibility
GRAPH_TOOLS = build_graph_tools()
