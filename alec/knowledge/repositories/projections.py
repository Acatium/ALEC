"""Projection repository — SQL queries for coordinator projections."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import (
    AlignmentOpp,
    Contradiction,
    ConvergenceConfig,
    ConvergenceMetrics,
    CoordinatorProjection,
    Gap,
    RankedIssue,
)

logger = structlog.get_logger()


class ProjectionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def build_projection(
        self,
        engagement_id: UUID,
        coordinator_id: UUID,
        last_cycle_at: datetime,
    ) -> CoordinatorProjection:
        """Build full coordinator projection from SQL queries. No LLM calls."""
        async with self._pool.acquire() as conn:
            coverage = await self._build_coverage_dashboard(conn, engagement_id)
            trust_section = await self._build_source_trust_section(conn, engagement_id)
            annotations_section = await self._build_annotations_section(conn, engagement_id)
            questions_section = await self._build_questions_section(conn, engagement_id)
            schema_section = await self._build_schema_section(conn, engagement_id)
            community_summary = await self._get_latest_community_summary(conn, engagement_id)

            # Append trust/annotations/questions/schema to coverage dashboard
            extra_sections = "\n".join(
                s for s in [
                    trust_section, annotations_section,
                    questions_section, schema_section,
                    community_summary,
                ] if s
            )
            if extra_sections:
                coverage = coverage + "\n\n" + extra_sections

            return CoordinatorProjection(
                problem_statement=await self._get_problem_statement(conn, engagement_id),
                coverage_dashboard=coverage,
                active_gaps=await self._find_gaps(conn, engagement_id),
                contradictions=await self._find_contradictions(conn, engagement_id),
                alignment_opportunities=await self._find_alignment_opportunities(
                    conn, engagement_id
                ),
                recent_findings=await self._summarize_recent_findings(
                    conn, engagement_id, last_cycle_at
                ),
                recent_decisions=await self._get_recent_decisions(conn, engagement_id, limit=10),
                model_summary=await self._build_model_summary(conn, engagement_id),
                community_summary=community_summary,
            )

    async def check_convergence(
        self,
        engagement_id: UUID,
        cycle_number: int,
        config: ConvergenceConfig,
    ) -> tuple[bool, ConvergenceMetrics]:
        """Check convergence using multi-signal metrics.

        Returns (converged, ConvergenceMetrics).
        """
        import math

        async with self._pool.acquire() as conn:
            # ── Raw counts (same window as before) ──────────────
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE metadata->>'impact_type' = 'reinforcement'
                    ) AS reinforcement_count,
                    COUNT(*) FILTER (
                        WHERE metadata->>'impact_type' = 'expansion'
                    ) AS expansion_count,
                    COUNT(*) FILTER (
                        WHERE metadata->>'impact_type' = 'challenge'
                        AND COALESCE(metadata->>'expected_contradiction', '') != 'true'
                    ) AS challenge_count
                FROM observations
                WHERE engagement_id = $1
                  AND created_at >= (
                      SELECT COALESCE(MAX(created_at), '1970-01-01')
                      FROM convergence_log
                      WHERE engagement_id = $1
                  )
                """,
                engagement_id,
            )

            r = stats["reinforcement_count"]
            e = stats["expansion_count"]
            c = stats["challenge_count"]
            raw_ratio = r / (e + c + 1)

            # ── Weighted reinforcement (anti-gaming cap + novelty decay) ──
            max_cap = config.max_reinforcement_per_entity_per_cycle
            weighted_rows = await conn.fetch(
                """
                WITH reinforcement_obs AS (
                    SELECT metadata->>'entity_name' AS entity_name,
                           COUNT(*) AS cnt
                    FROM observations
                    WHERE engagement_id = $1
                      AND metadata->>'impact_type' = 'reinforcement'
                      AND metadata->>'entity_name' IS NOT NULL
                      AND created_at >= (
                          SELECT COALESCE(MAX(created_at), '1970-01-01')
                          FROM convergence_log
                          WHERE engagement_id = $1
                      )
                    GROUP BY metadata->>'entity_name'
                )
                SELECT ro.entity_name, ro.cnt,
                       COALESCE(ent.observation_count, 1) AS total_obs
                FROM reinforcement_obs ro
                LEFT JOIN LATERAL (
                    SELECT observation_count FROM entities
                    WHERE engagement_id = $1
                      AND name = ro.entity_name
                      AND status = 'active'
                    LIMIT 1
                ) ent ON TRUE
                """,
                engagement_id,
            )

            weighted_r = 0.0
            for row in weighted_rows:
                capped = min(row["cnt"], max_cap)
                if config.novelty_decay:
                    obs = row["total_obs"] or 1
                    # Decay: more observations = less weight per reinforcement
                    decay = 1.0 / (math.log(obs + 2) * 1.4427)
                    weighted_r += capped * decay
                else:
                    weighted_r += capped

            # Fallback: if no entity_name metadata, use raw count
            if not weighted_rows and r > 0:
                weighted_r = float(min(r, max_cap))

            weighted_ratio = weighted_r / (e + c + 1)

            # ── Per-source ratios ─────────────────────────────
            source_rows = await conn.fetch(
                """
                SELECT source_ref,
                    COUNT(*) FILTER (
                        WHERE metadata->>'impact_type' = 'reinforcement'
                    ) AS src_r,
                    COUNT(*) FILTER (
                        WHERE metadata->>'impact_type' = 'expansion'
                    ) AS src_e
                FROM observations
                WHERE engagement_id = $1
                  AND created_at >= (
                      SELECT COALESCE(MAX(created_at), '1970-01-01')
                      FROM convergence_log
                      WHERE engagement_id = $1
                  )
                GROUP BY source_ref
                """,
                engagement_id,
            )
            per_source_ratios = {
                row["source_ref"]: row["src_r"] / (row["src_e"] + 1)
                for row in source_rows
            }

            # ── Expansion acceleration ────────────────────────
            prev_row = await conn.fetchrow(
                """
                SELECT expansion_rate FROM convergence_log
                WHERE engagement_id = $1
                ORDER BY cycle_number DESC LIMIT 1
                """,
                engagement_id,
            )
            prev_expansion = (
                prev_row["expansion_rate"]
                if prev_row and prev_row["expansion_rate"] is not None
                else e
            )
            expansion_acceleration = float(e - prev_expansion)

            # ── Log this cycle ────────────────────────────────
            await conn.execute(
                """
                INSERT INTO convergence_log
                    (engagement_id, cycle_number, reinforcement_count,
                     expansion_count, challenge_count, ratio,
                     weighted_ratio, expansion_rate, expansion_acceleration,
                     per_source_ratios, secondary_convergence)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, FALSE)
                """,
                engagement_id,
                cycle_number,
                r,
                e,
                c,
                raw_ratio,
                weighted_ratio,
                e,
                expansion_acceleration,
                json.dumps(per_source_ratios),
            )

            # ── Primary convergence: weighted_ratio above threshold ──
            recent = await conn.fetch(
                """
                SELECT weighted_ratio, expansion_acceleration
                FROM convergence_log
                WHERE engagement_id = $1
                ORDER BY cycle_number DESC
                LIMIT $2
                """,
                engagement_id,
                config.consecutive_cycles_required,
            )

            primary_converged = False
            if len(recent) >= config.consecutive_cycles_required:
                primary_converged = all(
                    (row["weighted_ratio"] or 0.0) >= config.convergence_threshold
                    for row in recent
                )

            # ── Secondary convergence: expansion decelerating ──
            secondary_converged = False
            decel_rows = await conn.fetch(
                """
                SELECT expansion_acceleration, weighted_ratio
                FROM convergence_log
                WHERE engagement_id = $1
                ORDER BY cycle_number DESC
                LIMIT $2
                """,
                engagement_id,
                config.expansion_deceleration_cycles,
            )
            if len(decel_rows) >= config.expansion_deceleration_cycles:
                all_decelerating = all(
                    (row["expansion_acceleration"] or 0.0) < 0
                    for row in decel_rows
                )
                all_above_min = all(
                    (row["weighted_ratio"] or 0.0) >= 1.0
                    for row in decel_rows
                )
                secondary_converged = all_decelerating and all_above_min

            # Update secondary_convergence flag for this cycle
            if secondary_converged:
                await conn.execute(
                    """
                    UPDATE convergence_log
                    SET secondary_convergence = TRUE
                    WHERE engagement_id = $1 AND cycle_number = $2
                    """,
                    engagement_id,
                    cycle_number,
                )

            metrics = ConvergenceMetrics(
                raw_ratio=raw_ratio,
                weighted_ratio=weighted_ratio,
                expansion_rate=e,
                expansion_acceleration=expansion_acceleration,
                per_source_ratios=per_source_ratios,
                primary_converged=primary_converged,
                secondary_converged=secondary_converged,
            )

            converged = primary_converged or secondary_converged
            return converged, metrics

    async def get_verified_sources(self, engagement_id: UUID) -> list[dict[str, Any]]:
        """Get verified source configs for the engagement."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT source_id, source_type, config, worker_profile
                FROM source_configs
                WHERE engagement_id = $1 AND status = 'verified'
                """,
                engagement_id,
            )
        return [
            {
                "source_id": str(r["source_id"]),
                "source_type": r["source_type"],
                "config": json.loads(r["config"]) if r["config"] else {},
                "worker_profile": (json.loads(r["worker_profile"]) if r["worker_profile"] else {}),
            }
            for r in rows
        ]

    # ── Research workspace projection sections ─────────────────────

    @staticmethod
    async def _build_source_trust_section(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> str:
        rows = await conn.fetch(
            """
            SELECT trust_tier,
                   array_agg(
                       source_type || ':' || COALESCE(
                           config->>'base_path', config->>'seed_url', ''
                       )
                   ) AS sources
            FROM source_configs
            WHERE engagement_id = $1 AND status IN ('verified', 'pending')
            GROUP BY trust_tier
            ORDER BY trust_tier
            """,
            engagement_id,
        )
        if not rows:
            return ""
        lines = ["## Source Trust Tiers"]
        for r in rows:
            source_list = ", ".join(r["sources"][:10])
            lines.append(f"  {r['trust_tier']}: {source_list}")
        return "\n".join(lines)

    @staticmethod
    async def _build_annotations_section(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> str:
        rows = await conn.fetch(
            """
            SELECT ua.annotation_type, ua.content, e.name AS entity_name
            FROM user_annotations ua
            JOIN entities e ON ua.entity_id = e.entity_id
            WHERE ua.engagement_id = $1
            ORDER BY ua.created_at DESC
            LIMIT 20
            """,
            engagement_id,
        )
        if not rows:
            return ""
        lines = ["## User Annotations"]
        for r in rows:
            content = f": {r['content']}" if r["content"] else ""
            lines.append(f"  [{r['entity_name']}] {r['annotation_type']}{content}")
        return "\n".join(lines)

    @staticmethod
    async def _build_questions_section(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> str:
        rows = await conn.fetch(
            """
            SELECT question_text FROM questions
            WHERE engagement_id = $1 AND status = 'open'
            ORDER BY created_at ASC
            LIMIT 10
            """,
            engagement_id,
        )
        if not rows:
            return ""
        lines = ["## Open Questions (user-submitted)"]
        for i, r in enumerate(rows, 1):
            lines.append(f"  {i}. {r['question_text']}")
        return "\n".join(lines)

    @staticmethod
    async def _build_schema_section(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> str:
        """Show defined schema types with usage counts."""
        rows = await conn.fetch(
            """
            SELECT es.kind, es.name, es.description,
                   COALESCE(usage.cnt, 0) AS usage_count
            FROM engagement_schema es
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt
                FROM entities e
                WHERE e.engagement_id = es.engagement_id
                  AND e.entity_type = es.name
                  AND e.status = 'active'
                  AND es.kind = 'entity_type'
            ) usage ON TRUE
            WHERE es.engagement_id = $1 AND es.is_active = TRUE
            ORDER BY es.kind, usage.cnt DESC, es.name
            """,
            engagement_id,
        )
        if not rows:
            return ""
        lines = ["## Engagement Schema"]
        entity_lines = []
        rel_lines = []
        for r in rows:
            entry = f"  {r['name']}"
            if r["kind"] == "entity_type":
                entry += f" ({r['usage_count']} entities)"
                if r["usage_count"] == 0:
                    entry += " [UNUSED]"
                entity_lines.append(entry)
            else:
                rel_lines.append(entry)
        if entity_lines:
            lines.append("Entity types:")
            lines.extend(entity_lines)
        if rel_lines:
            lines.append("Relationship types:")
            lines.extend(rel_lines)
        return "\n".join(lines)

    @staticmethod
    async def _get_latest_community_summary(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> str:
        """Get the latest community analysis summary for the projection."""
        row = await conn.fetchrow(
            """
            SELECT community_count, entity_count, modularity,
                   communities, hub_entities, bridge_entities, isolated_entities
            FROM community_analysis
            WHERE engagement_id = $1
            ORDER BY cycle_number DESC
            LIMIT 1
            """,
            engagement_id,
        )
        if not row:
            return ""

        communities = json.loads(row["communities"]) if isinstance(
            row["communities"], str
        ) else row["communities"]
        hubs = json.loads(row["hub_entities"]) if isinstance(
            row["hub_entities"], str
        ) else (row["hub_entities"] or [])
        bridges = json.loads(row["bridge_entities"]) if isinstance(
            row["bridge_entities"], str
        ) else (row["bridge_entities"] or [])
        isolated = json.loads(row["isolated_entities"]) if isinstance(
            row["isolated_entities"], str
        ) else (row["isolated_entities"] or [])

        lines = ["## Community Structure"]
        lines.append(
            f"  {row['community_count']} communities detected "
            f"across {row['entity_count']} entities"
        )
        if row["modularity"] is not None:
            lines.append(f"  Modularity: {row['modularity']:.3f}")
        for idx, members in sorted(communities.items(), key=lambda x: int(x[0])):
            preview = ", ".join(members[:5])
            suffix = f" (+{len(members) - 5} more)" if len(members) > 5 else ""
            lines.append(f"  Cluster {idx}: {preview}{suffix}")
        if hubs:
            lines.append(f"  Hubs: {', '.join(hubs[:10])}")
        if bridges:
            lines.append(f"  Bridges: {', '.join(bridges[:10])}")
        if isolated:
            lines.append(
                f"  Isolated ({len(isolated)}): {', '.join(isolated[:5])}"
            )
        return "\n".join(lines)

    # ── Private query methods ─────────────────────────────────────

    @staticmethod
    async def _get_problem_statement(conn: asyncpg.Connection, engagement_id: UUID) -> str:
        row = await conn.fetchrow(
            "SELECT problem_statement FROM engagements WHERE engagement_id = $1",
            engagement_id,
        )
        return row["problem_statement"] if row else ""

    @staticmethod
    async def _build_coverage_dashboard(conn: asyncpg.Connection, engagement_id: UUID) -> str:
        row = await conn.fetchrow(
            """
            WITH entity_stats AS (
                SELECT
                    e.entity_type,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE e.observation_count >= 3) AS well_explored,
                    COUNT(*) FILTER (WHERE e.observation_count = 1) AS referenced_only,
                    COUNT(*) FILTER (WHERE e.observation_count = 0) AS orphaned
                FROM entities e
                WHERE e.engagement_id = $1 AND e.status = 'active'
                GROUP BY e.entity_type
            ),
            relationship_stats AS (
                SELECT COUNT(*) AS total_rels,
                       COUNT(DISTINCT relationship_type) AS rel_types
                FROM relationships
                WHERE engagement_id = $1
            ),
            model_stats AS (
                SELECT COUNT(*) AS total_models,
                       COUNT(*) FILTER (WHERE model_type = 'discovered') AS discovered,
                       COUNT(*) FILTER (WHERE model_type = 'proposed') AS proposed
                FROM models
                WHERE engagement_id = $1
            ),
            alignment_stats AS (
                SELECT alignment_type, COUNT(*) AS cnt
                FROM alignments
                WHERE engagement_id = $1
                GROUP BY alignment_type
            ),
            task_stats AS (
                SELECT status, COUNT(*) AS cnt
                FROM tasks
                WHERE engagement_id = $1
                GROUP BY status
            )
            SELECT json_build_object(
                'entities', (
                    SELECT COALESCE(json_agg(row_to_json(entity_stats)), '[]')
                    FROM entity_stats
                ),
                'relationships', (
                    SELECT row_to_json(relationship_stats)
                    FROM relationship_stats
                ),
                'models', (
                    SELECT row_to_json(model_stats) FROM model_stats
                ),
                'alignments', (
                    SELECT COALESCE(json_agg(row_to_json(alignment_stats)), '[]')
                    FROM alignment_stats
                ),
                'tasks', (
                    SELECT COALESCE(json_agg(row_to_json(task_stats)), '[]')
                    FROM task_stats
                )
            ) AS dashboard
            """,
            engagement_id,
        )
        if not row or not row["dashboard"]:
            return "## Coverage Dashboard\n  No data yet."

        dashboard = row["dashboard"]
        raw = json.loads(dashboard) if isinstance(dashboard, str) else dashboard
        return _format_coverage_dashboard(raw)

    @staticmethod
    async def _find_gaps(conn: asyncpg.Connection, engagement_id: UUID) -> list[Gap]:
        rows = await conn.fetch(
            """
            WITH referenced_unexplored AS (
                SELECT
                    e.entity_id, e.name, e.entity_type, e.model_id,
                    m.name AS model_name, e.observation_count,
                    COUNT(r.relationship_id) AS reference_count,
                    'unexplored_entity' AS gap_type
                FROM entities e
                JOIN relationships r ON (r.from_entity = e.entity_id OR r.to_entity = e.entity_id)
                LEFT JOIN models m ON e.model_id = m.model_id
                WHERE e.engagement_id = $1
                  AND e.status = 'active'
                  AND e.observation_count <= 1
                GROUP BY e.entity_id, e.name, e.entity_type, e.model_id, m.name, e.observation_count
            ),
            unaligned_models AS (
                SELECT
                    m.model_id AS entity_id, m.name,
                    'model' AS entity_type, m.model_id,
                    m.name AS model_name, 0 AS observation_count,
                    (SELECT COUNT(*) FROM entities WHERE model_id = m.model_id) AS reference_count,
                    'unaligned_model' AS gap_type
                FROM models m
                WHERE m.engagement_id = $1
                  AND NOT EXISTS (
                      SELECT 1 FROM alignments a
                      JOIN entities e1 ON a.from_entity = e1.entity_id
                      JOIN entities e2 ON a.to_entity = e2.entity_id
                      WHERE (e1.model_id = m.model_id OR e2.model_id = m.model_id)
                  )
            ),
            unsurveyed_sources AS (
                SELECT
                    sc.source_id AS entity_id,
                    sc.source_type || ':' || COALESCE(
                        sc.config->>'base_path', sc.config->>'base_url', ''
                    ) AS name,
                    'source' AS entity_type,
                    NULL::UUID AS model_id,
                    NULL AS model_name,
                    0 AS observation_count,
                    0 AS reference_count,
                    'unsurveyed_source' AS gap_type
                FROM source_configs sc
                WHERE sc.engagement_id = $1
                  AND sc.status = 'verified'
                  AND NOT EXISTS (
                      SELECT 1 FROM tasks t
                      WHERE t.engagement_id = $1
                        AND t.source_type = sc.source_type
                        AND t.status = 'completed'
                  )
            )
            SELECT * FROM (
                SELECT * FROM referenced_unexplored
                UNION ALL SELECT * FROM unaligned_models
                UNION ALL SELECT * FROM unsurveyed_sources
            ) combined
            ORDER BY reference_count DESC, gap_type
            LIMIT 20
            """,
            engagement_id,
        )
        gaps = [
            Gap(
                entity_id=r["entity_id"],
                name=r["name"],
                entity_type=r["entity_type"],
                model_id=r["model_id"],
                model_name=r["model_name"],
                observation_count=r["observation_count"],
                reference_count=r["reference_count"],
                gap_type=r["gap_type"],
            )
            for r in rows
        ]

        # Add unused schema entity types as gaps
        schema_gap_rows = await conn.fetch(
            """
            SELECT es.name AS type_name
            FROM engagement_schema es
            WHERE es.engagement_id = $1
              AND es.kind = 'entity_type'
              AND es.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM entities e
                  WHERE e.engagement_id = $1
                    AND e.entity_type = es.name
                    AND e.status = 'active'
              )
            """,
            engagement_id,
        )
        from uuid import uuid4
        for r in schema_gap_rows:
            gaps.append(
                Gap(
                    entity_id=uuid4(),
                    name=f"No {r['type_name']} entities discovered",
                    entity_type=r["type_name"],
                    model_id=None,
                    model_name=None,
                    observation_count=0,
                    reference_count=0,
                    gap_type="unused_schema_type",
                )
            )

        return gaps

    @staticmethod
    async def _find_contradictions(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> list[Contradiction]:
        rows = await conn.fetch(
            """
            WITH conflicting_relationships AS (
                SELECT
                    r1.from_entity, e1.name AS from_name,
                    r1.to_entity, e2.name AS to_name,
                    r1.relationship_type AS type_a,
                    r2.relationship_type AS type_b,
                    r1.evidence AS evidence_a,
                    r2.evidence AS evidence_b,
                    r1.confidence AS confidence_a,
                    r2.confidence AS confidence_b,
                    'conflicting_relationship' AS contradiction_type
                FROM relationships r1
                JOIN relationships r2 ON r1.from_entity = r2.from_entity
                                      AND r1.to_entity = r2.to_entity
                                      AND r1.relationship_id < r2.relationship_id
                JOIN entities e1 ON r1.from_entity = e1.entity_id
                JOIN entities e2 ON r1.to_entity = e2.entity_id
                WHERE r1.engagement_id = $1
                  AND (r1.relationship_type, r2.relationship_type) IN (
                      ('calls', 'reads_from'),
                      ('depends_on', 'governs'),
                      ('supersedes', 'depends_on')
                  )
            ),
            explicit_contradictions AS (
                SELECT
                    a.from_entity, e1.name AS from_name,
                    a.to_entity, e2.name AS to_name,
                    'model:' || COALESCE(m1.name, '?') AS type_a,
                    'model:' || COALESCE(m2.name, '?') AS type_b,
                    a.evidence AS evidence_a,
                    a.evidence AS evidence_b,
                    a.confidence AS confidence_a,
                    a.confidence AS confidence_b,
                    'cross_model_contradiction' AS contradiction_type
                FROM alignments a
                JOIN entities e1 ON a.from_entity = e1.entity_id
                JOIN entities e2 ON a.to_entity = e2.entity_id
                LEFT JOIN models m1 ON e1.model_id = m1.model_id
                LEFT JOIN models m2 ON e2.model_id = m2.model_id
                WHERE a.engagement_id = $1
                  AND a.alignment_type = 'contradicts'
            )
            SELECT * FROM (
                SELECT * FROM conflicting_relationships
                UNION ALL SELECT * FROM explicit_contradictions
            ) combined
            ORDER BY LEAST(confidence_a, confidence_b) DESC
            LIMIT 15
            """,
            engagement_id,
        )
        return [
            Contradiction(
                from_entity=r["from_entity"],
                from_name=r["from_name"],
                to_entity=r["to_entity"],
                to_name=r["to_name"],
                type_a=r["type_a"],
                type_b=r["type_b"],
                evidence_a=list(r["evidence_a"]) if r["evidence_a"] else [],
                evidence_b=list(r["evidence_b"]) if r["evidence_b"] else [],
                confidence_a=r["confidence_a"],
                confidence_b=r["confidence_b"],
                contradiction_type=r["contradiction_type"],
            )
            for r in rows
        ]

    @staticmethod
    async def _find_alignment_opportunities(
        conn: asyncpg.Connection, engagement_id: UUID
    ) -> list[AlignmentOpp]:
        rows = await conn.fetch(
            """
            WITH cross_model_pairs AS (
                SELECT
                    e1.entity_id AS entity_a_id,
                    e1.name AS entity_a_name,
                    e1.entity_type AS entity_a_type,
                    m1.name AS model_a_name,
                    m1.purpose AS model_a_purpose,
                    e2.entity_id AS entity_b_id,
                    e2.name AS entity_b_name,
                    e2.entity_type AS entity_b_type,
                    m2.name AS model_b_name,
                    m2.purpose AS model_b_purpose,
                    1 - (e1.embedding <=> e2.embedding) AS similarity
                FROM entities e1
                JOIN entities e2 ON e1.engagement_id = e2.engagement_id
                                 AND e1.entity_id < e2.entity_id
                                 AND e1.model_id IS DISTINCT FROM e2.model_id
                JOIN models m1 ON e1.model_id = m1.model_id
                JOIN models m2 ON e2.model_id = m2.model_id
                WHERE e1.engagement_id = $1
                  AND e1.status = 'active'
                  AND e2.status = 'active'
                  AND e1.embedding IS NOT NULL
                  AND e2.embedding IS NOT NULL
                  AND 1 - (e1.embedding <=> e2.embedding) > 0.65
                  AND NOT EXISTS (
                      SELECT 1 FROM alignments a
                      WHERE (a.from_entity = e1.entity_id AND a.to_entity = e2.entity_id)
                         OR (a.from_entity = e2.entity_id AND a.to_entity = e1.entity_id)
                  )
            )
            SELECT * FROM cross_model_pairs
            ORDER BY similarity DESC
            LIMIT 15
            """,
            engagement_id,
        )
        return [
            AlignmentOpp(
                entity_a_id=r["entity_a_id"],
                entity_a_name=r["entity_a_name"],
                entity_a_type=r["entity_a_type"],
                model_a_name=r["model_a_name"],
                model_a_purpose=r["model_a_purpose"],
                entity_b_id=r["entity_b_id"],
                entity_b_name=r["entity_b_name"],
                entity_b_type=r["entity_b_type"],
                model_b_name=r["model_b_name"],
                model_b_purpose=r["model_b_purpose"],
                similarity=r["similarity"],
            )
            for r in rows
        ]

    @staticmethod
    async def _summarize_recent_findings(
        conn: asyncpg.Connection,
        engagement_id: UUID,
        last_cycle_at: datetime,
    ) -> str:
        rows = await conn.fetch(
            """
            SELECT
                t.task_id, t.directive, t.source_type, t.source_ref,
                t.max_scope, t.status, t.result_summary, t.completed_at,
                (SELECT COUNT(*) FROM observations o
                 WHERE o.worker_id = t.assigned_worker
                   AND o.created_at >= $2
                ) AS observations_written
            FROM tasks t
            WHERE t.engagement_id = $1
              AND t.status IN ('completed', 'failed')
              AND t.completed_at >= $2
            ORDER BY t.completed_at DESC
            LIMIT 10
            """,
            engagement_id,
            last_cycle_at,
        )
        if not rows:
            return "No recent findings."

        lines = ["## Recent Findings"]
        for r in rows:
            summary = ""
            if r["result_summary"]:
                rs = r["result_summary"]
                s = json.loads(rs) if isinstance(rs, str) else rs
                summary = f" → {json.dumps(s)}"
            lines.append(
                f"  [{r['status']}] {r['source_type']}:{r['source_ref']} "
                f"({r['max_scope']}) - {r['observations_written']} observations{summary}"
            )
            lines.append(f"    Directive: {r['directive'][:200]}")
        return "\n".join(lines)

    @staticmethod
    async def _get_recent_decisions(
        conn: asyncpg.Connection, engagement_id: UUID, limit: int = 10
    ) -> str:
        rows = await conn.fetch(
            """
            SELECT o.raw_text, o.created_at,
                   o.metadata->>'rationale' AS rationale
            FROM observations o
            WHERE o.engagement_id = $1
              AND o.observation_type = 'decision'
            ORDER BY o.created_at DESC
            LIMIT $2
            """,
            engagement_id,
            limit,
        )
        if not rows:
            return "No recent decisions."

        lines = ["## Recent Decisions"]
        for r in rows:
            lines.append(f"  - {r['raw_text'][:300]}")
            if r["rationale"]:
                lines.append(f"    Rationale: {r['rationale'][:200]}")
        return "\n".join(lines)

    @staticmethod
    async def _build_model_summary(conn: asyncpg.Connection, engagement_id: UUID) -> str:
        rows = await conn.fetch(
            """
            SELECT m.name, m.model_type, m.purpose,
                   COUNT(e.entity_id) AS entity_count
            FROM models m
            LEFT JOIN entities e ON e.model_id = m.model_id AND e.status = 'active'
            WHERE m.engagement_id = $1
            GROUP BY m.model_id, m.name, m.model_type, m.purpose
            ORDER BY entity_count DESC
            """,
            engagement_id,
        )
        if not rows:
            return "No models defined yet."

        lines = ["## Models"]
        for r in rows:
            purpose = f" — {r['purpose']}" if r["purpose"] else ""
            lines.append(
                f"  {r['name']} ({r['model_type']}, {r['entity_count']} entities){purpose}"
            )
        return "\n".join(lines)


def _format_coverage_dashboard(raw: dict[str, Any]) -> str:
    """Format dashboard JSON into ~1000 token text block."""
    lines = ["## Coverage Dashboard"]

    entities = raw.get("entities") or []
    for row in entities:
        lines.append(
            f"  {row['entity_type']}: {row['total']} total "
            f"({row['well_explored']} explored, "
            f"{row['referenced_only']} referenced only, "
            f"{row['orphaned']} orphaned)"
        )

    r = raw.get("relationships") or {}
    if r:
        lines.append(f"  Relationships: {r.get('total_rels', 0)} ({r.get('rel_types', 0)} types)")

    m = raw.get("models") or {}
    if m:
        lines.append(
            f"  Models: {m.get('total_models', 0)} "
            f"({m.get('discovered', 0)} discovered, {m.get('proposed', 0)} proposed)"
        )

    for row in raw.get("alignments") or []:
        lines.append(f"  Alignments [{row['alignment_type']}]: {row['cnt']}")

    for row in raw.get("tasks") or []:
        lines.append(f"  Tasks [{row['status']}]: {row['cnt']}")

    return "\n".join(lines)


# ── Annotation + trust tier query helpers ─────────────────────


async def get_entity_annotations(
    pool: asyncpg.Pool, engagement_id: UUID
) -> dict[UUID, list[str]]:
    """Get annotation types grouped by entity_id."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT entity_id, array_agg(annotation_type) AS types
            FROM user_annotations
            WHERE engagement_id = $1
            GROUP BY entity_id
            """,
            engagement_id,
        )
    return {row["entity_id"]: list(row["types"]) for row in rows}


async def get_entity_trust_tiers(
    pool: asyncpg.Pool, engagement_id: UUID
) -> dict[UUID, str]:
    """Get highest trust tier per entity (via observations → source_configs).

    Trust tier precedence: authoritative > analytical > reference.
    """
    tier_rank = {"authoritative": 3, "analytical": 2, "reference": 1}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT e.entity_id, sc.trust_tier
            FROM entities e
            JOIN observations o ON o.engagement_id = e.engagement_id
                AND o.metadata->>'entity_name' = e.name
            JOIN source_configs sc ON sc.engagement_id = e.engagement_id
                AND sc.source_type || ':' || COALESCE(
                    sc.config->>'base_path', sc.config->>'seed_url', ''
                ) = o.source_ref
            WHERE e.engagement_id = $1 AND e.status = 'active'
            """,
            engagement_id,
        )

    result: dict[UUID, str] = {}
    for row in rows:
        eid = row["entity_id"]
        tier = row["trust_tier"]
        if eid not in result or tier_rank.get(tier, 0) > tier_rank.get(result[eid], 0):
            result[eid] = tier
    return result


# ── Issue ranking ─────────────────────────────────────────────

# Annotation score modifiers
_ANNOTATION_MODIFIERS: dict[str, float] = {
    "important": 25.0,
    "explore_more": 15.0,
    "dismiss": -50.0,
    "correction": 10.0,
    "note": 5.0,
}

# Trust tier multipliers
_TRUST_MULTIPLIERS: dict[str, float] = {
    "authoritative": 1.3,
    "analytical": 1.1,
    "reference": 1.0,
}


def _get_entity_id_from_issue(issue_data: Gap | Contradiction | AlignmentOpp) -> UUID | None:
    """Extract the primary entity_id from an issue for annotation/trust lookup."""
    if isinstance(issue_data, Gap):
        return issue_data.entity_id
    elif isinstance(issue_data, Contradiction):
        return issue_data.from_entity
    elif isinstance(issue_data, AlignmentOpp):
        return issue_data.entity_a_id
    return None


def rank_issues(
    gaps: list[Gap],
    contradictions: list[Contradiction],
    alignment_opps: list[AlignmentOpp],
    entity_annotations: dict[UUID, list[str]] | None = None,
    entity_trust_tiers: dict[UUID, str] | None = None,
) -> list[RankedIssue]:
    """Pure Python scoring. No LLM. Returns top issues for coordinator.

    Optionally applies annotation modifiers and trust tier multipliers.
    """
    ranked: list[RankedIssue] = []

    for gap in gaps:
        if gap.gap_type == "unsurveyed_source":
            score = 100.0
        elif gap.gap_type == "unaligned_model":
            score = 50.0 + gap.reference_count * 0.5
        elif gap.gap_type == "unused_schema_type":
            score = 40.0
        else:
            score = gap.reference_count * 2.0
        ranked.append(RankedIssue(issue_type="gap", score=score, data=gap))

    for contradiction in contradictions:
        score = 30.0 + max(contradiction.confidence_a, contradiction.confidence_b) * 20.0
        ranked.append(RankedIssue(issue_type="contradiction", score=score, data=contradiction))

    for opp in alignment_opps:
        score = 20.0 + opp.similarity * 15.0
        ranked.append(RankedIssue(issue_type="alignment_opportunity", score=score, data=opp))

    # Apply annotation modifiers and trust tier multipliers
    if entity_annotations or entity_trust_tiers:
        annotations = entity_annotations or {}
        tiers = entity_trust_tiers or {}

        for issue in ranked:
            eid = _get_entity_id_from_issue(issue.data)
            if eid is None:
                continue

            # Annotation modifiers (additive)
            if eid in annotations:
                for ann_type in annotations[eid]:
                    issue.score += _ANNOTATION_MODIFIERS.get(ann_type, 0.0)

            # Trust tier multiplier
            if eid in tiers:
                issue.score *= _TRUST_MULTIPLIERS.get(tiers[eid], 1.0)

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:8]
