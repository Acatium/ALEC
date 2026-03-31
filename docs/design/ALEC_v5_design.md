# ALEC v5: Discovery Intelligence Platform

## Design Document

**Date:** 2026-02-07 / 2026-02-08
**Status:** Draft — Architectural Vision + Runtime Specs
**Authors:** Matt + Claude (design sessions)

---

## Table of Contents

1. [Commercial Framing](#1-commercial-framing)
2. [Product Vision: Discovery Intelligence](#2-product-vision-discovery-intelligence)
3. [Architecture: Coordinator + Discovery Swarm](#3-architecture-coordinator--discovery-swarm)
4. [Architecture: Three-Tier Memory](#4-architecture-three-tier-memory)
5. [Architecture: Communication & Runtime Model](#5-architecture-communication--runtime-model)
6. [Architecture: Tool Registry & Source Access](#6-architecture-tool-registry--source-access)
7. [Architecture: Developer Pipeline & Safety](#7-architecture-developer-pipeline--safety)
8. [Architecture: Agent Types & Prompt Governance](#8-architecture-agent-types--prompt-governance)
9. [Context Management and Handoff](#9-context-management-and-handoff)
10. [Interface Design](#10-interface-design)
11. [Application Layout](#11-application-layout)
12. [Core Insight: Ontology Alignment as the Unit of Insight](#12-core-insight-ontology-alignment-as-the-unit-of-insight)
13. [Generalization Architecture: Platform vs Domain](#13-generalization-architecture-platform-vs-domain)
14. [Ontology Agent](#14-ontology-agent)
15. [Open Questions](#15-open-questions)

---

## 1. Commercial Framing

### Value Proposition

For regulated industries (financial services, healthcare, insurance, government), "the AI figured it out from reading a bunch of stuff" is not acceptable. Regulators require: **what information informed this decision, where did it come from, and can you prove the reasoning chain?**

ALEC as a **decision attribution layer:**

- Knowledge is externalized and inspectable — every pattern has provenance
- Decision trees are reconstructable — auditable answers for regulators
- Knowledge can be governed before application — compliance teams review and approve patterns

### Two Commercial Pillars

**Pillar 1: Cost control through knowledge crystallization.** Amortize pattern derivation across all future applications instead of re-synthesizing from raw data every time. Straightforward ROI.

**Pillar 2: Knowledge harvesting as organizational asset.** Living map of "how our organization actually makes decisions." Captures tacit expertise that survives staff turnover. Evolves automatically with the business.

### Differentiation

- vs Fine-tuning: No ML pipeline, inspectable/editable knowledge, real-time adaptation
- vs RAG: Self-building knowledge base, not dependent on authored documentation
- vs Process mining: Captures tacit knowledge, not just process flows
- vs Agent platforms: Organizational learning layer that works underneath any agent platform (via MCP, tool APIs, plugins)

---

## 2. Product Vision: Discovery Intelligence

### The Immediate Product

Before the full enterprise vision, there's a closer, more buildable product: **a multi-agent discovery system for understanding complex enterprise landscapes.**

The use case: "I need to understand how the contents of this Confluence space, these dozens of code repositories, these Jira projects, and this SharePoint folder of governance documents intersect."

Target users: consultants, enterprise architects, product owners, M&A due diligence teams, compliance auditors — anyone doing structured discovery across complex systems.

### What It Does

1. **Accepts a problem statement** — what needs to be understood and which sources to explore
2. **Dispatches discovery agents** — specialized workers for different source types (code, Jira, Confluence, SharePoint, databases)
3. **Builds a knowledge graph** — entities, relationships, observations accumulate as workers explore
4. **Detects gaps and contradictions** — identifies what's unknown and what conflicts
5. **Directs further exploration** — automatically dispatches workers to fill gaps
6. **Produces synthesis** — coherent output that's greater than the sum of individual findings
7. **Retains everything** — knowledge persists across sessions, consolidates over time

### Why This Wins

- The user doesn't manually capture observations — agents do it
- The knowledge graph structures understanding automatically
- Gaps are detected and filled without human direction
- Knowledge persists and evolves across sessions
- Views and reports are generated on demand from the graph, not maintained as code

### The Self-Hosting Insight

The first customer is the development team building this system. Every Claude Code session loses context. Every agent-assisted discovery engagement loses observations between sessions. Building the discovery intelligence system and using it to build itself creates the tightest possible feedback loop.

---

## 3. Architecture: Coordinator + Discovery Swarm

### Why Existing Multi-Agent Frameworks Fail

Current frameworks (CrewAI, AutoGen, LangGraph, Swarm) solve task decomposition and routing. They don't solve:

- **Shared understanding** across parallel discovery agents building toward a coherent picture
- **Context window management** — sharing discoveries between agents with finite context
- **Persistent knowledge accumulation** — each run starts fresh
- **Directed exploration** — adapting exploration based on emerging understanding

### Blackboard Architecture

The pattern that works comes from 1980s AI research: a shared workspace (blackboard/knowledge graph) that all agents read from and write to, with a coordinator that monitors state and generates tasks.

```
┌─────────────────────────────────────────┐
│  COORDINATOR                            │
│  - Holds problem statement              │
│  - Reads knowledge graph (projections)  │
│  - Identifies gaps and contradictions   │
│  - Generates exploration tasks          │
│  - Decides convergence                  │
└──────┬──────────────────────┬───────────┘
       │ dispatches tasks     │ reads state
       ▼                      ▼
┌──────────────┐    ┌─────────────────────┐
│ WORKER POOL  │    │  KNOWLEDGE GRAPH    │
│              │    │  (the blackboard)   │
│ Worker A ────┼───►│                     │
│ Worker B ────┼───►│  entities           │
│ Worker C ────┼───►│  relationships      │
│ Worker D ────┼───►│  observations       │
│ ...          │    │  gaps               │
└──────────────┘    │  contradictions     │
                    └─────────────────────┘
```

> **Architecture Validated (2026-02-20):** The blackboard pattern is confirmed by arXiv multi-agent LLM surveys as the dominant pattern for knowledge-intensive coordination. PostgreSQL-only storage is consistent with OpenAI's production agent infrastructure precedent. The stateless-per-cycle coordinator avoids the most dangerous multi-agent failure mode (coordinator state drift). Single-process asyncio is appropriate for I/O-bound LLM workloads at current scale. See `docs/design/market_validation.md` for full analysis.

### Design Principles

**Workers are stateless and disposable.** Each gets a focused task, does it, writes findings to the graph, and terminates. No persistent context. No inter-worker communication. Each task fits in a single context window.

**The coordinator is stateful but graph-dependent.** It holds the problem statement and decision history but reads current state from the knowledge graph via bounded projections. It can be stopped and restarted without loss because the graph IS the state.

**The knowledge graph is the only persistent state.** Coordinator, workers, and consolidation processes are all consumers and producers of the graph. Any can be stopped and restarted.

### Worker Types

| Worker Type | Source | Capabilities |
|---|---|---|
| Code Explorer | Git repositories | Directory survey, dependency tracing, config analysis, API surface extraction |
| Ticket Miner | Jira, ServiceNow | Epic/story analysis, decision extraction from comments, stakeholder identification |
| Document Reader | Confluence, SharePoint | Page tree navigation, policy extraction, architecture diagram interpretation |
| Schema Analyzer | Databases, catalogs | Table/schema mapping, relationship inference, data lineage |
| Governance Auditor | Policy documents | Rule extraction, controlled entity identification, compliance mapping |

### Task Protocol

**Input to worker:**
```
{
  source_ref: "https://github.com/org/payments-service",
  directive: "Survey top-level structure. Identify external service
              dependencies, database connections, and API endpoints.",
  relevant_context: "<compressed summary of what's known about
                      entities this source might reference>",
  max_scope: "survey"  // survey | focused | deep
}
```

**Output from worker:**
```
{
  entities: [{name, type, source_ref, confidence}],
  relationships: [{from, to, type, evidence, source_ref}],
  observations: [{text, entities_referenced, source_ref}],
  suggested_followups: [{question, suggested_source}],
  scope_overflow: false
}
```

Workers produce structured output, not prose. The coordinator processes results programmatically.

### Coordination Loop

```
1. Read problem statement
2. Generate initial exploration tasks from stated sources
3. Dispatch workers (parallel, bounded concurrency)
4. As results arrive:
   a. Merge into knowledge graph
   b. Resolve entity matches (is "payments-svc" = "payment-service"?)
   c. Detect gaps (entities referenced but never explored)
   d. Detect contradictions (conflicting relationships)
   e. Generate new tasks to fill gaps / resolve contradictions
5. Repeat until convergence:
   - No new gaps detected in last N rounds
   - No unresolved contradictions
   - Coverage threshold reached
   - Or user says "enough"
6. Trigger synthesis
```

### Convergence Criteria

Discovery is potentially infinite. The coordinator needs heuristics for diminishing returns.

**First-generation heuristics** (simple, useful for early implementation):
- N consecutive exploration rounds produced fewer than K new entities
- Gap count stable for M rounds
- User-defined coverage targets met (e.g., "all services mapped with dependencies")
- Token/cost budget exhausted

**Enhanced multi-signal metric** (specified in `runtime_component_specs.md` Section 1.4):
- **Weighted reinforcement ratio** — reinforcement weighted by novelty decay (`1/log2(observation_count + 1)`), so repeated confirmation of well-known entities contributes less
- **Expansion deceleration** — sustained negative acceleration of expansion rate as a secondary convergence signal
- **Per-source tracking** — flags if a single source dominates reinforcement (> 60%), which may indicate artificial convergence
- **Expected contradiction exclusion** — contradictions classified as "expected" (see Section 12, GAP-G3) do not penalize convergence. Enterprise landscapes commonly have permanent contradictions (code vs documentation) that should not block convergence

---

## 4. Architecture: Three-Tier Memory

### Design Insight

Human memory doesn't pre-judge importance at encoding time. Storage is cheap. The magic is in retrieval — the right memories surface when the current context activates them. Memories that never get retrieved quietly fade. Consolidation (sleep) reorganizes and connects memories.

Computer memory has different cost profiles: storage is essentially free, search is nearly free, but **context injection is expensive** — every token of retrieved knowledge displaces a token for actual reasoning. The optimization target is: **maximize value per token of injected context.**

### Tier 1: Raw Observations (Store Everything)

Append-only event log. Full fidelity. Never searched directly.

```sql
CREATE TABLE observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    worker_id TEXT,
    source_ref TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    observation_type TEXT NOT NULL,
        -- entity, relationship, insight, contradiction, gap, decision
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
```

**Cost:** ~$0 per observation. Store millions for pennies.

### Tier 2: Structured Index (Knowledge Graph)

Extracted entities, relationships, and knowledge items with embeddings. This is what gets searched during retrieval.

```sql
CREATE TABLE entities (
    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
        -- service, database, team, api, policy, person,
        -- document, model, agent, tool
    aliases TEXT[] DEFAULT '{}',
    embedding vector(1536),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_referenced TIMESTAMPTZ DEFAULT NOW(),
    observation_count INT DEFAULT 0,
    status TEXT DEFAULT 'active',
        -- active, merged, deprecated
    properties JSONB DEFAULT '{}'
);

CREATE TABLE relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity UUID REFERENCES entities(entity_id),
    to_entity UUID REFERENCES entities(entity_id),
    relationship_type TEXT NOT NULL,
        -- depends_on, owned_by, reads_from, writes_to, calls,
        -- bypasses, contradicts, supersedes, governs
    evidence UUID[] DEFAULT '{}',
        -- observation_ids that support this
    confidence FLOAT DEFAULT 0.5,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_confirmed TIMESTAMPTZ DEFAULT NOW(),
    properties JSONB DEFAULT '{}'
);

CREATE TABLE knowledge_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536),
    entities_referenced UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    reinforcement_count INT DEFAULT 1,
    last_retrieved TIMESTAMPTZ,
    superseded_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active'
        -- active, consolidated, superseded, decayed
);
```

**Cost:** ~$0.0001 per observation (one embedding call).

### Tier 3: Consolidated Knowledge (Synthesized Summaries)

Periodically produced by the "sleep" process. Information-dense, attributed, ready for context injection.

```sql
CREATE TABLE consolidated_units (
    unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_entity UUID REFERENCES entities(entity_id),
    related_entities UUID[] DEFAULT '{}',
    summary TEXT NOT NULL,
    embedding vector(1536),
    source_items UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    token_count INT NOT NULL,
    freshness TIMESTAMPTZ DEFAULT NOW(),
    retrieval_count INT DEFAULT 0,
    version INT DEFAULT 1,
    status TEXT DEFAULT 'current'
        -- current, stale, archived
);
```

**Example consolidated unit (~150 tokens):**

```
## payments-service
(Consolidated from 47 observations across 14 sessions, updated 2 days ago)

Core service handling payment processing. Depends on payments-db
(direct writes, bypasses API layer — decision from Q2, session 34).
Called by: checkout-service, subscription-service, billing-service.
Calls: stripe-gateway, fraud-detection-service.

Known issues:
- Non-standard connection pool config (session 34, also seen in
  billing-service session 89)
- Schema split planned for Q3 (manual observation, Jan 15)
- 3 undocumented downstream consumers (sessions 52, 58, 61)

Open questions:
- Deployment pipeline not yet explored
- No governance documentation found for PII handling
```

### Consolidation Process ("Sleep")

Runs between sessions or during idle periods. Triggered when a cluster of Tier 2 knowledge items has changed since last consolidation.

**Process:**

1. **Identify stale clusters.** Find entities where knowledge_items added/updated since last consolidated_unit.
2. **Gather material.** Pull all active knowledge_items and source observations for entity.
3. **Synthesize.** LLM call: "Given these N observations about [entity], produce a consolidated summary. Preserve attribution. Compress to 200-400 tokens."
4. **Store.** Write consolidated unit with full provenance chain.
5. **Cross-link.** Second pass: find cross-entity patterns — entities referenced together that aren't explicitly linked. This is where non-obvious connections emerge.

Step 5 is the most valuable — it surfaces "didn't seem significant at the time" connections, analogous to human memory consolidation during sleep.

**Cost:** ~$0.01-0.10 per consolidation batch. Amortized across all future retrievals.

### Recall Mechanism

**Stage 1: Entity resolution (instant).** Match current context to known entities. Find related entities within 2 hops.

**Stage 2: Consolidated retrieval (instant).** Pull consolidated units for matched entities. Rank by freshness and retrieval history.

**Stage 3: Budget packing (instant).** Given context budget (e.g., 8,000 tokens), pack highest-ranked consolidated units. Return structured knowledge brief.

**Stage 4: Progressive disclosure (on demand).** Knowledge brief includes references. Agent can drill down to specific Tier 2 items or Tier 1 observations for detail.

### Monthly Cost Envelope (Individual Scale)

| Activity | Frequency | Unit Cost | Monthly |
|---|---|---|---|
| Raw observation storage | ~500/day | ~free | ~$0 |
| Embedding generation | ~500/day | $0.0001 | ~$1.50 |
| Consolidation | ~5/day | $0.05 | ~$7.50 |
| Retrieval search | ~50/day | ~free | ~$0 |
| **Total** | | | **~$10/month** |

---

## 5. Architecture: Communication & Runtime Model

### Design Decision: In-Process + Postgres

The system runs as a **single Python process** with asyncio concurrency. No Kafka for coordination, no Redis, no message broker. PostgreSQL is the only infrastructure dependency.

**Why this is sufficient:** The worst-case workload — "learn everything about this data platform ecosystem with a dozen Confluence sites, a dozen repos, Jira projects, SharePoint, SDKs, documentation" — produces at most a few dozen concurrent workers. That's `asyncio.Semaphore(20)` in a single process, not a distributed systems problem.

**What we eliminate:**
- Kafka for task coordination (topic-per-agent is operational overhead for short-lived request-response)
- Redis (no caching layer needed — Postgres handles everything)
- Service discovery (workers are functions, not services)
- Serialization overhead (worker results are Python dicts that go straight into SQL)
- Health checks / restart logic (failed coroutines are caught and re-queued by the supervisor)

### The Supervisor: Python, Not LLM

The thing managing agent lifecycles is **application code, not an LLM agent**. It doesn't need reasoning — it needs rules.

```
┌──────────────────────────────────────────────────────┐
│  ENGAGEMENT RUNTIME (autonomous, long-running)       │
│                                                      │
│  ┌────────────┐   spawns    ┌──────────────────┐    │
│  │ Supervisor │────────────►│ Coordinator v1   │    │
│  │ (Python)   │             │ (LLM agent)      │    │
│  │            │   spawns    │                  │    │
│  │ manages    │────────────►│ Coordinator v2   │    │
│  │ lifecycle  │             │ (after handoff)  │    │
│  │            │             └──────────────────┘    │
│  │            │   spawns    ┌──────────────────┐    │
│  │            │────────────►│ Workers (pool)   │    │
│  │            │             └──────────────────┘    │
│  │            │   spawns    ┌──────────────────┐    │
│  │            │────────────►│ APR (periodic)   │    │
│  │            │             │ Agent Perf Refl  │    │
│  └────────────┘             └──────────────────┘    │
│       │                                              │
│       │ all state in                                 │
│       ▼                                              │
│  ┌──────────┐                                        │
│  │ Postgres │                                        │
│  └──────────┘                                        │
└──────────────────────────────────────────────────────┘
         ▲
         │ reads (never blocks runtime)
         │
┌──────────────────────────────────────────────────────┐
│  UI (observatory + management)                       │
└──────────────────────────────────────────────────────┘
```

### Supervisor Main Loop

```python
class Supervisor:
    """Manages agent lifecycles. No LLM calls. Pure orchestration."""

    async def run(self, engagement_id: UUID):
        while not self.stopped:
            # 1. Check coordinator health
            if self.coordinator.context_pressure > 0.6:
                await self.handoff_coordinator()

            # 2. Reap completed workers
            completed = await self.reap_completed_workers()
            for result in completed:
                await self.write_to_db(result)

            # 3. Let coordinator generate next tasks (LLM call)
            if self.coordinator.ready_for_cycle:
                tasks = await self.coordinator.generate_tasks()
                for task in tasks:
                    await self.dispatch_worker(task)

            # 4. Periodic reflection (async, non-blocking)
            if self.should_reflect():
                await self.dispatch_apr()

            # 5. Apply auto-eligible prompt proposals
            await self.apply_auto_proposals()

            # 6. Check convergence
            if await self.check_convergence():
                await self.pause_engagement()
                break

            await asyncio.sleep(self.cycle_interval)

    async def handoff_coordinator(self):
        """Replace coordinator when context is getting full."""
        await self.coordinator.persist_state()
        new_coord = await self.spawn_coordinator(
            problem_statement=self.engagement.problem_statement,
        )
        old = self.coordinator
        self.coordinator = new_coord
        await old.shutdown()
```

### LLM as Capability, Not Orchestrator

The LLM is a **capability** that agents call when they need reasoning, not the orchestrator:

- **Python handles:** Task queuing, concurrency, DB writes, graph queries, convergence checks, agent lifecycle
- **LLM handles:** "Extract entities from this page", "What gaps exist in our understanding?", "Synthesize these observations into a summary"

The anti-pattern would be sending a message to the LLM saying "you are a coordinator, here are your workers, dispatch tasks." That puts the LLM in the control loop where it has to maintain state across calls, parse unstructured worker outputs, and make routing decisions — all things Python does better.

### The Resulting Stack

```
Python process
├── Supervisor (while True loop, pure Python)
│   ├── lifecycle management
│   ├── context pressure monitoring
│   └── convergence detection
│
├── Coordinator (Python state machine + 1 LLM call/cycle)
│   ├── reads graph via SQL (Python)
│   ├── detects gaps, contradictions, convergence (Python)
│   ├── generates task directives (LLM call)
│   └── dispatches workers via asyncio (Python)
│
├── Worker pool (asyncio.Semaphore bounded)
│   ├── each worker = async function with tool-use loop
│   ├── source tools: read, search, list_children (via connector)
│   ├── graph tools: add_entity, add_relationship, add_observation
│   ├── LLM decides what to read + extracts entities
│   └── writes incrementally to DB (partial results survive crashes)
│
├── APR (Python analytics + occasional LLM text generation)
│   ├── detects patterns in worker outputs (Python/SQL)
│   ├── classifies auto-apply vs human-review (Python rules)
│   └── drafts prompt text when change needed (LLM call)
│
├── Developer Pipeline (shared capability)
│   ├── generates queries/code on request (LLM call)
│   ├── validates against safety rules (Python, deterministic)
│   ├── executes in sandbox (read-only, timeout, resource-limited)
│   ├── caches proven queries for reuse (query asset library)
│   └── audit logs everything
│
├── asyncpg connection pool
│   └── all reads and writes
│
└── LLM client (async, pooled)
    └── Anthropic API

PostgreSQL (sole infrastructure dependency)
├── observations (Tier 1)
├── entities + relationships (Tier 2)
├── knowledge_items (Tier 2)
├── consolidated_units (Tier 3)
├── agent_types + prompt_versions (agent governance)
├── prompt_proposals (pending changes)
├── tasks (work queue)
├── source_configs (tool registry)
├── code_assets (query/code library)
└── code_executions (audit trail)
```

No Kafka. No Redis. No message broker. No service mesh.

### Engagement Model

An engagement is the **persistent, multi-session entity** that humans and agents interact with over days or weeks. It is the top-level organizational unit.

```
ENGAGEMENT (persistent)
├── Problem statement
├── Source configs
├── Knowledge graph (shared by ALL agents)
├── Active coordinators (one or more, each with a focus)
├── Worker pool (shared)
├── APR (shared)
├── Developer Pipeline + code asset library (shared)
└── Prompt versions (per agent type)
```

```sql
CREATE TABLE engagements (
    engagement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    status TEXT DEFAULT 'active',
        -- 'setup', 'active', 'paused', 'converged', 'archived'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    config JSONB DEFAULT '{}'
        -- auto_split, cost_budget, convergence_criteria
);

CREATE TABLE coordinator_instances (
    instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID REFERENCES engagements(engagement_id),
    focus_domain TEXT,          -- null = broad, or "streaming", "governance"
    source_filter TEXT[],       -- which sources this coordinator focuses on
    prompt_version_id UUID REFERENCES prompt_versions(version_id),
    status TEXT DEFAULT 'active',
        -- 'active', 'converged', 'merged', 'terminated'
    cycles_completed INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- All knowledge tables are scoped by engagement
-- observations, entities, relationships, etc. all have engagement_id
```

Engagements are isolated by `engagement_id`. Multiple engagements can run simultaneously against different (or overlapping) source sets. Within an engagement, all coordinators share the graph.

### Horizontal Coordination: Multi-Coordinator Engagements

Agents scale horizontally the same way knowledge does across tiers. An engagement can have **multiple coordinators**, each owning a sub-domain, all sharing the same knowledge graph.

**Single-Coordinator Phase (Initial Survey):**

Every engagement starts with one coordinator doing broad survey:

```
Coordinator (broad):
  "Survey all 4 configured sources. Map top-level entities.
   Identify natural domain boundaries."
  → Dispatches survey workers to all sources
  → Identifies: streaming, governance, lineage, compute
     are distinct sub-domains
```

**Multi-Coordinator Phase (Specialization):**

As the graph grows, the engagement naturally decomposes. Triggered by:
- The coordinator proposing a subdomain split (via `propose_subdomain` tool)
- The user directing focus ("go deeper on governance")
- The APR detecting redundant cross-domain dispatching

```
Engagement: "Understand the data platform ecosystem"
│
├── Coordinator A: "Streaming Platform"
│   ├── Focus: Kafka repos, Confluent docs, streaming Jira epics
│   └── Workers: code_explorer, doc_reader
│
├── Coordinator B: "Data Governance"
│   ├── Focus: SharePoint policies, compliance Jira, GOV Confluence
│   └── Workers: doc_reader, governance_auditor
│
├── Coordinator C: "Data Lineage & Schema"
│   ├── Focus: Schema repos, catalog databases, ARCH Confluence
│   └── Workers: schema_analyzer, code_explorer
│
└── Shared: knowledge graph, APR, worker pool, Developer Pipeline
```

**Cross-Coordinator Communication: The Graph IS the Channel**

Coordinators don't talk to each other. They don't need to.

```
Coordinator A discovers: "streaming-service writes to customer-db"
  → writes relationship to graph

Coordinator C (next cycle) reads projection:
  → sees new relationship touching its domain
  → "streaming-service writes to customer-db — I should explore
     that dependency from the lineage perspective"
  → dispatches focused worker
```

Eventually consistent and that's fine. No message passing, no shared queue, no cross-coordinator protocol. The graph is the sole coordination mechanism.

**Supervisor Manages the Fleet:**

```python
class Supervisor:
    coordinators: dict[str, Coordinator]  # keyed by focus domain

    async def run(self):
        while not self.stopped:
            # Run all coordinators in parallel
            cycle_results = await asyncio.gather(*[
                self.run_coordinator_cycle(coord)
                for coord in self.coordinators.values()
            ])
            for result in cycle_results:
                for action in result.actions:
                    if action.type == "dispatch_worker":
                        await self.dispatch_worker(action.task)
                    elif action.type == "propose_subdomain":
                        await self.handle_subdomain_proposal(action)
                    elif action.type == "signal_convergence":
                        await self.handle_convergence(action)
            ...
```

### Multi-Session Lifecycle

The engagement persists across sessions. This is what makes it organic:

```
Day 1 (Setup):
  User configures 4 sources via Configure Agent.
  Single coordinator does initial survey.
  System runs overnight. User sleeps.

Day 2 (Review):
  User opens UI. 147 entities, 89 relationships.
  Reviews 5 pending APR proposals. Approves 3.
  "Focus more on data governance" → new coordinator spawned.
  System continues.

Day 5 (Expand):
  User adds 2 new sources (ServiceNow, database catalog).
  Configure Agent onboards them.
  Existing coordinators pick up new source data.

Day 10 (Inquiry):
  Stakeholder asks: "What services touch PII?"
  Query Agent reads graph, generates view.
  No agents dispatched — pure graph query.

Day 15 (New team member):
  New person joins. Asks questions via Query Agent.
  Knowledge graph provides institutional context they'd
  otherwise spend weeks gathering.

Day 30 (Consolidation):
  APR proposes merging streaming and lineage coordinators
  (domains converged). User approves.
  Sleep process consolidates 2,000+ observations into
  150 consolidated units.
```

### Scaling Path (Future, Not MVP)

If the system ever needs distributed workers:
1. Add Postgres task queue with `FOR UPDATE SKIP LOCKED` (free work-stealing semantics)
2. Run worker processes on separate machines, polling the same DB
3. Coordinator doesn't change — it still reads the graph
4. Add Kafka only for the durable observation stream (audit/replay), never for coordination

---

## 6. Architecture: Tool Registry & Source Access

### Source Configuration

The coordinator can't dispatch a Confluence worker if it doesn't know Confluence is available and how to reach it. Every source needs three pieces of information:

1. **What type of source is it** — so it picks the right worker type
2. **How to reach it** — endpoint, project key, repo URL
3. **How to authenticate** — token, OAuth, API key, cookie

```yaml
# Example engagement source config
sources:
  - type: confluence
    base_url: https://company.atlassian.net/wiki
    spaces: ["DATA", "ARCH", "GOV"]
    auth:
      method: api_token
      username: matt@company.com
      token_env: CONFLUENCE_TOKEN

  - type: jira
    base_url: https://company.atlassian.net
    projects: ["DATA", "PLAT", "PCSR"]
    auth:
      method: api_token
      username: matt@company.com
      token_env: JIRA_TOKEN

  - type: github
    repos:
      - org/data-pipeline
      - org/schema-registry
      - org/governance-tools
    auth:
      method: pat
      token_env: GITHUB_TOKEN

  - type: sharepoint
    sites: ["https://company.sharepoint.com/sites/DataGov"]
    auth:
      method: oauth
      token_env: SHAREPOINT_TOKEN

  - type: url
    urls:
      - https://docs.confluent.io/platform/current/
      - https://sdk.company.com/docs/
    auth: none
```

### MCP vs Direct Access: Not Either/Or

**Direct access** is the default for well-documented APIs. **MCP** is an adapter for when someone already built a connector or auth is painful.

| Source | Access Method | Why |
|---|---|---|
| Git repos | Direct (clone + read) | Trivial, no API needed |
| Public URLs | Direct (HTTP fetch) | Just fetch + parse HTML |
| Confluence | Direct (REST API) | Well-documented, standard pagination |
| Jira | Direct (REST API) | Straightforward REST |
| SharePoint | MCP or direct | Auth is painful, MCP may save time |
| Databases | Direct (asyncpg) | Connection string + query |
| Weird enterprise stuff | MCP | Let the user bring their own connector |

### Source Connector Abstraction

Workers don't know about HTTP or auth. They get tool functions already bound to the right endpoint and credentials. Connectors are **read-only by interface design** — no write methods exist.

```python
class SourceConnector(Protocol):
    """Read-only interface. NO write methods. Safety by construction."""
    source_type: str

    async def survey(self) -> list[str]:
        """Return entry points for this source."""
        ...

    async def read(self, ref: str) -> str:
        """Read a specific resource, return as text."""
        ...

    async def search(self, query: str) -> list[dict]:
        """Search within this source."""
        ...

    async def list_children(self, ref: str) -> list[str]:
        """List sub-resources of a resource."""
        ...

    async def execute_read(self, query: str, language: str) -> str:
        """Execute a validated, sandboxed read query (via Developer Pipeline)."""
        ...

    async def get_schema(self) -> str:
        """Return schema/structure for Developer Pipeline code generation."""
        ...
```

For simple sources (git repos, URLs), the basic `read`/`search`/`list_children` methods are sufficient. For complex sources (databases, APIs with query languages), workers use `execute_read` which routes through the Developer Pipeline for dynamic query generation, validation, and sandboxed execution (see Section 7).

```python
class ConfluenceConnector(SourceConnector):
    source_type = "confluence"
    def __init__(self, base_url: str, space: str, auth: AuthConfig): ...

class MCPConnector(SourceConnector):
    """Generic adapter — wraps any MCP server as a SourceConnector."""
    source_type = "mcp"
    def __init__(self, server_config: dict): ...
```

### Guided Setup: Source Configuration as Conversation

Source configs are not YAML files the user writes by hand. They're produced through an interactive **guided setup** conversation with the Configure Agent.

**Example flow:**

```
User: I've got our Confluence at https://company.atlassian.net/wiki

System: Let me try to reach that.
        → HTTP 401. Need authentication.
        What auth method do you have?
        [ API Token ] [ OAuth ] [ MCP Server ] [ Other ]

User: Here's an API token: [pastes]

System: Testing... I can reach the API.
        Found 23 spaces. Which ones are relevant?
        [ DATA ] [ ARCH ] [ GOV ] [ ENG ] [ HR ] [ ... ]

User: DATA, ARCH, and GOV

System: Surveying those spaces...
        → DATA: 342 pages, mostly technical specs
        → ARCH: 89 pages, architecture decisions
        → GOV: 156 pages, policies and standards

        I've saved this connection config.
        Now — what should a worker exploring these spaces
        know? Any conventions, naming patterns, or areas
        to focus on?

User: The DATA space is organized by domain — each top-level
      page is a data domain (Customer, Product, Transaction).
      Under each domain there's a "Current State" and
      "Target State" section. Focus on Current State.

System: Got it. I've created a Confluence worker profile:
        - Navigate by domain (top-level pages)
        - Prioritize "Current State" sections
        - 3 spaces, ~587 pages total
        - Auth: API token (stored in env)

        Ready for the next source, or should I start?
```

### MCP Troubleshooting Path

When direct access fails, the guided setup naturally falls through to MCP:

```
System: Can't reach Confluence API directly.
        HTTP 403 — might be behind SSO/VPN.

User: Yeah, we have an MCP server for that.
      Here's the config: { "server": "confluence-mcp", ... }

System: Testing MCP server...
        → Tool list: [read_page, search, get_space_pages]
        → Test call: get_space_pages("DATA") → 342 results

        Works. I'll use MCP for this source.
        Capabilities are slightly different — no
        read_attachments available via this MCP server.
        That OK?
```

The system doesn't care whether it talks to Confluence via REST or MCP — the `SourceConnector` abstraction hides that.

### Guided Setup Produces Two Artifacts

Each source configuration conversation generates:

**1. Connection Config (machine-readable, tested)**

```sql
INSERT INTO source_configs (source_id, source_type, config, auth_config, status)
VALUES (
    gen_random_uuid(),
    'confluence',
    '{"base_url": "https://...", "spaces": ["DATA","ARCH","GOV"]}',
    '{"method": "api_token", "token_env": "CONFLUENCE_TOKEN"}',
    'verified'   -- actually tested during setup
);
```

**2. Worker Profile (the "training" — see Section 10)**

The user's domain knowledge about how to navigate the source becomes a learned prompt section for workers dispatched to that source.

### Source Config Storage

Configs and profiles persist in Postgres as part of the engagement state. If you hand off a discovery project, the tool configs come with it. Configs can be exported to YAML for portability or version control.

---

## 7. Architecture: Developer Pipeline & Safety

### The Problem With Pre-Built Templates

Pre-building every possible query template (SQL for schema analysis, JQL for Jira, CQL for Confluence) is safe but brittle. The system encounters novel queries constantly — new source types, unusual schemas, user questions that map to unforeseen patterns. Template-only approaches can't adapt.

### Developer Pipeline: Generate, Validate, Execute, Cache

The Developer Pipeline is a **shared capability** (not an agent) that any agent can call when it needs dynamic code or queries. It separates intent from implementation from safety:

```
Worker: "I need all Jira tickets in the DATA project resolved
         in the last 90 days with comments mentioning 'migration'"

    → Code Generator (LLM call)
      Writes: project = DATA AND resolution IS NOT EMPTY
              AND resolved >= -90d AND comment ~ "migration"

    → Validator (Python, deterministic)
      ✓ Read-only (no mutations)
      ✓ All fields in allowed set
      ✓ No injection patterns
      ✓ Result set bounded (has date filter)

    → Executor (sandboxed)
      Runs against Jira API, 5s timeout, 10k row limit

    → Asset Library
      Caches the proven query for reuse

    → Results back to Worker
```

**Who uses it:**
- Workers use it for source queries (SQL, JQL, CQL, GraphQL)
- Query Agent uses it for user-facing data queries
- Configure Agent can use it to generate connectors for new source types
- Coordinator uses it for novel graph projection queries

### Code Asset Library

When a generated query works, it becomes a reusable asset. When agent 7 needs a query and the Developer Pipeline builds one that works, agent 17 gets it from cache instead of regenerating.

```sql
CREATE TABLE code_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID REFERENCES engagements(engagement_id),

    -- What this code does (for retrieval)
    description TEXT NOT NULL,
    description_embedding vector(1536),

    -- The code itself
    language TEXT NOT NULL,        -- 'sql', 'jql', 'cql', 'python', 'graphql'
    code TEXT NOT NULL,

    -- Provenance
    source_type TEXT NOT NULL,     -- which connector type this is for
    generated_by TEXT,             -- which agent first requested it

    -- Effectiveness tracking
    usage_count INT DEFAULT 1,
    success_count INT DEFAULT 1,
    failure_count INT DEFAULT 0,
    last_used TIMESTAMPTZ DEFAULT NOW(),

    -- Governance
    validated BOOLEAN DEFAULT TRUE,
    status TEXT DEFAULT 'active',
        -- 'active', 'deprecated', 'failed'

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES code_assets(asset_id),

    -- Context
    requesting_agent TEXT NOT NULL,
    request_description TEXT NOT NULL,

    -- Result
    success BOOLEAN NOT NULL,
    result_summary TEXT,
    error_message TEXT,
    execution_time_ms INT,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Retrieval flow:**

```python
async def execute(self, request: CodeRequest) -> CodeResult:
    # 1. Check cache first (embedding similarity on description)
    cached = await self.find_similar_asset(
        description=request.description,
        source_type=request.source_type,
        language=request.language,
        threshold=0.85,
    )

    if cached and cached.success_rate > 0.8:
        # Reuse proven query — no LLM call needed
        code = cached.code
    elif cached and cached.success_rate > 0.5:
        # Use as starting point for LLM refinement
        code = await self.llm.refine_code(cached.code, request)
    else:
        # Generate fresh
        code = await self.llm.generate_code(request)

    # 2. Validate (always, even cached — schema may have changed)
    validation = self.validator.check(code, request.language)
    if not validation.safe:
        return CodeResult(success=False, error=validation.reasons)

    # 3. Execute in sandbox
    result = await self.sandbox.run(code, request.language)

    # 4. Update or create asset
    if result.success:
        await self.upsert_asset(request, code, success=True)
    else:
        await self.record_failure(request, code, result.error)

    # 5. Audit log (always)
    await self.audit(request, code, validation, result)

    return result
```

Over time, the asset library grows into a **proven query catalog** for each source type. The LLM generates less and less as the cache fills. This is the same pattern as the three-tier memory — observations crystallize into reusable assets.

### Connector Generation

The most powerful application: instead of pre-building connectors for every source type, the Developer Pipeline can **write connectors** based on API documentation:

```
Configure Agent: "User provided docs for an internal API at
                  https://data-catalog.internal/api/v2"

Developer Pipeline:
  1. LLM reads API docs → generates SourceConnector implementation
  2. Validator checks: read-only methods only, rate limiting present,
     error handling, timeout handling
  3. Test execution against actual API
  4. Store as reusable connector asset

Result: new source type available without code changes
```

### Four-Layer Safety Model

Safety is enforced by **Python code structure, not LLM instructions**. Each layer is independent — all four must pass.

**Layer 1: Source access — read-only by construction**

Source connectors have no write methods. The `SourceConnector` protocol interface literally does not include create/update/delete operations. Workers cannot modify external sources because the capability doesn't exist in their tools.

Per-source rate limiting wraps every connector:
- Configurable requests-per-minute (default: 30)
- Concurrent request limit (default: 5)
- Hard timeout per request (default: 30s)
- Content size cap (default: 50k chars per response)

**Layer 2: Static analysis — deterministic code validation**

Every piece of generated code is parsed and checked before execution:

```python
class SQLValidator:
    """Rejects any non-read SQL."""
    BANNED_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
                       "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC"}

    def check(self, sql: str) -> ValidationResult:
        tokens = sqlparse.parse(sql)
        for statement in tokens:
            if statement.get_type() in self.BANNED_KEYWORDS:
                return ValidationResult(safe=False, reasons=[...])
            if not self._has_result_limit(statement):
                return ValidationResult(safe=False, reasons=["Unbounded query"])
        return ValidationResult(safe=True)

class PythonValidator:
    """Rejects dangerous Python constructs."""
    BANNED_MODULES = {"os", "subprocess", "sys", "shutil", "socket", "ctypes"}
    BANNED_BUILTINS = {"exec", "eval", "compile", "__import__", "open"}

    def check(self, code: str) -> ValidationResult:
        tree = ast.parse(code)
        # Walk AST checking for banned imports, calls, attributes
        ...
```

**Layer 3: Execution sandbox**

Even if validation misses something, the sandbox makes damage impossible:
- Read-only database connections (`default_transaction_read_only: true`)
- Network restricted to configured source endpoints only
- No filesystem access
- Resource limits: CPU time, memory, result set size
- Hard timeout enforcement

**Layer 4: Output validation and audit**

- Result set size check (reject if exceeding limit)
- PII pattern scanning (flag sensitive data in results)
- Every generated query, validation result, and execution recorded in `code_executions`
- Full audit trail: who requested, what was generated, what was executed, what was returned

### Budget Enforcement

```python
class BudgetEnforcer:
    """Tracks and enforces cost limits. Pure Python."""

    # Per-engagement total spend cap
    engagement_max_tokens: int = 10_000_000

    # Per-worker task cap
    worker_max_tokens: int = 100_000

    # Per-coordinator cycle cap
    coordinator_max_tokens: int = 50_000

    # Per-source rate caps (API calls, not tokens)
    source_max_requests_per_hour: dict[str, int] = {
        "confluence": 500, "jira": 500,
        "github": 1000, "sharepoint": 200,
    }
```

The supervisor checks budget before dispatching any LLM call. Engagement pauses and notifies the user if budget is exhausted.

---

## 8. Architecture: Agent Types & Prompt Governance

### Agent Types

The system has five distinct agent types. Most are **primarily Python with targeted LLM calls**, not "LLM agents."

| Agent | Nature | Lifecycle | Python vs LLM |
|---|---|---|---|
| **Configure Agent** | Interactive | Per-setup-session | Mostly Python wizard; 1 LLM call to generate worker profile from user description |
| **Coordinator** | Stateful per-cycle | Fresh projection each cycle | Python state machine; 1 LLM call/cycle to write task directives |
| **Workers** | Stateless, disposable | Single task then terminate | LLM-heavy: multi-turn tool-use loop for extraction (5-10 LLM calls/task) |
| **APR** | Periodic, async | Triggered by supervisor | Python analytics; occasional LLM call to draft proposed prompt text |
| **Query Agent** | Interactive, on-demand | Per-user-question | LLM-heavy: understand question + synthesize answer (2-3 LLM calls) |

### LLM vs Python: Function-Level Audit

**Supervisor** — 100% Python. Lifecycle management, scheduling, threshold checks.

**Coordinator** — Python state machine + 1 LLM call per cycle:

| Function | LLM or Python | Why |
|---|---|---|
| Build projection from graph | Python | SQL queries + text formatting |
| Detect gaps | Python | `SELECT entities WHERE observation_count = 0` |
| Detect contradictions | Python | Conflicting relationships between same entities |
| Rank gaps by priority | Python | `reference_count * recency_weight` |
| Detect convergence | Python | `new_entities_per_cycle < threshold for N cycles` |
| Entity resolution | Python + embedding | Cosine similarity + alias matching |
| **Generate task directives** | **LLM** | Writing natural language instructions for workers |

**Workers** — LLM for extraction, Python for everything else:

| Function | LLM or Python | Why |
|---|---|---|
| **Decide what to read next** | **LLM** | Evaluate relevance from listing |
| Fetch source content | Python | Tool call execution |
| **Extract entities from text** | **LLM** | Unstructured → structured |
| **Extract relationships** | **LLM** | Semantic understanding |
| Write to graph | Python | Typed tool calls, Pydantic validation |
| Detect scope overflow | Python | Token counter |

**APR** — Python analytics + occasional LLM:

| Function | LLM or Python | Why |
|---|---|---|
| Detect scope_overflow patterns | Python | `COUNT(*) WHERE scope_overflow GROUP BY source` |
| Detect empty/low-yield workers | Python | Entity count per worker |
| Detect navigation divergence | Python | Compare outputs across runs |
| Identify underperforming prompts | Python | `AVG(entities_per_worker) GROUP BY agent_type` |
| Detect specialization opportunity | Python | Cluster worker outputs, measure variance |
| Classify auto-apply vs human-review | Python | Rules on section_key + impact |
| **Draft proposed prompt text** | **LLM** | Turn evidence into instructions |

**Configure Agent** — Mostly Python wizard:

| Function | LLM or Python | Why |
|---|---|---|
| Probe connectivity | Python | HTTP request, check status |
| List available spaces/repos | Python | API call, parse response |
| Present choices to user | Python | Templated UI flow |
| Validate credentials | Python | Try authenticated request |
| **Parse user description into worker profile** | **LLM** | NL → structured navigation hints |

**Query Agent** — Genuinely LLM-heavy:

| Function | LLM or Python | Why |
|---|---|---|
| Understand user question | LLM | Natural language understanding |
| Generate graph queries | LLM (via Developer Pipeline) | Translate question to query |
| Execute queries | Python | Run SQL, return results |
| Synthesize answer | LLM | Structured data → coherent response |

### LLM Call Budget Per Cycle

```
Coordinator cycle:      1 LLM call   (generate directives)
Worker (per task):      5-10 calls   (extraction loop)
APR (periodic):         0-3 calls    (only if proposals needed)
Configure (per source): 1 call       (profile generation)
Query (per question):   2-3 calls    (understand + synthesize)
Developer Pipeline:     0-1 calls    (0 if cached, 1 if generating)

Typical cycle with 5 active workers:
  1 (coordinator) + ~35 (workers) + 0-1 (developer) = ~37 LLM calls
```

### Worker Execution Model: Agentic With Tool-Use Loop

Workers are the one genuinely LLM-heavy agent type. Each worker is an async function that runs a multi-turn tool-use loop — reading source material, deciding what to explore next, and writing findings to the graph incrementally.

**Workers get two kinds of tools:**

| Tool Type | Examples | Provided By |
|---|---|---|
| **Source tools** (read-only) | `read`, `search`, `list_children`, `survey` | SourceConnector |
| **Graph tools** (write) | `add_entity`, `add_relationship`, `add_observation`, `suggest_followup` | Graph write layer |

**Structured output by construction:** There's no single JSON blob to validate — each finding is a typed tool call with Pydantic-validated parameters. If one call fails, the rest succeed.

**Incremental persistence:** Everything written via graph tools is already in Postgres. If a worker dies mid-task (LLM error, source timeout), partial results survive. The coordinator sees what was found and can dispatch a follow-up worker.

```python
async def run_worker(task: WorkerTask, connector: SourceConnector,
                     graph: GraphWriter, llm: LLMClient):
    """A worker is an async function with a tool-use loop."""
    messages = [system_prompt(task)]  # base + learned sections + directive
    tools = connector.as_tools() + graph.as_tools()

    while not budget_exceeded(messages):
        response = await llm.call(messages, tools=tools)

        if response.stop_reason == "end_turn":
            break  # worker decided it's done

        for tool_call in response.tool_calls:
            result = await execute_tool(tool_call, connector, graph)
            messages.append(tool_result(tool_call.id, result))

    return WorkerResult(
        scope_overflow=budget_exceeded(messages),
        entities_written=graph.entities_count,
        observations_written=graph.observations_count,
    )
```

### Coordinator Cycle: Stateless Per-Cycle

Each coordination cycle is a **fresh LLM call with a regenerated projection from the graph**. The coordinator does not accumulate conversation history — it reads state from the graph each time.

```python
async def coordinator_cycle(engagement, graph, llm):
    # ALL PYTHON — graph queries
    gaps = await graph.find_gaps()                       # SQL
    contradictions = await graph.find_contradictions()    # SQL
    coverage = await graph.coverage_dashboard()           # SQL
    recent = await graph.recent_findings(since=last_cycle)  # SQL

    if not gaps and not contradictions:
        return ConvergenceSignal()

    # SINGLE LLM CALL — generate directives for top gaps
    top_gaps = rank_gaps(gaps)[:5]  # Python: score and sort
    directives = await llm.generate_task_directives(
        problem_statement=engagement.problem_statement,
        gaps=top_gaps,
        available_sources=engagement.sources,
        recent_findings=recent,
    )

    return [DispatchWorker(d) for d in directives]
```

**Why stateless per-cycle:**
- **No handoff needed.** No conversation to transfer. New coordinator reads the same graph.
- **Horizontal scaling is natural.** Multiple coordinators read the same graph — no inter-coordinator messaging.
- **Context pressure disappears.** Each cycle uses ~10k tokens of projection. Could run 1,000 cycles without exhaustion.
- **Decision history is durable.** Every `record_decision` call writes to the observations table. The projection pulls recent decisions from the graph, not from memory.

### Prompt Architecture: Layered, Not Monolithic

Every agent prompt is composed of distinct layers, each independently versioned:

```
┌─────────────────────────────────────────┐
│ ASSEMBLED PROMPT (at dispatch time)     │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ BASE PROMPT (engineered, stable)    │ │
│ │ "You are a Confluence exploration   │ │
│ │  worker. Your job is to..."         │ │
│ │ - Output format requirements        │ │
│ │ - Entity extraction rules           │ │
│ │ - Relationship types to look for    │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ LEARNED: source_profile             │ │
│ │ "This Confluence instance uses      │ │
│ │  domain-based organization..."      │ │
│ │ [from: setup session, v2]           │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ LEARNED: navigation_hints           │ │
│ │ "Archive sections may contain       │ │
│ │  legacy domain docs — check these"  │ │
│ │ [from: APR reflection, auto-applied]│ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ LEARNED: extraction_patterns        │ │
│ │ "ADR pages follow template:         │ │
│ │  Status/Context/Decision/Conseq"    │ │
│ │ [from: APR, human-approved]         │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ TASK DIRECTIVE (per-dispatch)       │ │
│ │ "Survey the DATA space. Focus on    │ │
│ │  Current State sections..."         │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

Assembly is concatenation at dispatch time. Each section has its own version history, provenance, and governance status.

### Prompt Governance Schema

```sql
-- Agent type definitions
CREATE TABLE agent_types (
    agent_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
        -- 'coordinator', 'worker:confluence', 'worker:github',
        -- 'configure', 'apr', 'query'
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prompt versions (immutable snapshots)
CREATE TABLE prompt_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type_id UUID REFERENCES agent_types(agent_type_id),
    version_number INT NOT NULL,

    -- The actual prompt, decomposed
    base_prompt TEXT NOT NULL,
    learned_sections JSONB DEFAULT '{}',
        -- key: section_name
        -- value: {content, source_observations[], confidence}

    -- Provenance
    parent_version_id UUID REFERENCES prompt_versions(version_id),
    change_summary TEXT NOT NULL,
    change_type TEXT NOT NULL,
        -- 'initial', 'manual', 'auto_applied', 'human_approved'
    change_source TEXT,
        -- 'apr', 'user_feedback', 'setup', 'initial'
    evidence JSONB DEFAULT '{}',

    -- Governance
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    is_current BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_type_id, version_number)
);

-- Proposed changes (pending review or auto-apply evaluation)
CREATE TABLE prompt_proposals (
    proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type_id UUID REFERENCES agent_types(agent_type_id),
    current_version_id UUID REFERENCES prompt_versions(version_id),

    -- What changed
    section_key TEXT NOT NULL,
    proposed_content TEXT NOT NULL,
    diff_summary TEXT NOT NULL,

    -- Why
    reasoning TEXT NOT NULL,
    evidence_observations UUID[],
    confidence FLOAT NOT NULL,
    impact TEXT NOT NULL,    -- 'low', 'medium', 'high'

    -- Governance
    auto_apply_eligible BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',
        -- 'pending', 'approved', 'rejected', 'applied'
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    applied_version_id UUID REFERENCES prompt_versions(version_id),

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Agent Performance Reflector (APR)

The APR is a dedicated agent responsible for **meta-learning** — the system learning how to instruct itself. It runs periodically (triggered by the supervisor), reviews recent agent activity, and proposes prompt improvements.

#### APR Responsibilities

1. **Worker output quality review.** Did workers extract useful entities? Did they miss obvious things? Did they produce noise?
2. **Navigation pattern learning.** Workers found gold in unexpected places — update hints. Workers wasted time on empty sections — add deprioritization.
3. **Extraction pattern refinement.** Certain page templates or code patterns yield better entities with different instructions.
4. **Specialization detection.** A general worker type consistently handles one source differently — propose splitting into a specialized worker type.
5. **Cross-agent coordination improvements.** Coordinator dispatches redundant tasks — improve gap detection prompt. Workers duplicate entity extraction — improve dedup instructions.

#### APR Trigger Points

```
1. AFTER EACH COORDINATION CYCLE
   Supervisor dispatches APR with recent worker results:
   - Did outputs match coordinator expectations?
   - Any scope_overflow patterns? (scope instructions need tuning)
   - Any empty results? (navigation hints may be wrong)
   - Any unexpected high-value finds? (update hints)

2. AFTER N COMPLETED WORKERS (batch review)
   APR reviews patterns across multiple worker runs:
   - Consistent extraction gaps
   - Common entity resolution failures
   - Source-specific patterns the base prompt doesn't cover

3. AFTER ENGAGEMENT PAUSE/COMPLETE
   Full reflection pass:
   - What did we learn about each source type?
   - Which instructions led to high-value observations?
   - What should change for the next engagement?

4. ON USER FEEDBACK
   User says "that's wrong" or "focus more on X":
   - Direct prompt update proposal with high confidence
```

#### APR Output: Prompt Proposals

Each APR run produces zero or more proposals:

```json
{
  "agent_type": "worker:confluence",
  "section_key": "navigation_hints",
  "proposed_content": "Archive sections contain legacy domain documentation. Check these for domains not covered in Current State.",
  "diff_summary": "Add: check Archive for legacy domains",
  "reasoning": "Workers 7, 12, and 15 all found legacy domain documentation exclusively in Archive sections. Current hints deprioritize Archive.",
  "evidence_observations": ["obs-uuid-1", "obs-uuid-2", "obs-uuid-3"],
  "confidence": 0.85,
  "impact": "low"
}
```

#### Specialization Detection

The APR can propose **new agent types** when it detects that a general worker consistently needs source-specific behavior:

```
APR observation: "Workers dispatched to the GOV space consistently
need to extract regulatory references, compliance mappings, and
controlled entity lists — patterns not in the general Confluence
worker profile. Proposing: worker:confluence:governance as a
specialized type with governance-specific extraction rules."

Proposal:
  action: "create_agent_type"
  name: "worker:confluence:governance"
  parent_type: "worker:confluence"
  additional_sections:
    governance_extraction: "Look for regulatory references (GDPR,
      SOX, HIPAA). Extract controlled entity lists. Map policies
      to the services/data assets they govern."
  confidence: 0.78
  impact: "medium"  → requires human approval
```

### Auto-Apply vs Human Review

The governance boundary is based on **what the change affects:**

```
AUTO-APPLY (changes what you see):
├── Navigation hints (observed structure)
├── Source-specific patterns (page templates, naming conventions)
├── Alias additions (entity resolution improvements)
├── Deprioritization of empty/irrelevant areas
│
│   Criteria: confidence >= 0.7, evidence_count >= 2,
│             section_key in safe_sections

HUMAN REVIEW (changes what you look for):
├── Extraction criteria (what counts as an entity?)
├── Relationship type additions (new edge types)
├── Base prompt modifications
├── New agent type proposals (specialization)
├── Anything marked impact: "high"
```

**The rule: if it changes what you see, auto-apply. If it changes what you look for, ask a human.**

The supervisor applies auto-eligible proposals immediately. Human-review proposals accumulate in the queue and are applied when the user reviews them — the runtime never blocks.

### Prompt Evolution Visibility

Prompt changes are first-class auditable events, not hidden internals:

```
System: Discovery cycle 3 complete. 14 new entities found.

        I've auto-applied 2 prompt updates:
        → worker:confluence — added "Archive contains legacy
          domain docs" to navigation hints
          (evidence: 3 worker observations)
        → coordinator — added "payments-svc = Payments Service
          = PAYMENTS" alias (seen across 4 sources)

        1 proposal needs your review:
        → worker:confluence — Change extraction to capture
          "Decision" sections in ADR pages as first-class
          entities. Currently treated as observations.
          This would add ~40 decision entities.
          [Approve] [Reject] [Modify]
```

### The Virtuous Cycle

Prompt evolution observations are themselves Tier 1 data in the three-tier memory:

```
Tier 1: "Worker 7 found legacy docs in Archive section"
Tier 2: Knowledge item: "Archive sections contain legacy domain documentation"
Prompt: worker:confluence navigation_hints updated
Tier 3: Consolidated unit about Confluence source includes navigation pattern
```

The system learns about the world AND about how to learn about the world, through the same mechanism.

---

## 9. Context Management and Handoff

### Supervisor-Managed Agent Lifecycle

The supervisor (Python, not LLM) tracks context pressure for every active agent and handles lifecycle transitions autonomously — no human approval needed to spawn, handoff, or terminate agents.

```python
class AgentContext:
    max_tokens: int       # 100k coordinator, 50k workers
    estimated_used: int   # tracked from prompt + responses
    pressure: float       # used / max

    # Thresholds (supervisor acts autonomously)
    PLAN_HANDOFF = 0.6    # start planning handoff
    FLUSH_TO_DB = 0.75    # persist everything, slim context
    HARD_STOP = 0.9       # immediate handoff, no more tasks
```

### Coordinator Context Architecture

The coordinator operates on **projections** — purpose-built views of the knowledge graph that fit in a bounded token budget. It never holds the full graph in context.

```
COORDINATOR CONTEXT WINDOW (budget: ~100k tokens)
├── Problem statement: ~500 tokens (pinned, never evicted)
├── Coverage dashboard: ~1,000 tokens (regenerated each cycle)
│   "12 services found, 4 fully explored, 3 partially, 5 referenced only"
│   "8 databases found, 2 have governance docs, 6 do not"
│   "47 relationships mapped, 3 contradictions unresolved"
│
├── Active gaps: ~2,000 tokens (top 20 ranked by priority)
│   "payments-db: referenced 14 times, never directly explored"
│   "auth-service: called by 6 services, no Confluence docs found"
│
├── Recent findings: ~3,000 tokens (last N worker results, summarized)
│   "Worker 7 explored checkout-service: 3 new dependencies found"
│   "Worker 8 read Confluence/Architecture: contradicts worker 3"
│
├── Contradiction register: ~1,000 tokens
│   "Confluence says payments uses REST API; codebase shows direct DB"
│
├── Decision log: ~2,000 tokens (recent decisions with rationale)
│   "Dispatched worker to explore payments-db: 14 references, 0 exploration"
│   "Deprioritized logging-service: peripheral, low reference count"
│
└── Available: ~90k tokens for reasoning
```

### Coordinator Handoff Protocol

Because coordinators are stateless per-cycle (see Section 8), handoff is trivial — just spawn a new one. There's no conversation to transfer.

The only reasons to replace a coordinator:
- Its prompt needs updating (APR change)
- The engagement is splitting into sub-domains (new coordinator with narrower focus)
- The coordinator's focus domain has converged

**Process:** Supervisor terminates old coordinator, spawns new one. New coordinator reads problem statement from the engagement table, queries the graph for current state, and continues. Decision history is already in the observations table (each coordinator writes decisions as observations).

**Key insight:** The graph IS the state. Everything a coordinator needs to resume is queryable. No explicit state transfer protocol.

### Worker Context Rules

- Task directive + relevant context: bounded to ~5,000 tokens (provided by coordinator)
- Source material: read incrementally, don't load everything at once
- Working observations: write to graph as you go, don't accumulate
- If context exceeds 70% of window: stop, write findings, return `scope_overflow: true`
- **Workers never hand off.** If a task exceeds scope, decompose back to coordinator

### The Max Scope Parameter

Every worker task includes `max_scope` to prevent context overflow:

- **survey:** Read entry points only. README, top-level structure, config files.
- **focused:** Deep-dive on specific area identified by survey.
- **deep:** Exhaustive exploration of a bounded scope (single service, single Confluence page tree).

If a worker detects its task exceeds max_scope, it completes what it can, writes findings, and returns with a decomposition suggestion. The coordinator handles further breakdown.

### Worker Exploration Protocol

**Phase 1: Survey (broad, shallow).** Read entry points. Produce initial entity/relationship map. Identify areas needing deeper exploration.

**Phase 2: Targeted deep-dives (narrow, deep).** Based on survey, read specific files/pages/tickets most relevant to directive. Extract detailed observations.

**Phase 3: Report.** Write structured findings to graph. Include suggested follow-ups.

Each phase fits in a context window. Between phases, the worker writes intermediate findings to the graph.

### Autonomous Runtime Behavior

The system runs for hours without human intervention. Typical timeline:

```
00:00  Discovery starts, 4 sources configured
00:05  First survey workers complete. 47 entities found.
00:08  Coordinator dispatches 12 focused deep-dives.
00:15  APR runs. 2 auto-applied prompt updates, 1 queued for review.
       → Runtime continues without pausing.
00:20  Deep-dives completing. New gaps identified.
00:30  Coordinator context at 60%. Supervisor triggers handoff.
       → New coordinator spawns, picks up seamlessly.
00:45  User opens UI, sees 3 pending reviews.
       → Approves 2, rejects 1. APR notes rejection for learning.
01:00  Convergence detected. Supervisor pauses engagement.
       → User gets notification: "Discovery paused.
          147 entities, 89 relationships, 12 open gaps.
          Resume or synthesize?"
```

The user was never in the critical path. They could have been asleep.

---

## 10. Interface Design

### Three Interaction Modes

The system is **a process, not a conversation.** The conversation is just one way to interact with it.

```
1. SETUP (interactive, conversational)
   User + Configure Agent
   "Here are my sources, here's how to access them"
   Produces: source configs, initial worker profiles

2. RUNTIME (autonomous, hours/days)
   Supervisor + Coordinator + Workers + APR
   User is optional. UI is observatory.
   Human reviews accumulate in queue, applied when convenient.

3. INQUIRY (interactive, on-demand)
   User + Query Agent (reads knowledge graph)
   "What do we know about payments?"
   "Generate a dependency map"
   "What gaps remain?"
   Doesn't interrupt runtime — reads same DB.
```

### Core Principle: Stable Core, Disposable Views

Separate what's **stable** (engineered once) from what's **disposable** (generated on demand):

**Stable layer:**
- Knowledge graph in PostgreSQL
- Supervisor, coordinator, and worker agents
- API exposing the knowledge graph
- Source connectors and auth management

**Disposable layer:**
- Every visualization, dashboard, and stakeholder view is generated fresh from the knowledge graph
- If a view breaks, regenerate — don't debug
- Each view is self-contained with no dependencies on other views

### Primary Interface Layout

```
┌─ ALEC Discovery Intelligence ────────────────────────┐
│                                                       │
│  ┌─ Activity Feed ──────┬─ Agent Fleet ─────────────┐│
│  │ "Worker 12 done"     │ Coordinator: cycle 7      ││
│  │ "3 new entities"     │ Workers: 4/20 active      ││
│  │ "Proposal queued"    │ APR: idle (12min ago)     ││
│  │ "Auto-applied hint"  │ [Pause] [Resume] [Stop]  ││
│  ├──────────────────────┴───────────────────────────┤│
│  │                                                   ││
│  │  ┌─ Knowledge Graph ──┬─ Chat / Query ─────────┐ ││
│  │  │                    │                         │ ││
│  │  │  [interactive      │  > What do we know     │ ││
│  │  │   entity-relation  │    about the payments  │ ││
│  │  │   visualization]   │    service?            │ ││
│  │  │                    │                         │ ││
│  │  │                    │  System: payments-svc   │ ││
│  │  │                    │  is called by 6 svc... │ ││
│  │  └────────────────────┴─────────────────────────┘ ││
│  │                                                   ││
│  ├─ Pending Reviews ────────────────────────────────┤│
│  │ [1] Change extraction for ADR pages  [Y] [N] [?] ││
│  │ [2] Add new entity type: "SLA"       [Y] [N] [?] ││
│  │ [3] Specialize: worker:confluence:gov [Y] [N] [?]││
│  ├──────────────────────────────────────────────────┤│
│  │ ┌─ Prompt Management ──────────────────────────┐ ││
│  │ │ coordinator        v7  [view] [diff] [hist]  │ ││
│  │ │ worker:confluence  v4  [view] [diff] [hist]  │ ││
│  │ │ worker:github      v2  [view] [diff] [hist]  │ ││
│  │ │ worker:jira        v3  [view] [diff] [hist]  │ ││
│  │ │ apr                v1  [view] [diff] [hist]  │ ││
│  │ └──────────────────────────────────────────────┘ ││
│  └───────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────┘
```

### Worker Management Panel

The agent fleet section expands into a detailed management view:

```
┌─ Agent Fleet (expanded) ─────────────────────────────┐
│                                                       │
│  COORDINATOR                                          │
│  ├ Status: active (cycle 12, context 45%)             │
│  ├ Current prompt: v7                                 │
│  ├ Handoffs: 2 (automatic, no intervention needed)    │
│  └ [View prompt] [View decision log] [Force handoff]  │
│                                                       │
│  WORKERS                                              │
│  ├ Active: 4/20 slots                                 │
│  │  ├ worker-18: confluence/DATA/Customer (72%)       │
│  │  ├ worker-19: github/data-pipeline (45%)           │
│  │  ├ worker-20: jira/DATA project (31%)              │
│  │  └ worker-21: confluence/GOV/Policies (88%)        │
│  ├ Queued: 6 tasks                                    │
│  ├ Completed: 34 (avg 4.2 entities/worker)            │
│  ├ Failed: 1 (auth expired on SharePoint)             │
│  └ [View queue] [Adjust concurrency] [View history]   │
│                                                       │
│  AGENT PERFORMANCE REFLECTOR                          │
│  ├ Status: idle (last run: 12min ago)                 │
│  ├ Runs: 4 total                                      │
│  ├ Auto-applied: 7 changes                            │
│  ├ Pending review: 3 proposals                        │
│  ├ Rejected: 1 (user declined extraction change)      │
│  └ [View proposals] [Run now] [View history]           │
│                                                       │
│  SOURCE HEALTH                                        │
│  ├ confluence: OK (last access 2min ago)              │
│  ├ github: OK (last access 5min ago)                  │
│  ├ jira: OK (last access 3min ago)                    │
│  └ sharepoint: AUTH EXPIRED [Reconnect]               │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### Interaction Examples

**Starting discovery (Setup mode):**
```
> I need to understand how the contents of this Confluence space,
  these 12 GitHub repos, these 3 Jira projects, and this SharePoint
  folder of governance docs intersect. Focus on data dependencies
  and ownership.
```

**Requesting a view (Inquiry mode):**
```
> Show me a dependency map of all services and their database
  connections, color-coded by whether the dependency is documented.
```

**Adding manual observation (Inquiry mode):**
```
> I just learned from the payments team lead that they're planning
  to split the payments database into two schemas by Q3.
```

**Stakeholder output (Inquiry mode):**
```
> Generate a view for the compliance team showing all data assets
  that appear in code but aren't registered in any catalog.
```

### Why Views Are Disposable

Generated views should never be maintained as code because:
- New requirement = new view (not modifying existing code)
- No debugging visualizations (data problem → fix graph; rendering problem → regenerate)
- No technical debt accumulation
- The agent gets better at generating views because the knowledge graph provides a stable, well-typed data source

---

## 11. Application Layout

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Application Server (Python)                            │
│                                                         │
│  ┌─────────────────┐    ┌───────────────────────────┐  │
│  │  API (FastAPI)   │    │  Runtime (asyncio)        │  │
│  │                  │    │                           │  │
│  │  REST endpoints  │    │  Supervisor               │  │
│  │  WebSocket feed  │◄──►│  ├── Coordinator(s)       │  │
│  │  Query Agent     │    │  ├── Worker pool           │  │
│  │  Configure Agent │    │  ├── APR                   │  │
│  │                  │    │  └── Consolidation         │  │
│  └────────┬─────────┘    └─────────────┬─────────────┘  │
│           │                            │                 │
│           │    ┌───────────────────┐   │                 │
│           └───►│  Event Bus        │◄──┘                 │
│                │  (in-process)     │                     │
│                └───────────────────┘                     │
│                          │                               │
│  ┌───────────────────────┼───────────────────────────┐  │
│  │  LLM Client (async, pooled, abstracted)           │  │
│  │  → Anthropic / enterprise LLM gateway / etc.      │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Postgres │ │ Postgres │ │ pgvector │
        │ (state)  │ │ (NOTIFY) │ │ (embeds) │
        └──────────┘ └──────────┘ └──────────┘

┌─────────────────────────────────────────────────────────┐
│  Frontend (React/TypeScript)                            │
│                                                         │
│  REST ──► API endpoints                                 │
│  WS   ──► Real-time event feed                          │
└─────────────────────────────────────────────────────────┘
```

**Communication between API and Runtime:** In-process asyncio event bus for single-server deployment. For multi-server (AWS), PostgreSQL `LISTEN/NOTIFY` — zero additional infrastructure, built into Postgres. The API subscribes to runtime events and forwards them to WebSocket clients.

**LLM Client abstraction:** The `LLMClient` interface is pluggable — Anthropic API for development, enterprise LLM gateway/proxy for production. All agents call the same interface. Rate limiting, token tracking, and budget enforcement happen here.

### Application Structure

```
alec_v5/
│
├── alec/                          # Python package root
│   │
│   ├── api/                       # FastAPI application
│   │   ├── app.py                 # App factory, CORS, lifespan (starts runtime)
│   │   ├── deps.py                # Dependency injection (db pool, event bus, runtime ref)
│   │   ├── routes/
│   │   │   ├── engagements.py     # CRUD engagements, start/pause/resume
│   │   │   ├── models.py          # Model CRUD, alignment queries
│   │   │   ├── graph.py           # Entity/relationship browsing, projections
│   │   │   ├── agents.py          # Fleet status, worker queue, coordinator state
│   │   │   ├── proposals.py       # APR proposal review (approve/reject)
│   │   │   ├── prompts.py         # Prompt version viewing, diffing, history
│   │   │   ├── configure.py       # Source setup (interactive, stateful)
│   │   │   ├── query.py           # Query Agent endpoint (user questions)
│   │   │   └── events.py          # WebSocket: real-time event stream to UI
│   │   └── schemas/               # Pydantic request/response models
│   │       ├── engagement.py
│   │       ├── model.py
│   │       ├── entity.py
│   │       ├── agent.py
│   │       └── event.py
│   │
│   ├── runtime/                   # Autonomous execution engine
│   │   ├── supervisor.py          # Main loop: lifecycle, budget, convergence
│   │   ├── coordinator.py         # Per-cycle: projection → LLM → task directives
│   │   ├── worker.py              # Tool-use loop: source tools + graph tools
│   │   ├── apr.py                 # Ground-truth collector: pattern detection + hints
│   │   ├── consolidation.py       # Sleep process: Tier 2 → Tier 3 synthesis
│   │   ├── budget.py              # Token/cost tracking and enforcement
│   │   └── convergence.py         # Alignment stability metric
│   │
│   ├── agents/                    # LLM interaction layer
│   │   ├── llm_client.py          # Abstract LLM interface (pluggable backend)
│   │   ├── prompt_assembler.py    # Base + learned sections + directive → prompt
│   │   ├── tool_executor.py       # Execute tool calls, validate results
│   │   ├── prompts/               # Base prompt templates
│   │   │   ├── coordinator.py     # "Given this projection, generate task directives"
│   │   │   ├── worker.py          # "Explore this source, extract entities/relationships"
│   │   │   ├── query.py           # "Answer this question from the knowledge graph"
│   │   │   ├── configure.py       # "Guide the user through source setup"
│   │   │   └── consolidation.py   # "Synthesize these observations cross-model"
│   │   └── tools/                 # Tool definitions (JSON schema for LLM)
│   │       ├── graph_tools.py     # add_entity, add_relationship, add_observation, etc.
│   │       ├── source_tools.py    # read, search, list_children, survey
│   │       └── coordinator_tools.py  # dispatch_worker, record_decision, signal_convergence
│   │
│   ├── knowledge/                 # Knowledge graph operations
│   │   ├── entities.py            # Entity CRUD, resolution, alias management
│   │   ├── relationships.py       # Relationship CRUD, evidence tracking
│   │   ├── models.py              # Model CRUD, purpose/perspective metadata
│   │   ├── alignments.py          # Cross-model alignment operations
│   │   ├── observations.py        # Tier 1: append-only observation log
│   │   ├── knowledge_items.py     # Tier 2: structured index with embeddings
│   │   ├── consolidated.py        # Tier 3: synthesized summaries
│   │   ├── projections.py         # Bounded graph views for coordinator
│   │   │                          #   - alignment_state(model_id)
│   │   │                          #   - unresolved_contradictions()
│   │   │                          #   - orphan_entities()
│   │   │                          #   - convergence_dashboard()
│   │   │                          #   - coverage_by_model()
│   │   └── recall.py              # Budget-aware retrieval for context injection
│   │
│   ├── connectors/                # Source access layer
│   │   ├── protocol.py            # SourceConnector protocol (read-only interface)
│   │   ├── registry.py            # Connector registry (type → implementation)
│   │   ├── rate_limiter.py        # Per-source rate limiting wrapper
│   │   ├── local_files.py         # Local filesystem connector (for dev/testing)
│   │   ├── git.py                 # Git repository connector (clone + read)
│   │   └── mcp.py                 # MCP adapter (wraps any MCP server)
│   │                              # Additional connectors added per engagement:
│   │                              #   confluence.py, jira.py, sharepoint.py, etc.
│   │
│   ├── pipeline/                  # Developer Pipeline (shared capability)
│   │   ├── pipeline.py            # Orchestrator: cache check → generate → validate → execute
│   │   ├── generator.py           # LLM code generation
│   │   ├── validators/            # Static analysis (deterministic, no LLM)
│   │   │   ├── sql.py             # SQL read-only validation
│   │   │   ├── python.py          # Python AST safety check
│   │   │   └── jql.py             # JQL/CQL validation
│   │   ├── sandbox.py             # Sandboxed execution (timeout, resource limits)
│   │   └── assets.py              # Code asset library (embedding cache + reuse)
│   │
│   ├── events/                    # Internal event system
│   │   ├── bus.py                 # In-process async event bus
│   │   ├── types.py               # Event type definitions (dataclasses)
│   │   └── pg_notify.py           # PostgreSQL LISTEN/NOTIFY adapter
│   │                              #   (for multi-process deployment)
│   │
│   ├── db/                        # Database layer
│   │   ├── pool.py                # asyncpg connection pool management
│   │   ├── schema.sql             # Complete DDL
│   │   ├── migrations/            # Incremental schema migrations
│   │   └── embeddings.py          # Embedding generation (async, batched)
│   │
│   └── config/                    # Configuration
│       ├── settings.py            # Pydantic settings (env vars, defaults)
│       └── llm_backends.py        # LLM backend configs (Anthropic, enterprise, etc.)
│
├── frontend/                      # React/TypeScript UI
│   ├── src/
│   │   ├── api/                   # API client + WebSocket connection
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx      # Engagement overview: fleet, activity, convergence
│   │   │   ├── Graph.tsx          # Knowledge graph visualization (entity-relationship)
│   │   │   ├── Models.tsx         # Model comparison: alignment map, divergences
│   │   │   ├── Agents.tsx         # Fleet management: workers, coordinators, APR
│   │   │   ├── Proposals.tsx      # APR proposal review queue
│   │   │   ├── Prompts.tsx        # Prompt version management (view, diff, history)
│   │   │   ├── Query.tsx          # Chat interface for inquiry mode
│   │   │   ├── Setup.tsx          # Source configuration wizard
│   │   │   └── Engagement.tsx     # Engagement CRUD, problem statement, sources
│   │   ├── components/
│   │   │   ├── ActivityFeed.tsx   # Real-time event stream
│   │   │   ├── AlignmentMap.tsx   # Cross-model alignment visualization
│   │   │   ├── EntityDetail.tsx   # Entity with cross-model appearances
│   │   │   ├── ConvergenceGauge.tsx # Reinforcement/expansion/challenge ratio
│   │   │   ├── WorkerStatus.tsx   # Individual worker progress
│   │   │   └── PromptDiff.tsx     # Side-by-side prompt version comparison
│   │   └── hooks/
│   │       ├── useWebSocket.ts    # Real-time event subscription
│   │       ├── useEngagement.ts   # Engagement state management
│   │       └── useGraph.ts        # Graph query hooks
│   └── package.json
│
├── docker-compose.yml             # PostgreSQL + pgvector (app runs natively or in container)
├── pyproject.toml                 # Python project config
├── Dockerfile                     # Application container
└── docs/
    └── design/
        └── ALEC_v5_design.md      # This document
```

### Module Interface Map

Who calls whom, and through what interface:

```
API Routes ──► runtime.supervisor      (start/pause/resume engagement)
API Routes ──► knowledge.*             (read graph state for UI)
API Routes ──► agents.llm_client       (Query Agent, Configure Agent)
API Routes ◄── events.bus              (subscribe to real-time events)

Supervisor ──► coordinator             (trigger cycle)
Supervisor ──► worker                  (dispatch task)
Supervisor ──► apr                     (trigger reflection)
Supervisor ──► consolidation           (trigger sleep)
Supervisor ──► convergence             (check alignment stability)
Supervisor ──► budget                  (check before any LLM call)
Supervisor ──► events.bus              (emit lifecycle events)

Coordinator ──► knowledge.projections  (read bounded graph views)
Coordinator ──► agents.llm_client      (1 call/cycle: generate directives)
Coordinator ──► agents.prompt_assembler (build prompt from base + learned)

Worker ──► connectors.protocol         (read source material)
Worker ──► knowledge.entities          (write entities)
Worker ──► knowledge.relationships     (write relationships)
Worker ──► knowledge.observations      (write observations)
Worker ──► agents.llm_client           (5-10 calls: extraction loop)
Worker ──► pipeline.pipeline           (when dynamic query needed)
Worker ──► events.bus                  (emit completion events)

APR ──► knowledge.observations         (read recent worker outputs)
APR ──► knowledge.projections          (read worker performance data)
APR ──► db (prompt_proposals)          (write proposals)
APR ──► agents.llm_client              (occasional: draft hint text)

Consolidation ──► knowledge.knowledge_items  (read Tier 2)
Consolidation ──► knowledge.consolidated     (write Tier 3)
Consolidation ──► agents.llm_client          (synthesize summaries)

Pipeline ──► pipeline.assets           (check cache)
Pipeline ──► agents.llm_client         (generate code if not cached)
Pipeline ──► pipeline.validators       (static analysis)
Pipeline ──► pipeline.sandbox          (execute)
Pipeline ──► pipeline.assets           (store proven query)

All modules ──► db.pool                (asyncpg connection pool)
All modules ──► db.embeddings          (embedding generation)
```

### Database Schema (Complete)

```sql
-- ============================================================
-- ENGAGEMENT
-- ============================================================

CREATE TABLE engagements (
    engagement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    status TEXT DEFAULT 'setup',
        -- 'setup', 'active', 'paused', 'converged', 'archived'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    config JSONB DEFAULT '{}'
        -- convergence_thresholds, budget_limits, cycle_interval
);

-- ============================================================
-- MODELS & ALIGNMENT (Section 12)
-- ============================================================

CREATE TABLE models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    model_type TEXT NOT NULL,
        -- 'discovered', 'proposed', 'synthesized'
    purpose TEXT,
    perspective TEXT,
    expected_divergences TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TIER 1: RAW OBSERVATIONS (append-only)
-- ============================================================

CREATE TABLE observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    session_id UUID,             -- which runtime session produced this
    worker_id TEXT,
    source_ref TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    observation_type TEXT NOT NULL,
        -- 'entity', 'relationship', 'insight', 'contradiction',
        -- 'gap', 'decision', 'alignment'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- ============================================================
-- TIER 2: STRUCTURED INDEX
-- ============================================================

CREATE TABLE entities (
    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    model_id UUID REFERENCES models(model_id),
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
        -- 'service', 'database', 'team', 'api', 'policy',
        -- 'person', 'document', 'capability', 'domain',
        -- 'repository', 'schema', 'process'
    aliases TEXT[] DEFAULT '{}',
    embedding vector(1536),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_referenced TIMESTAMPTZ DEFAULT NOW(),
    observation_count INT DEFAULT 0,
    status TEXT DEFAULT 'active',
        -- 'active', 'merged', 'deprecated'
    properties JSONB DEFAULT '{}'
);

CREATE TABLE relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    from_entity UUID NOT NULL REFERENCES entities(entity_id),
    to_entity UUID NOT NULL REFERENCES entities(entity_id),
    relationship_type TEXT NOT NULL,
        -- 'depends_on', 'owned_by', 'reads_from', 'writes_to',
        -- 'calls', 'governs', 'implements', 'contains',
        -- 'supersedes', 'related_to'
    evidence UUID[] DEFAULT '{}',
    confidence FLOAT DEFAULT 0.5,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_confirmed TIMESTAMPTZ DEFAULT NOW(),
    properties JSONB DEFAULT '{}'
);

CREATE TABLE alignments (
    alignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    from_entity UUID NOT NULL REFERENCES entities(entity_id),
    to_entity UUID NOT NULL REFERENCES entities(entity_id),
    alignment_type TEXT NOT NULL,
        -- 'equivalent', 'overlaps_with', 'contains',
        -- 'contained_by', 'implements', 'contradicts',
        -- 'unaligned', 'supersedes'
    confidence FLOAT DEFAULT 0.5,
    evidence UUID[] DEFAULT '{}',
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    content TEXT NOT NULL,
    embedding vector(1536),
    entities_referenced UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    reinforcement_count INT DEFAULT 1,
    last_retrieved TIMESTAMPTZ,
    superseded_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active'
        -- 'active', 'consolidated', 'superseded', 'decayed'
);

-- ============================================================
-- TIER 3: CONSOLIDATED KNOWLEDGE
-- ============================================================

CREATE TABLE consolidated_units (
    unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    subject_entity UUID REFERENCES entities(entity_id),
    related_entities UUID[] DEFAULT '{}',
    summary TEXT NOT NULL,
    embedding vector(1536),
    source_items UUID[] DEFAULT '{}',
    source_observations UUID[] DEFAULT '{}',
    token_count INT NOT NULL,
    freshness TIMESTAMPTZ DEFAULT NOW(),
    retrieval_count INT DEFAULT 0,
    version INT DEFAULT 1,
    status TEXT DEFAULT 'current'
        -- 'current', 'stale', 'archived'
);

-- ============================================================
-- AGENT GOVERNANCE
-- ============================================================

CREATE TABLE agent_types (
    agent_type_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE prompt_versions (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type_id UUID NOT NULL REFERENCES agent_types(agent_type_id),
    version_number INT NOT NULL,
    base_prompt TEXT NOT NULL,
    learned_sections JSONB DEFAULT '{}',
    parent_version_id UUID REFERENCES prompt_versions(version_id),
    change_summary TEXT NOT NULL,
    change_type TEXT NOT NULL,
        -- 'initial', 'manual', 'auto_applied', 'human_approved'
    change_source TEXT,
    evidence JSONB DEFAULT '{}',
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_type_id, version_number)
);

CREATE TABLE prompt_proposals (
    proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    agent_type_id UUID NOT NULL REFERENCES agent_types(agent_type_id),
    current_version_id UUID REFERENCES prompt_versions(version_id),
    section_key TEXT NOT NULL,
    proposed_content TEXT NOT NULL,
    diff_summary TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    evidence_observations UUID[],
    confidence FLOAT NOT NULL,
    impact TEXT NOT NULL,
    auto_apply_eligible BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'pending',
        -- 'pending', 'approved', 'rejected', 'applied'
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    applied_version_id UUID REFERENCES prompt_versions(version_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- RUNTIME STATE
-- ============================================================

CREATE TABLE coordinator_instances (
    instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    focus_domain TEXT,
    source_filter TEXT[],
    prompt_version_id UUID REFERENCES prompt_versions(version_id),
    status TEXT DEFAULT 'active',
        -- 'active', 'converged', 'merged', 'terminated'
    cycles_completed INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    coordinator_id UUID REFERENCES coordinator_instances(instance_id),
    directive TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    max_scope TEXT DEFAULT 'survey',
        -- 'survey', 'focused', 'deep'
    relevant_context TEXT,
    status TEXT DEFAULT 'queued',
        -- 'queued', 'assigned', 'running', 'completed', 'failed'
    assigned_worker TEXT,
    result_summary JSONB,
        -- {entities_written, observations_written, scope_overflow, ...}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE convergence_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    cycle_number INT NOT NULL,
    reinforcement_count INT DEFAULT 0,
    expansion_count INT DEFAULT 0,
    challenge_count INT DEFAULT 0,
    ratio FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- SOURCE CONFIGURATION
-- ============================================================

CREATE TABLE source_configs (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    source_type TEXT NOT NULL,
    config JSONB NOT NULL,
    auth_config JSONB DEFAULT '{}',
    worker_profile JSONB DEFAULT '{}',
        -- Navigation hints, vocabulary, structure notes
        -- captured during guided setup
    status TEXT DEFAULT 'pending',
        -- 'pending', 'verified', 'failed', 'disabled'
    last_accessed TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- DEVELOPER PIPELINE
-- ============================================================

CREATE TABLE code_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    description TEXT NOT NULL,
    description_embedding vector(1536),
    language TEXT NOT NULL,
    code TEXT NOT NULL,
    source_type TEXT NOT NULL,
    generated_by TEXT,
    usage_count INT DEFAULT 1,
    success_count INT DEFAULT 1,
    failure_count INT DEFAULT 0,
    last_used TIMESTAMPTZ DEFAULT NOW(),
    validated BOOLEAN DEFAULT TRUE,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_executions (
    execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES code_assets(asset_id),
    requesting_agent TEXT NOT NULL,
    request_description TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    result_summary TEXT,
    error_message TEXT,
    execution_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_entities_embedding ON entities
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_knowledge_items_embedding ON knowledge_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_consolidated_embedding ON consolidated_units
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_code_assets_embedding ON code_assets
    USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_entities_engagement ON entities(engagement_id);
CREATE INDEX idx_entities_model ON entities(model_id);
CREATE INDEX idx_relationships_engagement ON relationships(engagement_id);
CREATE INDEX idx_alignments_engagement ON alignments(engagement_id);
CREATE INDEX idx_observations_engagement ON observations(engagement_id);
CREATE INDEX idx_tasks_engagement_status ON tasks(engagement_id, status);
CREATE INDEX idx_convergence_engagement ON convergence_log(engagement_id, cycle_number);
```

### Event Types

```python
# events/types.py — all internal events

@dataclass
class EngagementStarted:
    engagement_id: UUID

@dataclass
class CoordinatorCycleCompleted:
    engagement_id: UUID
    coordinator_id: UUID
    cycle_number: int
    tasks_dispatched: int
    gaps_remaining: int

@dataclass
class WorkerDispatched:
    engagement_id: UUID
    task_id: UUID
    worker_id: str
    source_type: str
    source_ref: str

@dataclass
class WorkerCompleted:
    engagement_id: UUID
    task_id: UUID
    worker_id: str
    entities_written: int
    observations_written: int
    scope_overflow: bool

@dataclass
class WorkerFailed:
    engagement_id: UUID
    task_id: UUID
    worker_id: str
    error: str

@dataclass
class AlignmentDetected:
    engagement_id: UUID
    alignment_id: UUID
    alignment_type: str          # equivalent, contradicts, etc.
    from_entity_name: str
    to_entity_name: str
    classification: str          # expected, unexpected, convergence

@dataclass
class ConvergenceUpdate:
    engagement_id: UUID
    cycle_number: int
    ratio: float                 # reinforcement / (expansion + challenge + 1)
    converged: bool

@dataclass
class ProposalCreated:
    engagement_id: UUID
    proposal_id: UUID
    agent_type: str
    section_key: str
    auto_apply_eligible: bool

@dataclass
class ProposalApplied:
    engagement_id: UUID
    proposal_id: UUID
    new_version_id: UUID

@dataclass
class ConsolidationCompleted:
    engagement_id: UUID
    units_created: int
    units_updated: int

@dataclass
class EngagementConverged:
    engagement_id: UUID
    total_entities: int
    total_alignments: int
    models_count: int
```

### Identified Gaps

The layout exercise reveals these gaps in the current design:

**GAP 1: Entity resolution ownership.** Who creates alignments? The design describes alignment types but not the process. Options:
- (a) Workers detect cross-model entities inline during extraction
- (b) Coordinator runs alignment detection as part of each cycle
- (c) A dedicated alignment process runs after workers complete
- Recommendation: (b) — coordinator already reads projections and has cross-model visibility. Add alignment detection to the coordinator cycle between "merge results" and "detect gaps."

**GAP 2: Model creation from sources.** Workers discover entities within sources, but who creates the `models` table entries? During setup, the Configure Agent creates models from user input (purpose, perspective). But what about models discovered organically — e.g., a worker finds an internal taxonomy document that nobody mentioned during setup?
- Recommendation: Workers can propose new models via a `suggest_model` graph tool. Coordinator evaluates and creates if warranted. User sees new models in the review queue.

**GAP 3: Configure Agent lifecycle.** The Configure Agent is interactive (user conversation) but the runtime is autonomous. How does the API handle a multi-turn setup conversation?
- Recommendation: Configure Agent is an API-side agent, not a runtime agent. It runs within the request/response cycle of the `/configure` endpoint, persisting conversation state in the session. It writes directly to `source_configs` and `models` tables. It does NOT go through the supervisor.

**GAP 4: Query Agent lifecycle.** Same issue. The Query Agent answers user questions interactively.
- Recommendation: Same as Configure Agent — API-side, not runtime. It reads the knowledge graph via `knowledge.*` modules, uses the Developer Pipeline for dynamic queries, and returns synthesized answers. Independent of the supervisor.

**GAP 5: Real-time UI event granularity.** What events does the UI need to render the dashboard? The event types above are a starting set. But the Activity Feed likely needs finer grain — e.g., "Worker 12 reading page Confluence/DATA/Customer/Current-State" for live progress indication.
- Recommendation: Workers emit periodic `WorkerProgress` events (current_action, tokens_used, entities_so_far). Throttled to 1/sec per worker to avoid flooding.

**GAP 6: Engagement state machine transitions.** Who transitions engagement status? The supervisor handles active→paused→converged. But setup→active is triggered by the user ("start discovery"). And paused→active is "resume."
- Recommendation: API handles setup→active (user trigger) and paused→active (user resume). Supervisor handles active→paused (convergence or budget) and active→converged. Archived is manual.

**GAP 7: Multi-coordinator coordination.** The design describes multiple coordinators sharing a graph. But the supervisor needs rules for: when to propose splitting, how to divide sources, how to detect when coordinators' domains have converged enough to merge.
- Recommendation: Start with single coordinator. Multi-coordinator is a later optimization. The architecture supports it (coordinator_instances table exists) but the supervisor logic starts simple.

**GAP 8: Embedding generation strategy.** Multiple tables need embeddings (entities, knowledge_items, consolidated_units, code_assets). Who generates them and when?
- Recommendation: `db/embeddings.py` provides an async batch embedding service. Workers and consolidation call it inline. Batching amortizes API calls (embed 20 texts in one call, not 20 calls). The LLM client abstraction applies here too — enterprise may have a different embedding endpoint.

### UI & Admin Surface Area

The autonomous runtime is half the application. The UI, admin APIs, and management interfaces are the other half. Underestimating this is the classic "it's just CRUD" trap — in practice this is where all the edge cases live.

#### Domain Map: 10 Management Areas

```
┌─────────────────────────────────────────────────────────────┐
│  ALEC v5 — Full UI Surface                                  │
│                                                             │
│  ┌─ ENGAGEMENT MANAGEMENT ────────────────────────────────┐ │
│  │  Create / configure / start / pause / resume / archive │ │
│  │  Problem statement, convergence criteria, budget limits │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ SOURCE CONFIGURATION ─────────────────────────────────┐ │
│  │  Guided setup wizard (interactive, multi-step)         │ │
│  │  Credential management (add/rotate/test)               │ │
│  │  Health monitoring (status, last access, error log)    │ │
│  │  Re-authentication flow when tokens expire             │ │
│  │  Source-specific settings (spaces, repos, projects)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ AGENT LIBRARY ────────────────────────────────────────┐ │
│  │  Browse agent types (coordinator, worker:*, query, etc)│ │
│  │  View/edit base prompts                                │ │
│  │  View/edit learned sections per agent type              │ │
│  │  Version history with full diff view                   │ │
│  │  Create specialized agent types                        │ │
│  │  Copy agent configs between engagements                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ AGENT FLEET (runtime observatory) ────────────────────┐ │
│  │  Coordinator: cycle count, context %, current focus    │ │
│  │  Workers: active/queued/completed/failed, live progress│ │
│  │  APR: last run, proposals generated, auto-applied count│ │
│  │  Controls: adjust concurrency, kill worker, force cycle│ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ PROPOSAL REVIEW ─────────────────────────────────────┐ │
│  │  Queue of pending APR proposals                        │ │
│  │  Evidence display (source observations, worker outputs)│ │
│  │  Approve / reject / modify actions                     │ │
│  │  History of past decisions (audit trail)               │ │
│  │  Auto-applied changelog                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ KNOWLEDGE GRAPH BROWSER ──────────────────────────────┐ │
│  │  Entity list with search/filter by model, type, status │ │
│  │  Entity detail: cross-model appearances, relationships │ │
│  │  Relationship explorer (from entity, follow edges)     │ │
│  │  Graph visualization (interactive, zoomable)           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ MODEL & ALIGNMENT MAP ────────────────────────────────┐ │
│  │  Model list with purpose, perspective, entity counts   │ │
│  │  Model detail: entities, internal relationships        │ │
│  │  Alignment map: cross-model view with divergence types │ │
│  │  Edit model metadata (purpose, perspective, expected)  │ │
│  │  Create model manually (user's proposed ontology)      │ │
│  │  Divergence report: expected vs unexpected, orphans    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ INQUIRY / QUERY INTERFACE ────────────────────────────┐ │
│  │  Chat-style Q&A against knowledge graph                │ │
│  │  Add manual observations ("I just learned that...")    │ │
│  │  Request generated views / reports                     │ │
│  │  Drill-down: consolidated → knowledge items → raw obs  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ MEMORY / CONSOLIDATION ───────────────────────────────┐ │
│  │  Tier 1→2→3 pipeline visibility                        │ │
│  │  Consolidated units browser (entity-scoped summaries)  │ │
│  │  Trigger manual consolidation                          │ │
│  │  Staleness indicators (units needing refresh)          │ │
│  │  Cross-link discoveries (emergence findings)           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌─ OPERATIONS ───────────────────────────────────────────┐ │
│  │  Budget dashboard: token spend, API calls, per-agent   │ │
│  │  Activity feed: real-time events, filterable by type   │ │
│  │  Convergence gauge: reinforcement/expansion/challenge  │ │
│  │  Developer Pipeline: code asset library, execution log │ │
│  │  Source health: connection status, rate limit state    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### API Endpoint Inventory

Each management area requires its own set of API endpoints. This is the full scope:

**Engagement Management (7 endpoints)**
```
POST   /api/engagements                    Create engagement
GET    /api/engagements                    List engagements
GET    /api/engagements/:id                Get engagement detail
PATCH  /api/engagements/:id                Update engagement (name, config)
POST   /api/engagements/:id/start          Start discovery runtime
POST   /api/engagements/:id/pause          Pause runtime
POST   /api/engagements/:id/resume         Resume runtime
```

**Source Configuration (8 endpoints)**
```
POST   /api/engagements/:id/sources        Add source config
GET    /api/engagements/:id/sources        List sources for engagement
GET    /api/sources/:id                    Get source detail
PATCH  /api/sources/:id                    Update source config
DELETE /api/sources/:id                    Remove source
POST   /api/sources/:id/test               Test source connectivity
POST   /api/sources/:id/refresh-auth       Re-authenticate
WS     /api/sources/:id/setup              Interactive setup wizard (stateful)
```

**Agent Library (10 endpoints)**
```
GET    /api/agent-types                    List all agent types
POST   /api/agent-types                    Create agent type (specialization)
GET    /api/agent-types/:id                Get agent type detail
PATCH  /api/agent-types/:id                Update agent type metadata
GET    /api/agent-types/:id/versions       List prompt versions
GET    /api/agent-types/:id/versions/:v    Get specific version
GET    /api/agent-types/:id/versions/:v/diff  Diff two versions
POST   /api/agent-types/:id/versions       Create new version (manual edit)
GET    /api/agent-types/:id/current        Get current active prompt (assembled)
POST   /api/agent-types/:id/rollback       Rollback to previous version
```

**Agent Fleet (7 endpoints)**
```
GET    /api/engagements/:id/fleet          Fleet overview (coordinator + workers + APR)
GET    /api/engagements/:id/coordinator    Coordinator detail (cycle, context %)
GET    /api/engagements/:id/workers        Worker list (active, queued, history)
GET    /api/engagements/:id/workers/:wid   Worker detail (progress, current action)
POST   /api/engagements/:id/workers/:wid/kill  Kill specific worker
PATCH  /api/engagements/:id/fleet/config   Update fleet config (concurrency, etc.)
POST   /api/engagements/:id/coordinator/cycle  Force coordinator cycle
```

**Proposal Review (5 endpoints)**
```
GET    /api/engagements/:id/proposals          List proposals (pending, applied, rejected)
GET    /api/proposals/:id                      Get proposal detail with evidence
POST   /api/proposals/:id/approve              Approve proposal
POST   /api/proposals/:id/reject               Reject proposal (with reason)
PATCH  /api/proposals/:id                      Modify proposal before approving
```

**Knowledge Graph (10 endpoints)**
```
GET    /api/engagements/:id/entities           List entities (filter: model, type, status)
GET    /api/entities/:id                       Entity detail (cross-model, relationships)
PATCH  /api/entities/:id                       Edit entity (name, aliases, properties)
POST   /api/entities/:id/merge                 Merge two entities
GET    /api/engagements/:id/relationships      List relationships (filter: type, entity)
GET    /api/engagements/:id/observations       List observations (filter: type, source, worker)
GET    /api/engagements/:id/graph/search       Semantic search across entities
GET    /api/engagements/:id/graph/neighbors    Get N-hop neighborhood of entity
GET    /api/engagements/:id/graph/paths        Find paths between two entities
GET    /api/engagements/:id/graph/stats        Graph statistics (counts, density, coverage)
```

**Model & Alignment (9 endpoints)**
```
GET    /api/engagements/:id/models             List models
POST   /api/engagements/:id/models             Create model (user's proposed ontology)
GET    /api/models/:id                         Model detail (entities, purpose, perspective)
PATCH  /api/models/:id                         Edit model metadata
GET    /api/engagements/:id/alignments         List alignments (filter: type, model pair)
POST   /api/engagements/:id/alignments         Create manual alignment
PATCH  /api/alignments/:id                     Edit alignment (type, confidence, notes)
GET    /api/engagements/:id/alignment-map       Cross-model alignment summary
GET    /api/engagements/:id/divergences         Divergence report (expected vs unexpected)
```

**Inquiry / Query (3 endpoints)**
```
POST   /api/engagements/:id/query              Ask question (Query Agent)
POST   /api/engagements/:id/observations       Add manual observation
POST   /api/engagements/:id/views/generate     Request generated view/report
```

**Memory / Consolidation (5 endpoints)**
```
GET    /api/engagements/:id/knowledge-items    List Tier 2 items
GET    /api/engagements/:id/consolidated       List Tier 3 consolidated units
GET    /api/consolidated/:id                   Consolidated unit detail (full provenance)
POST   /api/engagements/:id/consolidate        Trigger manual consolidation
GET    /api/engagements/:id/consolidation/status Pipeline status (stale clusters, etc.)
```

**Operations (6 endpoints)**
```
GET    /api/engagements/:id/budget             Budget dashboard (tokens, cost, per-agent)
GET    /api/engagements/:id/convergence        Convergence state (ratio, history)
GET    /api/engagements/:id/activity           Activity log (paginated, filterable)
WS     /api/engagements/:id/events             WebSocket: real-time event stream
GET    /api/engagements/:id/pipeline/assets    Code asset library
GET    /api/engagements/:id/pipeline/executions Execution audit trail
```

**Total: ~70 API endpoints across 10 management areas.**

#### UI Complexity Assessment

| Management Area | Pages | Complexity | Why |
|---|---|---|---|
| Engagement Management | 2 | Low | Standard CRUD + state machine controls |
| Source Configuration | 3 | **High** | Interactive wizard with multi-step stateful conversation, credential handling, health monitoring |
| Agent Library | 3 | **High** | Prompt editor with syntax highlighting, version diff view, learned section management, cross-engagement copy |
| Agent Fleet | 2 | Medium | Real-time updates via WebSocket, worker progress bars, controls |
| Proposal Review | 2 | Medium | Evidence display, diff preview, approval workflow |
| Knowledge Graph | 3 | **High** | Interactive graph visualization, semantic search, entity detail with cross-model view |
| Model & Alignment | 3 | **High** | Alignment map visualization, divergence classification, model comparison |
| Inquiry / Query | 1 | Medium | Chat interface, progressive disclosure (consolidated → items → raw) |
| Memory / Consolidation | 2 | Low | Browsing + status dashboard |
| Operations | 2 | Medium | Real-time activity feed, budget charts, convergence gauge |

**Total: ~23 pages, 4 of which are high-complexity.**

The four hardest UI components:
1. **Source setup wizard** — stateful multi-turn conversation in a UI, not a chat interface
2. **Prompt editor** — essentially an agent IDE: edit base prompt, manage learned sections, diff versions, preview assembled prompt
3. **Knowledge graph visualization** — interactive force-directed graph that's useful at 50 entities and 500 entities
4. **Alignment map** — novel visualization: showing how entities in different models relate, with divergence classification

#### Frontend Directory (Revised)

```
frontend/src/
├── api/
│   ├── client.ts                  # Axios/fetch wrapper, auth, error handling
│   ├── engagements.ts             # Engagement CRUD
│   ├── sources.ts                 # Source config + setup
│   ├── agents.ts                  # Agent types + fleet
│   ├── proposals.ts               # Proposal review
│   ├── graph.ts                   # Entity/relationship queries
│   ├── models.ts                  # Models + alignments
│   ├── query.ts                   # Query agent
│   ├── memory.ts                  # Knowledge items + consolidated units
│   └── operations.ts              # Budget, convergence, activity, pipeline
│
├── pages/
│   ├── engagements/
│   │   ├── EngagementList.tsx
│   │   └── EngagementDetail.tsx   # Overview + controls
│   ├── sources/
│   │   ├── SourceList.tsx
│   │   ├── SourceDetail.tsx
│   │   └── SetupWizard.tsx        # Multi-step guided setup
│   ├── agents/
│   │   ├── AgentTypeList.tsx      # Agent library browser
│   │   ├── AgentTypeDetail.tsx    # Prompt viewer/editor
│   │   └── PromptDiff.tsx         # Version comparison
│   ├── fleet/
│   │   ├── FleetOverview.tsx      # Coordinator + workers + APR
│   │   └── WorkerDetail.tsx       # Individual worker progress
│   ├── proposals/
│   │   ├── ProposalQueue.tsx      # Pending proposals
│   │   └── ProposalDetail.tsx     # Evidence + approve/reject
│   ├── graph/
│   │   ├── EntityList.tsx         # Search/filter entities
│   │   ├── EntityDetail.tsx       # Cross-model view
│   │   └── GraphVisualization.tsx # Interactive graph
│   ├── models/
│   │   ├── ModelList.tsx
│   │   ├── ModelDetail.tsx
│   │   └── AlignmentMap.tsx       # Cross-model alignment view
│   ├── inquiry/
│   │   └── QueryChat.tsx          # Chat interface + manual observations
│   ├── memory/
│   │   ├── ConsolidatedBrowser.tsx
│   │   └── ConsolidationStatus.tsx
│   └── operations/
│       ├── ActivityFeed.tsx
│       └── OperationsDashboard.tsx # Budget, convergence, source health
│
├── components/                     # Shared components
│   ├── layout/
│   │   ├── AppShell.tsx           # Navigation, sidebar, header
│   │   ├── EngagementSelector.tsx # Global engagement context
│   │   └── NotificationBell.tsx   # Pending proposals, alerts
│   ├── graph/
│   │   ├── ForceGraph.tsx         # d3/react-force-graph wrapper
│   │   ├── EntityNode.tsx         # Entity rendering in graph
│   │   └── AlignmentEdge.tsx      # Alignment rendering in graph
│   ├── agents/
│   │   ├── PromptEditor.tsx       # Code editor for prompts
│   │   ├── LearnedSectionEditor.tsx
│   │   └── VersionTimeline.tsx
│   ├── common/
│   │   ├── DataTable.tsx          # Sortable, filterable table
│   │   ├── SearchInput.tsx        # Semantic search component
│   │   ├── StatusBadge.tsx
│   │   ├── ConfidenceBar.tsx
│   │   └── JsonViewer.tsx
│   └── realtime/
│       ├── EventStream.tsx        # WebSocket event consumer
│       ├── ConvergenceGauge.tsx
│       └── WorkerProgress.tsx
│
└── hooks/
    ├── useWebSocket.ts            # WebSocket connection management
    ├── useEngagement.ts           # Current engagement context
    ├── usePolling.ts              # Fallback polling for non-WS data
    └── useDebounce.ts
```

#### Build Priority

Given "solve my problem first" — the UI areas in build priority order:

1. **Engagement + Source Config** — you can't do anything without setting up an engagement and sources
2. **Fleet Observatory + Activity Feed** — you need to see what the runtime is doing
3. **Knowledge Graph Browser + Model/Alignment Map** — this is the primary deliverable, the thing you're building the system TO SEE
4. **Inquiry/Query Interface** — once the graph has data, you need to ask questions
5. **Proposal Review** — APR proposals need human review
6. **Agent Library + Prompt Editor** — prompt management becomes important as you tune
7. **Memory/Consolidation + Operations** — nice to have, not blocking

---

## 12. Core Insight: Ontology Alignment as the Unit of Insight

### The Observation

In complex knowledge work, insight doesn't come from building the "right" model. It comes from understanding the **relationships between multiple valid models** of the same reality.

Every complex domain has multiple models running simultaneously. They're not wrong — they're **contextual**. A product taxonomy was built for portfolio management. Jira boards reflect how humans organize work. A strategy document reflects how an executive thinks about the problem. Code reflects years of pragmatic decisions. A consultant's value stream model is a simplification for decision-making.

Each model is a cut through reality optimized for a specific purpose. The insight lives in the alignment — where models agree, where they disagree, and why.

### Concrete Example

A real discovery engagement involved:

| Source | Model | Purpose |
|---|---|---|
| Spreadsheet | Product taxonomy (domains → capabilities) | Portfolio management |
| Confluence | Product boards → Jira deliverables | Work organization by team |
| Strategy doc | ~12 different problem framings | Executive communication |
| Proposed | 5 value streams | Simplification for decisions |
| Codebase | Organic module structure | 5 years of pragmatic growth |

These aren't different names for the same things. They're **different ways of carving up the same space.** One taxonomy domain spans three Jira boards. One Jira board spans two value streams. The code doesn't respect any of the boundaries.

The deliverable wasn't any single model — it was the **alignment map** showing how they relate, where the gaps are, and what the contradictions mean.

### Why This Is Generically True

The best team members in any domain — product development, software engineering, support, consulting — share a common capability: they can **switch between mental models** (customer, engineer, designer, business owner) and synthesize across them.

This perspective-switching is the core act of complex knowledge work:
- **M&A due diligence:** Acquirer's model vs target's model vs financial model vs what the code actually does
- **Compliance:** Regulatory framework vs policy documents vs implementation vs what people believe the rules are
- **Enterprise architecture:** As-is vs to-be vs code reality vs team ownership model
- **Product strategy:** What we said we'd build vs what we built vs what customers actually use
- **End user support:** User's mental model vs system's actual behavior vs documentation vs known issues

In every case, the single most valuable artifact is the alignment map between models — not any one model in isolation.

### What ALEC Externalizes

High-performing individuals do this synthesis in their heads. ALEC externalizes it, making the capability:

- **Durable** — survives staff turnover, context loss, session boundaries
- **Shareable** — a new team member immediately sees all perspectives and their relationships
- **Scalable** — no human can hold 12 models in their head simultaneously; the system can
- **Attributable** — every alignment has provenance: why we believe these concepts relate, from which source, with what confidence

When your best consultant leaves, they take their mental models with them. If the alignment map is externalized, that capability survives.

### Architectural Implications

The knowledge graph becomes **model-centric**, not entity-centric.

**Models are first-class objects:**

```sql
CREATE TABLE models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID REFERENCES engagements(engagement_id),
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    model_type TEXT NOT NULL,
        -- 'discovered'   (extracted from a source)
        -- 'proposed'     (user's target ontology)
        -- 'synthesized'  (system-generated reconciliation)
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Entities belong to models:**

```sql
ALTER TABLE entities ADD COLUMN model_id UUID REFERENCES models(model_id);
```

**Cross-model alignment is the primary insight structure:**

```sql
CREATE TABLE alignments (
    alignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity UUID REFERENCES entities(entity_id),
    to_entity UUID REFERENCES entities(entity_id),
    alignment_type TEXT NOT NULL,
        -- 'equivalent'    (same thing, different name)
        -- 'overlaps_with' (partial intersection)
        -- 'contains'      (superset)
        -- 'contained_by'  (subset)
        -- 'implements'    (code realizes concept)
        -- 'contradicts'   (models disagree on boundary/behavior)
        -- 'unaligned'     (exists in one model, no counterpart)
        -- 'supersedes'    (newer model replaces older)
    confidence FLOAT DEFAULT 0.5,
    evidence UUID[] DEFAULT '{}',
    notes TEXT,
    created_by TEXT,
        -- 'worker', 'coordinator', 'user', 'apr'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**The coordinator's primary question shifts** from "what entities haven't we explored?" to "where are the models misaligned, and is that intentional or a gap in our understanding?"

**Consolidation becomes cross-model synthesis.** Instead of "here's everything we know about payments-service," it's "here's how 'payments' appears across 4 models, where they agree, and where they diverge."

**The user's proposed model is the target ontology.** The system maps everything else onto it and surfaces what doesn't fit — which is precisely the deliverable.

### Model Purpose as Query Dimension

During engagement setup, the Configure Agent captures not just "what" a source is but "why" it exists:

1. **What is this source?** (type, access, scope)
2. **Why does it exist?** (purpose — what question it was built to answer)
3. **Whose view is it?** (perspective — which stakeholder type)
4. **Where do you expect it to diverge from other sources?** (expected divergences)
5. **What should workers know about navigating it?** (worker profile / navigation hints)

Items 2–4 are what turn raw discovery into insight. They're also the things only the human knows — the system can't infer that a taxonomy was built for investment allocation by reading the spreadsheet.

**Schema update:**

```sql
CREATE TABLE models (
    model_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID REFERENCES engagements(engagement_id),
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    model_type TEXT NOT NULL,
        -- 'discovered', 'proposed', 'synthesized'
    purpose TEXT,
        -- "What question was this model built to answer?"
        -- e.g., "Portfolio investment allocation"
        -- e.g., "Team delivery ownership"
    perspective TEXT,
        -- Whose viewpoint: 'product', 'engineering',
        -- 'compliance', 'executive', 'customer', 'operations'
    expected_divergences TEXT,
        -- "Boundaries here reflect investment, not team structure.
        --  Cross-team splits are expected."
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Workers carry perspective as context.** When a worker explores a source, it knows the model's purpose:

```
Worker directive: "Explore the DATA Jira project. This project
is organized for TEAM DELIVERY (squad: Data Platform). Boundaries
reflect who does the work. When you encounter entities that span
the taxonomy's 'Customer Management' and 'Analytics' domains,
note the cross-boundary relationship but don't treat it as conflict."
```

**Coordinator classifies divergences by purpose compatibility:**

| Classification | Meaning | Example |
|---|---|---|
| **Expected divergence** | Different purposes produce different boundaries (normal) | Taxonomy splits by investment; Jira splits by team |
| **Unexpected divergence** | Same purpose, different conclusions (genuine conflict) | Strategy doc and taxonomy disagree on priorities |
| **Cross-purpose alignment** | Multiple purposes agree (strong signal) | Taxonomy, Jira, strategy, AND code agree on boundary |
| **Orphan** | Exists in one model only, no counterpart anywhere | Code module nobody claims |

This transforms output from "200 divergences" (overwhelming) to "12 divergences that shouldn't exist given each model's purpose" (actionable).

**The Configure Agent is conducting a structured interview,** not just testing connectivity. The conversation during setup is itself generating Tier 1 observations and model metadata that inform the entire discovery process.

### Entity Resolution as a Subset

Simple entity resolution (same thing, different names) is the `equivalent` alignment type. It's necessary but it's the easy case. The harder and more valuable problem is alignment — determining how concepts in different models relate when they're not "the same thing" but "different cuts through the same reality."

Layered resolution still applies:
1. **Deterministic:** Normalize names, substring matching
2. **Alias accumulation:** Config references, "also known as" patterns
3. **Embedding similarity:** Name + context
4. **Co-reference heuristic:** Entities sharing 3+ relationships to the same others
5. **Human disambiguation:** Queue ambiguous cases (confidence 0.5–0.8)

But this only produces `equivalent` alignments. The richer alignment types (`overlaps_with`, `contains`, `contradicts`) require the coordinator to reason about model boundaries — which is where the LLM call per cycle earns its keep.

### The Archaeological Metaphor and Two-Tier Value

The core process is **archaeological**: the user provides the big rocks (their models, purposes, expected boundaries) during onboarding. Workers break sources into small rocks. The system removes noise to reveal structure that was already there but buried across silos. For this work, simple labeled connections are more than sufficient — don't over-engineer the vocabulary.

**Tier 1: Reliable Core (day 1 value)**
- Automated inventory across heterogeneous sources
- Evidence-based connection reasoning — every alignment has provenance
- Purpose-aware divergence classification — expected vs unexpected
- The alignment map itself as a deliverable

This is the archaeological layer. The system is very good at conducting inventory and reasoning about connections based on evidence. The representation stays simple: entities, relationships, models, alignments with a small fixed vocabulary of types.

**Tier 2: Emergent Frontier (aspirational, not promised)**
- **Absence as signal:** "No governance documentation exists for the billing domain across 4 sources and 500 pages" — visible only when everything else is mapped
- **Transitive chains across silos:** Service A → depends on Service B → owned by Team X → being reorganized — three facts from three sources nobody connected
- **Consolidation cross-linking:** Entities that co-occur in observations without explicit relationships — "why does the fraud service keep appearing alongside the legacy batch reconciler?"
- **Statistical alignment patterns:** "Every code-taxonomy divergence corresponds to an acquisition" — correlation visible only with enough data

These aren't the system "thinking new thoughts." They're the system holding more context than any human can and noticing patterns in the juxtaposition. Whether that constitutes genuine insight or connecting dots that were always there is philosophical — from the user's perspective, it's actionable either way.

The design supports both tiers. Tier 1 is structural (graph + alignment types + purpose metadata). Tier 2 emerges from consolidation (sleep process step 5), coordinator gap detection across models, and the graph making transitive relationships queryable. We design for emergence but deliver on archaeology.

---

## 13. Generalization Architecture: Platform vs Domain

### The Position ALEC Occupies in AI History

ALEC sits in a novel position between RAG and fine-tuning:

```
Fine-tuning          ALEC v5              RAG
(opaque weights)     (structured graph)   (raw document chunks)

Knowledge is:        Knowledge is:        Knowledge is:
- in the model       - external to model  - external to model
- not inspectable    - inspectable        - inspectable
- learned from data  - learned from data  - authored by humans
- not editable       - editable           - editable
- not attributed     - attributed         - sort-of attributed
- automatic          - automatic          - manual
```

Five parallels from AI/ML history inform this design:

**1. Symbolic AI + Connectionist Acquisition.** 1980s expert systems had the right idea (inspectable knowledge bases) but the wrong acquisition method (manual). Neural networks solved acquisition but lost inspectability. ALEC uses LLMs (connectionist) to build structured knowledge (symbolic). This is the architecture the expert systems researchers wanted but couldn't build.

**2. Complementary Learning Systems.** The brain's hippocampus (fast, episodic) and neocortex (slow, consolidated) map directly to ALEC's three-tier memory. Tier 1 = hippocampal encoding. Tier 3 = neocortical consolidation. The "sleep" process is explicitly named for this. **Design implication:** consolidation is where insight lives — it deserves first-class status, not background scheduling.

**3. Non-Differentiable External Memory.** Neural Turing Machines and Differentiable Neural Computers tried to make external memory part of the gradient computation. Elegant, but creates the same opacity problem. ALEC deliberately uses **non-differentiable** external memory (PostgreSQL rows). By giving up end-to-end differentiability, you gain inspectability, editability, and governance. **Design implication:** the "not differentiable" property is a feature to emphasize, not a limitation.

**4. Cross-Substrate Knowledge Distillation.** Standard distillation compresses knowledge from a large model into a smaller model — same substrate (weights). ALEC distills from implicit LLM understanding into explicit structured form. The structured output is arguably better because it has provenance, confidence, and can be corrected without retraining. The mental model is **crystallization**, not degradation.

**5. Inspectable Convergence.** Neural network convergence (loss stops decreasing) is necessary but not sufficient — you can't inspect what was learned. ALEC's convergence (alignment stability) is directly interpretable — the converged state IS the deliverable.

**The Bitter Lesson, Amended:** Sutton's Bitter Lesson says computation beats human knowledge. ALEC amends this: **computation wins for ACQUISITION, but structured representation wins for TRUST.** In regulated industries, you need both.

### The Core Problem: Platform vs Domain Conflation

The initial design entangled two layers that should be separate:

- **Platform logic** — coordinator cycle, worker loop, three-tier memory, consolidation, convergence, prompt governance. This is domain-independent.
- **Domain schema** — entity types, relationship types, worker specializations, perspective vocabularies. This was hardcoded to "enterprise architecture discovery."

Every hardcoded `entity_type` enum (`service`, `database`, `team`, `api`, `policy`...) is an enterprise architecture concept. Every hardcoded `relationship_type` (`depends_on`, `reads_from`, `writes_to`, `calls`...) is a software dependency concept. These are correct for the initial use case but prevent the system from working for research synthesis, codebase understanding, incident investigation, competitive intelligence, or any other discovery domain.

### Three-Layer Architecture

```
┌──────────────────────────────────────────────────┐
│  PLATFORM LAYER (domain-independent)              │
│                                                    │
│  Runtime: supervisor, coordinator cycle,           │
│           worker loop, consolidation               │
│  Memory: three-tier (observations → index →        │
│          consolidated), convergence detection       │
│  Governance: prompt versioning, APR, auto/human    │
│  Safety: budget, sandboxing, rate limiting          │
│  Events: in-process bus, pg_notify                 │
│  API: engagement CRUD, fleet management,           │
│       proposal review, query interface              │
├──────────────────────────────────────────────────┤
│  SCHEMA LAYER (per-engagement, from template)      │
│                                                    │
│  Entity types: what kinds of things to find        │
│  Relationship types: how things connect            │
│  Alignment types: how perspectives relate          │
│  Prompts: coordinator, worker, consolidation       │
│  Upper categories: domain-independent parents      │
│  Ontology Agent: proposes and evolves schema       │
├──────────────────────────────────────────────────┤
│  CONNECTOR LAYER (pluggable)                       │
│                                                    │
│  Source implementations: survey/read/search/list   │
│  Validators: per-source-type code validation       │
│  Auth adapters: per-source authentication          │
│  (New sources without platform changes)            │
└──────────────────────────────────────────────────┘
```

### What's Platform-Level (Stays Fixed)

| Component | Why It's General |
|---|---|
| Three-tier memory | Any knowledge-building process has raw observations, structured index, and synthesized summaries |
| Coordinator cycle (project → detect → rank → direct) | Any directed exploration follows this pattern |
| Worker loop (read → extract → write to graph) | Any source exploration follows this pattern |
| Consolidation (synthesize → cross-link) | Any knowledge consolidation follows this pattern |
| Convergence (reinforcement / expansion / challenge) | Domain-independent stability metric |
| Prompt governance (base + learned, APR, auto/human) | Any LLM-driven process benefits from prompt evolution |
| Impact classification (reinforcement / expansion / challenge) | Domain-independent observation classification |
| Max scope (survey / focused / deep) | General exploration depth control |
| Budget enforcement | Always needed |
| Source connector protocol (survey / read / search / list_children) | General enough for any information source |
| Engagement lifecycle (setup → active → paused → converged) | General workflow |
| Core alignment types (equivalent, overlaps_with, contains, contradicts, unaligned, supersedes) | General enough for any multi-perspective analysis |

### What's Engagement-Level (Configurable)

| Component | Why It Varies | Example Variation |
|---|---|---|
| Entity types | Different domains have different things | Enterprise: service, database, team. Research: theory, claim, evidence |
| Relationship types | Different domains have different connections | Enterprise: calls, depends_on. Research: cites, supports, contradicts |
| Additional alignment types | Some domains need domain-specific alignment vocabulary | Enterprise: `implements` (code realizes concept). Research: `validates` (experiment confirms theory) |
| Worker prompts | Different domains need different extraction instructions | Enterprise: "look for API endpoints." Research: "look for methodology and sample sizes" |
| Coordinator prompts | Different domains prioritize different gap types | Enterprise: "unexplored services." Research: "untested hypotheses" |
| Consolidation prompts | Different domains synthesize differently | Enterprise: cross-model architecture summary. Research: literature review synthesis |
| Perspective vocabulary | Different domains have different viewpoints | Enterprise: product, engineering, compliance. Research: theoretical, empirical, methodological |

### Engagement Templates

To avoid cold-start complexity, engagements are created from templates:

```sql
CREATE TABLE engagement_templates (
    template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    -- Pre-configured domain schema
    entity_types JSONB NOT NULL,        -- [{name, description, examples, parent_category}]
    relationship_types JSONB NOT NULL,  -- [{name, description, directional, parent_category, typical_from, typical_to}]
    additional_alignment_types JSONB,   -- beyond platform defaults
    -- Pre-configured base prompts
    coordinator_base_prompt TEXT,
    worker_base_prompt TEXT,
    consolidation_prompt TEXT,
    ontology_agent_prompt TEXT,
    -- Defaults
    default_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Shipped templates:**

| Template | Entity Types | Relationship Types |
|---|---|---|
| **Enterprise Architecture** | service, database, team, api, policy, person, document, domain, process | depends_on, owned_by, reads_from, writes_to, calls, governs, implements, contains |
| **Research Synthesis** | theory, claim, evidence, method, dataset, author, finding, question | supports, contradicts, extends, cites, uses_method, produces, questions |
| **Codebase Understanding** | module, class, function, endpoint, config, dependency, test, pattern | imports, calls, inherits, implements, configures, tests, depends_on |
| **General Discovery** | concept, entity, source, pattern, question, observation | relates_to, contains, contradicts, supports, precedes, depends_on |

The first engagement uses "Enterprise Architecture" because that's the initial use case. The platform doesn't privilege it.

### Engagement Schema Tables

Replace hardcoded enums with per-engagement configuration:

```sql
-- Engagement-level schema definition
-- Populated from template at creation, evolved by Ontology Agent at runtime
CREATE TABLE engagement_schema (
    engagement_id UUID NOT NULL REFERENCES engagements(engagement_id),
    schema_type TEXT NOT NULL,          -- 'entity_type', 'relationship_type', 'alignment_type'
    type_name TEXT NOT NULL,
    description TEXT NOT NULL,          -- injected into agent prompts
    parent_category TEXT,               -- FK to relationship_categories (see upper ontology)
    examples TEXT[],                    -- injected into agent prompts
    typical_from TEXT[],                -- for relationships: which entity types at source
    typical_to TEXT[],                  -- for relationships: which entity types at target
    added_by TEXT DEFAULT 'template',   -- 'template', 'ontology_agent', 'user', 'setup'
    evidence_observations UUID[],       -- observations that motivated adding this type
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (engagement_id, schema_type, type_name)
);
```

The `entities.entity_type` column remains TEXT but is validated against `engagement_schema` at write time. Workers receive the available types dynamically in their prompts. The Ontology Agent proposes schema evolution at runtime.

### Upper Relationship Categories

A small set of domain-independent relationship patterns that domain-specific types specialize. These are **platform-level** — they ship with the system and rarely change.

```sql
CREATE TABLE relationship_categories (
    category TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    default_members TEXT[]              -- types that ship with this category
);

INSERT INTO relationship_categories VALUES
    ('compositional', 'Part-whole and containment relationships',
     ARRAY['contains', 'part_of']),
    ('dependency', 'Functional dependency, enablement, requirement',
     ARRAY['depends_on', 'requires', 'enables']),
    ('temporal', 'Time ordering and co-occurrence',
     ARRAY['precedes', 'follows', 'concurrent_with']),
    ('epistemic', 'Knowledge relationships: support, contradiction, extension',
     ARRAY['supports', 'contradicts', 'extends']),
    ('structural', 'Connection or association without strong directionality',
     ARRAY['connected_to', 'associated_with']),
    ('governance', 'Ownership, control, authority, responsibility',
     ARRAY['governs', 'owned_by', 'managed_by']),
    ('realization', 'Abstract concept made concrete',
     ARRAY['implements', 'instantiates', 'exemplifies']),
    ('identity', 'Sameness and similarity',
     ARRAY['equivalent', 'similar_to']);
```

Domain-specific relationship types are children of these categories:

```
Enterprise:   "calls"      → child of dependency
              "reads_from" → child of dependency
              "owned_by"   → child of governance

Research:     "cites"      → child of epistemic (supports)
              "refutes"    → child of epistemic (contradicts)
              "builds_on"  → child of epistemic (extends)

Codebase:     "imports"    → child of dependency
              "inherits"   → child of realization
              "tests"      → child of epistemic (supports)
```

**Why this matters:**

1. **Cross-engagement transfer.** `calls` (enterprise) and `imports` (codebase) are both dependency relationships. Knowledge about dependency patterns transfers.
2. **Domain-independent consolidation.** The consolidation prompt can reason at category level: "This entity has many dependency relationships and few governance relationships" — meaningful regardless of domain.
3. **Ontology Agent guidance.** When proposing new types, the Ontology Agent classifies into upper categories, constraining the space of proposals.

### Dynamic Prompt Assembly

Worker prompts assemble entity and relationship types from `engagement_schema` at dispatch time:

```python
async def assemble_schema_context(engagement_id: UUID, pool: asyncpg.Pool) -> str:
    """Generate the schema section for worker/coordinator prompts."""
    async with pool.acquire() as conn:
        entity_types = await conn.fetch("""
            SELECT type_name, description, examples
            FROM engagement_schema
            WHERE engagement_id = $1 AND schema_type = 'entity_type'
            ORDER BY type_name
        """, engagement_id)

        relationship_types = await conn.fetch("""
            SELECT type_name, description, typical_from, typical_to
            FROM engagement_schema
            WHERE engagement_id = $1 AND schema_type = 'relationship_type'
            ORDER BY type_name
        """, engagement_id)

    sections = ["## Entity Types for This Engagement"]
    for et in entity_types:
        examples = ", ".join(et['examples']) if et['examples'] else "none yet"
        sections.append(f"- **{et['type_name']}**: {et['description']} (e.g., {examples})")

    sections.append("\n## Relationship Types for This Engagement")
    for rt in relationship_types:
        sections.append(f"- **{rt['type_name']}**: {rt['description']}")

    return "\n".join(sections)
```

This replaces the hardcoded enum lists in tool definitions. The `add_entity` tool's `entity_type` enum and the `add_relationship` tool's `relationship_type` enum are populated dynamically from the engagement schema.

### Applicability Across Use Cases

The generalized platform supports these use cases without code changes — only template selection:

| Use Case | Template | Sources | Insight Type |
|---|---|---|---|
| Enterprise architecture mapping | Enterprise Architecture | Confluence, Git, Jira, SharePoint | Cross-model alignment of technology landscape |
| Research literature synthesis | Research Synthesis | PDF papers, arXiv, PubMed, Zotero | Theory-evidence mapping, gap detection |
| Codebase onboarding | Codebase Understanding | Git repos, docs, tests, CI configs | Architecture comprehension, dependency mapping |
| Incident investigation | General Discovery (customized) | Logs, code, tickets, monitoring, runbooks | Causal chain reconstruction |
| Competitive intelligence | General Discovery (customized) | Public websites, filings, patents, press | Market landscape mapping |
| M&A due diligence | Enterprise Architecture | Target's tech stack, docs, governance | Risk identification, integration mapping |
| Compliance audit | Enterprise Architecture + custom | Regulations, policies, code, configs | Gap analysis between requirement and reality |
| Personal knowledge management | Research Synthesis (customized) | Books, articles, notes, bookmarks | Concept mapping, connection discovery |

All share the same runtime, memory architecture, governance model, and convergence mechanics. The domain-specific behavior comes from the schema layer and prompts.

---

## 14. Ontology Agent

### The Missing Agent

The initial design distributes schema responsibility without clear ownership:

- Configure Agent captures source metadata but doesn't reason about what to look for
- Workers extract into a pre-defined type system they were given
- APR tunes prompts but doesn't question the schema itself
- Coordinator detects coverage gaps but not vocabulary gaps

The Ontology Agent fills this gap. Its question is: **what categories of things matter for this problem, and how should we organize what we find?**

### Agent Characteristics

| Property | Value |
|---|---|
| Nature | Analytical, periodic |
| Lifecycle | Setup (initial proposal) + Runtime (evolution monitoring) |
| Python vs LLM | Mostly Python pattern detection; 2-3 LLM calls per run |
| Visibility to user | Invisible (Layer 3-4). Effects visible as "system getting smarter" |
| Outputs | Schema proposals, not knowledge graph entries |

### Lifecycle

**Setup Phase:**

```
User provides problem statement + source descriptions
    │
    ▼
Ontology Agent reads problem statement + source metadata
→ proposes initial schema (entity types, relationship types)
→ classifies each type into upper categories
→ proposes initial models (what perspectives might exist)
    │
    ▼
User sees plain-language description:
  "I'll explore these sources looking for services, databases,
   teams, and their dependencies. I expect the Confluence docs
   and the codebase to give different views of the same
   landscape. Sound right?"
    │
[User adjusts or approves in natural language]
```

**Runtime Phase (periodic, like APR):**

```
Ontology Agent reviews recent worker outputs:
→ detects entities classified as 'other' or forced into poor-fit types
   ("workers keep extracting 'SLA' objects — not in our vocabulary")
→ detects relationships forced into 'related_to' because nothing better exists
→ detects type overlap ("'capability' and 'domain' used interchangeably")
→ detects type gaps (clusters of observations that don't map to any type)
→ proposes schema evolution
```

**Consolidation Phase:**

```
Ontology Agent reviews consolidated units:
→ are summaries coherent with the current schema?
→ do cross-links suggest missing relationship types?
→ is the schema too fine-grained (many types with few instances)?
→ is the schema too coarse (few types with diverse instances)?
```

### Output Types

```python
@dataclass
class SchemaProposal:
    """Initial schema proposal from problem statement."""
    entity_types: list[EntityTypeDef]
    relationship_types: list[RelationshipTypeDef]
    model_suggestions: list[ModelSuggestion]
    reasoning: str

@dataclass
class EntityTypeDef:
    name: str                       # "service"
    description: str                # "A deployed software component with APIs"
    examples: list[str]             # ["payments-service", "auth-gateway"]
    parent_category: str | None     # from upper ontology

@dataclass
class RelationshipTypeDef:
    name: str                       # "calls"
    description: str                # "Makes API calls to"
    parent_category: str            # "dependency"
    directional: bool               # True
    typical_from: list[str]         # ["service"]
    typical_to: list[str]           # ["service", "api"]

@dataclass
class SchemaEvolution:
    """Runtime schema change proposal."""
    action: str                     # 'add_type', 'merge_types', 'split_type',
                                    # 'deprecate_type', 'add_relationship'
    evidence: list[UUID]            # observation_ids that motivate this
    proposed_change: EntityTypeDef | RelationshipTypeDef
    impact: str                     # 'low', 'medium', 'high'
    auto_apply_eligible: bool       # low-impact additions can auto-apply
    reasoning: str
```

### LLM vs Python Split

| Function | LLM or Python | Why |
|---|---|---|
| Propose initial schema from problem statement | **LLM** | Requires understanding the domain |
| Detect type-fit issues in worker outputs | Python | Count entities classified as 'other', measure type distribution skew |
| Detect type overlap/redundancy | Python + embedding | Cosine similarity of type descriptions; co-occurrence analysis |
| Propose new types or type changes | **LLM** | Turn evidence into coherent type definitions |
| Classify schema change impact | Python | Rules: addition = low, rename = medium, restructure = high |
| Merge/split types | **LLM** | Requires judgment about category boundaries |

### Schema Evolution Governance

Schema changes use the same governance model as APR prompt proposals:

```
AUTO-APPLY (low impact, additive):
├── New entity type (doesn't affect existing data)
├── New relationship type (doesn't affect existing data)
├── Adding examples to existing types
│
│   Criteria: evidence_count >= 3, impact = 'low',
│             action in ('add_type', 'add_relationship')

HUMAN REVIEW (medium/high impact, structural):
├── Merging types (affects existing entities)
├── Splitting types (affects existing entities)
├── Deprecating types (affects extraction going forward)
├── Changing type descriptions (affects worker behavior)
├── Adding alignment types (changes cross-model analysis)
```

### Ontology Agent Trigger Points

```python
class OntologyAgentTrigger:
    """When to run the Ontology Agent. Python rules, no LLM."""

    # After N new entities, check type-fit
    entity_threshold: int = 50

    # After N observations classified as 'other' or 'related_to'
    misfit_threshold: int = 10

    # Periodic (even without triggers)
    max_interval: timedelta = timedelta(hours=1)

    async def should_run(self, engagement_id: UUID, pool: asyncpg.Pool) -> bool:
        async with pool.acquire() as conn:
            # Check for type-fit issues
            misfit_count = await conn.fetchval("""
                SELECT COUNT(*) FROM entities
                WHERE engagement_id = $1
                  AND (entity_type = 'other'
                       OR entity_type NOT IN (
                           SELECT type_name FROM engagement_schema
                           WHERE engagement_id = $1
                             AND schema_type = 'entity_type'
                       ))
                  AND created_at > COALESCE(
                      (SELECT MAX(created_at) FROM engagement_schema
                       WHERE engagement_id = $1 AND added_by = 'ontology_agent'),
                      '1970-01-01'::timestamptz
                  )
            """, engagement_id)

            if misfit_count >= self.misfit_threshold:
                return True

            # Check for relationship type misuse
            related_to_count = await conn.fetchval("""
                SELECT COUNT(*) FROM relationships
                WHERE engagement_id = $1
                  AND relationship_type = 'related_to'
                  AND first_seen > COALESCE(
                      (SELECT MAX(created_at) FROM engagement_schema
                       WHERE engagement_id = $1 AND added_by = 'ontology_agent'),
                      '1970-01-01'::timestamptz
                  )
            """, engagement_id)

            if related_to_count >= self.misfit_threshold:
                return True

            return False
```

### Ontology Standards: What We Borrow, What We Avoid

**Avoid:**
- **OWL/RDF** — Semantic web formalism. Extremely expressive, extremely verbose. Built for machine-to-machine interoperability across the internet. We need none of that.
- **TOGAF/ArchiMate** — Enterprise architecture frameworks that prescribe THE ontology. Using these would lock us to one domain.
- **SUMO/BFO** — Upper ontologies attempting to formalize all of reality. Philosophically interesting, practically impractical.

**Borrow:**
- **Property graph model** (Neo4j/openCypher): nodes with labels and properties, typed directed edges. This IS our internal model. No formal adoption needed — we already do this.
- **Upper categories concept** from ontology research: a small set of domain-independent relationship patterns that domain-specific types specialize. Lighter than a formal upper ontology. See Section 13's `relationship_categories` table.
- **Wikidata's qualifier/reference pattern**: items have statements, statements have qualifiers (context) and references (provenance). Our observation → knowledge_item → consolidated_unit chain serves the same purpose. Study Wikidata's approach to schema evolution (open-ended property creation, community governance) as a practical model for the Ontology Agent's behavior.

**The stance:** no formal standard adopted. Conceptual alignment with property graphs (de facto industry standard) and lightweight upper categories (inspired by ontology research). The formalization trap remains avoided — the Ontology Agent helps schemas **emerge from evidence**, not conform to a prescribed model.

### Hiding Complexity: Progressive Disclosure

The Ontology Agent operates invisibly. Users never interact with it directly. Its effects are visible as the system "getting smarter."

**Four layers of disclosure:**

```
Layer 1 — Everyone sees (natural language):
  "Here's what I found. Here are 3 things sources disagree about."
  Summaries, visual graph, plain-language gap descriptions.

Layer 2 — Curious users ("why do you think that?"):
  Evidence chains: "I saw this in Confluence page X, confirmed in repo Y."
  Confidence indicators: "3 sources agree" vs "only seen once."

Layer 3 — Power users ("how are you organizing this?"):
  Schema browser: entity types, relationship types, what they mean.
  Ontology evolution log: what types were added and why.
  Prompt management: what workers are looking for.

Layer 4 — Administrators (governance and audit):
  Full audit trail. Prompt version history. Schema governance.
  Cost/performance metrics. Evidence provenance chains.
```

Most users never go past Layer 2. Layers 3-4 exist for the regulated-industry value proposition.

**The vocabulary swap:** The system maintains internal (ontology) and external (user-facing) vocabularies:

| Internal (ontology) | External (user-facing) |
|---|---|
| entity_type: 'service' | "component" or just the entity name |
| relationship_type: 'depends_on' | "connects to" or "relies on" |
| alignment_type: 'contradicts' | "these sources disagree" |
| observation_type: 'gap' | "I haven't explored this yet" |
| convergence ratio: 3.2 | "I'm fairly confident in the picture" |

The UI and Query Agent translate from internal to external vocabulary. The internal ontology drives behavior; the external vocabulary drives the experience.

**Schema changes surface as natural language:**
- NOT: "New entity_type 'sla' added to engagement_schema"
- YES: "I noticed your Confluence docs reference SLAs frequently, and they don't fit the existing categories. I've started tracking them separately so I can find patterns across them."

### Relationship to APR

The Ontology Agent and APR are peers — both do meta-learning but on different aspects:

| Aspect | APR | Ontology Agent |
|---|---|---|
| What it tunes | How workers explore (navigation hints, extraction patterns) | What vocabulary workers use (entity types, relationship types) |
| Ground truth signal | Binary: worker found content there or didn't | Distribution: type usage skew, 'other' count, 'related_to' overuse |
| Output | Prompt section proposals | Schema evolution proposals |
| Governance | Same auto-apply / human-review model | Same auto-apply / human-review model |
| Frequency | After worker batches complete | After entity/relationship thresholds met |

They don't overlap. APR says "look in Archive sections for legacy docs." Ontology Agent says "start distinguishing between 'active services' and 'deprecated services' as separate types."

### Build Priority

The Ontology Agent is a prerequisite for the "first discovery cycle" milestone because without it, every engagement requires manual schema configuration, defeating the "invisible complexity" goal.

**v1 (required for first cycle):** Single LLM call during setup. Reads problem statement + source descriptions, proposes schema from the selected template, user approves in plain language. ~200 lines of code, one prompt.

**v2 (runtime evolution):** Periodic monitoring. Detects type-fit issues, proposes new types. Auto-apply additions, human review for structural changes.

**v3 (cross-engagement learning):** Schemas from past engagements inform proposals for new ones. Types that proved useful across multiple engagements get promoted to template defaults.

### Updated Agent Roster

```
SETUP PHASE:
  Configure Agent     Source onboarding (connectivity, auth, scope)
  Ontology Agent      Schema proposal from problem statement + template

RUNTIME (autonomous):
  Supervisor          Lifecycle management (Python, no LLM)
  Coordinator         Gap detection → task directives (1 LLM call/cycle)
  Workers             Source exploration → knowledge extraction (5-10 LLM calls/task)
  Ontology Agent      Schema evolution monitoring (2-3 LLM calls, periodic)
  APR                 Prompt evolution (2-3 LLM calls, periodic)
  Consolidation       Tier 2 → Tier 3 synthesis (1 LLM call/entity, periodic)

INQUIRY (on-demand):
  Query Agent         User questions against the graph (2-3 LLM calls/question)
```

---

## 15. Open Questions

### Technical

1. ~~**Entity resolution across sources.**~~ **RESOLVED → Section 12.** Reframed as ontology alignment. Simple entity resolution (same thing, different names) is the `equivalent` alignment type. The harder problem — how concepts in different models relate — is handled by the `alignments` table and coordinator reasoning. Layered resolution (deterministic → embedding → co-reference → human disambiguation) handles the simple cases.

2. ~~**Consolidation prompt design.**~~ **PARTIALLY RESOLVED → Section 12.** Consolidation is cross-model synthesis, not entity summary. Prompt structure: "How does entity X appear across N models? Where do they agree, diverge, and is the divergence expected given each model's purpose?" The consolidated unit IS the backing story — the coherent narrative that makes observations hang together. Empirical tuning still needed for token density and attribution formatting.

3. ~~**Convergence tuning.**~~ **RESOLVED → Section 12.** Convergence = alignment stability. Every new observation either (a) reinforces an existing alignment, (b) expands the alignment map, or (c) challenges an existing alignment. When the ratio shifts to mostly reinforcement for N consecutive cycles, the backing story is stable. Metric: `reinforcement / (expansion + challenge + 1)`. More meaningful than entity count — you can always find more entities; what matters is whether new evidence fits the story or reshapes it.

4. ~~**Contradiction resolution.**~~ **RESOLVED → Section 12.** Contradictions are `contradicts` alignment edges, not problems to resolve. Some contradictions ARE the finding ("Confluence says REST API; code shows direct DB" = architecture bypass). The coordinator surfaces them with purpose context: contradictions between models with the same purpose are actionable; contradictions between models with different purposes are often expected divergence.

5. ~~**Graph query interface.**~~ **RESOLVED.** Model-scoped projections solve the bounding problem. The coordinator asks: "alignment state for Model X" (bounded by one model's entities), "unresolved contradictions" (bounded by challenge count), "orphans across all models" (entities with zero cross-model edges), "convergence dashboard" (reinforcement/expansion/challenge ratios). These are SQL queries, not LLM calls. Always bounded once models are the organizing principle.

6. ~~**APR calibration.**~~ **RESOLVED.** Constrain the APR to things with **binary ground truth**: navigation hints (worker found content there or didn't), vocabulary/aliases (source returned results or didn't), source structure (page tree matches hint or doesn't), access anti-patterns (area was empty or wasn't), query patterns (query worked or didn't). These don't need A/B testing or statistical significance — the feedback is observable. Everything without strong ground truth (extraction criteria, entity types, strategic priorities) goes to human review. This makes the APR a **ground-truth collector** doing mostly Python pattern detection, not a meta-learner optimizing subjective outcomes. The only LLM call is to write hint text in natural language.

7. ~~**Specialization threshold.**~~ **RESOLVED.** Don't overthink it. Start general. APR proposes specialization when it sees consistent source-specific patterns across multiple workers. Human approves or rejects. If the specialized type doesn't outperform the general type after N tasks on verifiable metrics (entities per task, scope overflow rate), deprecate it. Let practice lead.

8. ~~**LLM rate limiting under concurrency.**~~ **RESOLVED.** Solved by architecture. Single process, single LLM client with `asyncio.Semaphore`. Token budget per engagement. Priority queue: coordinator > workers > APR. Exponential backoff on 429s. Implementation detail, not design question.

### Product

9. ~~**First target market.**~~ **RESOLVED.** Self. Build for own use, validate on real engagements. Everything else is way down the roadmap and should not inflate the design.

10. ~~**Pricing model.**~~ **DEFERRED.** Irrelevant until there are external users.

11. ~~**Source connector strategy.**~~ **DEFERRED.** Connector infrastructure gets stubbed out (the `SourceConnector` protocol + one test implementation for local files/git). Real connectors built when on the ground with real sources. The hard problems are coordinator reasoning, worker extraction quality, consolidation, and convergence — not HTTP calls to Confluence.

12. ~~**Competitive positioning.**~~ **PARTIALLY RESOLVED.** Market research (2026-02-20) confirmed no direct competitor in ALEC's exact niche. Positioning: lead with compliance/provenance, not "knowledge graphs." Beachhead verticals: M&A due diligence, compliance auditing. See `docs/design/market_validation.md`.

### Strategic

13. ~~**Open source vs proprietary.**~~ **RESOLVED.** Proprietary. Personal tooling for own practice.

14. ~~**Platform vs application.**~~ **RESOLVED.** Application. Runs on dev machine, evolves from there. No platform ambitions at this stage.

15. ~~**Relationship to existing ALEC.**~~ **RESOLVED.** Start fresh. PostgreSQL + pgvector carry over as infrastructure choices but all application code is new.

16. **MCP integration.** **OPEN.** Model Context Protocol could provide standardized source connectors (filesystem, GitHub, databases) and reduce custom connector development. Workers could use MCP servers as connector implementations. Additive — does not require architectural changes. Evaluate after core runtime is stable.

---

## Appendix A: Comparison to Existing Solutions

| Solution | What It Does | What It Doesn't Do |
|---|---|---|
| **Collibra/Alation/Atlan** | Manual catalog curation with basic ML | Auto-extract knowledge from behavior; cross-source synthesis |
| **Monte Carlo/Bigeye** | Data observability and lineage | Tacit knowledge capture; decision attribution |
| **Claude MCP / OpenAI Agents** | Give agent access to data sources | Persistent organizational learning; knowledge governance |
| **CrewAI / AutoGen / LangGraph** | Multi-agent task orchestration | Shared knowledge accumulation; context management; convergence |
| **Obsidian / Notion** | Manual note-taking and linking | Automated capture; structured retrieval; consolidation |
| **RAG systems** | Chunk and retrieve documents | Self-building knowledge base; synthesis; provenance |
| **Zep / Graphiti** | Temporal knowledge graph for LLM conversation memory | Coordinated multi-source exploration; convergence detection; non-conversation knowledge |
| **Hebbia** | RAG + structured extraction for financial document Q&A ($700M+) | Persistent cross-session knowledge graph; multi-agent coordination; general-purpose discovery |
| **Glean** | Enterprise search + knowledge graph with connector ecosystem ($4.6B) | Coordinated exploration; convergence; discover-and-synthesize (vs index-and-query) |
| **ALEC v5 (this design)** | Automated discovery + persistent memory + coordinated exploration + self-improving agents | *(everything above, unified)* |

**Positioning note (2026-02-20):** Lead with compliance and provenance, not "knowledge graphs." Enterprise buyers search for audit trails, compliance documentation, and due diligence automation. ALEC's provenance-tracked knowledge graph is the mechanism, not the value proposition. See `docs/design/market_validation.md` for full competitive analysis.

---

*This document captures the design conversations of 2026-02-07 and 2026-02-08. It represents architectural intent, not committed implementation.*

---

## Appendix B: Design Session Log

### Decisions Made (2026-02-07, Session 1)

**Architectural:**
- In-process asyncio + Postgres (no Kafka/Redis for coordination)
- Supervisor is Python code, not LLM
- Most agents are primarily Python with targeted LLM calls (see LLM vs Python audit)
- Workers are agentic (multi-turn tool-use loop with source + graph tools)
- Coordinators are stateless per-cycle (fresh projection from graph, 1 LLM call/cycle)
- Developer Pipeline: generate → validate → sandbox → cache (shared capability)
- Code asset library: proven queries cached and reused across agents
- Four-layer safety: read-only connectors, static analysis, sandbox, audit
- Guided setup for source onboarding
- Dedicated Agent Performance Reflector for prompt evolution
- Auto-apply vs human-review governance boundary
- Three interaction modes: Setup, Runtime, Inquiry
- Ontology alignment is the core insight mechanism, not entity resolution
- Models are first-class with purpose and perspective metadata
- Knowledge graph is model-centric, not entity-centric
- Contradictions are features (`contradicts` edges), not problems to resolve
- APR limited to ground-truth learning only (binary verifiable patterns)
- Convergence = alignment stability (reinforcement/expansion/challenge ratio)
- Configure Agent and Query Agent are API-side, not runtime-managed
- Single coordinator to start; multi-coordinator deferred

**Strategic:**
- Start fresh from ALEC v4 (no migration, no backward compatibility)
- Proprietary personal tooling (no open source, no platform ambitions)
- Solve own problem first; external users way down the roadmap
- Connectors deferred — stub protocol, build real connectors on the ground
- UI/admin is half the application (~70 endpoints, ~23 pages)

### Decisions Made (2026-02-08, Session 2)

**Generalization (Section 13):**
- **Platform vs Domain separation:** Architecture split into three layers — Platform (domain-independent runtime), Schema (per-engagement configuration), Connector (pluggable source implementations)
- **No hardcoded ontology:** Entity types, relationship types, and domain vocabulary are engagement-level configuration, not platform-level enums. Workers receive available types dynamically in their prompts
- **Engagement templates:** Cold-start solved by templates (Enterprise Architecture, Research Synthesis, Codebase Understanding, General Discovery). Templates provide default schema + prompts. Platform doesn't privilege any template
- **Upper relationship categories:** 8 domain-independent categories (compositional, dependency, temporal, epistemic, structural, governance, realization, identity) that domain-specific types specialize. Enables cross-engagement transfer and domain-independent consolidation
- **`engagement_schema` table:** Replaces hardcoded enums. Per-engagement entity types and relationship types, each with description, examples, parent category. Populated from template, evolved by Ontology Agent
- **Dynamic prompt assembly:** Worker and coordinator prompts assemble entity/relationship types from `engagement_schema` at dispatch time, not from constants

**Ontology Agent (Section 14):**
- **New agent type:** Ontology Agent owns schema development — what categories of things matter and how they relate. Fills the gap between Configure Agent (source setup) and APR (prompt tuning)
- **Setup + Runtime lifecycle:** Proposes initial schema from problem statement during setup. Monitors type-fit during runtime (detects 'other' entities, 'related_to' overuse, type overlap). Periodic, like APR
- **Schema evolution governance:** Same auto-apply / human-review model as APR. Additions auto-apply; structural changes (merge, split, deprecate) require human review
- **Invisible to users:** Operates at Layer 3-4. Effects visible as "system getting smarter." Schema changes surface as natural language ("I noticed your docs reference SLAs frequently, I've started tracking them separately")
- **Progressive disclosure:** Four layers — L1 natural language summaries (everyone), L2 evidence chains (curious users), L3 schema/prompt management (power users), L4 audit trail (administrators)
- **Internal/external vocabulary:** System maintains two vocabularies. Internal (ontology terms for machine processing) and external (natural language for user experience). UI and Query Agent translate between them
- **Peer to APR:** APR tunes how workers explore (navigation hints). Ontology Agent tunes what vocabulary workers use (entity types, relationship types). No overlap

**Ontology Standards (Section 14):**
- **No formal standard adopted.** OWL/RDF (too heavy), TOGAF/ArchiMate (too prescriptive), SUMO/BFO (too philosophical) all rejected
- **Property graph alignment:** Conceptual alignment with property graph model (nodes with labels and properties, typed directed edges) — de facto industry standard, already what we build
- **Upper categories inspired by ontology research:** Not an upper ontology, just 8 universal relationship patterns. Lighter than BFO, more structured than no categories at all
- **Study Wikidata:** Items + statements + qualifiers + references pattern is battle-tested at scale. Schema evolution model (open-ended, community-governed) is a practical reference for Ontology Agent behavior

**AI History Parallels (Section 13):**
- **Symbolic AI + Connectionist Acquisition:** LLMs as the knowledge acquisition layer that 1980s expert systems couldn't solve. Output is structured and inspectable, not opaque weights
- **Complementary Learning Systems:** Three-tier memory maps to hippocampus/neocortex model. Consolidation ("sleep") is where insight lives — deserves first-class status
- **Non-Differentiable External Memory:** Deliberately giving up end-to-end differentiability to gain inspectability, editability, and governance. This is a feature, not a limitation
- **Cross-Substrate Knowledge Distillation:** LLM implicit understanding → explicit structured form. Mental model is "crystallization" not "degradation"
- **Bitter Lesson Amended:** Computation wins for acquisition, structured representation wins for trust. Regulated industries need both

### Design Philosophy

- **Archaeological metaphor:** Big rocks from user (onboarding), small rocks from workers (extraction), remove noise to show signal. Simple connections are sufficient for the reliable core.
- **Two-tier value:** Tier 1 (reliable) is automated inventory + evidence-based connections. Tier 2 (aspirational) is emergent insight from absence detection, transitive chains, co-occurrence patterns. Design for both, deliver on Tier 1.
- **Keep representation simple.** Small fixed vocabulary of alignment types. Don't over-engineer meta-symbology. The formalization trap (TOGAF, ArchiMate, UML) creates more complexity than it solves.
- **The backing story:** Convergence isn't about reading everything — it's about having a coherent narrative that makes the evidence hang together. Without a backing story, you're just reciting observations.
- **Platform generality, domain specificity.** The platform is domain-independent. The schema layer makes it domain-specific. The first use case is enterprise architecture discovery, but the architecture supports research synthesis, codebase understanding, incident investigation, and any other knowledge-building domain without code changes.
- **Invisible complexity.** Users experience a system that understands their domain and gets smarter over time. The ontology, schema evolution, prompt governance, and convergence mechanics are real but hidden behind progressive disclosure. Traceability and evidence are always accessible but never forced.

### Reference Case

The canonical example for design decisions is a real consulting engagement involving:
- A spreadsheet with a product taxonomy (domains → capabilities) — built for investment allocation
- Confluence product boards showing Jira deliverables — organized by team delivery
- A product strategy document with ~12 different problem framings — executive communication
- A proposed 5 value stream model — user's simplification for decisions
- An organic codebase with no consistent structure — 5 years of pragmatic growth

This case demonstrates that different sources represent different **contextual ontologies** (mental models), not different names for the same things. The insight comes from mapping between models, not collapsing them into one.

### Rabbit Holes Avoided

- **Meta-symbology for emergent ontology:** Discussed, deliberately set aside. Formal ontology languages become more complex than the problems they solve. Simple labeled edges are sufficient.
- **APR as meta-learner optimizing subjective quality:** Replaced with ground-truth collector. Junior analyst analogy: they learn vocabulary, navigation, and anti-patterns (binary ground truth), not "how to think about the problem."
- **Grandiose enterprise build phases:** Original 6-phase plan with enterprise features was too much for "solve my problem first."
- **Formal ontology standards (OWL, TOGAF, BFO):** Discussed, deliberately avoided. Upper categories borrowed as lightweight concept. The formalization trap still applies — emergent schemas from evidence, not conformance to prescribed models.
- **Hardcoded enterprise ontology:** Initial design baked enterprise architecture concepts into SQL enums and tool definitions. Refactored to engagement-level configuration via templates. Platform is domain-independent.

### Design Status & Next Sessions

**Completed (~90%):**
- Core insight and architectural reframing (Section 12)
- All 15 open questions resolved (Section 15)
- Full application layout with module interfaces and DB schema (Section 11)
- Full UI/admin surface area with ~70 endpoints, ~23 pages (Section 11)
- 8 architectural gaps identified with recommendations (Section 11)
- Core runtime component specs (→ [runtime_component_specs.md](runtime_component_specs.md))
- Generalization architecture: platform vs domain vs connector layers (Section 13)
- Ontology Agent design (Section 14)
- Upper relationship categories and engagement templates (Section 13)
- AI history parallels and design implications (Section 13)

**Remaining (~10%) — Next session priorities:**
1. **Build sequence:** Organize around "first discovery cycle" milestone — minimum set of components to run a real engagement. Incorporate Ontology Agent v1 as prerequisite.
2. **Hard UI component designs:** Alignment map visualization (Sankey? matrix? alluvial?), source setup wizard UX, prompt editor / agent IDE, knowledge graph visualization at multiple scales.
3. **Integration patterns:** LLM client abstraction (Anthropic ↔ enterprise gateway), embedding service abstraction.
