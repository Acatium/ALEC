"""Consolidation system prompt and user message builder."""

from __future__ import annotations

from alec.knowledge.domain import ConsolidationMaterial

CONSOLIDATION_SYSTEM_PROMPT = """\
You are a knowledge consolidation agent. Your task is to synthesize \
all available information about a single entity into a dense, \
attributed summary.

You receive:
1. The entity's name, type, aliases, and properties
2. All observations referencing this entity (from multiple sources/workers)
3. All relationships (incoming and outgoing)
4. Any cross-model alignments

You produce: A consolidated summary (150-400 tokens) in the following format:

## [Entity Name] ([entity_type])
(Consolidated from N observations across M sources)

[1-2 sentence core description based on all evidence]

Relationships:
- [direction] [relationship_type] [other_entity] (confidence: X)

Cross-Model Appearances:
- [model_name]: [how this entity appears, noting alignment/divergence]

Open Questions:
- [things we don't know yet]
- [contradictions still unresolved]

## Rules

1. Dense: every sentence carries information. No filler.
2. Attributed: reference source types ("per docs", "seen in codebase").
3. Cross-model aware: describe how each model sees the entity.
4. Highlight surprises and contradictions.
5. Only include information present in the material. Do not invent.
6. If there are no cross-model appearances, omit that section.
7. If there are no open questions, omit that section.
8. Return ONLY the summary text. No JSON wrapper.
"""


def build_consolidation_user_message(material: ConsolidationMaterial) -> str:
    """Build the user message for a consolidation LLM call.

    Pure function — no I/O, no side effects.
    """
    lines: list[str] = []

    # Entity header
    lines.append(f"# Entity: {material.entity_name} ({material.entity_type})")
    if material.aliases:
        lines.append(f"Aliases: {', '.join(material.aliases)}")
    if material.properties:
        props = ", ".join(f"{k}={v}" for k, v in material.properties.items())
        lines.append(f"Properties: {props}")
    lines.append("")

    # Observations
    lines.append(f"## Observations ({len(material.observations)})")
    for obs in material.observations:
        source = obs.get("source_ref", "unknown")
        text = obs.get("raw_text", "")
        obs_type = obs.get("observation_type", "")
        lines.append(f"- [{obs_type}] (source: {source}): {text}")
    lines.append("")

    # Outgoing relationships
    if material.relationships_outgoing:
        lines.append(f"## Outgoing Relationships ({len(material.relationships_outgoing)})")
        for rel in material.relationships_outgoing:
            to_name = rel.get("to_name", "?")
            rel_type = rel.get("relationship_type", "?")
            confidence = rel.get("confidence", 0.5)
            lines.append(f"- --[{rel_type}]--> {to_name} (confidence: {confidence})")
        lines.append("")

    # Incoming relationships
    if material.relationships_incoming:
        lines.append(f"## Incoming Relationships ({len(material.relationships_incoming)})")
        for rel in material.relationships_incoming:
            from_name = rel.get("from_name", "?")
            rel_type = rel.get("relationship_type", "?")
            confidence = rel.get("confidence", 0.5)
            lines.append(f"- {from_name} --[{rel_type}]--> this (confidence: {confidence})")
        lines.append("")

    # Alignments
    if material.alignments:
        lines.append(f"## Cross-Model Alignments ({len(material.alignments)})")
        for align in material.alignments:
            other_name = align.get("other_entity_name", "?")
            model_name = align.get("model_name", "?")
            align_type = align.get("alignment_type", "?")
            lines.append(f"- {align_type} with {other_name} (model: {model_name})")
        lines.append("")

    return "\n".join(lines)
