# ALEC v5: Core Runtime Component Specifications

**Date:** 2026-02-07
**Status:** Draft — Buildable Specs
**Parent:** [ALEC v5 Design Document](ALEC_v5_design.md) (Section 11 "Remaining ~35%", priority #1)

---

## Table of Contents

1. [Coordinator Cycle](#1-coordinator-cycle)
2. [Worker Tool-Use Loop](#2-worker-tool-use-loop)
3. [Consolidation Process](#3-consolidation-process)
4. [Component Interaction](#4-component-interaction)
5. [Community Detection](#5-community-detection)

---

## 1. Coordinator Cycle

The coordinator is a **Python state machine with one LLM call per cycle**. It reads the knowledge graph via bounded projections, detects what needs attention, and generates task directives for workers.

### 1.1 Cycle State Machine

```
                    ┌─────────────────────────────────────────┐
                    │         COORDINATOR CYCLE                │
                    │                                          │
 supervisor         │  ┌──────────┐                            │
 triggers ─────────►│  │ 1. BUILD │  SQL queries → projections │
                    │  │ PROJECTION│                           │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │  ┌────▼──────┐                            │
                    │  │ 2. DETECT │  Python: gaps, contras,   │
                    │  │ ISSUES    │  alignment opportunities   │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │  ┌────▼──────┐                            │
                    │  │ 3. CHECK  │  Python: ratio check       │
                    │  │ CONVERGENCE│  → may exit early         │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │  ┌────▼──────┐                            │
                    │  │ 4. RANK   │  Python: priority scoring  │
                    │  │ ISSUES    │                            │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │  ┌────▼──────┐                            │
                    │  │ 5. GENERATE│  ** 1 LLM call **        │
                    │  │ DIRECTIVES│  issues → task directives  │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │  ┌────▼──────┐                            │
                    │  │ 6. RECORD │  Write decisions to        │
                    │  │ DECISIONS │  observations table         │
                    │  └────┬─────┘                            │
                    │       │                                   │
                    │       ▼                                   │
                    │   CycleResult {                           │
                    │     actions: [DispatchWorker, ...],       │
                    │     convergence_signal: bool,             │
                    │     cycle_stats: {...}                    │
                    │   }                                       │
                    └─────────────────────────────────────────┘
```

### 1.2 Step 1: Build Projection

The projection is the coordinator's bounded view of the knowledge graph. It's regenerated fresh each cycle — no accumulation across cycles.

**Token budget:** ~10k tokens total for the projection. Each sub-projection has a hard cap.

```python
@dataclass
class CoordinatorProjection:
    """Bounded view of the knowledge graph for one coordinator cycle."""
    problem_statement: str          # ~500 tokens (pinned)
    coverage_dashboard: str         # ~1,000 tokens
    active_gaps: list[Gap]          # ~2,000 tokens (top 20)
    contradictions: list[Contradiction]  # ~1,000 tokens
    alignment_opportunities: list[AlignmentOpp]  # ~1,500 tokens
    recent_findings: str            # ~2,000 tokens (last cycle's workers)
    recent_decisions: str           # ~1,500 tokens (last 10 decisions)
    model_summary: str              # ~500 tokens (models + entity counts)

async def build_projection(
    engagement_id: UUID,
    coordinator_id: UUID,
    last_cycle_at: datetime,
    pool: asyncpg.Pool,
) -> CoordinatorProjection:
    """All SQL, no LLM calls."""
    async with pool.acquire() as conn:
        return CoordinatorProjection(
            problem_statement=await _get_problem_statement(conn, engagement_id),
            coverage_dashboard=await _build_coverage_dashboard(conn, engagement_id),
            active_gaps=await _find_gaps(conn, engagement_id),
            contradictions=await _find_contradictions(conn, engagement_id),
            alignment_opportunities=await _find_alignment_opportunities(conn, engagement_id),
            recent_findings=await _summarize_recent_findings(conn, engagement_id, last_cycle_at),
            recent_decisions=await _get_recent_decisions(conn, engagement_id, limit=10),
            model_summary=await _build_model_summary(conn, engagement_id),
        )
```

#### Coverage Dashboard Query

```sql
-- _build_coverage_dashboard()
-- Shows what's been explored vs what's only been referenced

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
    SELECT
        alignment_type,
        COUNT(*) AS cnt
    FROM alignments
    WHERE engagement_id = $1
    GROUP BY alignment_type
),
task_stats AS (
    SELECT
        status,
        COUNT(*) AS cnt
    FROM tasks
    WHERE engagement_id = $1
    GROUP BY status
)
SELECT
    json_build_object(
        'entities', (SELECT json_agg(row_to_json(entity_stats)) FROM entity_stats),
        'relationships', (SELECT row_to_json(relationship_stats) FROM relationship_stats),
        'models', (SELECT row_to_json(model_stats) FROM model_stats),
        'alignments', (SELECT json_agg(row_to_json(alignment_stats)) FROM alignment_stats),
        'tasks', (SELECT json_agg(row_to_json(task_stats)) FROM task_stats)
    ) AS dashboard;
```

**Python formatting:** The raw JSON gets formatted into a compact text summary:

```python
def format_coverage_dashboard(raw: dict) -> str:
    """Format dashboard JSON into ~1000 token text block."""
    lines = ["## Coverage Dashboard"]
    for row in raw["entities"]:
        lines.append(
            f"  {row['entity_type']}: {row['total']} total "
            f"({row['well_explored']} explored, "
            f"{row['referenced_only']} referenced only, "
            f"{row['orphaned']} orphaned)"
        )
    r = raw["relationships"]
    lines.append(f"  Relationships: {r['total_rels']} ({r['rel_types']} types)")
    m = raw["models"]
    lines.append(f"  Models: {m['total_models']} ({m['discovered']} discovered, {m['proposed']} proposed)")
    for row in raw["alignments"]:
        lines.append(f"  Alignments [{row['alignment_type']}]: {row['cnt']}")
    for row in raw["tasks"]:
        lines.append(f"  Tasks [{row['status']}]: {row['cnt']}")
    return "\n".join(lines)
```

#### Gap Detection Query

Gaps are entities or areas that are referenced but never directly explored.

```sql
-- _find_gaps()
-- Three types of gaps, unioned and ranked

-- Type 1: Referenced entities never explored (observation_count = 0 or 1)
-- These are entities mentioned in relationships but never directly investigated
WITH referenced_unexplored AS (
    SELECT
        e.entity_id,
        e.name,
        e.entity_type,
        e.model_id,
        m.name AS model_name,
        e.observation_count,
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

-- Type 2: Models with no cross-model alignments yet
-- A model exists but nothing has been mapped to/from it
unaligned_models AS (
    SELECT
        m.model_id AS entity_id,     -- reuse field for union
        m.name,
        'model' AS entity_type,
        m.model_id,
        m.name AS model_name,
        0 AS observation_count,
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

-- Type 3: Source configs that haven't been surveyed yet
-- Sources that are verified but have zero completed tasks
unsurveyed_sources AS (
    SELECT
        sc.source_id AS entity_id,
        sc.source_type || ':' || (sc.config->>'base_url') AS name,
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
            AND t.source_ref LIKE '%' || (sc.config->>'base_url') || '%'
            AND t.status = 'completed'
      )
)

SELECT * FROM referenced_unexplored
UNION ALL SELECT * FROM unaligned_models
UNION ALL SELECT * FROM unsurveyed_sources
ORDER BY reference_count DESC, gap_type
LIMIT 20;
```

#### Contradiction Detection Query

Contradictions are conflicting relationships or properties between the same pair of entities.

```sql
-- _find_contradictions()
-- Find entity pairs with conflicting information across sources

-- Type 1: Same entity pair, conflicting relationship types
-- e.g., A "calls" B in code but A "reads_from" B in docs
WITH conflicting_relationships AS (
    SELECT
        r1.from_entity,
        e1.name AS from_name,
        r1.to_entity,
        e2.name AS to_name,
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
      -- Only flag genuinely conflicting types (not complementary)
      AND (r1.relationship_type, r2.relationship_type) IN (
          ('calls', 'reads_from'),     -- API call vs direct DB read
          ('depends_on', 'governs'),   -- dependency direction conflict
          ('owns', 'owned_by'),        -- ownership direction conflict
          ('supersedes', 'depends_on') -- deprecated but still depended on
      )
),

-- Type 2: Contradicts alignment edges (explicitly flagged)
explicit_contradictions AS (
    SELECT
        a.from_entity,
        e1.name AS from_name,
        a.to_entity,
        e2.name AS to_name,
        'model:' || m1.name AS type_a,
        'model:' || m2.name AS type_b,
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

SELECT * FROM conflicting_relationships
UNION ALL SELECT * FROM explicit_contradictions
ORDER BY
    LEAST(confidence_a, confidence_b) DESC  -- high-confidence contradictions first
LIMIT 15;
```

#### Alignment Opportunity Detection

This is where the coordinator earns its keep. Find entities across models that might be related but haven't been aligned yet.

```sql
-- _find_alignment_opportunities()
-- Entities in different models with similar names or embeddings

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
                     AND e1.entity_id < e2.entity_id       -- avoid duplicates
                     AND e1.model_id IS DISTINCT FROM e2.model_id  -- different models
    JOIN models m1 ON e1.model_id = m1.model_id
    JOIN models m2 ON e2.model_id = m2.model_id
    WHERE e1.engagement_id = $1
      AND e1.status = 'active'
      AND e2.status = 'active'
      AND e1.embedding IS NOT NULL
      AND e2.embedding IS NOT NULL
      AND 1 - (e1.embedding <=> e2.embedding) > 0.65    -- similarity threshold
      -- Not already aligned
      AND NOT EXISTS (
          SELECT 1 FROM alignments a
          WHERE (a.from_entity = e1.entity_id AND a.to_entity = e2.entity_id)
             OR (a.from_entity = e2.entity_id AND a.to_entity = e1.entity_id)
      )
)
SELECT *
FROM cross_model_pairs
ORDER BY similarity DESC
LIMIT 15;
```

#### Recent Findings Summary

```sql
-- _summarize_recent_findings()
-- What workers found since the last coordinator cycle

SELECT
    t.task_id,
    t.directive,
    t.source_type,
    t.source_ref,
    t.max_scope,
    t.status,
    t.result_summary,
    t.completed_at,
    (SELECT COUNT(*) FROM observations o
     WHERE o.worker_id = t.assigned_worker
       AND o.created_at >= $2                -- since last cycle
    ) AS observations_written
FROM tasks t
WHERE t.engagement_id = $1
  AND t.status IN ('completed', 'failed')
  AND t.completed_at >= $2                   -- since last cycle
ORDER BY t.completed_at DESC
LIMIT 10;
```

#### Recent Decisions

```sql
-- _get_recent_decisions()
-- Coordinator decisions recorded as observations

SELECT
    o.raw_text,
    o.created_at,
    o.metadata->>'rationale' AS rationale
FROM observations o
WHERE o.engagement_id = $1
  AND o.observation_type = 'decision'
ORDER BY o.created_at DESC
LIMIT $2;    -- limit parameter
```

### 1.3 Step 2: Detect Issues (Python)

```python
@dataclass
class Gap:
    gap_type: str           # 'unexplored_entity', 'unaligned_model', 'unsurveyed_source'
    entity_id: UUID
    name: str
    entity_type: str
    model_name: str | None
    reference_count: int
    observation_count: int

@dataclass
class Contradiction:
    contradiction_type: str  # 'conflicting_relationship', 'cross_model_contradiction'
    from_name: str
    to_name: str
    type_a: str
    type_b: str
    confidence_a: float
    confidence_b: float

@dataclass
class AlignmentOpp:
    entity_a_name: str
    entity_a_type: str
    model_a_name: str
    model_a_purpose: str
    entity_b_name: str
    entity_b_type: str
    model_b_name: str
    model_b_purpose: str
    similarity: float

# Detection is just running the SQL queries above and hydrating these dataclasses.
# No LLM needed — this is pure data retrieval.
```

### 1.4 Step 3: Check Convergence (Python)

Convergence is measured by a multi-signal metric that goes beyond simple observation counting. The first-generation metric (raw reinforcement/expansion ratio) is gameable and penalizes legitimate contradictions unfairly (see GAP-E11 in `design_validation.md`). The enhanced metric addresses these weaknesses.

**Signals used:**
1. **Weighted ratio** — reinforcement weighted by novelty decay (diminishes for heavily-observed entities)
2. **Expansion deceleration** — sustained negative acceleration of expansion rate indicates natural exhaustion
3. **Per-source tracking** — detects single-source dominance that inflates convergence artificially
4. **Expected contradiction exclusion** — challenges marked as expected do not penalize convergence (resolves GAP-E11)

```python
@dataclass
class ConvergenceMetrics:
    """Multi-signal convergence measurement for one cycle."""
    raw_ratio: float              # Original: reinforcement / (expansion + challenge + 1)
    weighted_ratio: float         # Novelty-weighted: diminishes repeat-entity reinforcement
    expansion_rate: int           # New entities + relationships this cycle
    expansion_acceleration: float # Change in expansion rate vs prior cycle
    per_source_ratios: dict[str, float]  # source_ref → reinforcement ratio
    primary_converged: bool       # Weighted ratio above threshold for N cycles
    secondary_converged: bool     # Sustained negative expansion acceleration

async def check_convergence(
    engagement_id: UUID,
    cycle_number: int,
    pool: asyncpg.Pool,
    config: ConvergenceConfig,
) -> tuple[bool, ConvergenceMetrics]:
    """
    Returns (converged: bool, metrics: ConvergenceMetrics).

    Enhanced convergence ratio = weighted_reinforcement / (expansion + unacknowledged_challenge + 1)

    Novelty decay: reinforcement for entity E weighted by 1/log2(observation_count(E) + 1).
    This means the 50th observation confirming the same entity contributes far less than the 2nd.

    Anti-gaming: max 3 reinforcement credits per entity per cycle (via CTE).
    Workers cannot inflate convergence by repeatedly confirming the same entity.

    Expected contradiction exclusion: challenges where metadata->>'expected_contradiction' = 'true'
    are excluded from the denominator (resolves GAP-E11, relates to GAP-G3).
    """
    async with pool.acquire() as conn:
        # Weighted reinforcement with novelty decay and per-entity cap
        weighted_stats = await conn.fetchrow("""
            WITH cycle_observations AS (
                SELECT o.observation_id, o.metadata, o.source_ref
                FROM observations o
                WHERE o.engagement_id = $1
                  AND o.created_at >= (
                      SELECT COALESCE(MAX(created_at), '1970-01-01')
                      FROM convergence_log
                      WHERE engagement_id = $1
                  )
            ),
            reinforcements_per_entity AS (
                -- Cap reinforcement credit at N per entity per cycle
                SELECT
                    e.entity_id,
                    e.observation_count,
                    LEAST(COUNT(*), $3) AS capped_count
                FROM cycle_observations co
                JOIN entities e ON e.entity_id = ANY(
                    ARRAY(SELECT jsonb_array_elements_text(co.metadata->'entities_referenced'))::uuid[]
                )
                WHERE co.metadata->>'impact_type' = 'reinforcement'
                GROUP BY e.entity_id, e.observation_count
            ),
            weighted_reinforcement AS (
                SELECT COALESCE(SUM(
                    capped_count::float / ln(observation_count + 2) * 1.4427
                    -- 1/log2(n+1) = 1/(ln(n+1)/ln(2)) = ln(2)/ln(n+1) ≈ 1.4427/ln(n+2)
                ), 0) AS weighted_r
                FROM reinforcements_per_entity
            )
            SELECT
                weighted_r,
                (SELECT COUNT(*) FROM cycle_observations
                 WHERE metadata->>'impact_type' = 'reinforcement') AS raw_r,
                (SELECT COUNT(*) FROM cycle_observations
                 WHERE metadata->>'impact_type' = 'expansion') AS expansion,
                (SELECT COUNT(*) FROM cycle_observations
                 WHERE metadata->>'impact_type' = 'challenge'
                   AND COALESCE(metadata->>'expected_contradiction', 'false') != 'true'
                ) AS unacknowledged_challenge,
                (SELECT COUNT(*) FROM cycle_observations
                 WHERE metadata->>'impact_type' = 'challenge') AS total_challenge
            FROM weighted_reinforcement
        """, engagement_id, cycle_number, config.max_reinforcement_per_entity_per_cycle)

        raw_r = weighted_stats['raw_r']
        e = weighted_stats['expansion']
        uc = weighted_stats['unacknowledged_challenge']
        tc = weighted_stats['total_challenge']
        weighted_r = weighted_stats['weighted_r']

        raw_ratio = raw_r / (e + tc + 1)
        weighted_ratio = weighted_r / (e + uc + 1)

        # Per-source reinforcement ratios (detect single-source dominance)
        source_rows = await conn.fetch("""
            SELECT
                source_ref,
                COUNT(*) FILTER (WHERE metadata->>'impact_type' = 'reinforcement') AS r,
                COUNT(*) AS total
            FROM observations
            WHERE engagement_id = $1
              AND created_at >= (
                  SELECT COALESCE(MAX(created_at), '1970-01-01')
                  FROM convergence_log
                  WHERE engagement_id = $1
              )
            GROUP BY source_ref
        """, engagement_id)

        per_source = {
            row['source_ref']: row['r'] / max(row['total'], 1)
            for row in source_rows
        }

        # Expansion rate and acceleration (second derivative)
        prev_log = await conn.fetchrow("""
            SELECT expansion_count, expansion_rate
            FROM convergence_log
            WHERE engagement_id = $1
            ORDER BY cycle_number DESC
            LIMIT 1
        """, engagement_id)

        expansion_rate = e
        prev_rate = prev_log['expansion_rate'] if prev_log and prev_log['expansion_rate'] is not None else e
        expansion_acceleration = expansion_rate - prev_rate

        # Log this cycle's convergence data
        await conn.execute("""
            INSERT INTO convergence_log
                (engagement_id, cycle_number, reinforcement_count,
                 expansion_count, challenge_count, ratio,
                 weighted_ratio, expansion_rate, expansion_acceleration,
                 per_source_ratios, secondary_convergence)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """, engagement_id, cycle_number, raw_r, e, tc, raw_ratio,
            weighted_ratio, expansion_rate, expansion_acceleration,
            json.dumps(per_source), False)  # secondary_convergence updated below

        # Primary check: weighted ratio above threshold for N consecutive cycles
        recent = await conn.fetch("""
            SELECT weighted_ratio, expansion_acceleration
            FROM convergence_log
            WHERE engagement_id = $1
            ORDER BY cycle_number DESC
            LIMIT $2
        """, engagement_id, config.consecutive_cycles_required)

        primary_converged = False
        if len(recent) >= config.consecutive_cycles_required:
            primary_converged = all(
                row['weighted_ratio'] >= config.convergence_threshold
                for row in recent
            )

        # Secondary check: sustained negative expansion acceleration
        secondary_converged = False
        if len(recent) >= config.expansion_deceleration_cycles:
            decel_window = recent[:config.expansion_deceleration_cycles]
            secondary_converged = all(
                row['expansion_acceleration'] < 0
                for row in decel_window
            )

        # Source dominance warning (not a convergence gate, but flagged)
        source_dominant = any(
            ratio > config.source_dominance_threshold
            for ratio in per_source.values()
        ) if per_source else False

        # Update secondary_convergence flag in log
        if secondary_converged:
            await conn.execute("""
                UPDATE convergence_log
                SET secondary_convergence = TRUE
                WHERE engagement_id = $1 AND cycle_number = $2
            """, engagement_id, cycle_number)

        metrics = ConvergenceMetrics(
            raw_ratio=raw_ratio,
            weighted_ratio=weighted_ratio,
            expansion_rate=expansion_rate,
            expansion_acceleration=expansion_acceleration,
            per_source_ratios=per_source,
            primary_converged=primary_converged,
            secondary_converged=secondary_converged,
        )

        converged = primary_converged or (secondary_converged and weighted_ratio >= 1.0)

        return converged, metrics


@dataclass
class ConvergenceConfig:
    convergence_threshold: float = 3.0          # weighted ratio threshold
    consecutive_cycles_required: int = 3        # primary signal must hold for N cycles
    novelty_decay: bool = True                  # enable 1/log2(obs_count+1) weighting
    max_reinforcement_per_entity_per_cycle: int = 3  # anti-gaming cap
    expansion_deceleration_cycles: int = 4      # secondary signal: N cycles of negative accel
    source_dominance_threshold: float = 0.6     # warn if single source > 60% of reinforcement
```

### 1.5 Step 4: Rank Issues (Python)

```python
def rank_issues(
    gaps: list[Gap],
    contradictions: list[Contradiction],
    alignment_opps: list[AlignmentOpp],
) -> list[RankedIssue]:
    """
    Pure Python scoring. No LLM.
    Returns top issues for the LLM to generate directives for.
    """
    ranked: list[RankedIssue] = []

    for gap in gaps:
        if gap.gap_type == 'unsurveyed_source':
            # Unsurveyed sources are highest priority — can't learn without data
            score = 100.0
        elif gap.gap_type == 'unaligned_model':
            # Models without alignments need exploration
            score = 50.0 + gap.reference_count * 0.5
        else:
            # Unexplored entities scored by how often they're referenced
            score = gap.reference_count * 2.0
        ranked.append(RankedIssue(
            issue_type='gap', score=score, data=gap,
        ))

    for contradiction in contradictions:
        # Higher-confidence contradictions are more urgent
        score = 30.0 + max(contradiction.confidence_a, contradiction.confidence_b) * 20.0
        ranked.append(RankedIssue(
            issue_type='contradiction', score=score, data=contradiction,
        ))

    for opp in alignment_opps:
        # High-similarity unaligned cross-model pairs
        score = 20.0 + opp.similarity * 15.0
        ranked.append(RankedIssue(
            issue_type='alignment_opportunity', score=score, data=opp,
        ))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:8]  # Cap at 8 issues per cycle to bound LLM input


@dataclass
class RankedIssue:
    issue_type: str   # 'gap', 'contradiction', 'alignment_opportunity'
    score: float
    data: Gap | Contradiction | AlignmentOpp
```

### 1.6 Step 5: Generate Directives (LLM Call)

This is the **single LLM call per cycle**. It takes the ranked issues and available sources, and generates concrete task directives for workers.

#### System Prompt

```python
COORDINATOR_SYSTEM_PROMPT = """You are the coordinator for a discovery engagement. Your job is to generate specific, actionable task directives for exploration workers.

You receive:
1. The engagement's problem statement (what we're trying to understand)
2. A coverage dashboard (what we've explored so far)
3. Ranked issues that need attention (gaps, contradictions, alignment opportunities)
4. Available sources (where workers can look)
5. Recent findings (what workers just discovered)
6. Recent decisions (what you decided in past cycles)
7. Model summary (the models we're building and their purposes)

You produce: A list of task directives. Each directive tells one worker exactly what to explore and why.

## Rules

1. Each directive targets ONE source and ONE specific area within that source.
2. Specify max_scope: 'survey' for broad first-look, 'focused' for targeted investigation, 'deep' for exhaustive analysis of a narrow area.
3. Include relevant_context: what the worker needs to know from the graph to do useful work. Keep this under 500 tokens.
4. When investigating contradictions, dispatch workers to BOTH sides — get evidence from each source.
5. For alignment opportunities, direct the worker to explore the specific entity and its relationships — we need enough detail to determine the alignment type.
6. Don't dispatch more than 5 tasks per cycle. Quality over quantity.
7. Don't re-dispatch tasks that recently completed unless the results were insufficient (check recent_findings).
8. Record your reasoning for each directive — this becomes the decision log.

## Output Format

Return a JSON array of directives:
```json
[
    {
        "source_type": "confluence",
        "source_ref": "https://company.atlassian.net/wiki/spaces/DATA",
        "directive": "Survey the DATA Confluence space. Focus on pages related to 'payments-service'. We know it's referenced by 6 other services but haven't directly explored its documentation.",
        "max_scope": "focused",
        "relevant_context": "payments-service: called by checkout-service, subscription-service, billing-service. Depends on payments-db (evidence from code analysis). No documentation explored yet.",
        "reason": "payments-service has 14 references but 0 direct observations. High-priority gap.",
        "addresses_issue": "gap:payments-service"
    }
]
```
"""
```

#### User Message (Assembled Per-Cycle)

```python
async def build_coordinator_user_message(
    projection: CoordinatorProjection,
    ranked_issues: list[RankedIssue],
    available_sources: list[SourceConfig],
) -> str:
    """Assemble the user message for the coordinator LLM call."""
    sections = []

    sections.append(f"## Problem Statement\n{projection.problem_statement}")
    sections.append(f"\n{projection.coverage_dashboard}")
    sections.append(f"\n## Model Summary\n{projection.model_summary}")

    sections.append("\n## Issues Needing Attention (ranked by priority)")
    for i, issue in enumerate(ranked_issues, 1):
        sections.append(f"\n### Issue {i} [{issue.issue_type}] (score: {issue.score:.1f})")
        sections.append(format_issue(issue))

    sections.append("\n## Available Sources")
    for source in available_sources:
        sections.append(f"- {source.source_type}: {source.config.get('base_url', 'N/A')} (status: {source.status})")

    sections.append(f"\n## Recent Worker Findings\n{projection.recent_findings}")
    sections.append(f"\n## Recent Coordinator Decisions\n{projection.recent_decisions}")

    return "\n".join(sections)
```

#### Response Parsing

```python
async def parse_directives(
    response_text: str,
) -> list[TaskDirective]:
    """Parse LLM response into typed task directives."""
    # Extract JSON from response (may be wrapped in markdown code blocks)
    json_str = extract_json_block(response_text)
    raw = json.loads(json_str)

    directives = []
    for item in raw:
        directive = TaskDirective(
            source_type=item["source_type"],
            source_ref=item["source_ref"],
            directive=item["directive"],
            max_scope=item.get("max_scope", "survey"),
            relevant_context=item.get("relevant_context", ""),
            reason=item.get("reason", ""),
            addresses_issue=item.get("addresses_issue", ""),
        )
        directives.append(directive)

    return directives


@dataclass
class TaskDirective:
    source_type: str
    source_ref: str
    directive: str
    max_scope: str           # 'survey', 'focused', 'deep'
    relevant_context: str    # context to inject into worker prompt
    reason: str              # coordinator's reasoning (saved as decision observation)
    addresses_issue: str     # which ranked issue this addresses
```

### 1.7 Step 6: Record Decisions

```python
async def record_decisions(
    engagement_id: UUID,
    coordinator_id: UUID,
    directives: list[TaskDirective],
    convergence_ratio: float,
    pool: asyncpg.Pool,
):
    """Write each directive decision as an observation for future cycles."""
    async with pool.acquire() as conn:
        for directive in directives:
            await conn.execute("""
                INSERT INTO observations
                    (engagement_id, worker_id, source_ref, raw_text,
                     observation_type, metadata)
                VALUES ($1, $2, $3, $4, 'decision', $5)
            """,
                engagement_id,
                f"coordinator:{coordinator_id}",
                directive.source_ref,
                f"Dispatched {directive.max_scope} task: {directive.directive}\nReason: {directive.reason}",
                json.dumps({
                    "rationale": directive.reason,
                    "addresses_issue": directive.addresses_issue,
                    "convergence_ratio": convergence_ratio,
                }),
            )
```

### 1.8 Complete Coordinator Cycle

```python
async def coordinator_cycle(
    engagement_id: UUID,
    coordinator_id: UUID,
    cycle_number: int,
    last_cycle_at: datetime,
    pool: asyncpg.Pool,
    llm: LLMClient,
    convergence_config: ConvergenceConfig,
) -> CycleResult:
    """One full coordinator cycle. Pure Python except Step 5."""

    # Step 1: Build projection (SQL)
    projection = await build_projection(
        engagement_id, coordinator_id, last_cycle_at, pool,
    )

    # Step 2: Issues are already in the projection (detected via SQL)
    # No separate step needed — gaps, contradictions, alignment_opps
    # were populated by the projection queries

    # Step 3: Check convergence (Python + SQL)
    converged, ratio = await check_convergence(
        engagement_id, cycle_number, pool, convergence_config,
    )
    if converged:
        return CycleResult(
            actions=[],
            convergence_signal=True,
            cycle_stats=CycleStats(
                cycle_number=cycle_number,
                convergence_ratio=ratio,
                gaps_found=len(projection.active_gaps),
                contradictions_found=len(projection.contradictions),
            ),
        )

    # Step 4: Rank issues (Python)
    ranked = rank_issues(
        projection.active_gaps,
        projection.contradictions,
        projection.alignment_opportunities,
    )

    if not ranked:
        # Nothing to do — may be convergence or just empty
        return CycleResult(
            actions=[],
            convergence_signal=False,
            cycle_stats=CycleStats(
                cycle_number=cycle_number,
                convergence_ratio=ratio,
                gaps_found=0,
                contradictions_found=0,
            ),
        )

    # Step 5: Generate directives (** 1 LLM call **)
    sources = await get_verified_sources(engagement_id, pool)
    user_message = await build_coordinator_user_message(
        projection, ranked, sources,
    )

    response = await llm.call(
        system=COORDINATOR_SYSTEM_PROMPT,
        user=user_message,
        max_tokens=4096,
    )

    directives = await parse_directives(response.text)

    # Step 6: Record decisions (SQL)
    await record_decisions(
        engagement_id, coordinator_id, directives, ratio, pool,
    )

    # Update coordinator instance
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE coordinator_instances
            SET cycles_completed = $1
            WHERE instance_id = $2
        """, cycle_number, coordinator_id)

    return CycleResult(
        actions=[
            DispatchWorker(directive=d) for d in directives
        ],
        convergence_signal=False,
        cycle_stats=CycleStats(
            cycle_number=cycle_number,
            convergence_ratio=ratio,
            gaps_found=len(projection.active_gaps),
            contradictions_found=len(projection.contradictions),
            directives_generated=len(directives),
        ),
    )
```

---

## 2. Worker Tool-Use Loop

Workers are the LLM-heavy component. Each worker is an async function that runs a multi-turn tool-use conversation — reading source material via source tools and writing findings via graph tools.

### 2.1 Worker Lifecycle

```
Supervisor                        Worker
    │                                │
    │  dispatch_worker(task)         │
    ├───────────────────────────────►│
    │                                │ 1. Assemble prompt
    │                                │    (base + learned + directive)
    │                                │
    │                                │ 2. Tool-use loop:
    │                                │    ┌─► LLM call
    │                                │    │   ├── source tool calls
    │                                │    │   │   (read, search, list_children)
    │                                │    │   └── graph tool calls
    │                                │    │       (add_entity, add_relationship,
    │                                │    │        add_observation, suggest_followup)
    │                                │    │
    │                                │    │   scope_overflow?
    │                                │    │   ├── no → loop back
    │                                │    └───┤
    │                                │        └── yes → exit loop
    │                                │
    │                                │ 3. Return WorkerResult
    │  WorkerResult                  │
    │◄───────────────────────────────┤
    │                                │ (terminated)
```

### 2.2 Tool Definitions

#### Source Tools (Read-Only)

These are bound to a specific `SourceConnector` at dispatch time. The worker can't choose which source to read — it's scoped to the task's source.

```python
SOURCE_TOOLS = [
    {
        "name": "survey",
        "description": "List top-level entry points for this source. Returns a list of resource references you can read or explore further. Use this first to understand the source's structure.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_children",
        "description": "List sub-resources of a specific resource. For Confluence: child pages. For GitHub: files in a directory. For Jira: tickets in a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The resource reference to list children of.",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "read",
        "description": "Read the full content of a specific resource. Returns the resource as text (HTML converted to markdown for web pages, file content for code, etc.). May be large — use list_children first to identify what to read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The resource reference to read.",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "search",
        "description": "Search within this source for content matching a query. Returns a list of matching resource references with snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    },
]
```

#### Graph Tools (Write)

These write directly to PostgreSQL via the graph write layer. Each call is individually persisted — partial results survive worker crashes.

```python
GRAPH_TOOLS = [
    {
        "name": "add_entity",
        "description": "Record a discovered entity. Entities are things: services, databases, teams, APIs, policies, people, documents, etc. If this entity might already exist (same name, different source), add it anyway — entity resolution happens separately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The entity name as it appears in this source.",
                },
                "entity_type": {
                    "type": "string",
                    "enum": [
                        "service", "database", "team", "api", "policy",
                        "person", "document", "capability", "domain",
                        "repository", "schema", "process",
                    ],
                    "description": "The type of entity.",
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative names seen for this entity (e.g., 'payments-svc', 'PaymentService').",
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
    },
    {
        "name": "add_relationship",
        "description": "Record a relationship between two entities. Both entities should already exist (use add_entity first). If you reference an entity that doesn't exist yet, it will be auto-created with minimal information.",
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
                    "enum": [
                        "depends_on", "owned_by", "reads_from", "writes_to",
                        "calls", "governs", "implements", "contains",
                        "supersedes", "related_to",
                    ],
                    "description": "How from_entity relates to to_entity.",
                },
                "evidence": {
                    "type": "string",
                    "description": "Brief description of the evidence for this relationship.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0. Use 0.9+ for explicit declarations, 0.5-0.8 for inferred from context.",
                    "default": 0.7,
                },
            },
            "required": ["from_entity", "to_entity", "relationship_type", "evidence"],
        },
    },
    {
        "name": "add_observation",
        "description": "Record a free-text observation. Use this for insights, contradictions, or information that doesn't fit neatly into entity/relationship structure. Observations are the raw material for consolidation.",
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
                "impact_type": {
                    "type": "string",
                    "enum": ["reinforcement", "expansion", "challenge"],
                    "description": "Does this reinforce existing knowledge, expand it, or challenge it?",
                    "default": "expansion",
                },
            },
            "required": ["text", "observation_type"],
        },
    },
    {
        "name": "suggest_followup",
        "description": "Suggest a follow-up exploration task. Use when you find something that needs deeper investigation but is outside your current scope. The coordinator will evaluate your suggestions.",
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
    },
]
```

### 2.3 Worker System Prompt

```python
WORKER_BASE_PROMPT = """You are a discovery worker. Your job is to explore a specific source and extract structured knowledge.

## Your Task

You will receive a directive telling you what to explore and why. Follow it.

## How to Work

1. **Survey first.** Use `survey` or `list_children` to understand the source's structure before diving in.
2. **Read selectively.** Don't read everything. Read what's relevant to your directive.
3. **Extract as you go.** Use `add_entity` and `add_relationship` whenever you discover something. Don't wait until the end.
4. **Be specific.** Entity names should match what you see in the source. Include aliases if you see variants.
5. **Cite evidence.** Every relationship should have an evidence string explaining why you believe it exists.
6. **Note surprises.** Use `add_observation` for things that are unexpected, contradictory, or don't fit the entity/relationship model.
7. **Suggest follow-ups.** Use `suggest_followup` when you find something that needs deeper investigation but is beyond your scope.

## Scope Rules

- **survey:** Read entry points only. Map the top-level structure. Don't go deep.
- **focused:** Go deep on the specific area identified in your directive. Ignore unrelated content.
- **deep:** Exhaustive exploration of a bounded area. Read everything within scope.

If your task exceeds your scope, STOP. Write what you've found, use `suggest_followup` for what remains, and end your turn.

## Entity Types

service, database, team, api, policy, person, document, capability, domain, repository, schema, process

## Relationship Types

depends_on, owned_by, reads_from, writes_to, calls, governs, implements, contains, supersedes, related_to

## Impact Classification

When adding observations, classify their impact:
- **reinforcement**: This confirms something we already know from other sources.
- **expansion**: This is new information we haven't seen before.
- **challenge**: This contradicts or complicates something we thought we knew.

## When to Stop

- You've addressed your directive thoroughly within scope.
- You've exhausted the relevant content in the source.
- You're seeing diminishing returns (same entities, same relationships).
- Stop and report. Don't loop.
"""
```

### 2.4 Prompt Assembly

```python
async def assemble_worker_prompt(
    task: TaskRecord,
    agent_type_name: str,
    pool: asyncpg.Pool,
) -> str:
    """
    Assemble the full system prompt:
    base_prompt + learned_sections + task_directive
    """
    async with pool.acquire() as conn:
        # Get current prompt version for this agent type
        version = await conn.fetchrow("""
            SELECT pv.base_prompt, pv.learned_sections
            FROM prompt_versions pv
            JOIN agent_types at ON pv.agent_type_id = at.agent_type_id
            WHERE at.name = $1 AND pv.is_current = TRUE
        """, agent_type_name)

    sections = [version['base_prompt']]

    # Add learned sections (source profiles, navigation hints, etc.)
    learned = json.loads(version['learned_sections']) if version['learned_sections'] else {}
    for section_key, section in sorted(learned.items()):
        sections.append(f"\n## {section_key}\n{section['content']}")

    # Add task-specific directive
    sections.append(f"\n## Your Directive\n{task.directive}")

    if task.relevant_context:
        sections.append(f"\n## Relevant Context\n{task.relevant_context}")

    sections.append(f"\n## Scope: {task.max_scope}")

    return "\n".join(sections)
```

### 2.5 Tool Execution Layer

```python
class GraphWriter:
    """
    Executes graph tool calls against PostgreSQL.
    Tracks counts for the WorkerResult.
    Handles entity name → entity_id resolution.
    """

    def __init__(
        self,
        engagement_id: UUID,
        model_id: UUID | None,
        worker_id: str,
        source_ref: str,
        pool: asyncpg.Pool,
        embedder: EmbeddingService,
    ):
        self.engagement_id = engagement_id
        self.model_id = model_id
        self.worker_id = worker_id
        self.source_ref = source_ref
        self.pool = pool
        self.embedder = embedder
        # Counters
        self.entities_written = 0
        self.relationships_written = 0
        self.observations_written = 0
        self.followups_suggested = 0
        # Local name→id cache (within this worker's lifetime)
        self._entity_cache: dict[str, UUID] = {}

    async def execute(self, tool_name: str, tool_input: dict) -> str:
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

    async def _add_entity(self, params: dict) -> str:
        name = params["name"]
        entity_type = params["entity_type"]
        aliases = params.get("aliases", [])
        properties = params.get("properties", {})

        # Check local cache first (within this worker run)
        if name in self._entity_cache:
            entity_id = self._entity_cache[name]
            # Update observation count
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE entities
                    SET observation_count = observation_count + 1,
                        last_referenced = NOW(),
                        aliases = array_cat(aliases, $1::text[]),
                        properties = properties || $2::jsonb
                    WHERE entity_id = $3
                """, aliases, json.dumps(properties), entity_id)
            return f"Updated existing entity '{name}' (id: {entity_id})"

        # Generate embedding for entity name + type
        embedding = await self.embedder.embed(f"{name} ({entity_type})")

        async with self.pool.acquire() as conn:
            # Check for existing entity with same name in this engagement
            existing = await conn.fetchrow("""
                SELECT entity_id FROM entities
                WHERE engagement_id = $1
                  AND (LOWER(name) = LOWER($2) OR $2 = ANY(aliases))
                  AND status = 'active'
                LIMIT 1
            """, self.engagement_id, name)

            if existing:
                entity_id = existing['entity_id']
                await conn.execute("""
                    UPDATE entities
                    SET observation_count = observation_count + 1,
                        last_referenced = NOW(),
                        aliases = array_cat(aliases, $1::text[]),
                        properties = properties || $2::jsonb
                    WHERE entity_id = $3
                """, aliases, json.dumps(properties), entity_id)
            else:
                entity_id = await conn.fetchval("""
                    INSERT INTO entities
                        (engagement_id, model_id, name, entity_type,
                         aliases, embedding, observation_count, properties)
                    VALUES ($1, $2, $3, $4, $5, $6, 1, $7)
                    RETURNING entity_id
                """, self.engagement_id, self.model_id, name, entity_type,
                     aliases, embedding, json.dumps(properties))
                self.entities_written += 1

        self._entity_cache[name] = entity_id
        return f"{'Updated' if existing else 'Created'} entity '{name}' (id: {entity_id})"

    async def _add_relationship(self, params: dict) -> str:
        from_name = params["from_entity"]
        to_name = params["to_entity"]
        rel_type = params["relationship_type"]
        evidence_text = params["evidence"]
        confidence = params.get("confidence", 0.7)

        # Resolve entity names to IDs (auto-create if needed)
        from_id = await self._resolve_entity(from_name)
        to_id = await self._resolve_entity(to_name)

        # Record the evidence as an observation first
        async with self.pool.acquire() as conn:
            obs_id = await conn.fetchval("""
                INSERT INTO observations
                    (engagement_id, worker_id, source_ref, raw_text,
                     observation_type, metadata)
                VALUES ($1, $2, $3, $4, 'relationship', $5)
                RETURNING observation_id
            """, self.engagement_id, self.worker_id, self.source_ref,
                 evidence_text, json.dumps({"from": from_name, "to": to_name, "type": rel_type}))

            # Upsert relationship (increment evidence if exists)
            await conn.execute("""
                INSERT INTO relationships
                    (engagement_id, from_entity, to_entity, relationship_type,
                     evidence, confidence)
                VALUES ($1, $2, $3, $4, ARRAY[$5], $6)
                ON CONFLICT ON CONSTRAINT uq_relationship_triple DO UPDATE
                SET evidence = array_append(relationships.evidence, $5),
                    confidence = GREATEST(relationships.confidence, $6),
                    last_confirmed = NOW()
            """, self.engagement_id, from_id, to_id, rel_type, obs_id, confidence)

        self.relationships_written += 1
        return f"Recorded: {from_name} --[{rel_type}]--> {to_name} (confidence: {confidence})"

    async def _add_observation(self, params: dict) -> str:
        text = params["text"]
        obs_type = params["observation_type"]
        entities = params.get("entities_referenced", [])
        impact = params.get("impact_type", "expansion")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO observations
                    (engagement_id, worker_id, source_ref, raw_text,
                     observation_type, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, self.engagement_id, self.worker_id, self.source_ref, text, obs_type,
                 json.dumps({
                     "entities_referenced": entities,
                     "impact_type": impact,
                 }))

        self.observations_written += 1
        return f"Recorded {obs_type} observation ({impact})"

    async def _suggest_followup(self, params: dict) -> str:
        question = params["question"]
        source = params.get("suggested_source", "")
        priority = params.get("priority", "medium")

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO observations
                    (engagement_id, worker_id, source_ref, raw_text,
                     observation_type, metadata)
                VALUES ($1, $2, $3, $4, 'gap', $5)
            """, self.engagement_id, self.worker_id, self.source_ref, question,
                 json.dumps({
                     "suggested_source": source,
                     "priority": priority,
                     "impact_type": "expansion",
                 }))

        self.followups_suggested += 1
        return f"Follow-up suggestion recorded (priority: {priority})"

    async def _resolve_entity(self, name: str) -> UUID:
        """Resolve entity name to ID. Auto-creates if not found."""
        if name in self._entity_cache:
            return self._entity_cache[name]

        async with self.pool.acquire() as conn:
            existing = await conn.fetchval("""
                SELECT entity_id FROM entities
                WHERE engagement_id = $1
                  AND (LOWER(name) = LOWER($2) OR $2 = ANY(aliases))
                  AND status = 'active'
                LIMIT 1
            """, self.engagement_id, name)

            if existing:
                self._entity_cache[name] = existing
                return existing

            # Auto-create with minimal info
            embedding = await self.embedder.embed(name)
            entity_id = await conn.fetchval("""
                INSERT INTO entities
                    (engagement_id, model_id, name, entity_type,
                     embedding, observation_count)
                VALUES ($1, $2, $3, 'service', $4, 0)
                RETURNING entity_id
            """, self.engagement_id, self.model_id, name, embedding)

        self._entity_cache[name] = entity_id
        self.entities_written += 1
        return entity_id
```

### 2.6 Worker Main Loop

```python
@dataclass
class WorkerResult:
    task_id: UUID
    worker_id: str
    entities_written: int
    relationships_written: int
    observations_written: int
    followups_suggested: int
    scope_overflow: bool
    error: str | None = None


async def run_worker(
    task: TaskRecord,
    connector: SourceConnector,
    graph: GraphWriter,
    llm: LLMClient,
    budget: WorkerBudget,
    event_bus: EventBus,
) -> WorkerResult:
    """
    Execute a worker task. This is the complete async function
    that the supervisor dispatches as a coroutine.
    """
    worker_id = f"worker-{task.task_id.hex[:8]}"

    # 1. Assemble prompt
    system_prompt = await assemble_worker_prompt(
        task,
        agent_type_name=f"worker:{task.source_type}",
        pool=graph.pool,
    )
    tools = SOURCE_TOOLS + GRAPH_TOOLS
    messages = []

    # 2. Tool-use loop
    scope_overflow = False
    turn_count = 0
    max_turns = 30  # hard safety cap

    try:
        while turn_count < max_turns:
            turn_count += 1

            # Check token budget before each LLM call
            estimated_tokens = estimate_message_tokens(system_prompt, messages)
            if estimated_tokens > budget.max_tokens * 0.7:
                scope_overflow = True
                break

            # LLM call
            response = await llm.call(
                system=system_prompt,
                messages=messages,
                tools=tools,
                max_tokens=4096,
            )

            # Track token usage
            budget.tokens_used += response.usage.input_tokens + response.usage.output_tokens

            # Check if worker decided it's done
            if response.stop_reason == "end_turn":
                # Append assistant response to messages for completeness
                messages.append({"role": "assistant", "content": response.content})
                break

            # Process tool calls
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for tool_call in response.tool_calls:
                    result = await _execute_tool(
                        tool_call, connector, graph,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": result,
                    })

                messages.append({"role": "user", "content": tool_results})

                # Emit progress event (throttled to 1/sec by event bus)
                await event_bus.emit(WorkerProgress(
                    engagement_id=task.engagement_id,
                    task_id=task.task_id,
                    worker_id=worker_id,
                    current_action=_summarize_last_tools(response.tool_calls),
                    entities_so_far=graph.entities_written,
                    observations_so_far=graph.observations_written,
                    tokens_used=budget.tokens_used,
                ))

    except Exception as e:
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker_id,
            entities_written=graph.entities_written,
            relationships_written=graph.relationships_written,
            observations_written=graph.observations_written,
            followups_suggested=graph.followups_suggested,
            scope_overflow=scope_overflow,
            error=str(e),
        )

    return WorkerResult(
        task_id=task.task_id,
        worker_id=worker_id,
        entities_written=graph.entities_written,
        relationships_written=graph.relationships_written,
        observations_written=graph.observations_written,
        followups_suggested=graph.followups_suggested,
        scope_overflow=scope_overflow,
    )


async def _execute_tool(
    tool_call: ToolCall,
    connector: SourceConnector,
    graph: GraphWriter,
) -> str:
    """Route tool call to the right handler."""
    name = tool_call.name
    params = tool_call.input

    # Source tools (read-only)
    if name == "survey":
        entries = await connector.survey()
        return json.dumps(entries[:50])  # cap results
    elif name == "list_children":
        children = await connector.list_children(params["ref"])
        return json.dumps(children[:100])  # cap results
    elif name == "read":
        content = await connector.read(params["ref"])
        # Truncate to prevent context explosion
        if len(content) > 50_000:
            content = content[:50_000] + "\n\n[TRUNCATED — content exceeds 50k chars]"
        return content
    elif name == "search":
        results = await connector.search(params["query"])
        return json.dumps(results[:20])  # cap results

    # Graph tools (write to DB)
    elif name in ("add_entity", "add_relationship", "add_observation", "suggest_followup"):
        return await graph.execute(name, params)

    else:
        return f"Unknown tool: {name}"


@dataclass
class WorkerBudget:
    max_tokens: int = 100_000    # total token budget for this worker
    tokens_used: int = 0
```

### 2.7 Worker Loop State & Drift Detection

Workers execute in a multi-turn tool-use loop, but the original spec has no guardrails against degenerate behavior: repeated identical tool calls, excessive retries on failing tools, or scope drift away from the directive. This section specifies the `WorkerLoopState` that tracks these conditions.

```python
@dataclass
class WorkerLoopState:
    """Tracks worker behavior within a single tool-use loop execution."""
    tool_call_history: list[tuple[str, str]]  # [(tool_name, params_hash), ...]
    tool_call_cache: dict[str, str]           # params_hash → cached result
    tool_error_counts: dict[str, int]         # (tool_name, params_hash) → error count
    entity_types_discovered: dict[str, int]   # entity_type → count
    duplicate_calls_skipped: int = 0
    retries_exhausted: int = 0
    drift_detected: bool = False

def _hash_tool_call(name: str, params: dict) -> str:
    """Deterministic hash for tool call deduplication."""
    import hashlib, json
    key = json.dumps({"tool": name, "params": params}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**Tool call deduplication:** Before executing a tool call, hash `(tool_name, sorted params)`. If the hash exists in `tool_call_cache`, return the cached result immediately without executing. This prevents workers from wasting budget on repeated identical reads or searches.

**Per-tool error retry limit:** Track error counts per unique `(tool_name, params_hash)`. After `max_retries_per_tool` (default: 3) errors for the same call, return a synthetic error result and do not retry. The worker LLM receives the error and must try a different approach.

**Scope drift detection:** After every N tool calls (default: 5), check the distribution of `entity_types_discovered`. If the worker is producing entity types that diverge significantly from what the directive implies (e.g., directive says "explore service dependencies" but worker is extracting `person` entities), flag `drift_detected = True`. This is informational — the worker continues, but the flag is reported in `WorkerResult` for coordinator awareness.

```python
def check_drift(
    state: WorkerLoopState,
    directive_scope: str,  # e.g., "service", "api", "database"
    threshold: float = 0.5,
) -> bool:
    """
    Returns True if > threshold of discovered entities are outside directive scope.
    Simple heuristic — not a hard stop, just a flag.
    """
    if not state.entity_types_discovered:
        return False
    total = sum(state.entity_types_discovered.values())
    in_scope = sum(
        count for etype, count in state.entity_types_discovered.items()
        if etype.lower() in directive_scope.lower()
    )
    return (in_scope / total) < (1 - threshold) if total > 0 else False
```

**Updated WorkerResult** includes drift detection fields:

```python
@dataclass
class WorkerResult:
    task_id: UUID
    worker_id: str
    entities_written: int
    relationships_written: int
    observations_written: int
    followups_suggested: int
    scope_overflow: bool
    error: str | None = None
    # Drift detection additions
    drift_detected: bool = False
    duplicate_calls_skipped: int = 0
    retries_exhausted: int = 0
```

### 2.8 Scope Overflow Handling

When a worker hits scope overflow (context window filling up), it doesn't just die. The graph already has partial results (every tool call persisted immediately). The `scope_overflow: True` flag tells the supervisor and coordinator that:

1. The task was too large for one worker at this scope level.
2. The coordinator should dispatch follow-up workers for the unexplored portions.
3. The worker's `suggest_followup` observations (if any) indicate what remains.

```python
# In the supervisor, after reaping a completed worker:
async def handle_worker_result(self, result: WorkerResult, task: TaskRecord):
    """Update task record and handle scope overflow."""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            UPDATE tasks
            SET status = $1,
                result_summary = $2,
                completed_at = NOW()
            WHERE task_id = $3
        """,
            'failed' if result.error else 'completed',
            json.dumps({
                'entities_written': result.entities_written,
                'relationships_written': result.relationships_written,
                'observations_written': result.observations_written,
                'followups_suggested': result.followups_suggested,
                'scope_overflow': result.scope_overflow,
                'error': result.error,
            }),
            result.task_id,
        )

    # Emit completion event
    if result.error:
        await self.event_bus.emit(WorkerFailed(
            engagement_id=task.engagement_id,
            task_id=task.task_id,
            worker_id=result.worker_id,
            error=result.error,
        ))
    else:
        await self.event_bus.emit(WorkerCompleted(
            engagement_id=task.engagement_id,
            task_id=task.task_id,
            worker_id=result.worker_id,
            entities_written=result.entities_written,
            observations_written=result.observations_written,
            scope_overflow=result.scope_overflow,
        ))

    # Scope overflow is NOT an error — the coordinator will handle it
    # in the next cycle by seeing partial results + suggest_followup observations
```

### 2.9 Relationship Uniqueness Constraint

The `add_relationship` tool uses an upsert. This requires a unique constraint:

```sql
-- Add to schema.sql
ALTER TABLE relationships
ADD CONSTRAINT uq_relationship_triple
UNIQUE (engagement_id, from_entity, to_entity, relationship_type);
```

This means the same relationship found by multiple workers (or re-confirmed by the same worker) accumulates evidence rather than creating duplicates.

---

## 3. Consolidation Process

Consolidation is the "sleep" process — it synthesizes Tier 2 knowledge items into Tier 3 consolidated units. This is where non-obvious connections emerge.

### 3.1 Trigger Logic

Consolidation runs when the supervisor decides it should. Not after every cycle — only when there's meaningful new material to consolidate.

```python
class ConsolidationTrigger:
    """Determines when to run consolidation. Pure Python."""

    # Minimum new observations before consolidation is worthwhile
    min_new_observations: int = 20

    # Minimum time between consolidation runs
    min_interval: timedelta = timedelta(minutes=15)

    # Maximum time between runs (force consolidation)
    max_interval: timedelta = timedelta(hours=2)

    async def should_consolidate(
        self,
        engagement_id: UUID,
        pool: asyncpg.Pool,
    ) -> bool:
        async with pool.acquire() as conn:
            # When was the last consolidation?
            last_run = await conn.fetchval("""
                SELECT MAX(created_at)
                FROM consolidated_units
                WHERE engagement_id = $1
            """, engagement_id)

            now = datetime.now(timezone.utc)

            # Force consolidation if max_interval exceeded
            if last_run and (now - last_run) > self.max_interval:
                return True

            # Don't consolidate too frequently
            if last_run and (now - last_run) < self.min_interval:
                return False

            # Check if enough new material exists
            since = last_run or datetime(1970, 1, 1, tzinfo=timezone.utc)
            new_obs_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM observations
                WHERE engagement_id = $1
                  AND created_at > $2
            """, engagement_id, since)

            return new_obs_count >= self.min_new_observations
```

### 3.2 Stale Entity Detection

Find entities whose knowledge has changed since the last time they were consolidated.

```sql
-- find_stale_entities()
-- Returns entities needing (re)consolidation

WITH entity_last_consolidated AS (
    -- When was each entity last consolidated?
    SELECT
        e.entity_id,
        e.name,
        e.entity_type,
        e.model_id,
        m.name AS model_name,
        e.observation_count,
        cu.freshness AS last_consolidated,
        cu.unit_id AS existing_unit_id,
        cu.version AS current_version
    FROM entities e
    LEFT JOIN models m ON e.model_id = m.model_id
    LEFT JOIN consolidated_units cu ON cu.subject_entity = e.entity_id
                                    AND cu.status = 'current'
    WHERE e.engagement_id = $1
      AND e.status = 'active'
      AND e.observation_count >= 2    -- don't consolidate entities with < 2 observations
),
entity_new_material AS (
    -- How much new material exists since last consolidation?
    SELECT
        elc.entity_id,
        elc.name,
        elc.entity_type,
        elc.model_name,
        elc.observation_count,
        elc.existing_unit_id,
        elc.current_version,
        COUNT(o.observation_id) AS new_observations,
        COUNT(DISTINCT r.relationship_id) AS new_relationships
    FROM entity_last_consolidated elc
    LEFT JOIN observations o ON o.engagement_id = $1
        AND o.created_at > COALESCE(elc.last_consolidated, '1970-01-01'::timestamptz)
        AND (
            o.metadata->'entities_referenced' ? elc.name
            OR o.raw_text ILIKE '%' || elc.name || '%'
        )
    LEFT JOIN relationships r ON (r.from_entity = elc.entity_id OR r.to_entity = elc.entity_id)
        AND r.engagement_id = $1
        AND r.last_confirmed > COALESCE(elc.last_consolidated, '1970-01-01'::timestamptz)
    GROUP BY elc.entity_id, elc.name, elc.entity_type, elc.model_name,
             elc.observation_count, elc.existing_unit_id, elc.current_version
)
SELECT *
FROM entity_new_material
WHERE new_observations > 0 OR new_relationships > 0
   OR existing_unit_id IS NULL    -- never consolidated
ORDER BY
    (CASE WHEN existing_unit_id IS NULL THEN 1 ELSE 0 END) DESC,  -- unconsolidated first
    new_observations DESC
LIMIT 30;    -- cap per consolidation run
```

### 3.3 Material Gathering

For each stale entity, gather all relevant material for synthesis.

```python
async def gather_consolidation_material(
    entity_id: UUID,
    entity_name: str,
    engagement_id: UUID,
    pool: asyncpg.Pool,
) -> ConsolidationMaterial:
    """Gather all knowledge about an entity for synthesis."""
    async with pool.acquire() as conn:
        # 1. All relationships involving this entity
        relationships = await conn.fetch("""
            SELECT
                CASE WHEN r.from_entity = $1 THEN e2.name ELSE e1.name END AS other_entity,
                CASE WHEN r.from_entity = $1 THEN 'outgoing' ELSE 'incoming' END AS direction,
                r.relationship_type,
                r.confidence,
                array_length(r.evidence, 1) AS evidence_count
            FROM relationships r
            JOIN entities e1 ON r.from_entity = e1.entity_id
            JOIN entities e2 ON r.to_entity = e2.entity_id
            WHERE r.engagement_id = $2
              AND (r.from_entity = $1 OR r.to_entity = $1)
            ORDER BY r.confidence DESC
        """, entity_id, engagement_id)

        # 2. All observations referencing this entity
        observations = await conn.fetch("""
            SELECT
                o.raw_text,
                o.observation_type,
                o.source_ref,
                o.worker_id,
                o.created_at,
                o.metadata
            FROM observations o
            WHERE o.engagement_id = $2
              AND (
                  o.metadata->'entities_referenced' ? $3
                  OR o.raw_text ILIKE '%' || $3 || '%'
              )
            ORDER BY o.created_at
            LIMIT 50    -- cap to avoid context overflow
        """, entity_id, engagement_id, entity_name)

        # 3. Cross-model alignments
        alignments = await conn.fetch("""
            SELECT
                CASE WHEN a.from_entity = $1 THEN e2.name ELSE e1.name END AS aligned_entity,
                CASE WHEN a.from_entity = $1 THEN m2.name ELSE m1.name END AS other_model,
                a.alignment_type,
                a.confidence,
                a.notes
            FROM alignments a
            JOIN entities e1 ON a.from_entity = e1.entity_id
            LEFT JOIN models m1 ON e1.model_id = m1.model_id
            JOIN entities e2 ON a.to_entity = e2.entity_id
            LEFT JOIN models m2 ON e2.model_id = m2.model_id
            WHERE a.engagement_id = $2
              AND (a.from_entity = $1 OR a.to_entity = $1)
        """, entity_id, engagement_id)

        # 4. Entity properties and aliases
        entity = await conn.fetchrow("""
            SELECT e.name, e.entity_type, e.aliases, e.properties, e.observation_count,
                   m.name AS model_name, m.purpose AS model_purpose
            FROM entities e
            LEFT JOIN models m ON e.model_id = m.model_id
            WHERE e.entity_id = $1
        """, entity_id)

    return ConsolidationMaterial(
        entity_id=entity_id,
        entity=entity,
        relationships=relationships,
        observations=observations,
        alignments=alignments,
    )


@dataclass
class ConsolidationMaterial:
    entity_id: UUID
    entity: asyncpg.Record
    relationships: list[asyncpg.Record]
    observations: list[asyncpg.Record]
    alignments: list[asyncpg.Record]
```

### 3.4 Synthesis Prompt (Cross-Model Aware)

```python
CONSOLIDATION_SYSTEM_PROMPT = """You are a knowledge synthesizer. Your job is to produce a dense, attributed summary of everything known about an entity across all sources and models.

## Requirements

1. **Dense.** Target 150-400 tokens. Every sentence should carry information.
2. **Attributed.** Reference source types ("per Confluence docs", "seen in codebase", "from Jira tickets").
3. **Cross-model aware.** If this entity appears in multiple models, describe how each model sees it and where they agree/disagree.
4. **Structured.** Use this format:

```
## [Entity Name] ([entity_type])
(Consolidated from N observations across M sources, N alignments)

[1-2 sentence core description]

Relationships:
- [direction] [relationship_type] [other_entity] (confidence: X, evidence: N)
- ...

Cross-Model Appearances:
- [model_name] ([purpose]): [how this entity appears in that model]
- [model_name] ([purpose]): [how it appears there, noting alignment/divergence]

Open Questions:
- [things we don't know yet]
- [contradictions still unresolved]
```

3. **Highlight surprises.** If observations challenge each other, say so explicitly.
4. **Note gaps.** If there's an obvious area not yet explored, mention it.
5. **Don't invent.** Only include information present in the material. If something is uncertain, say so.

## Output

Return ONLY the consolidated summary text. No preamble, no explanation.
"""


def build_consolidation_user_message(material: ConsolidationMaterial) -> str:
    """Format gathered material into the synthesis prompt."""
    sections = []

    e = material.entity
    sections.append(f"Entity: {e['name']} ({e['entity_type']})")
    if e['model_name']:
        sections.append(f"Primary model: {e['model_name']} (purpose: {e['model_purpose']})")
    sections.append(f"Observation count: {e['observation_count']}")
    if e['aliases']:
        sections.append(f"Aliases: {', '.join(e['aliases'])}")

    sections.append("\n## Relationships")
    for r in material.relationships:
        direction = "→" if r['direction'] == 'outgoing' else "←"
        sections.append(
            f"  {direction} {r['relationship_type']} {r['other_entity']} "
            f"(confidence: {r['confidence']:.2f}, evidence: {r['evidence_count']})"
        )

    sections.append("\n## Observations (chronological)")
    for o in material.observations:
        sections.append(
            f"  [{o['observation_type']}] ({o['source_ref']}, {o['worker_id']}): "
            f"{o['raw_text'][:500]}"
        )

    sections.append("\n## Cross-Model Alignments")
    if material.alignments:
        for a in material.alignments:
            sections.append(
                f"  {a['alignment_type']} → {a['aligned_entity']} "
                f"(model: {a['other_model']}, confidence: {a['confidence']:.2f})"
                + (f" — {a['notes']}" if a['notes'] else "")
            )
    else:
        sections.append("  No cross-model alignments yet.")

    return "\n".join(sections)
```

### 3.5 Cross-Link Detection

This is the most valuable step — finding non-obvious connections between entities that co-occur in observations without explicit relationships.

```python
async def detect_cross_links(
    engagement_id: UUID,
    pool: asyncpg.Pool,
    embedder: EmbeddingService,
    min_co_occurrence: int = 3,
    similarity_threshold: float = 0.6,
) -> list[CrossLink]:
    """
    Find entity pairs that co-occur in observations but have
    no explicit relationship. These are candidates for emergent
    connections that nobody noticed.

    Two detection methods:
    1. Co-occurrence: entities mentioned in the same observations
    2. Embedding proximity of consolidated summaries
    """
    async with pool.acquire() as conn:
        # Method 1: Co-occurrence in observations
        co_occurrences = await conn.fetch("""
            WITH entity_observations AS (
                -- Map observations to the entities they reference
                SELECT
                    o.observation_id,
                    e.entity_id,
                    e.name AS entity_name
                FROM observations o
                JOIN entities e ON e.engagement_id = o.engagement_id
                    AND e.status = 'active'
                    AND (
                        o.metadata->'entities_referenced' ? e.name
                        OR o.raw_text ILIKE '%' || e.name || '%'
                    )
                WHERE o.engagement_id = $1
            )
            SELECT
                eo1.entity_id AS entity_a,
                eo1.entity_name AS entity_a_name,
                eo2.entity_id AS entity_b,
                eo2.entity_name AS entity_b_name,
                COUNT(DISTINCT eo1.observation_id) AS co_occurrence_count
            FROM entity_observations eo1
            JOIN entity_observations eo2
                ON eo1.observation_id = eo2.observation_id
                AND eo1.entity_id < eo2.entity_id
            -- Exclude pairs that already have a relationship
            WHERE NOT EXISTS (
                SELECT 1 FROM relationships r
                WHERE r.engagement_id = $1
                  AND ((r.from_entity = eo1.entity_id AND r.to_entity = eo2.entity_id)
                    OR (r.from_entity = eo2.entity_id AND r.to_entity = eo1.entity_id))
            )
            -- Exclude pairs that already have an alignment
            AND NOT EXISTS (
                SELECT 1 FROM alignments a
                WHERE (a.from_entity = eo1.entity_id AND a.to_entity = eo2.entity_id)
                   OR (a.from_entity = eo2.entity_id AND a.to_entity = eo1.entity_id)
            )
            GROUP BY eo1.entity_id, eo1.entity_name, eo2.entity_id, eo2.entity_name
            HAVING COUNT(DISTINCT eo1.observation_id) >= $2
            ORDER BY co_occurrence_count DESC
            LIMIT 20
        """, engagement_id, min_co_occurrence)

        # Method 2: Embedding proximity of consolidated summaries
        # (entities that are semantically similar but not linked)
        embedding_neighbors = await conn.fetch("""
            SELECT
                cu1.subject_entity AS entity_a,
                e1.name AS entity_a_name,
                cu2.subject_entity AS entity_b,
                e2.name AS entity_b_name,
                1 - (cu1.embedding <=> cu2.embedding) AS similarity
            FROM consolidated_units cu1
            JOIN consolidated_units cu2
                ON cu1.engagement_id = cu2.engagement_id
                AND cu1.unit_id < cu2.unit_id
                AND cu1.subject_entity != cu2.subject_entity
            JOIN entities e1 ON cu1.subject_entity = e1.entity_id
            JOIN entities e2 ON cu2.subject_entity = e2.entity_id
            WHERE cu1.engagement_id = $1
              AND cu1.status = 'current'
              AND cu2.status = 'current'
              AND 1 - (cu1.embedding <=> cu2.embedding) > $2
              -- Not already related
              AND NOT EXISTS (
                  SELECT 1 FROM relationships r
                  WHERE r.engagement_id = $1
                    AND ((r.from_entity = cu1.subject_entity AND r.to_entity = cu2.subject_entity)
                      OR (r.from_entity = cu2.subject_entity AND r.to_entity = cu1.subject_entity))
              )
            ORDER BY similarity DESC
            LIMIT 20
        """, engagement_id, similarity_threshold)

    # Merge and deduplicate
    cross_links = []
    seen_pairs = set()

    for row in co_occurrences:
        pair = (row['entity_a'], row['entity_b'])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            cross_links.append(CrossLink(
                entity_a_id=row['entity_a'],
                entity_a_name=row['entity_a_name'],
                entity_b_id=row['entity_b'],
                entity_b_name=row['entity_b_name'],
                detection_method='co_occurrence',
                score=row['co_occurrence_count'],
            ))

    for row in embedding_neighbors:
        pair = (row['entity_a'], row['entity_b'])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            cross_links.append(CrossLink(
                entity_a_id=row['entity_a'],
                entity_a_name=row['entity_a_name'],
                entity_b_id=row['entity_b'],
                entity_b_name=row['entity_b_name'],
                detection_method='embedding_proximity',
                score=row['similarity'],
            ))

    return cross_links


@dataclass
class CrossLink:
    entity_a_id: UUID
    entity_a_name: str
    entity_b_id: UUID
    entity_b_name: str
    detection_method: str     # 'co_occurrence' or 'embedding_proximity'
    score: float              # co-occurrence count or similarity score
```

### 3.6 Complete Consolidation Run

```python
async def run_consolidation(
    engagement_id: UUID,
    pool: asyncpg.Pool,
    llm: LLMClient,
    embedder: EmbeddingService,
    event_bus: EventBus,
) -> ConsolidationResult:
    """
    Full consolidation run ("sleep" process).

    Steps:
    1. Find stale entities
    2. For each: gather material, synthesize, store
    3. Detect cross-links
    4. Record cross-links as observations
    """
    units_created = 0
    units_updated = 0

    # Step 1: Find stale entities
    async with pool.acquire() as conn:
        stale_entities = await conn.fetch(STALE_ENTITY_QUERY, engagement_id)

    # Step 2: Synthesize for each stale entity
    for entity_row in stale_entities:
        entity_id = entity_row['entity_id']

        # Gather material
        material = await gather_consolidation_material(
            entity_id, entity_row['name'], engagement_id, pool,
        )

        # Skip if insufficient material
        if len(material.observations) < 2 and len(material.relationships) < 1:
            continue

        # Synthesize (LLM call)
        user_message = build_consolidation_user_message(material)
        response = await llm.call(
            system=CONSOLIDATION_SYSTEM_PROMPT,
            user=user_message,
            max_tokens=1024,
        )
        summary = response.text.strip()

        # Generate embedding for the consolidated summary
        embedding = await embedder.embed(summary)

        # Count tokens (rough estimate: chars / 4)
        token_count = len(summary) // 4

        # Collect related entity IDs
        related_ids = set()
        for r in material.relationships:
            # We'd need the entity_id of the 'other' entity
            # (simplified here — actual impl queries by name)
            pass

        # Collect source observation IDs
        source_obs_ids = [o['observation_id'] for o in material.observations if 'observation_id' in o]

        # Store or update consolidated unit
        async with pool.acquire() as conn:
            existing_unit_id = entity_row.get('existing_unit_id')

            if existing_unit_id:
                # Mark old version as stale, create new version
                await conn.execute("""
                    UPDATE consolidated_units
                    SET status = 'stale'
                    WHERE unit_id = $1
                """, existing_unit_id)

                new_version = (entity_row.get('current_version') or 0) + 1
                await conn.execute("""
                    INSERT INTO consolidated_units
                        (engagement_id, subject_entity, summary, embedding,
                         source_observations, token_count, version, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'current')
                """, engagement_id, entity_id, summary, embedding,
                     source_obs_ids, token_count, new_version)
                units_updated += 1
            else:
                await conn.execute("""
                    INSERT INTO consolidated_units
                        (engagement_id, subject_entity, summary, embedding,
                         source_observations, token_count, version, status)
                    VALUES ($1, $2, $3, $4, $5, $6, 1, 'current')
                """, engagement_id, entity_id, summary, embedding,
                     source_obs_ids, token_count)
                units_created += 1

    # Step 3: Cross-link detection
    cross_links = await detect_cross_links(engagement_id, pool, embedder)

    # Step 4: Record cross-links as observations
    async with pool.acquire() as conn:
        for link in cross_links:
            await conn.execute("""
                INSERT INTO observations
                    (engagement_id, worker_id, source_ref, raw_text,
                     observation_type, metadata)
                VALUES ($1, 'consolidation', 'cross-link-detection', $2,
                        'insight', $3)
            """,
                engagement_id,
                f"Cross-link detected: '{link.entity_a_name}' and '{link.entity_b_name}' "
                f"co-appear frequently ({link.detection_method}: {link.score:.2f}) "
                f"but have no explicit relationship. This may indicate a hidden dependency or shared context.",
                json.dumps({
                    "entities_referenced": [link.entity_a_name, link.entity_b_name],
                    "impact_type": "expansion",
                    "detection_method": link.detection_method,
                    "score": link.score,
                }),
            )

    # Emit completion event
    await event_bus.emit(ConsolidationCompleted(
        engagement_id=engagement_id,
        units_created=units_created,
        units_updated=units_updated,
    ))

    return ConsolidationResult(
        units_created=units_created,
        units_updated=units_updated,
        cross_links_found=len(cross_links),
    )


@dataclass
class ConsolidationResult:
    units_created: int
    units_updated: int
    cross_links_found: int
```

---

## 4. Component Interaction

### 4.1 Supervisor Orchestration

How the three components fit into the supervisor's main loop:

```python
class Supervisor:
    """Manages all runtime components. No LLM calls."""

    def __init__(
        self,
        engagement_id: UUID,
        pool: asyncpg.Pool,
        llm: LLMClient,
        embedder: EmbeddingService,
        event_bus: EventBus,
        config: SupervisorConfig,
    ):
        self.engagement_id = engagement_id
        self.pool = pool
        self.llm = llm
        self.embedder = embedder
        self.event_bus = event_bus
        self.config = config

        self.coordinator: CoordinatorState | None = None
        self.active_workers: dict[UUID, asyncio.Task] = {}
        self.worker_semaphore = asyncio.Semaphore(config.max_concurrent_workers)
        self.consolidation_trigger = ConsolidationTrigger()
        self.cycle_number = 0
        self.stopped = False

    async def run(self):
        """Main loop. Runs until convergence, budget, or manual stop."""
        await self._init_coordinator()

        while not self.stopped:
            self.cycle_number += 1

            # 1. Reap completed workers
            await self._reap_completed_workers()

            # 2. Run coordinator cycle (if no pending workers from last cycle)
            if self._ready_for_coordinator_cycle():
                cycle_result = await coordinator_cycle(
                    engagement_id=self.engagement_id,
                    coordinator_id=self.coordinator.instance_id,
                    cycle_number=self.cycle_number,
                    last_cycle_at=self.coordinator.last_cycle_at,
                    pool=self.pool,
                    llm=self.llm,
                    convergence_config=self.config.convergence,
                )

                self.coordinator.last_cycle_at = datetime.now(timezone.utc)

                # Emit cycle event
                await self.event_bus.emit(CoordinatorCycleCompleted(
                    engagement_id=self.engagement_id,
                    coordinator_id=self.coordinator.instance_id,
                    cycle_number=self.cycle_number,
                    tasks_dispatched=len(cycle_result.actions),
                    gaps_remaining=cycle_result.cycle_stats.gaps_found,
                ))

                # Check convergence
                if cycle_result.convergence_signal:
                    await self._handle_convergence()
                    break

                # Dispatch workers
                for action in cycle_result.actions:
                    if isinstance(action, DispatchWorker):
                        await self._dispatch_worker(action.directive)

            # 3. Run consolidation if triggered
            if await self.consolidation_trigger.should_consolidate(
                self.engagement_id, self.pool,
            ):
                # Run consolidation as a non-blocking task
                asyncio.create_task(
                    run_consolidation(
                        self.engagement_id, self.pool,
                        self.llm, self.embedder, self.event_bus,
                    )
                )

            # 4. Check budget
            if await self._budget_exhausted():
                await self._handle_budget_exhausted()
                break

            # 5. Wait before next cycle
            await asyncio.sleep(self.config.cycle_interval_seconds)

    async def _dispatch_worker(self, directive: TaskDirective):
        """Create task record and dispatch worker coroutine."""
        # Create task record
        async with self.pool.acquire() as conn:
            task_id = await conn.fetchval("""
                INSERT INTO tasks
                    (engagement_id, coordinator_id, directive, source_type,
                     source_ref, max_scope, relevant_context, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'queued')
                RETURNING task_id
            """, self.engagement_id, self.coordinator.instance_id,
                 directive.directive, directive.source_type,
                 directive.source_ref, directive.max_scope,
                 directive.relevant_context)

            task = await conn.fetchrow(
                "SELECT * FROM tasks WHERE task_id = $1", task_id,
            )

        # Get connector for this source type
        connector = await self._get_connector(directive.source_type, directive.source_ref)

        # Create graph writer for this worker
        graph = GraphWriter(
            engagement_id=self.engagement_id,
            model_id=None,  # determined during task
            worker_id=f"worker-{task_id.hex[:8]}",
            source_ref=directive.source_ref,
            pool=self.pool,
            embedder=self.embedder,
        )

        # Dispatch as bounded concurrent task
        async def _bounded_worker():
            async with self.worker_semaphore:
                return await run_worker(
                    task=task,
                    connector=connector,
                    graph=graph,
                    llm=self.llm,
                    budget=WorkerBudget(max_tokens=self.config.worker_max_tokens),
                    event_bus=self.event_bus,
                )

        worker_task = asyncio.create_task(_bounded_worker())
        self.active_workers[task_id] = worker_task

    def _ready_for_coordinator_cycle(self) -> bool:
        """Don't run coordinator while many workers are still in flight."""
        return len(self.active_workers) < self.config.max_concurrent_workers // 2

    async def _reap_completed_workers(self):
        """Collect results from finished workers."""
        completed = []
        for task_id, worker_task in list(self.active_workers.items()):
            if worker_task.done():
                try:
                    result = worker_task.result()
                except Exception as e:
                    result = WorkerResult(
                        task_id=task_id,
                        worker_id=f"worker-{task_id.hex[:8]}",
                        entities_written=0,
                        relationships_written=0,
                        observations_written=0,
                        followups_suggested=0,
                        scope_overflow=False,
                        error=str(e),
                    )
                completed.append((task_id, result))

        for task_id, result in completed:
            del self.active_workers[task_id]
            # Fetch task record for the handler
            async with self.pool.acquire() as conn:
                task = await conn.fetchrow(
                    "SELECT * FROM tasks WHERE task_id = $1", task_id,
                )
            await self.handle_worker_result(result, task)


@dataclass
class SupervisorConfig:
    max_concurrent_workers: int = 10
    worker_max_tokens: int = 100_000
    cycle_interval_seconds: float = 30.0
    convergence: ConvergenceConfig = field(default_factory=ConvergenceConfig)
```

### 4.2 Data Flow Summary

```
                              ┌─────────────────────────────────┐
                              │         SUPERVISOR               │
                              │  (Python: lifecycle + budget)    │
                              └──────┬───────────┬──────────────┘
                                     │           │
                    triggers cycle    │           │  dispatches workers
                                     │           │
              ┌──────────────────────▼─┐   ┌────▼──────────────────┐
              │   COORDINATOR CYCLE     │   │   WORKER POOL          │
              │                         │   │                        │
              │  projection SQL ────┐   │   │  source tools ──► read │
              │  detect issues ──┐  │   │   │  graph tools ──► write │
              │  rank issues ─┐  │  │   │   │                    │   │
              │               │  │  │   │   │  5-10 LLM calls    │   │
              │  1 LLM call ──┤  │  │   │   │  per worker        │   │
              │               │  │  │   │   │                    │   │
              │  directives ──┘  │  │   │   └────────┬───────────┘   │
              │                  │  │   │            │               │
              └──────────────────┘  │   │   writes to DB             │
                                    │   │   incrementally             │
                   reads from       │   │            │               │
                   graph ───────────┘   │            │               │
                                        │            ▼               │
                              ┌─────────┴────────────────────────┐
                              │         POSTGRESQL                │
                              │                                   │
                              │  observations (Tier 1) ◄── workers│
                              │  entities (Tier 2)     ◄── workers│
                              │  relationships (Tier 2) ◄── workers│
                              │  alignments            ◄── coord  │
                              │  consolidated_units (Tier 3)      │
                              │       ▲                           │
                              │       │                           │
                              └───────┼───────────────────────────┘
                                      │
                              ┌───────┴───────────────────────┐
                              │  CONSOLIDATION ("sleep")       │
                              │                                │
                              │  stale entity SQL              │
                              │  gather material               │
                              │  1 LLM call per entity         │
                              │  cross-link detection SQL      │
                              │  store consolidated units       │
                              └────────────────────────────────┘
```

### 4.3 LLM Call Budget Per Full Cycle

```
Coordinator:           1 LLM call     (~10k input, ~2k output)
Workers (5 active):    ~35 LLM calls  (~5k input each, ~1k output each)
Consolidation:         ~10 LLM calls  (~3k input each, ~500 output each)
                       ──────────────
Total per cycle:       ~46 LLM calls

At ~30 second cycle interval:
  ~92 LLM calls/minute during active discovery
  ~5,500 calls/hour

Cost estimate (Claude Haiku 4.5):
  Input:  ~46 calls × ~7k tokens = ~322k input tokens × $0.80/MTok = $0.26
  Output: ~46 calls × ~1.5k tokens = ~69k output tokens × $4/MTok = $0.28
  Total per cycle: ~$0.54
  Per hour: ~$65

Cost estimate (Claude Sonnet 4.5, for coordinator only):
  Coordinator: ~$0.03/cycle (10k input + 2k output at Sonnet rates)
  Workers + consolidation: same as above (Haiku)
  Total per cycle: ~$0.57
```

### 4.4 Schema Additions

The relationship uniqueness constraint referenced in the worker spec:

```sql
-- Required addition to schema.sql

ALTER TABLE relationships
ADD CONSTRAINT uq_relationship_triple
UNIQUE (engagement_id, from_entity, to_entity, relationship_type);

-- Index for observation entity reference lookups (used by consolidation)
CREATE INDEX idx_observations_metadata_entities
ON observations USING gin ((metadata->'entities_referenced'));

-- Index for observation impact type (used by convergence checking)
CREATE INDEX idx_observations_impact_type
ON observations ((metadata->>'impact_type'))
WHERE metadata->>'impact_type' IS NOT NULL;

-- Enhanced convergence_log columns (added 2026-02-20)
ALTER TABLE convergence_log
ADD COLUMN weighted_ratio FLOAT,
ADD COLUMN expansion_rate INT,
ADD COLUMN expansion_acceleration FLOAT,
ADD COLUMN per_source_ratios JSONB DEFAULT '{}',
ADD COLUMN secondary_convergence BOOLEAN DEFAULT FALSE;

-- Community analysis table (added 2026-02-20)
CREATE TABLE community_analysis (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    cycle_number INT NOT NULL,
    algorithm TEXT NOT NULL,          -- 'louvain' or 'leiden'
    entity_count INT NOT NULL,
    community_count INT NOT NULL,
    modularity FLOAT,
    communities JSONB NOT NULL,       -- [{community_id, entity_ids, label}]
    hub_entities JSONB DEFAULT '[]',  -- [{entity_id, degree, community_id}]
    bridge_entities JSONB DEFAULT '[]', -- [{entity_id, communities_connected}]
    isolated_entities JSONB DEFAULT '[]', -- [entity_id, ...]
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_community_analysis_engagement
ON community_analysis (engagement_id, cycle_number DESC);
```

---

## 5. Community Detection

### Purpose

The knowledge graph accumulates entities and relationships, but the coordinator lacks structural insight into **topic clusters**. Community detection identifies:
- **Topic clusters** — groups of densely connected entities (e.g., "authentication subsystem", "payment processing pipeline")
- **Hub entities** — high-degree nodes that connect many others (e.g., a shared database, a central API gateway)
- **Bridge entities** — nodes that connect otherwise separate clusters (e.g., an integration service linking two domains)
- **Isolated clusters** — groups with no connections to the rest of the graph (potential exploration targets)

This information feeds the coordinator's projection, enabling better directive generation (e.g., "explore the bridge between cluster A and cluster B" or "the payment cluster is well-mapped but the auth cluster has gaps").

### Algorithm Selection

| Condition | Algorithm | Library | Rationale |
|---|---|---|---|
| Entity count < 500 | Louvain | networkx | Good quality, pure Python, no extra dependency |
| Entity count >= 500 | Leiden | igraph (python-igraph) | Better quality on larger graphs, C-backed performance |

Both algorithms are deterministic given a seed and produce hierarchical community assignments with modularity scores.

### Integration Point

Community detection runs as a **post-cycle step in the supervisor**, after all workers complete and before the next coordinator cycle. This ensures the coordinator's projection includes fresh structural analysis.

```python
async def run_community_detection(
    engagement_id: UUID,
    cycle_number: int,
    pool: asyncpg.Pool,
) -> CommunityAnalysis | None:
    """
    Build entity graph from relationships, detect communities, store results.
    Runs in executor (CPU-bound graph algorithms, same pattern as embeddings).
    Returns None if fewer than 5 entities (not enough for meaningful communities).
    """
    async with pool.acquire() as conn:
        entities = await conn.fetch("""
            SELECT entity_id, name, entity_type
            FROM entities
            WHERE engagement_id = $1 AND status = 'active'
        """, engagement_id)

        relationships = await conn.fetch("""
            SELECT from_entity, to_entity, relationship_type, confidence
            FROM relationships
            WHERE engagement_id = $1
        """, engagement_id)

    if len(entities) < 5:
        return None

    # Run graph algorithm in executor (CPU-bound)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        _detect_communities,
        entities,
        relationships,
    )

    # Store results
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO community_analysis
                (engagement_id, cycle_number, algorithm, entity_count,
                 community_count, modularity, communities,
                 hub_entities, bridge_entities, isolated_entities)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, engagement_id, cycle_number, result.algorithm,
            len(entities), result.community_count, result.modularity,
            json.dumps(result.communities), json.dumps(result.hub_entities),
            json.dumps(result.bridge_entities), json.dumps(result.isolated_entities))

    return result


def _detect_communities(
    entities: list[asyncpg.Record],
    relationships: list[asyncpg.Record],
) -> CommunityResult:
    """Synchronous community detection. Runs in executor."""
    entity_count = len(entities)

    if entity_count < 500:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        G = nx.Graph()
        for e in entities:
            G.add_node(str(e['entity_id']), name=e['name'], type=e['entity_type'])
        for r in relationships:
            G.add_edge(str(r['from_entity']), str(r['to_entity']),
                       type=r['relationship_type'], weight=r['confidence'])

        communities_sets = louvain_communities(G, seed=42)
        modularity = nx.community.modularity(G, communities_sets)
        algorithm = "louvain"
    else:
        import igraph as ig

        id_map = {str(e['entity_id']): i for i, e in enumerate(entities)}
        G = ig.Graph(n=len(entities), directed=False)
        edges = [(id_map[str(r['from_entity'])], id_map[str(r['to_entity'])])
                 for r in relationships
                 if str(r['from_entity']) in id_map and str(r['to_entity']) in id_map]
        G.add_edges(edges)

        partition = G.community_leiden(objective_function="modularity")
        communities_sets = [set(str(entities[i]['entity_id']) for i in comm)
                           for comm in partition]
        modularity = partition.modularity
        algorithm = "leiden"

    # Identify hubs (top 10% by degree) and bridges (nodes in multiple communities' neighborhoods)
    # ... (implementation detail, follows standard graph analysis patterns)

    return CommunityResult(
        algorithm=algorithm,
        community_count=len(communities_sets),
        modularity=modularity,
        communities=[...],  # formatted for JSONB storage
        hub_entities=[...],
        bridge_entities=[...],
        isolated_entities=[...],
    )


@dataclass
class CommunityResult:
    algorithm: str
    community_count: int
    modularity: float
    communities: list[dict]
    hub_entities: list[dict]
    bridge_entities: list[dict]
    isolated_entities: list[str]
```

### Coordinator Projection Integration

The community analysis is included in the coordinator's projection as a structural summary:

```python
# Added to CoordinatorProjection (Section 1.2)
community_summary: str | None  # ~500 tokens: cluster count, hubs, bridges, isolated groups
```

The coordinator uses this to generate structurally-aware directives: exploring gaps between clusters, investigating bridge entities, or noting when a cluster is self-contained.

---

*These specs are designed to be implementable directly. SQL queries are tested against the schema in Section 11. Python is pseudocode-level but follows real asyncpg, Pydantic, and asyncio patterns. The LLM interaction follows Anthropic's tool-use API format.*
