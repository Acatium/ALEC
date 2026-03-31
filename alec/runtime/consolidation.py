"""ConsolidationService — synthesizes per-entity knowledge and detects cross-links."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from alec.agents.prompts.consolidation import (
    CONSOLIDATION_SYSTEM_PROMPT,
    build_consolidation_user_message,
)
from alec.events.types import ConsolidationCompleted, ConsolidationStarted
from alec.knowledge.domain import (
    ConsolidationConfig,
    ConsolidationResult,
    StaleEntity,
)

if TYPE_CHECKING:
    from alec.agents.llm_client import LLMClient
    from alec.db.embeddings import EmbeddingService
    from alec.events.bus import EventBus
    from alec.knowledge.repositories.consolidation import ConsolidationRepository

logger = structlog.get_logger()


class ConsolidationService:
    """Orchestrates the full consolidation run.

    Flow:
    1. Check trigger condition
    2. Find stale entities
    3. For each: gather material → LLM synthesis → embed summary → store unit
    4. Detect cross-links
    5. Record cross-links as observations
    """

    def __init__(
        self,
        repo: ConsolidationRepository,
        llm: LLMClient,
        embedder: EmbeddingService,
        event_bus: EventBus,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._embedder = embedder
        self._event_bus = event_bus

    async def run(
        self,
        engagement_id: UUID,
        config: ConsolidationConfig,
    ) -> ConsolidationResult | None:
        """Run consolidation if triggered. Returns None if not triggered."""
        # Check trigger
        if not await self._repo.should_consolidate(engagement_id, config):
            logger.debug("consolidation.skipped", engagement_id=str(engagement_id))
            return None

        # Find stale entities
        stale_entities = await self._repo.find_stale_entities(
            engagement_id,
            config.max_entities_per_run,
        )

        if not stale_entities:
            logger.info("consolidation.no_stale_entities", engagement_id=str(engagement_id))
            # Still detect cross-links even with no stale entities
            cross_links = await self._repo.detect_cross_links(engagement_id, config)
            recorded = 0
            if cross_links:
                await self._repo.record_cross_link_observations(engagement_id, cross_links)
                recorded = len(cross_links)
            return ConsolidationResult(
                entities_consolidated=0,
                units_created=0,
                units_updated=0,
                cross_links_detected=len(cross_links),
                cross_links_recorded=recorded,
                errors=[],
            )

        await self._event_bus.emit(
            ConsolidationStarted(
                engagement_id=engagement_id,
                stale_entity_count=len(stale_entities),
            )
        )

        logger.info(
            "consolidation.started",
            engagement_id=str(engagement_id),
            stale_entities=len(stale_entities),
        )

        # Synthesize each entity
        units_created = 0
        units_updated = 0
        errors: list[str] = []

        for entity in stale_entities:
            try:
                await self._synthesize_entity(engagement_id, entity)
                if entity.has_existing_unit:
                    units_updated += 1
                else:
                    units_created += 1
            except Exception as e:
                msg = f"Entity '{entity.name}' consolidation failed: {e}"
                logger.warning("consolidation.entity_error", entity=entity.name, error=str(e))
                errors.append(msg)

        entities_consolidated = units_created + units_updated

        # Detect cross-links
        cross_links = await self._repo.detect_cross_links(engagement_id, config)
        recorded = 0
        if cross_links:
            await self._repo.record_cross_link_observations(engagement_id, cross_links)
            recorded = len(cross_links)

        result = ConsolidationResult(
            entities_consolidated=entities_consolidated,
            units_created=units_created,
            units_updated=units_updated,
            cross_links_detected=len(cross_links),
            cross_links_recorded=recorded,
            errors=errors,
        )

        await self._event_bus.emit(
            ConsolidationCompleted(
                engagement_id=engagement_id,
                units_created=units_created,
                units_updated=units_updated,
                cross_links_detected=len(cross_links),
            )
        )

        logger.info(
            "consolidation.completed",
            engagement_id=str(engagement_id),
            entities_consolidated=entities_consolidated,
            cross_links=len(cross_links),
            errors=len(errors),
        )

        return result

    async def _synthesize_entity(
        self,
        engagement_id: UUID,
        entity: StaleEntity,
    ) -> bool:
        """Gather material, call LLM, embed, store. Returns True on success."""
        # Gather material
        material = await self._repo.gather_material(engagement_id, entity)

        # Build user message
        user_message = build_consolidation_user_message(material)

        # LLM synthesis
        response = await self._llm.call(
            system=CONSOLIDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1024,
        )

        summary = response.text.strip()
        if not summary:
            raise ValueError(f"Empty summary for entity '{entity.name}'")

        # Embed the summary
        embedding = await self._embedder.embed(summary)

        # Count tokens (rough estimate: words * 1.3)
        token_count = int(len(summary.split()) * 1.3)

        # Collect source observation IDs from material
        source_obs_ids: list[UUID] = []
        for obs in material.observations:
            obs_id = obs.get("observation_id")
            if obs_id is not None:
                source_obs_ids.append(obs_id)

        # Store consolidated unit
        await self._repo.store_consolidated_unit(
            engagement_id=engagement_id,
            entity_id=entity.entity_id,
            summary=summary,
            embedding=embedding,
            source_observation_ids=source_obs_ids,
            token_count=token_count,
            is_update=entity.has_existing_unit,
        )

        logger.debug(
            "consolidation.entity_synthesized",
            entity=entity.name,
            tokens=token_count,
            is_update=entity.has_existing_unit,
        )

        return True
