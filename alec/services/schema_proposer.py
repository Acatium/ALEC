"""Schema proposer — LLM-based schema suggestion for engagements."""

from __future__ import annotations

import json
from typing import Any

import structlog

from alec.agents.llm_client import LLMClient
from alec.agents.prompts.schema_proposal import SCHEMA_PROPOSAL_PROMPT

logger = structlog.get_logger()


class SchemaProposer:
    """Analyzes a problem statement and suggests schema types."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def propose(
        self, problem_statement: str, sources: list[str]
    ) -> dict[str, Any]:
        """Propose entity and relationship types for a domain.

        Returns a dict with template_base, entity_types, relationship_types, reasoning.
        """
        sources_desc = "\n".join(f"  - {s}" for s in sources) if sources else "  (none)"
        user_msg = (
            f"## Problem Statement\n{problem_statement}\n\n"
            f"## Sources\n{sources_desc}"
        )

        response = await self._llm.call(
            system=SCHEMA_PROPOSAL_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4096,
        )

        return self._parse_response(response.text)

    @staticmethod
    def _parse_response(text: str) -> dict[str, Any]:
        """Parse LLM response into structured proposal."""
        try:
            # Try direct JSON parse
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result: dict[str, Any] = json.loads(text[start:end])
            else:
                logger.warning("schema_proposer.no_json", text=text[:200])
                return _fallback_proposal()
        except json.JSONDecodeError:
            logger.warning("schema_proposer.json_error", text=text[:200])
            return _fallback_proposal()

        # Validate structure
        if not isinstance(result.get("entity_types"), list):
            result["entity_types"] = []
        if not isinstance(result.get("relationship_types"), list):
            result["relationship_types"] = []
        if "template_base" not in result:
            result["template_base"] = "general_discovery"
        if "reasoning" not in result:
            result["reasoning"] = ""

        return result


def _fallback_proposal() -> dict[str, Any]:
    return {
        "template_base": "general_discovery",
        "entity_types": [],
        "relationship_types": [],
        "reasoning": "Could not generate proposal. Use general_discovery template.",
    }
