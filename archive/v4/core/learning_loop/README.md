# Learning Loop Service (v3)

The Learning Loop is a unified service containing 4 components that work together to extract learning signals from conversations, cluster similar problems, and improve bullet selection over time.

## Architecture (v3, Dec 2025)

```
SESSION → llm.response.received → REFLECTOR (buffers turn data to Redis)
                                      │
SESSION → session.ended ──────────────┘
                                      │
                                      ▼
                               REFLECTOR
                    ┌─────────────────┴─────────────────┐
                    │                                   │
             Turn Analysis                    Counter Updates +
             Attribution                      caused_failure edges
                    │                                   │
                    ▼                                   ▼
             aku.proposed                     attribution.resolved
                    │                                   │
                    ▼                                   ▼
               CURATOR                            CLUSTERER
             (quality gate)                   (cluster assignment)
                    │                                   │
                    ▼                                   ▼
              bullet.accepted                    solved_by edges

SESSION → bullets.requested → ADVISOR → Redis (bullets)
```

**v3 Key Changes (Dec 2025):**
- **REFLECTOR owns feedback loop:** Attribution, counter updates, caused_failure edges, AKU extraction
- **CLUSTERER simplified:** Only cluster assignment and solved_by edges
- **CURATOR as quality gate:** Single entry point for all AKU sources
- **Two-space embeddings:** situation_embedding (retrieval) + assertion_embedding (dedup)
- **Only two edge types:** `solved_by` and `caused_failure` (removed `similar_to`, `not_applicable_for`)

## Components

### REFLECTOR (`reflector/`)
Owns the entire feedback loop: turn analysis, attribution, counter updates, edge creation, AKU extraction.

- **Consumes:** `llm.response.received` (buffers turns), `session.ended` (triggers analysis)
- **Produces:** `aku.proposed`, `attribution.resolved`
- **Key Features:**
  - **Turn-by-Turn Analysis:** Analyzes each turn for sub-task, micro-outcome, bullet attribution
  - **Counter Updates:** Directly updates helpful/harmful/neutral counts based on micro-outcomes
  - **Edge Creation:** Creates `caused_failure` edges for harmful bullets
  - **AKU Extraction:** Detects stuck→recovery patterns and extracts learning moments
  - **Outcome Reconciliation:** Forces final turn to 'solved' if session succeeded

### CURATOR (`curator/`)
Quality gate and deduplication for all AKU sources.

- **Consumes:** `aku.proposed` (from REFLECTOR and STRATEGIST)
- **Produces:** `bullet.accepted`, `bullet.merged`
- **Key Features:**
  - **Dedup on assertion_embedding:** Allows same situation with different solutions
  - **Source-based thresholds:** reflector=0.70, strategist=0.90
  - **Two-space storage:** Stores both situation_embedding and assertion_embedding
  - **Status lifecycle:** candidate → active → archived

### CLUSTERER (`clusterer/`)
Simplified to cluster assignment and solved_by edges only.

- **Consumes:** `attribution.resolved`, `bullet.accepted`, `bullet.merged`
- **Produces:** Cluster assignments, solved_by edges in PostgreSQL
- **Key Features:**
  - **Cluster Assignment:** Assigns turns to problem_clusters by situation_embedding similarity
  - **solved_by Edges:** Creates edges from cluster to bullets that helped
  - **Cluster Statistics:** Updates turn_count, success_count, failure_count
  - **Status Transitions:** candidate→active (3 confirmations), active→archived (3 failures)

### ADVISOR (`advisor/`)
Thompson Sampling selection with cluster-specific filtering.

- **Consumes:** `bullets.requested` events
- **Produces:** Bullet recommendations via Redis
- **Key Features:**
  - **Vector Search:** On situation_embedding (threshold=0.50)
  - **Cluster Solutions:** Via solved_by edges
  - **Cluster Exclusions:** Via caused_failure edges (cluster-specific filtering)
  - **Thompson Sampling:** `score = similarity × thompson_sample × age_decay`
  - **TS Floor:** Bullets below 25% floor excluded (global baseline)
  - **Returns cluster_id:** For next turn's filtering

## Database Schema

| Table | Purpose |
|-------|---------|
| `playbook_bullets` | Bullet storage with situation_embedding, assertion_embedding, counters |
| `session_turns` | Turn-level data with situation_embedding |
| `problem_clusters` | Cluster centroids (384d vectors) |
| `knowledge_edges` | Graph edges (solved_by, caused_failure only) |

## Event Flow (v3)

```
SESSION                        REFLECTOR                      CLUSTERER
   │                              │                              │
   │ llm.response.received        │                              │
   ├─────────────────────────────►│                              │
   │                       buffer_turn()                         │
   │                              │                              │
   │ session.ended                │                              │
   ├─────────────────────────────►│                              │
   │                       _analyze_turns()                      │
   │                       - Per-turn micro-outcome              │
   │                       - Bullet attribution                  │
   │                              │                              │
   │                       _update_counters()                    │
   │                       - helpful++/harmful++/neutral++       │
   │                              │                              │
   │                       _create_edges()                       │
   │                       - caused_failure for harmed bullets   │
   │                              │                              │
   │                       _extract_akus()                       │
   │                       - Detect stuck→recovery               │
   │                       ──────► aku.proposed → CURATOR        │
   │                              │                              │
   │                       attribution.resolved                  │
   │                              ├─────────────────────────────►│
   │                              │                       _handle_attribution()
   │                              │                       - Assign to cluster
   │                              │                       - Create solved_by edges
   │                              │                       - Update cluster stats
```

## Configuration

```bash
# Thompson Sampling
THOMPSON_AGE_DECAY=0.005           # 0.5% daily decay
THOMPSON_FLOOR=0.25                # Minimum TS score

# Clustering
CLUSTER_ASSIGNMENT_THRESHOLD=0.4   # Max distance for assignment

# Deduplication thresholds
CURATOR_DEDUP_REFLECTOR=0.70       # For REFLECTOR-sourced AKUs
CURATOR_DEDUP_STRATEGIST=0.90      # For STRATEGIST-sourced AKUs
```

## Development

### Running Locally

```bash
# Start with other services
docker-compose up -d learning-loop

# View logs
docker-compose logs -f learning-loop

# FAST: Restart after code changes (volume mounted)
docker-compose restart learning-loop

# SLOW: Only rebuild after dependency changes (requirements.txt)
docker-compose build learning-loop --quiet
docker-compose up -d learning-loop
```

### Testing

```bash
# Run tests
pytest core/learning_loop/tests -v

# Run specific component tests
pytest core/learning_loop/tests/unit/test_advisor_selector.py -v
pytest core/learning_loop/tests/unit/test_reflector_service.py -v
```

## Key Design Decisions

### Two Dialogues Architecture

The Learning Loop operates through two distinct feedback loops:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TACTICAL DIALOGUE                                     │
│                    (Which bullets work?)                                     │
│                                                                              │
│   ADVISOR ──────► shows bullets ──────► SESSION                             │
│      ▲                                     │                                 │
│      │                                     ▼                                 │
│   Thompson                            REFLECTOR                              │
│   Sampling ◄──── counter updates ◄────────┘                                 │
│                  (helpful/harmful)                                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       STRATEGIC DIALOGUE                                     │
│                   (What knowledge is missing?)                               │
│                                                                              │
│   CLUSTERER ──► gap detection ──► LIBRARIAN ──► STRATEGIST                  │
│       ▲                                              │                       │
│       │                                              ▼                       │
│   solved_by    ◄─── target_cluster_id ◄─── CURATOR ◄── aku.proposed         │
│   edge                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Tactical:** Optimizes WITHIN existing knowledge (exploitation)
**Strategic:** EXPANDS knowledge itself (exploration)

The `target_cluster_id` field closes the strategic loop - synthesized bullets link directly to the gaps they were created for.

### REFLECTOR Owns Feedback Loop
- Single service handles attribution, counters, AND edge creation
- No race conditions between counter updates and edge creation
- Clear ownership: REFLECTOR decides what helped/harmed

### Two-Space Embedding Model
- `situation_embedding`: For retrieval - find bullets for similar situations
- `assertion_embedding`: For deduplication - find similar assertions
- Same situation can have different solutions (not duplicates)
- Different situations can share same solution (cross-situation transfer)

### Two-Layer Exclusion
1. **Thompson Sampling Floor (Global):** Bullets below 25% excluded everywhere
2. **caused_failure Edges (Cluster-Specific):** Bullet excluded only for specific problem types

### Simplified Edge Types
- `solved_by`: Cluster → Bullet (positive signal)
- `caused_failure`: Cluster → Bullet (negative signal)
- Removed: `similar_to`, `not_applicable_for`, `refines`, `related_to`

### Cold-Start Handling
- Clusters are created for problem discovery even without bullets
- Cluster statistics (success/failure) only count **guided** turns (bullets_shown > 0)
- Cold-start sessions contribute to problem taxonomy, not effectiveness metrics
- This prevents polluting cluster stats with baseline LLM performance

## Debugging

```sql
-- Check turn-level attribution
SELECT session_id, turn_number, micro_outcome,
       array_length(bullets_helped, 1) as helped,
       array_length(bullets_harmed, 1) as harmed
FROM session_turns ORDER BY created_at DESC LIMIT 10;

-- Check cluster edges
SELECT edge_type, COUNT(*) FROM knowledge_edges
WHERE source_type = 'cluster' GROUP BY edge_type;

-- Check problem clusters
SELECT cluster_id::text, label, turn_count, success_count, failure_count
FROM problem_clusters ORDER BY turn_count DESC LIMIT 10;

-- Check bullet counters
SELECT bullet_id::text, helpful_count, harmful_count, neutral_count, status
FROM playbook_bullets ORDER BY updated_at DESC LIMIT 10;
```
