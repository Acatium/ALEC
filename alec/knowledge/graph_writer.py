"""GraphWriter — executes graph tool calls against PostgreSQL.

Handles entity name → entity_id resolution with local caching.
Tracks write counts for WorkerResult.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from alec.db.embeddings import EmbeddingService
from alec.knowledge.name_similarity import name_similarity_score, normalize_entity_name
from alec.knowledge.repositories.entities import EntityRepository
from alec.knowledge.repositories.observations import ObservationRepository
from alec.knowledge.repositories.relationships import RelationshipRepository

logger = structlog.get_logger()


class GraphWriter:
    """Executes graph tool calls. Tracks counts. Handles entity resolution."""

    def __init__(
        self,
        engagement_id: UUID,
        model_id: UUID | None,
        worker_id: str,
        source_ref: str,
        entities: EntityRepository,
        relationships: RelationshipRepository,
        observations: ObservationRepository,
        embedder: EmbeddingService,
        similarity_threshold: float = 0.85,
    ) -> None:
        self.engagement_id = engagement_id
        self.model_id = model_id
        self.worker_id = worker_id
        self.source_ref = source_ref
        self._entities = entities
        self._relationships = relationships
        self._observations = observations
        self._embedder = embedder
        self._similarity_threshold = similarity_threshold

        # Counters
        self.entities_written = 0
        self.relationships_written = 0
        self.observations_written = 0
        self.followups_suggested = 0

        # Local name→id cache (within this worker's lifetime)
        self._entity_cache: dict[str, UUID] = {}
        # Track relationship triples seen by this worker
        self._seen_triples: set[tuple[str, str, str]] = set()

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a graph tool call. Returns result text for the LLM."""
        match tool_name:
            case "add_entity":
                return await self._add_entity(tool_input)
            case "add_relationship":
                return await self._add_relationship(tool_input)
            case "add_observation":
                return await self._add_observation(tool_input)
            case "suggest_followup":
                return await self._suggest_followup(tool_input)
            case _:
                return f"Unknown tool: {tool_name}"

    async def _add_entity(self, params: dict[str, Any]) -> str:
        name = params["name"]
        entity_type = params["entity_type"]
        aliases = params.get("aliases", [])
        properties = params.get("properties", {})

        # Check local cache first
        if name in self._entity_cache:
            entity_id = self._entity_cache[name]
            await self._entities.update_on_rediscovery(entity_id, aliases, properties)
            await self._record_entity_observation(name, entity_type, "reinforcement")
            return f"Updated existing entity '{name}' (id: {entity_id})"

        # Check DB for existing entity by exact name/alias
        existing = await self._entities.find_by_name(self.engagement_id, name)

        if existing:
            entity_id = existing.entity_id
            await self._entities.update_on_rediscovery(entity_id, aliases, properties)
            self._entity_cache[name] = entity_id
            await self._record_entity_observation(name, entity_type, "reinforcement")
            return f"Updated existing entity '{name}' (id: {entity_id})"

        # String similarity check before embedding (fast, catches variants)
        string_match = await self._string_similarity_match(name, aliases, properties)
        if string_match is not None:
            return string_match

        # Generate embedding BEFORE similarity check so we can use it for the query
        embedding = await self._embedder.embed(name)

        # Fuzzy match: check for semantically similar entities
        similar = await self._entities.find_similar(
            self.engagement_id, embedding, threshold=self._similarity_threshold, limit=1
        )
        if similar:
            match, similarity = similar[0]
            entity_id = match.entity_id
            # Add the new name as an alias on the matched entity
            new_aliases = list(set(aliases + [name]))
            await self._entities.update_on_rediscovery(entity_id, new_aliases, properties)
            self._entity_cache[name] = entity_id
            logger.info(
                "graph_writer.fuzzy_match",
                new_name=name,
                matched_name=match.name,
                similarity=f"{similarity:.3f}",
            )
            await self._record_entity_observation(name, entity_type, "reinforcement")
            return (
                f"Matched '{name}' to existing entity '{match.name}' "
                f"(similarity: {similarity:.2f}, id: {entity_id})"
            )

        # Create new entity (embedding already computed)
        entity_id = await self._entities.create(
            engagement_id=self.engagement_id,
            name=name,
            entity_type=entity_type,
            model_id=self.model_id,
            aliases=aliases,
            embedding=embedding,
            properties=properties,
        )
        self._entity_cache[name] = entity_id
        self.entities_written += 1
        await self._record_entity_observation(name, entity_type, "expansion")
        return f"Created entity '{name}' (id: {entity_id})"

    async def _record_entity_observation(
        self,
        name: str,
        entity_type: str,
        impact_type: str,
    ) -> None:
        """Record an observation for convergence tracking."""
        await self._observations.create(
            engagement_id=self.engagement_id,
            source_ref=self.source_ref,
            raw_text=f"Entity '{name}' ({entity_type})",
            observation_type="entity_discovered",
            worker_id=self.worker_id,
            metadata={"entity_name": name, "impact_type": impact_type},
        )

    async def _add_relationship(self, params: dict[str, Any]) -> str:
        from_name = params["from_entity"]
        to_name = params["to_entity"]
        rel_type = params["relationship_type"]
        evidence_text = params["evidence"]
        confidence = params.get("confidence", 0.7)

        # Resolve entity names to IDs (auto-create if needed)
        from_id = await self._resolve_entity(from_name)
        to_id = await self._resolve_entity(to_name)

        # Determine impact type: new triple = expansion, seen before = reinforcement
        triple = (from_name, to_name, rel_type)
        if triple in self._seen_triples:
            impact_type = "reinforcement"
        else:
            # Check DB for existing relationship from other workers
            existing = await self._relationships.find_by_entity(
                self.engagement_id,
                from_id,
            )
            has_existing = any(
                r.to_entity == to_id and r.relationship_type == rel_type for r in existing
            )
            impact_type = "reinforcement" if has_existing else "expansion"
            self._seen_triples.add(triple)

        # Record evidence as an observation with impact_type
        obs_id = await self._observations.create(
            engagement_id=self.engagement_id,
            source_ref=self.source_ref,
            raw_text=evidence_text,
            observation_type="relationship",
            worker_id=self.worker_id,
            metadata={
                "from": from_name,
                "to": to_name,
                "type": rel_type,
                "impact_type": impact_type,
            },
        )

        # Upsert relationship
        await self._relationships.upsert(
            engagement_id=self.engagement_id,
            from_entity=from_id,
            to_entity=to_id,
            relationship_type=rel_type,
            evidence_id=obs_id,
            confidence=confidence,
        )

        self.relationships_written += 1
        return f"Recorded: {from_name} --[{rel_type}]--> {to_name} (confidence: {confidence})"

    async def _add_observation(self, params: dict[str, Any]) -> str:
        text = params["text"]
        obs_type = params.get("observation_type", "insight")
        entities_referenced = params.get("entities_referenced", [])
        # Impact type is always "expansion" for free-text observations.
        # Entity and relationship tools handle their own impact classification.
        impact = "expansion"

        await self._observations.create(
            engagement_id=self.engagement_id,
            source_ref=self.source_ref,
            raw_text=text,
            observation_type=obs_type,
            worker_id=self.worker_id,
            metadata={
                "entities_referenced": entities_referenced,
                "impact_type": impact,
            },
        )

        self.observations_written += 1
        return f"Recorded {obs_type} observation ({impact})"

    async def _suggest_followup(self, params: dict[str, Any]) -> str:
        question = params["question"]
        source = params.get("suggested_source", "")
        priority = params.get("priority", "medium")

        await self._observations.create(
            engagement_id=self.engagement_id,
            source_ref=self.source_ref,
            raw_text=question,
            observation_type="gap",
            worker_id=self.worker_id,
            metadata={
                "suggested_source": source,
                "priority": priority,
                "impact_type": "expansion",
            },
        )

        self.followups_suggested += 1
        return f"Follow-up suggestion recorded (priority: {priority})"

    async def _string_similarity_match(
        self,
        name: str,
        aliases: list[str],
        properties: dict[str, Any],
    ) -> str | None:
        """Try to match entity by string similarity. Returns result string or None."""
        normalized = normalize_entity_name(name)
        tokens = normalized.split()
        if not tokens:
            return None

        candidates = await self._entities.find_by_normalized_prefix(
            self.engagement_id, tokens, limit=20
        )
        if not candidates:
            return None

        best_score = 0.0
        best_candidate = None
        for candidate in candidates:
            score = name_similarity_score(
                candidate.name, candidate.aliases, name
            )
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is not None and best_score >= 0.70:
            entity_id = best_candidate.entity_id
            new_aliases = list(set(aliases + [name]))
            await self._entities.update_on_rediscovery(entity_id, new_aliases, properties)
            self._entity_cache[name] = entity_id
            logger.info(
                "graph_writer.string_match",
                new_name=name,
                matched_name=best_candidate.name,
                score=f"{best_score:.3f}",
            )
            await self._record_entity_observation(name, "unknown", "reinforcement")
            return (
                f"Matched '{name}' to existing entity '{best_candidate.name}' "
                f"(string similarity: {best_score:.2f}, id: {entity_id})"
            )

        return None

    async def _string_similarity_resolve(self, name: str) -> UUID | None:
        """Try to resolve entity by string similarity. Returns entity_id or None."""
        normalized = normalize_entity_name(name)
        tokens = normalized.split()
        if not tokens:
            return None

        candidates = await self._entities.find_by_normalized_prefix(
            self.engagement_id, tokens, limit=20
        )
        if not candidates:
            return None

        best_score = 0.0
        best_candidate = None
        for candidate in candidates:
            score = name_similarity_score(
                candidate.name, candidate.aliases, name
            )
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is not None and best_score >= 0.70:
            entity_id = best_candidate.entity_id
            await self._entities.update_on_rediscovery(entity_id, [name], {})
            self._entity_cache[name] = entity_id
            logger.info(
                "graph_writer.string_resolve",
                new_name=name,
                matched_name=best_candidate.name,
                score=f"{best_score:.3f}",
            )
            return entity_id

        return None

    async def _resolve_entity(self, name: str) -> UUID:
        """Resolve entity name to ID. Tries exact match, then fuzzy, then auto-creates."""
        if name in self._entity_cache:
            return self._entity_cache[name]

        existing = await self._entities.find_by_name(self.engagement_id, name)
        if existing:
            self._entity_cache[name] = existing.entity_id
            return existing.entity_id

        # String similarity check before embedding
        string_match_id = await self._string_similarity_resolve(name)
        if string_match_id is not None:
            return string_match_id

        # Fuzzy match before auto-creating
        embedding = await self._embedder.embed(name)
        similar = await self._entities.find_similar(
            self.engagement_id, embedding, threshold=self._similarity_threshold, limit=1
        )
        if similar:
            match, similarity = similar[0]
            await self._entities.update_on_rediscovery(match.entity_id, [name], {})
            self._entity_cache[name] = match.entity_id
            logger.info(
                "graph_writer.fuzzy_resolve",
                new_name=name,
                matched_name=match.name,
                similarity=f"{similarity:.3f}",
            )
            return match.entity_id

        # Auto-create with minimal info (embedding already computed)
        entity_id = await self._entities.create(
            engagement_id=self.engagement_id,
            name=name,
            entity_type="unknown",
            model_id=self.model_id,
            embedding=embedding,
            properties={"auto_created": True},
        )

        self._entity_cache[name] = entity_id
        self.entities_written += 1
        await self._record_entity_observation(name, "unknown", "expansion")
        return entity_id
