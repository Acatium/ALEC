"""Post-cycle entity deduplication sweep."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import asyncpg
import structlog

from alec.db.embeddings import EmbeddingService
from alec.knowledge.merge import merge_entities
from alec.knowledge.name_similarity import name_similarity_score

logger = structlog.get_logger()


@dataclass
class DedupResult:
    """Result of a dedup sweep."""

    pairs_evaluated: int = 0
    auto_merged: int = 0
    candidates_logged: int = 0
    errors: list[str] = field(default_factory=list)


async def _merge_alias_cross_matches(
    engagement_id: UUID,
    pool: asyncpg.Pool,
    result: DedupResult,
    already_merged: set[UUID],
) -> None:
    """Auto-merge entities where one's name appears in the other's aliases.

    If entity A has entity B's name in its aliases (or vice versa), the system
    already determined they're the same thing during creation. These are
    unconditional merges — no scoring needed.
    """
    async with pool.acquire() as conn:
        pairs = await conn.fetch(
            """
            SELECT
                a.entity_id AS id_a, a.name AS name_a,
                a.observation_count AS obs_a,
                b.entity_id AS id_b, b.name AS name_b,
                b.observation_count AS obs_b
            FROM entities a
            JOIN entities b
                ON a.engagement_id = b.engagement_id
                AND a.entity_id < b.entity_id
            WHERE a.engagement_id = $1
              AND a.status = 'active'
              AND b.status = 'active'
              AND (
                  LOWER(a.name) = ANY(SELECT LOWER(unnest(b.aliases)))
                  OR LOWER(b.name) = ANY(SELECT LOWER(unnest(a.aliases)))
              )
            LIMIT 100
            """,
            engagement_id,
        )

    for pair in pairs:
        try:
            id_a: UUID = pair["id_a"]
            id_b: UUID = pair["id_b"]

            # Skip if either entity was already merged this sweep
            if id_a in already_merged or id_b in already_merged:
                continue

            obs_a: int = pair["obs_a"]
            obs_b: int = pair["obs_b"]

            if obs_a >= obs_b:
                target_id, source_id = id_a, id_b
                target_name, source_name = pair["name_a"], pair["name_b"]
            else:
                target_id, source_id = id_b, id_a
                target_name, source_name = pair["name_b"], pair["name_a"]

            async with pool.acquire() as conn:
                async with conn.transaction():
                    await merge_entities(
                        conn, engagement_id, target_id, source_id
                    )
            result.auto_merged += 1
            already_merged.add(source_id)
            result.pairs_evaluated += 1
            logger.info(
                "dedup.alias_cross_merge",
                target=target_name,
                source=source_name,
            )

        except Exception as e:
            error_msg = (
                f"Error merging alias cross-match "
                f"{pair['name_a']}/{pair['name_b']}: {e}"
            )
            logger.warning("dedup.pair_error", error=error_msg)
            result.errors.append(error_msg)
            result.pairs_evaluated += 1


async def run_dedup_sweep(
    engagement_id: UUID,
    pool: asyncpg.Pool,
    embedder: EmbeddingService,
    auto_merge_threshold: float = 0.92,
) -> DedupResult:
    """Find and resolve near-duplicate entities after a cycle.

    Phase 1 — Alias cross-match (unconditional merge):
        If entity A's name appears in entity B's aliases (or vice versa),
        auto-merge immediately. No scoring needed.

    Phase 2 — Embedding + string similarity:
        1. Self-join entities on pgvector cosine similarity >= 0.65
        2. Score each pair with both embedding similarity and string similarity
        3. Auto-merge when combined_score >= threshold
        4. Log remaining candidates as dedup_candidate observations for user review

    Returns DedupResult with counts.
    """
    result = DedupResult()
    already_merged: set[UUID] = set()

    # Phase 1: Alias cross-matches — unconditional merges
    await _merge_alias_cross_matches(
        engagement_id, pool, result, already_merged
    )

    # Phase 2: Embedding similarity pairs
    async with pool.acquire() as conn:
        pairs = await conn.fetch(
            """
            SELECT
                a.entity_id AS id_a, a.name AS name_a, a.entity_type AS type_a,
                a.aliases AS aliases_a, a.observation_count AS obs_a,
                b.entity_id AS id_b, b.name AS name_b, b.entity_type AS type_b,
                b.aliases AS aliases_b, b.observation_count AS obs_b,
                1 - (a.embedding <=> b.embedding) AS embedding_sim
            FROM entities a
            JOIN entities b
                ON a.engagement_id = b.engagement_id
                AND a.entity_id < b.entity_id
                AND a.embedding IS NOT NULL
                AND b.embedding IS NOT NULL
                AND 1 - (a.embedding <=> b.embedding) >= 0.65
            WHERE a.engagement_id = $1
              AND a.status = 'active'
              AND b.status = 'active'
            ORDER BY embedding_sim DESC
            LIMIT 200
            """,
            engagement_id,
        )

    for pair in pairs:
        try:
            id_a: UUID = pair["id_a"]
            id_b: UUID = pair["id_b"]

            # Skip if either entity was already merged this sweep
            if id_a in already_merged or id_b in already_merged:
                continue

            result.pairs_evaluated += 1
            embedding_sim: float = pair["embedding_sim"]
            aliases_a = list(pair["aliases_a"]) if pair["aliases_a"] else []
            aliases_b = list(pair["aliases_b"]) if pair["aliases_b"] else []

            # String similarity in both directions
            string_sim_a = name_similarity_score(
                pair["name_a"], aliases_a, pair["name_b"]
            )
            string_sim_b = name_similarity_score(
                pair["name_b"], aliases_b, pair["name_a"]
            )
            string_sim = max(string_sim_a, string_sim_b)

            # Combined score: weighted average favoring the better signal
            combined = max(
                0.5 * embedding_sim + 0.5 * string_sim,
                0.7 * embedding_sim + 0.3 * string_sim,
                0.3 * embedding_sim + 0.7 * string_sim,
            )

            obs_a: int = pair["obs_a"]
            obs_b: int = pair["obs_b"]

            # Auto-merge if score is high enough
            if combined >= auto_merge_threshold:
                if obs_a >= obs_b:
                    target_id, source_id = id_a, id_b
                else:
                    target_id, source_id = id_b, id_a

                async with pool.acquire() as conn:
                    async with conn.transaction():
                        await merge_entities(
                            conn, engagement_id, target_id, source_id
                        )
                result.auto_merged += 1
                already_merged.add(source_id)
                logger.info(
                    "dedup.auto_merged",
                    target=pair["name_a"] if obs_a >= obs_b else pair["name_b"],
                    source=pair["name_b"] if obs_a >= obs_b else pair["name_a"],
                    combined_score=f"{combined:.3f}",
                )
            else:
                # Log as candidate for user review
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO observations
                            (engagement_id, source_ref, raw_text,
                             observation_type, metadata)
                        VALUES ($1, 'dedup_sweep', $2, 'dedup_candidate', $3::jsonb)
                        """,
                        engagement_id,
                        (
                            f"Potential duplicate: '{pair['name_a']}' and "
                            f"'{pair['name_b']}' (score: {combined:.2f})"
                        ),
                        f'{{"entity_a": "{pair["id_a"]}", "entity_b": "{pair["id_b"]}", '
                        f'"embedding_sim": {embedding_sim:.3f}, '
                        f'"string_sim": {string_sim:.3f}, '
                        f'"combined": {combined:.3f}}}',
                    )
                result.candidates_logged += 1

        except Exception as e:
            error_msg = f"Error processing pair {pair['name_a']}/{pair['name_b']}: {e}"
            logger.warning("dedup.pair_error", error=error_msg)
            result.errors.append(error_msg)

    logger.info(
        "dedup.sweep_complete",
        pairs_evaluated=result.pairs_evaluated,
        auto_merged=result.auto_merged,
        candidates_logged=result.candidates_logged,
        errors=len(result.errors),
    )

    return result
