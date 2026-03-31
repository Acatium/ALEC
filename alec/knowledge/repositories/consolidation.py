"""Consolidation repository — trigger check, stale detection, material, storage, cross-links."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import (
    ConsolidationConfig,
    ConsolidationMaterial,
    CrossLink,
    StaleEntity,
)

logger = structlog.get_logger()


class ConsolidationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def should_consolidate(
        self,
        engagement_id: UUID,
        config: ConsolidationConfig,
    ) -> bool:
        """Check if consolidation should run based on trigger conditions.

        Triggers when:
        1. At least min_new_observations new observations since last consolidation
        2. At least min_interval_minutes since last consolidation
        3. OR max_interval_minutes exceeded (force run)
        """
        async with self._pool.acquire() as conn:
            # Find last consolidation time
            last_run = await conn.fetchval(
                """
                SELECT MAX(freshness)
                FROM consolidated_units
                WHERE engagement_id = $1
                """,
                engagement_id,
            )

            now = datetime.now(timezone.utc)

            if last_run is not None:
                elapsed_minutes = (now - last_run).total_seconds() / 60

                # Rate limit: don't run too frequently
                if elapsed_minutes < config.min_interval_minutes:
                    return False

                # Force run if max interval exceeded
                if elapsed_minutes >= config.max_interval_minutes:
                    return True

                # Check for minimum new observations
                new_obs_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM observations
                    WHERE engagement_id = $1
                      AND created_at > $2
                    """,
                    engagement_id,
                    last_run,
                )
                return bool(new_obs_count >= config.min_new_observations)
            else:
                # No prior consolidation — check if enough observations exist
                obs_count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM observations
                    WHERE engagement_id = $1
                    """,
                    engagement_id,
                )
                return bool(obs_count >= config.min_new_observations)

    async def find_stale_entities(
        self,
        engagement_id: UUID,
        max_entities: int = 30,
    ) -> list[StaleEntity]:
        """Find entities that need (re-)consolidation.

        Prioritizes:
        1. Entities with no consolidated unit (unconsolidated)
        2. Entities with new observations since last consolidation
        Requires at least 2 observations to be worth consolidating.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH entity_obs AS (
                    SELECT
                        e.entity_id,
                        e.name,
                        e.entity_type,
                        e.observation_count,
                        cu.unit_id IS NOT NULL AS has_existing_unit,
                        COALESCE(cu.freshness, '1970-01-01'::timestamptz) AS last_consolidated,
                        COUNT(o.observation_id) FILTER (
                            WHERE o.created_at > COALESCE(cu.freshness, '1970-01-01'::timestamptz)
                        ) AS new_observations
                    FROM entities e
                    LEFT JOIN consolidated_units cu
                        ON cu.subject_entity = e.entity_id
                        AND cu.status = 'current'
                    LEFT JOIN observations o
                        ON o.engagement_id = e.engagement_id
                        AND (
                            o.raw_text ILIKE '%%' || e.name || '%%'
                            OR o.metadata::text ILIKE '%%' || e.name || '%%'
                        )
                    WHERE e.engagement_id = $1
                      AND e.status = 'active'
                      AND e.observation_count >= 2
                    GROUP BY e.entity_id, e.name, e.entity_type,
                             e.observation_count, cu.unit_id, cu.freshness
                )
                SELECT *
                FROM entity_obs
                WHERE new_observations > 0 OR NOT has_existing_unit
                ORDER BY
                    has_existing_unit ASC,
                    new_observations DESC
                LIMIT $2
                """,
                engagement_id,
                max_entities,
            )

        return [
            StaleEntity(
                entity_id=r["entity_id"],
                name=r["name"],
                entity_type=r["entity_type"],
                observation_count=r["observation_count"],
                new_observations=r["new_observations"],
                has_existing_unit=r["has_existing_unit"],
            )
            for r in rows
        ]

    async def gather_material(
        self,
        engagement_id: UUID,
        entity: StaleEntity,
    ) -> ConsolidationMaterial:
        """Gather all material for one entity's consolidation."""
        async with self._pool.acquire() as conn:
            # Entity details
            entity_row = await conn.fetchrow(
                """
                SELECT name, entity_type, aliases, properties
                FROM entities
                WHERE entity_id = $1
                """,
                entity.entity_id,
            )

            # Observations referencing this entity (by name in raw_text or metadata)
            obs_rows = await conn.fetch(
                """
                SELECT observation_id, source_ref, raw_text, observation_type,
                       worker_id, metadata, created_at
                FROM observations
                WHERE engagement_id = $1
                  AND (
                      raw_text ILIKE '%%' || $2 || '%%'
                      OR metadata::text ILIKE '%%' || $2 || '%%'
                  )
                ORDER BY created_at DESC
                LIMIT 50
                """,
                engagement_id,
                entity.name,
            )

            # Outgoing relationships
            out_rows = await conn.fetch(
                """
                SELECT r.relationship_type, r.confidence,
                       e2.name AS to_name, e2.entity_type AS to_type
                FROM relationships r
                JOIN entities e2 ON r.to_entity = e2.entity_id
                WHERE r.from_entity = $1
                  AND r.engagement_id = $2
                """,
                entity.entity_id,
                engagement_id,
            )

            # Incoming relationships
            in_rows = await conn.fetch(
                """
                SELECT r.relationship_type, r.confidence,
                       e1.name AS from_name, e1.entity_type AS from_type
                FROM relationships r
                JOIN entities e1 ON r.from_entity = e1.entity_id
                WHERE r.to_entity = $1
                  AND r.engagement_id = $2
                """,
                entity.entity_id,
                engagement_id,
            )

            # Cross-model alignments
            align_rows = await conn.fetch(
                """
                SELECT
                    a.alignment_type, a.confidence,
                    CASE WHEN a.from_entity = $1 THEN e2.name ELSE e1.name END AS other_entity_name,
                    CASE WHEN a.from_entity = $1
                         THEN COALESCE(m2.name, 'unknown')
                         ELSE COALESCE(m1.name, 'unknown')
                    END AS model_name
                FROM alignments a
                JOIN entities e1 ON a.from_entity = e1.entity_id
                JOIN entities e2 ON a.to_entity = e2.entity_id
                LEFT JOIN models m1 ON e1.model_id = m1.model_id
                LEFT JOIN models m2 ON e2.model_id = m2.model_id
                WHERE (a.from_entity = $1 OR a.to_entity = $1)
                  AND a.engagement_id = $2
                """,
                entity.entity_id,
                engagement_id,
            )

        return ConsolidationMaterial(
            entity_id=entity.entity_id,
            entity_name=entity_row["name"],
            entity_type=entity_row["entity_type"],
            aliases=list(entity_row["aliases"]) if entity_row["aliases"] else [],
            properties=(json.loads(entity_row["properties"]) if entity_row["properties"] else {}),
            observations=[
                {
                    "observation_id": r["observation_id"],
                    "source_ref": r["source_ref"],
                    "raw_text": r["raw_text"],
                    "observation_type": r["observation_type"],
                    "worker_id": r["worker_id"],
                }
                for r in obs_rows
            ],
            relationships_outgoing=[
                {
                    "to_name": r["to_name"],
                    "to_type": r["to_type"],
                    "relationship_type": r["relationship_type"],
                    "confidence": float(r["confidence"]),
                }
                for r in out_rows
            ],
            relationships_incoming=[
                {
                    "from_name": r["from_name"],
                    "from_type": r["from_type"],
                    "relationship_type": r["relationship_type"],
                    "confidence": float(r["confidence"]),
                }
                for r in in_rows
            ],
            alignments=[
                {
                    "other_entity_name": r["other_entity_name"],
                    "model_name": r["model_name"],
                    "alignment_type": r["alignment_type"],
                    "confidence": float(r["confidence"]),
                }
                for r in align_rows
            ],
        )

    async def store_consolidated_unit(
        self,
        engagement_id: UUID,
        entity_id: UUID,
        summary: str,
        embedding: list[float],
        source_observation_ids: list[UUID],
        token_count: int,
        is_update: bool,
    ) -> UUID:
        """Store or replace a consolidated unit for an entity."""
        async with self._pool.acquire() as conn:
            if is_update:
                # Mark old version as stale
                old_version = await conn.fetchval(
                    """
                    UPDATE consolidated_units
                    SET status = 'stale'
                    WHERE subject_entity = $1
                      AND engagement_id = $2
                      AND status = 'current'
                    RETURNING version
                    """,
                    entity_id,
                    engagement_id,
                )
                new_version = (old_version or 0) + 1
            else:
                new_version = 1

            unit_id: UUID = await conn.fetchval(
                """
                INSERT INTO consolidated_units
                    (engagement_id, subject_entity, summary, embedding,
                     source_observations, token_count, version, status, freshness)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'current', NOW())
                RETURNING unit_id
                """,
                engagement_id,
                entity_id,
                summary,
                embedding,
                source_observation_ids,
                token_count,
                new_version,
            )

        return unit_id

    async def detect_cross_links(
        self,
        engagement_id: UUID,
        config: ConsolidationConfig,
    ) -> list[CrossLink]:
        """Detect non-obvious connections between entities.

        Two methods:
        1. Co-occurrence in observations (entities mentioned together)
        2. Embedding proximity of consolidated summaries
        """
        cross_links: list[CrossLink] = []

        async with self._pool.acquire() as conn:
            # Method 1: Co-occurrence
            cooccur_rows = await conn.fetch(
                """
                WITH entity_obs AS (
                    SELECT e.entity_id, e.name,
                           o.observation_id
                    FROM entities e
                    JOIN observations o ON o.engagement_id = e.engagement_id
                        AND (
                            o.raw_text ILIKE '%%' || e.name || '%%'
                            OR o.metadata::text ILIKE '%%' || e.name || '%%'
                        )
                    WHERE e.engagement_id = $1
                      AND e.status = 'active'
                )
                SELECT
                    eo1.entity_id AS entity_a_id,
                    eo1.name AS entity_a_name,
                    eo2.entity_id AS entity_b_id,
                    eo2.name AS entity_b_name,
                    COUNT(DISTINCT eo1.observation_id) AS co_occurrence_count
                FROM entity_obs eo1
                JOIN entity_obs eo2
                    ON eo1.observation_id = eo2.observation_id
                    AND eo1.entity_id < eo2.entity_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM relationships r
                    WHERE r.engagement_id = $1
                      AND (
                          (r.from_entity = eo1.entity_id AND r.to_entity = eo2.entity_id)
                          OR (r.from_entity = eo2.entity_id AND r.to_entity = eo1.entity_id)
                      )
                )
                AND NOT EXISTS (
                    SELECT 1 FROM alignments a
                    WHERE a.engagement_id = $1
                      AND (
                          (a.from_entity = eo1.entity_id AND a.to_entity = eo2.entity_id)
                          OR (a.from_entity = eo2.entity_id AND a.to_entity = eo1.entity_id)
                      )
                )
                GROUP BY eo1.entity_id, eo1.name, eo2.entity_id, eo2.name
                HAVING COUNT(DISTINCT eo1.observation_id) >= $2
                ORDER BY co_occurrence_count DESC
                LIMIT 20
                """,
                engagement_id,
                config.co_occurrence_threshold,
            )

            for r in cooccur_rows:
                cross_links.append(
                    CrossLink(
                        entity_a_id=r["entity_a_id"],
                        entity_a_name=r["entity_a_name"],
                        entity_b_id=r["entity_b_id"],
                        entity_b_name=r["entity_b_name"],
                        detection_method="co_occurrence",
                        strength=float(r["co_occurrence_count"]),
                        detail=(
                            f"Co-appear in {r['co_occurrence_count']} observations "
                            f"but have no explicit relationship"
                        ),
                    )
                )

            # Method 2: Embedding similarity of consolidated summaries
            embed_rows = await conn.fetch(
                """
                SELECT
                    cu1.subject_entity AS entity_a_id,
                    e1.name AS entity_a_name,
                    cu2.subject_entity AS entity_b_id,
                    e2.name AS entity_b_name,
                    1 - (cu1.embedding <=> cu2.embedding) AS similarity
                FROM consolidated_units cu1
                JOIN consolidated_units cu2
                    ON cu1.engagement_id = cu2.engagement_id
                    AND cu1.subject_entity < cu2.subject_entity
                    AND cu1.status = 'current'
                    AND cu2.status = 'current'
                JOIN entities e1 ON cu1.subject_entity = e1.entity_id
                JOIN entities e2 ON cu2.subject_entity = e2.entity_id
                WHERE cu1.engagement_id = $1
                  AND cu1.embedding IS NOT NULL
                  AND cu2.embedding IS NOT NULL
                  AND 1 - (cu1.embedding <=> cu2.embedding) > $2
                  AND NOT EXISTS (
                      SELECT 1 FROM relationships r
                      WHERE r.engagement_id = $1
                        AND (
                            (r.from_entity = cu1.subject_entity
                             AND r.to_entity = cu2.subject_entity)
                            OR (r.from_entity = cu2.subject_entity
                                AND r.to_entity = cu1.subject_entity)
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM alignments a
                      WHERE a.engagement_id = $1
                        AND (
                            (a.from_entity = cu1.subject_entity
                             AND a.to_entity = cu2.subject_entity)
                            OR (a.from_entity = cu2.subject_entity
                                AND a.to_entity = cu1.subject_entity)
                        )
                  )
                ORDER BY similarity DESC
                LIMIT 20
                """,
                engagement_id,
                config.embedding_similarity_threshold,
            )

            # Deduplicate: skip pairs already found by co-occurrence
            seen_pairs: set[tuple[UUID, UUID]] = {
                (cl.entity_a_id, cl.entity_b_id) for cl in cross_links
            }

            for r in embed_rows:
                pair = (r["entity_a_id"], r["entity_b_id"])
                if pair not in seen_pairs:
                    cross_links.append(
                        CrossLink(
                            entity_a_id=r["entity_a_id"],
                            entity_a_name=r["entity_a_name"],
                            entity_b_id=r["entity_b_id"],
                            entity_b_name=r["entity_b_name"],
                            detection_method="embedding_similarity",
                            strength=float(r["similarity"]),
                            detail=(
                                f"Consolidated summaries have "
                                f"{r['similarity']:.2f} cosine similarity"
                            ),
                        )
                    )
                    seen_pairs.add(pair)

        return cross_links

    async def record_cross_link_observations(
        self,
        engagement_id: UUID,
        cross_links: list[CrossLink],
    ) -> None:
        """Record each cross-link as an insight observation."""
        async with self._pool.acquire() as conn:
            for cl in cross_links:
                await conn.execute(
                    """
                    INSERT INTO observations
                        (engagement_id, source_ref, raw_text,
                         observation_type, worker_id, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    engagement_id,
                    "consolidation",
                    (
                        f"Cross-link detected: '{cl.entity_a_name}' and "
                        f"'{cl.entity_b_name}' {cl.detail}. "
                        f"This may indicate a hidden dependency or shared context."
                    ),
                    "insight",
                    "consolidation",
                    json.dumps(
                        {
                            "entity_a_id": str(cl.entity_a_id),
                            "entity_b_id": str(cl.entity_b_id),
                            "detection_method": cl.detection_method,
                            "strength": cl.strength,
                            "impact_type": "expansion",
                        }
                    ),
                )

        logger.info(
            "consolidation.cross_links_recorded",
            engagement_id=str(engagement_id),
            count=len(cross_links),
        )
