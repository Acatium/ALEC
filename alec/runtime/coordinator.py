"""Coordinator service — builds projection, generates directives via LLM."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from alec.agents.llm_client import LLMClient
from alec.agents.prompts.coordinator import COORDINATOR_SYSTEM_PROMPT, build_coordinator_prompt
from alec.knowledge.domain import (
    AlignmentOpp,
    Contradiction,
    ConvergenceConfig,
    CoordinatorProjection,
    CycleResult,
    CycleStats,
    Gap,
    RankedIssue,
    TaskRecord,
)
from alec.knowledge.repositories.projections import (
    ProjectionRepository,
    get_entity_annotations,
    get_entity_trust_tiers,
    rank_issues,
)
from alec.knowledge.repositories.tasks import TaskRepository

logger = structlog.get_logger()


class CoordinatorService:
    """Stateless coordinator cycle: projection → rank → LLM → directives."""

    def __init__(
        self,
        projections: ProjectionRepository,
        tasks: TaskRepository,
        llm: LLMClient,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
    ) -> None:
        self._projections = projections
        self._tasks = tasks
        self._llm = llm
        self._entity_types = entity_types
        self._relationship_types = relationship_types

    async def run_cycle(
        self,
        engagement_id: UUID,
        coordinator_id: UUID,
        cycle_number: int,
        last_cycle_at: datetime,
        convergence_config: ConvergenceConfig,
    ) -> CycleResult:
        """Execute one coordinator cycle. Returns CycleResult with directives."""

        # Step 1: Build projection (all SQL)
        projection = await self._projections.build_projection(
            engagement_id,
            coordinator_id,
            last_cycle_at,
        )

        # Step 2: Check convergence
        converged, metrics = await self._projections.check_convergence(
            engagement_id,
            cycle_number,
            convergence_config,
        )

        if converged:
            logger.info(
                "coordinator.converged",
                cycle=cycle_number,
                weighted_ratio=metrics.weighted_ratio,
                primary=metrics.primary_converged,
                secondary=metrics.secondary_converged,
            )
            return CycleResult(
                directives=[],
                convergence_signal=True,
                cycle_stats=CycleStats(
                    cycle_number=cycle_number,
                    convergence_ratio=metrics.weighted_ratio,
                    gaps_found=len(projection.active_gaps),
                    contradictions_found=len(projection.contradictions),
                ),
            )

        # Step 3: Rank issues (with annotation/trust tier boosts)
        annotations = await get_entity_annotations(
            self._projections._pool, engagement_id
        )
        trust_tiers = await get_entity_trust_tiers(
            self._projections._pool, engagement_id
        )
        ranked = rank_issues(
            projection.active_gaps,
            projection.contradictions,
            projection.alignment_opportunities,
            entity_annotations=annotations if annotations else None,
            entity_trust_tiers=trust_tiers if trust_tiers else None,
        )

        if not ranked:
            logger.info("coordinator.no_issues", cycle=cycle_number)
            return CycleResult(
                directives=[],
                convergence_signal=False,
                cycle_stats=CycleStats(
                    cycle_number=cycle_number,
                    convergence_ratio=metrics.weighted_ratio,
                    gaps_found=0,
                    contradictions_found=0,
                ),
            )

        # Step 4: Get sources
        sources = await self._projections.get_verified_sources(engagement_id)

        # Step 5: Generate directives (1 LLM call)
        user_message = self._build_user_message(projection, ranked, sources)

        if self._entity_types or self._relationship_types:
            system_prompt = build_coordinator_prompt(
                self._entity_types, self._relationship_types
            )
        else:
            system_prompt = COORDINATOR_SYSTEM_PROMPT

        response = await self._llm.call(
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=4096,
        )

        directives = self._parse_directives(response.text, engagement_id, coordinator_id)

        # Step 6: Persist directives as tasks
        for d in directives:
            task_id = await self._tasks.create(
                engagement_id=engagement_id,
                coordinator_id=coordinator_id,
                directive=d.directive,
                source_type=d.source_type,
                source_ref=d.source_ref,
                max_scope=d.max_scope,
                relevant_context=d.relevant_context,
            )
            d.task_id = task_id

        logger.info(
            "coordinator.cycle_complete",
            cycle=cycle_number,
            directives=len(directives),
            weighted_ratio=metrics.weighted_ratio,
        )

        return CycleResult(
            directives=directives,
            convergence_signal=False,
            cycle_stats=CycleStats(
                cycle_number=cycle_number,
                convergence_ratio=metrics.weighted_ratio,
                gaps_found=len(projection.active_gaps),
                contradictions_found=len(projection.contradictions),
                directives_generated=len(directives),
            ),
        )

    def _build_user_message(
        self,
        projection: CoordinatorProjection,
        ranked: list[RankedIssue],
        sources: list[dict[str, Any]],
    ) -> str:
        """Build the user message for the coordinator LLM call."""
        p = projection
        sections = [
            f"## Problem Statement\n{p.problem_statement}",
            f"\n{p.coverage_dashboard}",
            "\n## Ranked Issues",
        ]

        for i, issue in enumerate(ranked, 1):
            summary = _issue_summary(issue)
            sections.append(f"  {i}. [{issue.issue_type}] score={issue.score:.1f}: {summary}")

        sections.append(f"\n{p.recent_findings}")
        sections.append(f"\n{p.recent_decisions}")
        sections.append(f"\n{p.model_summary}")

        sections.append("\n## Available Sources")
        for s in sources:
            sections.append(f"  - {s['source_type']}: {json.dumps(s['config'])}")

        return "\n".join(sections)

    @staticmethod
    def _parse_directives(
        text: str,
        engagement_id: UUID,
        coordinator_id: UUID,
    ) -> list[TaskRecord]:
        """Parse LLM output into TaskRecord objects."""
        # Extract JSON array from response
        try:
            # Try to find JSON array in the text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                raw = json.loads(text[start:end])
            else:
                logger.warning("coordinator.no_json_array", text=text[:200])
                return []
        except json.JSONDecodeError:
            logger.warning("coordinator.json_parse_error", text=text[:200])
            return []

        directives = []
        for item in raw[:5]:  # Cap at 5
            try:
                from uuid import uuid4

                directives.append(
                    TaskRecord(
                        task_id=uuid4(),  # Placeholder, will be replaced on DB insert
                        engagement_id=engagement_id,
                        coordinator_id=coordinator_id,
                        directive=item.get("directive", ""),
                        source_type=item.get("source_type", "unknown"),
                        source_ref=item.get("source_ref", ""),
                        max_scope=item.get("max_scope", "survey"),
                        relevant_context=item.get("relevant_context"),
                    )
                )
            except Exception as e:
                logger.warning("coordinator.directive_parse_error", error=str(e))
                continue

        return directives


def _issue_summary(issue: RankedIssue) -> str:
    """Format an issue for the coordinator prompt."""
    d = issue.data
    if isinstance(d, Gap):
        return f"{d.gap_type}: '{d.name}' ({d.entity_type}, refs={d.reference_count})"
    elif isinstance(d, Contradiction):
        return f"{d.contradiction_type}: {d.from_name}↔{d.to_name} ({d.type_a} vs {d.type_b})"
    elif isinstance(d, AlignmentOpp):
        return (
            f"{d.entity_a_name} ({d.model_a_name}) ↔ "
            f"{d.entity_b_name} ({d.model_b_name}), sim={d.similarity:.2f}"
        )
    return str(d)
