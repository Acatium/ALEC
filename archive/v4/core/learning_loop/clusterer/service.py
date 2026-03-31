"""CLUSTERER service - Cluster management only.

v4 Simplified Schema (gap-aku-001):
- Renamed bullets → AKUs
- Uses akus table (not playbook_bullets)
- Uses aku_id column (not bullet_id)
- Consumes aku.accepted, aku.merged (not bullet.*)

Responsibilities:
1. Assign turns to clusters (from attribution.resolved)
2. Update cluster counters (success/failure)
3. Link AKUs to clusters (from aku.accepted)
4. Create solved_by edges for new AKUs
5. AKU status transitions (candidate → active, active → archived)

Note: AKU counter updates and caused_failure edges are handled by REFLECTOR.
"""

import os
from typing import Any, Optional
from uuid import uuid4

from core.common import BaseService
from core.common.embedding_client import EmbeddingClient
from core.common.kafka_client import Event


def _embedding_to_str(embedding) -> str:
    """Convert embedding to pgvector string format.

    Handles both Python lists (from embedding client) and strings (from DB).
    """
    if isinstance(embedding, str):
        # Already a pgvector string from database
        return embedding
    # Python list from embedding client
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _extract_aku_id(aku: Any) -> Optional[str]:
    """Extract AKU ID from either a dict or string/UUID.

    SESSION sends akus_used as list[dict] with full AKU objects.
    This helper extracts the UUID string regardless of input format.

    Handles both old field names (bullet_id) and new (aku_id) for compatibility.
    Returns None for invalid UUIDs to prevent database errors.
    """
    from core.learning_loop.shared.text_parser import is_valid_uuid

    aku_id = None
    if isinstance(aku, dict):
        raw_id = aku.get("id") or aku.get("aku_id") or aku.get("bullet_id")
        aku_id = str(raw_id) if raw_id else None
    elif aku:
        aku_id = str(aku)

    # Validate UUID format before returning (defense in depth)
    if aku_id and not is_valid_uuid(aku_id):
        return None

    return aku_id


def _extract_aku_ids(akus: list) -> list[str]:
    """Extract list of AKU UUIDs from mixed format list."""
    result = []
    for a in akus:
        aid = _extract_aku_id(a)
        if aid:
            result.append(aid)
    return result


# Configuration
CLUSTER_THRESHOLD = float(os.getenv("ALEC_CLUSTER_THRESHOLD", "0.65"))
PROMOTE_HELPFUL_COUNT = int(os.getenv("ALEC_PROMOTE_HELPFUL", "3"))
ARCHIVE_HARMFUL_RATIO = float(os.getenv("ALEC_ARCHIVE_HARMFUL_RATIO", "2.0"))
# Semantic bridge: create cluster for ADVISOR's understanding if it differs from REFLECTOR's
BRIDGE_THRESHOLD = float(os.getenv("ALEC_BRIDGE_THRESHOLD", "0.70"))
BRIDGE_CLUSTER_THRESHOLD = float(os.getenv("ALEC_BRIDGE_CLUSTER_THRESHOLD", "0.80"))


class ClustererService(BaseService):
    """CLUSTERER - Cluster management and solved_by edges."""

    def __init__(self):
        super().__init__("clusterer")
        self._embedding_client: Optional[EmbeddingClient] = None

    def _get_topics(self) -> list[str]:
        return ["attribution.resolved", "aku.accepted", "aku.merged"]

    async def start(self) -> None:
        """Start the service with embedding client."""
        self.logger.info("service_starting")
        self._start_metrics_server()
        await self._init_postgres()
        await self._init_kafka()

        self._embedding_client = EmbeddingClient()
        await self._embedding_client.start()

        await self._require_kafka().start_consumer(
            topics=self._get_topics(),
            handler=self._handle_event_wrapper,
            group_id=f"{self.service_name}-events",
        )
        self.logger.info("service_started")

    async def _handle_event(self, event: Event) -> None:
        """Route events to handlers."""
        if event.event_type == "attribution.resolved":
            await self._handle_attribution_resolved(event)
        elif event.event_type == "aku.accepted":
            await self._handle_aku_accepted(event)
        elif event.event_type == "aku.merged":
            await self._handle_aku_merged(event)

    async def _handle_attribution_resolved(self, event: Event) -> None:
        """Assign session to cluster, update cluster counters."""
        payload = event.payload
        session_id: str = payload.get("session_id", "")
        domain = payload.get("domain")
        situation = payload.get("situation")  # Session-level problem
        resolved_turns = payload.get("resolved_turns", [])

        # Assign session to cluster ONCE based on situation (not per-turn)
        cluster_id = None
        if situation and self._embedding_client:
            try:
                situation_emb = self._embedding_client.embed(situation)
                cluster_id = await self._assign_to_cluster(
                    situation_emb, domain, label=situation
                )
            except Exception as e:
                self.logger.warning("situation_cluster_failed", error=str(e))

        for turn in resolved_turns:
            if not cluster_id:
                continue

            # Only count outcomes when AKUs were shown (guided attempts)
            # Cold-start sessions shouldn't pollute cluster statistics
            akus_shown = turn.get("bullets_shown", [])  # Still named bullets_shown in event payload
            if akus_shown:
                micro_outcome = turn.get("micro_outcome")
                if micro_outcome in ("stuck", "error"):
                    await self._increment_cluster_counter(cluster_id, "failure_count")
                elif micro_outcome == "solved":
                    await self._increment_cluster_counter(cluster_id, "success_count")

            # Store turn with cluster assignment
            await self._store_turn(turn, session_id, cluster_id)

        # Check for AKU status transitions
        for turn in resolved_turns:
            for aku in turn.get("bullets_shown", []):
                aku_id = _extract_aku_id(aku)
                if aku_id:
                    await self._maybe_promote_aku(aku_id)
                    await self._maybe_archive_aku(aku_id)

        # Create solved_by edges for AKUs that helped this cluster
        if cluster_id:
            akus_helped = payload.get("bullets_helped", [])  # Still named bullets_helped in event payload
            for aku_id in _extract_aku_ids(akus_helped):
                await self._upsert_edge(cluster_id, aku_id, "solved_by")

        # Check for semantic bridge opportunity
        # If ADVISOR's initial understanding differs from REFLECTOR's resolved understanding,
        # create a cluster for the initial framing with edges to helpful/harmful bullets
        similarity = payload.get("similarity", 1.0)
        initial_situation = payload.get("initial_situation")
        initial_embedding = payload.get("initial_embedding")
        bullets_helped = payload.get("bullets_helped", [])
        bullets_harmed = payload.get("bullets_harmed", [])

        if (
            similarity < BRIDGE_THRESHOLD
            and initial_situation
            and initial_embedding
            and (bullets_helped or bullets_harmed)
        ):
            await self._create_semantic_bridge(
                initial_situation=initial_situation,
                initial_embedding=initial_embedding,
                domain=domain,
                bullets_helped=bullets_helped,
                bullets_harmed=bullets_harmed,
            )

        self.logger.info(
            "attribution_processed",
            session_id=session_id,
            turn_count=len(resolved_turns),
            cluster_id=cluster_id,
            semantic_bridge=similarity < BRIDGE_THRESHOLD if initial_situation else False,
        )

    async def _handle_aku_accepted(self, event: Event) -> None:
        """Link new AKU to cluster, create solved_by edge.

        If target_cluster_id is provided (from STRATEGIST), link directly to that
        cluster - this closes the strategic dialogue loop. Otherwise, find cluster
        by embedding similarity (for REFLECTOR-extracted AKUs).
        """
        payload = event.payload
        aku_id = payload.get("aku_id")
        domain = payload.get("domain")
        situation = payload.get("situation")  # For cluster label
        target_cluster_id = payload.get("target_cluster_id")  # From STRATEGIST

        if not aku_id:
            return

        # If STRATEGIST specified a target cluster, use it directly
        # This closes the CLUSTERER ↔ STRATEGIST dialogue loop
        if target_cluster_id:
            cluster_id = target_cluster_id
            self.logger.info(
                "aku_linked_to_target",
                aku_id=aku_id,
                cluster_id=cluster_id,
                source="strategist",
            )
        else:
            # Fall back to embedding-based cluster assignment
            situation_emb = await self._get_aku_situation_embedding(aku_id)
            if not situation_emb:
                self.logger.warning("aku_embedding_missing", aku_id=aku_id)
                return

            cluster_id = await self._assign_to_cluster(situation_emb, domain, label=situation)
            self.logger.info(
                "aku_linked",
                aku_id=aku_id,
                cluster_id=cluster_id,
                source="reflector",
            )

        # Create solved_by edge (new AKUs are presumed helpful)
        await self._upsert_edge(cluster_id, aku_id, "solved_by")

    async def _handle_aku_merged(self, event: Event) -> None:
        """Update cluster links for merged AKU."""
        # When an AKU is merged (evidence incremented), we don't need
        # to create new cluster links - the existing AKU already has them
        aku_id = event.payload.get("aku_id")
        self.logger.debug("aku_merged", aku_id=aku_id)

    async def _assign_turn_to_cluster(
        self, turn: dict, domain: Optional[str]
    ) -> Optional[str]:
        """Assign turn to cluster by sub_task embedding."""
        sub_task = turn.get("sub_task")
        if not sub_task or not self._embedding_client:
            return None

        try:
            sub_task_emb = self._embedding_client.embed(sub_task)
            return await self._assign_to_cluster(sub_task_emb, domain, label=sub_task)
        except Exception as e:
            self.logger.warning("turn_cluster_assignment_failed", error=str(e))
            return None

    async def _assign_to_cluster(
        self,
        embedding: list[float],
        domain: Optional[str] = None,
        label: Optional[str] = None,
    ) -> str:
        """Assign to cluster by embedding similarity."""
        # Try to find nearest existing cluster
        nearest = await self._require_pool().fetchrow(
            """
            SELECT cluster_id, 1 - (centroid <=> $1::vector) as similarity
            FROM problem_clusters
            WHERE 1 - (centroid <=> $1::vector) > $2
            ORDER BY similarity DESC
            LIMIT 1
            """,
            _embedding_to_str(embedding),
            CLUSTER_THRESHOLD,
        )

        if nearest:
            return str(nearest["cluster_id"])
        else:
            # Create new cluster
            return await self._create_cluster(embedding, domain, label)

    async def _create_cluster(
        self,
        centroid: list,
        domain: Optional[str] = None,
        label: Optional[str] = None,
    ) -> str:
        """Create cluster with fixed centroid."""
        cluster_id = str(uuid4())

        await self._require_pool().execute(
            """
            INSERT INTO problem_clusters (cluster_id, centroid, label, domain, created_at)
            VALUES ($1, $2::vector, $3, $4, NOW())
            """,
            cluster_id,
            _embedding_to_str(centroid),
            label[:200] if label else None,  # Truncate long labels
            domain,
        )

        self.logger.info(
            "cluster_created",
            cluster_id=cluster_id,
            label=label[:50] if label else None,
        )

        return cluster_id

    async def _get_aku_situation_embedding(
        self, aku_id: str
    ) -> Optional[list[float]]:
        """Fetch AKU's situation embedding."""
        try:
            result = await self._require_pool().fetchrow(
                """
                SELECT situation_embedding FROM akus WHERE aku_id = $1
                """,
                aku_id,
            )
            return result["situation_embedding"] if result else None
        except Exception as e:
            self.logger.warning("fetch_embedding_failed", error=str(e))
            return None

    async def _increment_cluster_counter(
        self, cluster_id: str, counter: str
    ) -> None:
        """Increment cluster success/failure counter AND turn_count.

        turn_count tracks total guided turns for this cluster (denominator).
        success_count/failure_count track outcomes (numerator).
        """
        try:
            # Always increment turn_count along with the specific counter
            await self._require_pool().execute(
                f"""
                UPDATE problem_clusters
                SET {counter} = {counter} + 1,
                    turn_count = turn_count + 1,
                    updated_at = NOW()
                WHERE cluster_id = $1
                """,
                cluster_id,
            )
        except Exception as e:
            self.logger.warning(
                "cluster_counter_failed",
                cluster_id=cluster_id,
                counter=counter,
                error=str(e),
            )

    async def _store_turn(
        self, turn: dict, session_id: str, cluster_id: Optional[str]
    ) -> None:
        """Update turn with analysis results (SESSION creates the row)."""
        # Extract UUIDs from AKU dicts (SESSION sends full objects)
        akus_helped = _extract_aku_ids(turn.get("bullets_helped", []))
        akus_harmed = _extract_aku_ids(turn.get("bullets_harmed", []))

        try:
            await self._require_pool().execute(
                """
                UPDATE session_turns
                SET sub_task = $3,
                    micro_outcome = $4,
                    akus_helped = $5,
                    akus_harmed = $6,
                    cluster_id = $7
                WHERE session_id = $1 AND turn_number = $2
                """,
                session_id,
                turn.get("turn_number", 0),
                turn.get("sub_task"),
                turn.get("micro_outcome"),
                akus_helped,
                akus_harmed,
                cluster_id,
            )
        except Exception as e:
            self.logger.warning("turn_store_failed", error=str(e))

    async def _upsert_edge(
        self, cluster_id: str, aku_id: str, edge_type: str
    ) -> None:
        """Create or strengthen edge.

        Note: target_type='aku' (v4 schema, was 'solution' or 'bullet').
        """
        try:
            await self._require_pool().execute(
                """
                INSERT INTO knowledge_edges (
                    source_type, source_id, target_type, target_id,
                    edge_type, weight, evidence_count
                )
                VALUES ('cluster', $1, 'aku', $2, $3, 1.0, 1)
                ON CONFLICT (source_type, source_id, target_type, target_id, edge_type) DO UPDATE SET
                    evidence_count = knowledge_edges.evidence_count + 1,
                    weight = 1.0 - (1.0 / (knowledge_edges.evidence_count + 2)),
                    updated_at = NOW()
                """,
                cluster_id,
                aku_id,
                edge_type,
            )
        except Exception as e:
            self.logger.warning(
                "edge_upsert_failed",
                cluster_id=cluster_id,
                aku_id=aku_id,
                edge_type=edge_type,
                error=str(e),
            )

    async def _maybe_promote_aku(self, aku_id: str) -> None:
        """Promote candidate → active if proven useful."""
        try:
            result = await self._require_pool().execute(
                """
                UPDATE akus
                SET status = 'active'
                WHERE aku_id = $1
                  AND status = 'candidate'
                  AND helpful_count >= $2
                """,
                aku_id,
                PROMOTE_HELPFUL_COUNT,
            )
            if result and "UPDATE 1" in result:
                self.logger.info("aku_promoted", aku_id=aku_id)
        except Exception as e:
            self.logger.warning("promotion_failed", aku_id=aku_id, error=str(e))

    async def _maybe_archive_aku(self, aku_id: str) -> None:
        """Archive AKU if consistently harmful.

        v4 Simplified: Removed last_validated_at check (column no longer exists).
        Uses evidence_count as proxy for age instead.
        """
        try:
            result = await self._require_pool().execute(
                """
                UPDATE akus
                SET status = 'archived'
                WHERE aku_id = $1
                  AND status = 'active'
                  AND harmful_count > helpful_count * $2
                  AND evidence_count >= 5
                """,
                aku_id,
                ARCHIVE_HARMFUL_RATIO,
            )
            if result and "UPDATE 1" in result:
                self.logger.info("aku_archived", aku_id=aku_id)
        except Exception as e:
            self.logger.warning("archive_failed", aku_id=aku_id, error=str(e))

    async def _create_semantic_bridge(
        self,
        initial_situation: str,
        initial_embedding: list,
        domain: Optional[str],
        bullets_helped: list[str],  # Still named bullets_helped in event payload
        bullets_harmed: list[str],  # Still named bullets_harmed in event payload
    ) -> None:
        """Create cluster for ADVISOR's initial framing with edges to helpful/harmful AKUs.

        This builds semantic bridges so future queries framed like the initial_situation
        will find AKUs that helped or learn to avoid AKUs that harmed.
        """
        # Find or create cluster for ADVISOR's initial understanding
        cluster_id = await self._find_or_create_bridge_cluster(
            situation=initial_situation,
            embedding=initial_embedding,
            domain=domain,
        )

        if not cluster_id:
            return

        # Create solved_by edges for helpful AKUs
        solved_by_count = 0
        for aku_id in bullets_helped:
            await self._upsert_edge(cluster_id, aku_id, "solved_by")
            solved_by_count += 1

        # Create caused_failure edges for harmful AKUs
        caused_failure_count = 0
        for aku_id in bullets_harmed:
            await self._upsert_edge(cluster_id, aku_id, "caused_failure")
            caused_failure_count += 1

        self.logger.info(
            "semantic_bridge_created",
            cluster_id=cluster_id,
            situation=initial_situation[:50],
            solved_by_count=solved_by_count,
            caused_failure_count=caused_failure_count,
        )

    async def _find_or_create_bridge_cluster(
        self,
        situation: str,
        embedding: list,
        domain: Optional[str],
    ) -> Optional[str]:
        """Find existing cluster or create new one for ADVISOR's situation.

        Uses higher threshold (0.80) than normal clustering to avoid merging
        similar but distinct problem framings.
        """
        try:
            emb_str = _embedding_to_str(embedding)

            # Try to find existing cluster with high similarity
            pool = self._require_pool()
            result = await pool.fetchrow(
                """
                SELECT cluster_id FROM problem_clusters
                WHERE 1 - (centroid <=> $1::vector) > $2
                ORDER BY 1 - (centroid <=> $1::vector) DESC
                LIMIT 1
                """,
                emb_str,
                BRIDGE_CLUSTER_THRESHOLD,
            )

            if result:
                return str(result["cluster_id"])

            # Create new cluster for this initial framing
            cluster_id = str(uuid4())
            await pool.execute(
                """
                INSERT INTO problem_clusters (cluster_id, centroid, label, domain)
                VALUES ($1, $2::vector, $3, $4)
                """,
                cluster_id,
                emb_str,
                situation[:200],
                domain,
            )

            self.logger.info(
                "bridge_cluster_created",
                cluster_id=cluster_id,
                label=situation[:50],
            )

            return cluster_id
        except Exception as e:
            self.logger.warning("bridge_cluster_failed", error=str(e))
            return None
