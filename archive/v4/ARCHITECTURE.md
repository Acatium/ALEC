# ALEC Architecture (v4)

**Adaptive Learning & Execution Core** - A learning system that observes AI interactions, extracts patterns, and improves responses through event-driven architecture.

---

## Core Concept

Conversations generate **AKUs** (Atomic Knowledge Units) that guide the LLM:
- Stored in Redis (24h TTL) for fast reads; permanently stored in PostgreSQL (`akus` table)
- Learning Loop observes sessions, injects relevant AKUs, learns via Thompson Sampling
- System improves autonomously through effectiveness feedback loops

---

## Architecture Layers (v4)

```
┌─────────────────────────────────────────┐
│  Session Layer: session (Port 8008)     │
│  (Pure orchestration: AKUs → LLM)       │
└────────────┬───────────▲────────────────┘
             │           │ writes AKUs
     emits   ▼           │
┌─────────────────────────────────────────┐
│  Event Bus: Kafka                       │
└────────────┬────────────────────────────┘
             │ consumes
             ▼
┌─────────────────────────────────────────┐
│  Learning Loop: 4 Services              │
│  • REFLECTOR: Feedback loop owner       │
│  • CURATOR: Quality gate + dedup        │
│  • CLUSTERER: Cluster assignment        │
│  • ADVISOR: Thompson Sampling selection │
└────────────┬────────────────────────────┘
             │ emits attribution.resolved
             ▼
┌─────────────────────────────────────────┐
│  Agents: Strategic Intelligence         │
│  • LIBRARIAN: Gap detection + hygiene   │
│  • STRATEGIST: LLM synthesis for gaps   │
└────────────┬────────────────────────────┘
             │ reads/writes
             ▼
┌─────────────────────────────────────────┐
│  Storage: PostgreSQL + pgvector         │
└─────────────────────────────────────────┘
```

---

## v4 Key Changes (Dec 2025)

1. **Schema simplification:** `playbook_bullets` → `akus` table (30+ fields → 14 fields)
2. **Renamed columns:** `bullet_id` → `aku_id`, `bullets_helped/harmed` → `akus_helped/harmed`
3. **Removed deprecated fields:** modality, polarity, category, domain, content, tags
4. **Two-space embeddings:** situation_embedding (retrieval) + assertion_embedding (dedup)
5. **Only two edge types:** `solved_by` and `caused_failure` (target_type: 'aku')
6. **Two-layer exclusion:** Thompson Sampling floor (global) + caused_failure edges (cluster-specific)

---

## Services

### Session (Port 8008)
Pure orchestration: reads AKUs from Redis, calls Claude API, emits events to Kafka.
- AKU-enhanced prompts (injected AFTER first user message for prompt caching)
- Windowed conversation history (first turn + last 4 turns)
- Resilient: continues with cached AKUs if Learning Loop slow/down

### Learning Loop (Unified Service)

**REFLECTOR** - Owns the entire feedback loop:
- Buffers turns from `llm.response.received` events
- Analyzes turns on `session.ended` for sub-task, micro-outcome, AKU attribution
- **Counter Updates:** Directly updates helpful/harmful/neutral counts
- **Edge Creation:** Creates `caused_failure` edges for harmful AKUs
- **AKU Extraction:** Detects stuck→recovery patterns, emits `aku.proposed`
- **Outcome Reconciliation:** Forces final turn to 'solved' if session succeeded
- Emits `attribution.resolved` with turn-level data for CLUSTERER

**CURATOR** - Quality gate and deduplication:
- Consumes `aku.proposed` from REFLECTOR and STRATEGIST
- **Dedup on assertion_embedding:** Allows same situation with different solutions
- **Source-based thresholds:** reflector=0.70, strategist=0.90
- **Two-space storage:** Stores both situation_embedding and assertion_embedding
- Emits `aku.accepted` or `aku.merged`

**CLUSTERER** - Simplified to cluster assignment and solved_by edges:
- Consumes `attribution.resolved`, `aku.accepted`, `aku.merged`
- Assigns turns to `problem_clusters` by situation_embedding similarity
- Creates `solved_by` edges for AKUs that helped
- Updates cluster statistics (turn_count, success_count, failure_count)
- Handles status transitions: candidate→active (3 confirmations), active→archived (3 failures)

**ADVISOR** - Thompson Sampling selection with cluster filtering:
- **Vector Search:** On situation_embedding (threshold=0.50)
- **Cluster Solutions:** Via solved_by edges
- **Cluster Exclusions:** Via caused_failure edges (cluster-specific filtering)
- **Scoring:** `final_score = similarity × thompson_sample × age_decay`
- **TS Floor:** AKUs below 25% excluded globally
- **Returns cluster_id:** For next turn's cluster-specific filtering

### Agents Service (Strategic Intelligence)

| Agent | Role | Actions |
|-------|------|---------|
| **LIBRARIAN** | Passive/Analytical | Gap detection, struggling clusters, auto-archive |
| **STRATEGIST** | Active/Strategic | LLM synthesis to fill knowledge gaps |

**LIBRARIAN** - Library intelligence and hygiene:
- Gap detection: clusters with failures but no `solved_by` edges → emits `library.gap.detected`
- Struggling clusters: has solutions but poor success rate (<50%) → emits `library.cluster.struggling`
- Auto-archive: AKUs with harmful_count >= threshold AND harmful > helpful

**STRATEGIST** - LLM synthesis for knowledge gaps:
- Consumes `library.gap.detected`, `library.cluster.struggling`
- **Pre-synthesis dedup:** Checks for similar AKUs BEFORE LLM call
- LLM synthesis: Creates new AKUs to fill knowledge gaps
- Emits `aku.proposed` → flows through CURATOR

---

## Data Structures

### AKU (Atomic Knowledge Unit)

```
aku_id: UUID
situation: "When [general problem description]"
assertion: "Specific actionable advice"
situation_embedding: vector(1536)
assertion_embedding: vector(1536)
helpful_count, harmful_count, neutral_count: int
status: "candidate" | "active" | "archived" | "banned"
source: "reflector" | "strategist" | "human-curated" | ...
cluster_id: UUID (optional)
metadata: JSONB
created_at: timestamp
```

### AKU Storage (`akus` table)

| Field | Purpose |
|-------|---------|
| `situation_embedding` | For retrieval - find AKUs for similar situations |
| `assertion_embedding` | For deduplication - find similar assertions |
| `helpful_count`, `harmful_count`, `neutral_count` | Effectiveness counters |
| `status` | candidate → active → archived |
| `cluster_id` | Link to problem_clusters for graph traversal |

### Events

| Event | Producer | Consumer(s) | Purpose |
|-------|----------|-------------|---------|
| `akus.requested` | session | ADVISOR | Per-turn selection |
| `llm.response.received` | session | REFLECTOR | Buffer turn data |
| `session.ended` | session/eval | REFLECTOR | Trigger analysis |
| `aku.proposed` | REFLECTOR, STRATEGIST | CURATOR | New AKU for quality gate |
| `aku.accepted` | CURATOR | CLUSTERER | New AKU stored |
| `aku.merged` | CURATOR | CLUSTERER | Evidence incremented |
| `attribution.resolved` | REFLECTOR | CLUSTERER | Turn-level attribution |
| `library.gap.detected` | LIBRARIAN | STRATEGIST | Knowledge gap found |
| `library.cluster.struggling` | LIBRARIAN | STRATEGIST | Low success cluster |

### Knowledge Graph Edge Types (v4)

| Edge Type | Meaning | Source→Target | Creator |
|-----------|---------|---------------|---------|
| `solved_by` | Solution worked for problem | cluster→aku | CLUSTERER |
| `caused_failure` | Solution harmed on problem | cluster→aku | REFLECTOR |

**Removed in v4:** `similar_to`, `not_applicable_for`, `refines`, `related_to`

---

## Key Design Decisions

### REFLECTOR Owns Feedback Loop
- Single service handles attribution, counters, AND caused_failure edge creation
- No race conditions between counter updates and edge creation
- Clear ownership: REFLECTOR decides what helped/harmed

### Two-Space Embedding Model
- **situation_embedding:** For retrieval - find AKUs for similar situations
- **assertion_embedding:** For deduplication - find similar assertions
- Same situation can have different solutions (not duplicates)
- Different situations can share same solution (cross-situation transfer)

### Two-Layer Exclusion
1. **Thompson Sampling Floor (Global):** AKUs below 25% excluded everywhere
2. **caused_failure Edges (Cluster-Specific):** AKU excluded only for specific problem types

### Thompson Sampling
- Formula: `score = similarity × thompson_sample × age_decay`
- Alpha: `helpful_count + 1`
- Beta: `harmful_count + 0.2 × neutral_count + 1`
- Age decay: 0.5% daily (`exp(-days * 0.005)`)

### Turn-Level Attribution
REFLECTOR analyzes each turn to determine which AKUs helped/harmed:
- Micro-outcomes: `solved`, `progress`, `stuck`, `error`
- Ground truth reconciliation: if session succeeded but no 'solved' turns, force final turn → solved

### Two Dialogues Architecture

The system operates through two distinct feedback loops ("dialogues"):

**Tactical Dialogue: ADVISOR ↔ REFLECTOR**
```
ADVISOR: "I showed these AKUs for this situation"
    ↓
REFLECTOR: "AKU A helped, AKU B harmed"
    ↓
ADVISOR: "I'll update beliefs (Thompson Sampling)"
```
- **Focus:** Which AKUs work?
- **Timescale:** Per-turn, per-session
- **Mechanism:** Counter updates → Thompson Sampling
- **Question:** "Given existing knowledge, what should I show?"

**Strategic Dialogue: CLUSTERER ↔ STRATEGIST**
```
CLUSTERER: "Cluster X has failures but no solutions"
    ↓
LIBRARIAN: "Gap detected"
    ↓
STRATEGIST: "Synthesized AKU for cluster X"
    ↓
CLUSTERER: "Linked AKU to cluster X via target_cluster_id"
```
- **Focus:** What knowledge is missing?
- **Timescale:** Across sessions, aggregate patterns
- **Mechanism:** Gap detection → Synthesis → Edge creation
- **Question:** "What new knowledge should we create?"

**Key insight:** The tactical loop optimizes WITHIN existing knowledge (exploitation), while the strategic loop EXPANDS knowledge (exploration). The `target_cluster_id` field closes the strategic loop by ensuring synthesized AKUs are linked to the gaps they were created for.

### Cold-Start Handling
- Clusters are created for problem discovery even without AKUs
- Cluster statistics (success/failure) only count **guided** turns (akus_shown > 0)
- Cold-start sessions contribute to problem taxonomy, not effectiveness metrics

---

## Data Flow

### Per-Turn Flow
1. Session emits `akus.requested` → ADVISOR selects via Thompson Sampling → writes to Redis
2. Session reads AKUs, calls Claude → emits `llm.response.received`
3. REFLECTOR buffers turn data

### Session End Flow
```
SESSION                        REFLECTOR                      CLUSTERER
   │                              │                              │
   │ session.ended                │                              │
   ├─────────────────────────────►│                              │
   │                       _analyze_turns()                      │
   │                       - micro-outcomes                      │
   │                       - AKU attribution                     │
   │                              │                              │
   │                       _update_counters()                    │
   │                       - helpful++/harmful++                 │
   │                              │                              │
   │                       _create_edges()                       │
   │                       - caused_failure edges                │
   │                              │                              │
   │                       _extract_akus()                       │
   │                       ──────► aku.proposed → CURATOR        │
   │                              │                              │
   │                       attribution.resolved                  │
   │                              ├─────────────────────────────►│
   │                              │                       _assign_to_cluster()
   │                              │                       _create_solved_by_edges()
```

**Key:** Decoupled, eventually consistent. Session never blocks on Learning Loop.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Services | Python 3.11+, FastAPI |
| Event Bus | Kafka (KRaft mode) |
| Cache | Redis 7 |
| Database | PostgreSQL 17 + pgvector 0.8 |
| LLM | Claude Haiku 4.5 |
| Frontend | React 18, TypeScript, Vite |

---

## Performance Targets

- Session latency: P95 <500ms
- Learning Loop: <2s per event
- Vector search: <100ms with pgvector indexes

---

## Related Documentation

- [CLAUDE.md](CLAUDE.md) - Development context, commands, debugging SQL
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development guide
- [core/learning_loop/README.md](core/learning_loop/README.md) - Learning Loop details
- [core/session_v3/README.md](core/session_v3/README.md) - SESSION v3 service details

**Last Updated:** 2025-12-21 (v4 AKU schema simplification)
