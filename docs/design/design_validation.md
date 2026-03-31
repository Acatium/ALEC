# ALEC v5: Design Validation

**Date:** 2026-02-08
**Method:** User story edge-case analysis (155 stories) evaluated against design documents
**Input Documents:** `ALEC_v5_design.md`, `runtime_component_specs.md`

---

## Table of Contents

1. [Methodology](#1-methodology)
2. [Summary](#2-summary)
3. [Full Gaps](#3-full-gaps)
4. [Partial Gaps](#4-partial-gaps)
5. [Design Strengths](#5-design-strengths)
6. [Prioritized Recommendations](#6-prioritized-recommendations)
7. [User Story Reference](#7-user-story-reference)
8. [Design Decisions from Market & Architecture Validation](#8-design-decisions-from-market--architecture-validation-2026-02-20)

---

## 1. Methodology

155 "As a user, I..." statements were developed across 6 personas to test the design's coverage of real-world interaction edge cases:

| Persona | Focus | Story Count |
|---|---|---|
| Inputs | Getting data/knowledge into the system | 25 |
| Outputs | Extracting knowledge and views | 23 |
| Governance | Controlling learning, prompts, schema, audit | 28 |
| Configuration | Tuning behavior, budgets, performance | 16 |
| Operational Oversight | Monitoring agents, sources, pipelines | 20 |
| Edge Cases & Failure Modes | Robustness, security, scale, concurrency | 43 |

Each story was evaluated against the design documents as:
- **Fully covered:** Design specifies schema, endpoint, workflow, or explicit handling
- **Partially covered:** Design acknowledges the need but lacks endpoint, workflow, or edge-case handling
- **Gap:** Design does not address the scenario

---

## 2. Summary

| Category | Stories | Fully Covered | Partially Covered | Gap |
|---|---|---|---|---|
| Inputs | 25 | 16 (64%) | 3 (12%) | 6 (24%) |
| Outputs | 23 | 17 (74%) | 2 (9%) | 4 (17%) |
| Governance | 28 | 19 (68%) | 3 (11%) | 6 (21%) |
| Configuration | 16 | 11 (69%) | 1 (6%) | 4 (25%) |
| Operational Oversight | 20 | 15 (75%) | 3 (15%) | 2 (10%) |
| Edge Cases & Failure Modes | 43 | 24 (56%) | 8 (19%) | 11 (26%) |
| **Total** | **155** | **102 (66%)** | **20 (13%)** | **33 (21%)** |

**Interpretation:** The core runtime architecture (coordinator cycle, worker loop, three-tier memory, prompt governance) is thoroughly specified. Gaps concentrate in: user-facing CRUD for graph manipulation, data export, governance configurability, failure recovery, and multi-user access.

---

## 3. Full Gaps

### 3.1 Inputs

#### GAP-I1: No manual entity creation endpoint

**Story #19:** As a user, I want to create an entity manually (e.g., a planned service that doesn't exist in any source yet) so my proposed architecture appears in the graph.

**Analysis:** The entity API has GET (list), GET (detail), PATCH (edit), and POST (merge). No POST to create an entity from scratch. Users who know about a planned service or off-system component have no path to add it as a structured entity. The manual observation endpoint (`POST /api/engagements/:id/observations`) creates an observation, not a structured entity.

**Impact:** Users cannot seed the graph with known topology. The system can only learn from connected sources, not from the user's existing knowledge.

**Recommendation:** Add `POST /api/engagements/:id/entities` accepting name, entity_type, model_id, aliases, and properties. Generate embedding on creation.

---

#### GAP-I2: No manual relationship creation endpoint

**Story #20:** As a user, I want to create a relationship manually between two entities when I know the connection but no source documents it.

**Analysis:** The relationships API is read-only (GET list, GET filter). No POST endpoint. A user who knows two services connect but no source documents it cannot directly create the edge.

**Impact:** Same as GAP-I1 — the graph cannot be enriched with human knowledge in structured form.

**Recommendation:** Add `POST /api/engagements/:id/relationships` accepting from_entity, to_entity, relationship_type, evidence (text), and confidence. Create the observation and relationship atomically.

---

#### GAP-I3: No relationship deletion or invalidation

**Story #25:** As a user, I want to mark a relationship as incorrect so it's removed from the graph.

**Analysis:** No DELETE or PATCH endpoint for relationships. The `relationships` table has no `status` field for soft-delete. If the system extracted an incorrect relationship, the user has no way to remove or mark it as invalid.

**Impact:** Incorrect graph data persists permanently. Over time, incorrect relationships poison consolidated knowledge and coordinator decisions.

**Recommendation:** Add `status` field to `relationships` table (`active`, `invalidated`). Add `DELETE /api/relationships/:id` (soft-delete to `invalidated`). Alternatively, add `PATCH /api/relationships/:id` supporting status changes.

---

#### GAP-I4: No engagement cloning

**Story #5:** As a user, I want to clone an existing engagement's configuration to start a similar discovery against different sources.

**Analysis:** No clone/copy mechanism in the API endpoint inventory. The Agent Library UI mentions "copy agent configs between engagements" as a capability, but no endpoint or data flow is specified.

**Impact:** Users performing similar discoveries (e.g., same template, similar sources) must re-configure from scratch each time.

**Recommendation:** Add `POST /api/engagements/:id/clone` that copies source configs (minus credentials), engagement_schema, agent_types, and current prompt_versions into a new engagement.

---

#### GAP-I5: No file upload as source type

**Story #22:** As a user, I want to upload a document (PDF, spreadsheet) that isn't in any connected source and have it explored.

**Analysis:** The `local_files.py` connector exists for dev/testing, but no file upload mechanism is described in the API or UI. Source types assume live, API-accessible systems. A user with a PDF governance document or spreadsheet taxonomy that isn't in any connected source has no path to get it explored.

**Impact:** Disconnected documents (emailed spreadsheets, downloaded PDFs, exported reports) cannot be incorporated into discovery.

**Recommendation:** Add a `file_upload` source type. `POST /api/engagements/:id/sources/upload` accepts file(s), stores locally, creates a `local_files` connector scoped to the upload directory.

---

#### GAP-I6: No knowledge graph export

**Story #37:** As a user, I want to export the knowledge graph (or a subset) to a format I can share with others who don't have access to ALEC.

**Analysis:** No export endpoint or format specification anywhere in the design. The ~70 API endpoints are all for in-app consumption.

**Impact:** Discovery findings are locked inside ALEC. Users cannot share results with stakeholders, include them in presentations, or archive them outside the system. This directly undermines the commercial value proposition for consulting engagements.

**Recommendation:** Add `GET /api/engagements/:id/export` supporting formats: JSON (full graph), CSV (entities + relationships as tables), and optionally GraphML (for graph tools). Support filtering by model, entity type, and confidence threshold.

---

### 3.2 Outputs

#### GAP-O1: Query Agent uncertainty handling

**Story #33:** As a user, I want the Query Agent to tell me when it's uncertain or when the graph doesn't have enough data to answer confidently.

**Analysis:** The Query Agent is described as LLM-driven (understand question + generate queries + synthesize answer), but no prompt guidance specifies behavior when the graph lacks data. The design mentions progressive disclosure (drill down to evidence) but not how the agent handles absence of evidence.

**Impact:** Users may receive confidently-stated answers based on thin evidence, or no useful response when the system hasn't explored a topic.

**Recommendation:** Add to the Query Agent prompt: explicit instructions to state confidence level, cite evidence count, and suggest exploration when data is insufficient. Add a `confidence` field to query responses.

---

#### GAP-O2: No audit trail export

**Story #76:** As a user, I want to export the audit trail for compliance documentation.

**Analysis:** Prompt versions, code executions, and observations are all stored and queryable via API, but no export endpoint packages them for external consumption. This gap also applies to story #73 (full audit trail accessibility).

**Impact:** Directly undermines the regulated-industry value proposition. Compliance teams need exportable documentation, not just in-app browsing.

**Recommendation:** Add `GET /api/engagements/:id/audit/export` producing a structured report: prompt version history, schema evolution log, code execution log, alignment decisions with provenance.

---

#### GAP-O3: Source contribution statistics

**Story #41:** As a user, I want to see which sources contributed the most entities/relationships so I know where value is coming from.

**Analysis:** Observations track `source_ref` and `worker_id`, so the raw data exists. But no specific query, endpoint, or UI element aggregates per-source contribution metrics (entities discovered, relationships found, observations written, worker success rate).

**Impact:** Users cannot assess ROI per source or identify which sources to prioritize.

**Recommendation:** Add a source-level statistics query to the operations dashboard: `SELECT source_ref, COUNT(DISTINCT entity_id), COUNT(DISTINCT relationship_id), COUNT(*) FROM observations GROUP BY source_ref`.

---

#### GAP-O4: Manual convergence trigger with synthesis

**Story #83:** As a user, I want to manually tell the system "enough" and trigger a final synthesis even if convergence criteria aren't met.

**Analysis:** `POST /api/engagements/:id/pause` stops the runtime. `POST /api/engagements/:id/consolidate` triggers consolidation. But there's no single "I'm done, produce the final deliverable" action that combines: stop exploration, run full consolidation, generate a synthesis report.

**Impact:** Users must manually orchestrate the end-of-engagement workflow across multiple endpoints.

**Recommendation:** Add `POST /api/engagements/:id/finalize` that: pauses the runtime, triggers full consolidation (all entities, not just stale ones), runs cross-link detection, and produces an engagement summary.

---

### 3.3 Governance

#### GAP-G1: Cannot override auto-applied prompt changes

**Story #54:** As a user, I want to override an auto-applied change if I disagree with it.

**Analysis:** Auto-applied changes create new prompt versions. Rollback exists (`POST /api/agent-types/:id/rollback`) but it's not connected to the auto-apply changelog. The user would need to: find the auto-applied change in the changelog, identify which version to roll back to, and rollback. No direct "undo this auto-applied change" action.

**Impact:** Auto-apply becomes a one-way door. Users who disagree with an automatic change face friction reversing it.

**Recommendation:** Link auto-applied changes to their resulting version IDs. Add `POST /api/proposals/:id/revert` that creates a new version reverting the specific change.

---

#### GAP-G2: Auto-apply thresholds not configurable

**Story #55:** As a user, I want to change the auto-apply thresholds (require my approval for ALL prompt changes, or auto-apply more liberally).

**Analysis:** Auto-apply criteria (`confidence >= 0.7, evidence_count >= 2, section_key in safe_sections`) are hardcoded in the design. No per-engagement configuration.

**Impact:** Users who want stricter governance (regulated industries: "approve everything") or looser governance ("trust the system") cannot adjust the balance.

**Recommendation:** Add governance thresholds to `engagement.config` JSONB: `auto_apply_confidence_threshold`, `auto_apply_min_evidence`, `auto_apply_sections`. Expose in engagement settings UI.

---

#### GAP-G3: Cannot mark divergence as "expected"

> **Status: PARTIALLY ADDRESSED (2026-02-20).** The enhanced convergence metric in `runtime_component_specs.md` Section 1.4 now excludes expected contradictions from the convergence denominator via `metadata->>'expected_contradiction'`. The API endpoint for user classification override is not yet specified. See Section 8.1 below.

**Story #71:** As a user, I want to mark a contradiction as "expected divergence" so it stops being flagged as an issue.

**Analysis:** Section 12 describes purpose-based divergence classification (expected vs unexpected) as coordinator reasoning. But there's no field on the `alignments` table for user override of the classification, and no endpoint to mark a specific divergence as expected. Contradictions continue to appear in the coordinator's projection and count against convergence.

**Impact:** Known, accepted contradictions (code bypasses documented API — this is a deliberate architecture decision) perpetually surface as issues, reducing the coordinator's gap-detection precision and potentially blocking convergence.

**Recommendation:** Add `classification` field to `alignments` table: `auto` (system-determined), `expected`, `unexpected`, `acknowledged`. Add `PATCH /api/alignments/:id` supporting classification override. Coordinator projection filters out `expected` and `acknowledged` alignments from contradiction detection.

---

#### GAP-G4: No API for schema type management

**Stories #59, #60:** As a user, I want to manually add or deprecate entity/relationship types.

**Analysis:** The `engagement_schema` table supports the data model, but no API endpoints exist for users to directly manage schema types. The only paths in are: template (at creation time) and Ontology Agent (at runtime). The `engagement_schema` table also lacks a `status` field for deprecation lifecycle.

**Impact:** Users cannot proactively configure the schema. Must wait for the Ontology Agent to detect patterns, which may take many cycles.

**Recommendation:** Add schema management endpoints:
- `GET /api/engagements/:id/schema` — list types
- `POST /api/engagements/:id/schema` — add type
- `PATCH /api/engagements/:id/schema/:type_name` — edit/deprecate type
- Add `status` field to `engagement_schema`: `active`, `deprecated`

---

#### GAP-G5: No mechanism to copy prompt configs between engagements

**Story #68:** As a user, I want to copy agent configurations (prompts, learned sections) from one engagement to another.

**Analysis:** Listed in the Agent Library UI surface area as a capability, but no API endpoint is defined. Prompt versions are scoped to agent types (global), not engagements, but learned sections may be engagement-specific. The relationship between engagement-scoped and global prompt state is unspecified.

**Impact:** Knowledge about how to explore sources (learned sections, navigation hints) is trapped in individual engagements. New engagements start cold even when the same source types have been explored before.

**Recommendation:** Clarify prompt scope (global vs engagement). Add `POST /api/agent-types/:id/versions/import` accepting a version from another engagement. Support selective import (base prompt, specific learned sections).

---

#### GAP-G6: No data flow documentation for privacy/security

**Story #139:** As a user, I want to understand what data leaves my environment vs what stays local.

**Analysis:** Critical for the regulated-industry value proposition. Source content is sent to the LLM API for extraction (workers) and synthesis (consolidation). Embeddings go to the embedding API. Everything else stays in local Postgres. But this data flow is not documented as an explicit architecture artifact.

**Impact:** Regulated customers cannot assess data residency and privacy compliance without this information. Security reviews will require it.

**Recommendation:** Create a data flow diagram documenting:
- Source content → LLM API (extraction, synthesis, query answering)
- Entity names → Embedding API (embedding generation)
- All structured data → local PostgreSQL (observations, entities, relationships, etc.)
- No data flows from ALEC to external sources (read-only connectors)

---

### 3.4 Configuration

#### GAP-C1: No proactive budget warning notifications

**Story #79:** As a user, I want to be notified when budget reaches 80% so I can decide whether to top up or converge.

**Analysis:** The design says the system "pauses and notifies when budget is exhausted" but there's no proactive warning at configurable thresholds. The budget dashboard is pull-based (GET endpoint). No push notification, WebSocket event type, or alert mechanism for approaching limits.

**Impact:** Users running overnight engagements won't know budget is nearly exhausted until they check. The system pauses abruptly instead of giving the user time to decide.

**Recommendation:** Add `BudgetWarning` event type emitted at configurable thresholds (default: 50%, 80%, 95%). Deliver via WebSocket and optionally webhook. Add `budget_warning_thresholds` to `engagement.config`.

---

#### GAP-C2: No per-agent-type LLM model selection

**Story #90:** As a user, I want to choose which LLM model powers each agent type for cost/quality tradeoff.

**Analysis:** Cost estimates assume Haiku for workers and Sonnet for coordinator, but no configuration mechanism exists. The `LLMClient` abstraction is pluggable at the backend level (Anthropic vs enterprise gateway) but not at the model-selection level per agent type. The `agent_types` table has no `model` field.

**Impact:** Users cannot optimize cost/quality tradeoff. A coordinator that needs Sonnet-level reasoning and workers that can run on Haiku are forced to use the same model.

**Recommendation:** Add `model` field to `agent_types` table (or `engagement.config` per-agent-type overrides). The `LLMClient.call()` method accepts a model parameter, with agent-type default as fallback.

---

#### GAP-C3: Embedding provider abstraction unspecified

**Story #92:** As a user, I want to configure different embedding providers for different deployments.

**Analysis:** Listed explicitly in Section 15 as remaining work: "Integration patterns: embedding service abstraction." `db/embeddings.py` is referenced in the application structure but not specified.

**Impact:** Deployment flexibility. Enterprise customers may have their own embedding endpoints.

**Recommendation:** Define `EmbeddingService` protocol (analogous to `LLMClient`): `async def embed(text: str) -> list[float]`, `async def embed_batch(texts: list[str]) -> list[list[float]]`. Configuration via `config/settings.py`.

---

#### GAP-C4: No push notification / alerting system

**Stories #79, #101:** As a user, I want proactive alerts for budget thresholds and auth expiry.

**Analysis:** The design has WebSocket for real-time UI events and `LISTEN/NOTIFY` for multi-process communication, but no general-purpose alerting system. Budget warnings, auth expiry, worker failures, and convergence events are all candidates for proactive notification.

**Impact:** Overnight/unattended operations produce no alerts. Users discover issues only when they check the UI.

**Recommendation:** Add an `AlertService` that evaluates conditions on each supervisor cycle and emits alerts via: WebSocket (if UI connected), optional webhook (for Slack/email integration), and `alerts` table (for persistent alert history).

---

### 3.5 Operational Oversight

#### GAP-OP1: No auth expiry push notification

**Story #101:** As a user, I want to be alerted when a source's authentication expires so I can re-authenticate.

**Analysis:** The UI shows "AUTH EXPIRED [Reconnect]" in the source health panel, but this is pull-based. No push notification when auth expires. For overnight runs, the user won't know until they check.

**Impact:** Auth expiry during unattended operation causes cascading worker failures for the affected source. Discovery progress stalls silently.

**Recommendation:** Covered by GAP-C4 (general alerting system). Source connector should detect auth failures (HTTP 401/403) and emit a `SourceAuthExpired` event. AlertService escalates to push notification.

---

#### GAP-OP2: No automatic task retry mechanism

**Story #126:** As a user, I want failed tasks to be automatically retried when the failure was transient (source timeout, rate limit, network blip).

**Analysis:** Failed tasks are marked `status='failed'` in the tasks table. The coordinator might dispatch new tasks to the same area in the next cycle (if the gap still exists), but there's no explicit retry mechanism. No retry count, no backoff strategy, no distinction between transient and permanent failures.

**Impact:** Transient source failures (network timeout, rate limit backoff) cause permanent task failures. The coordinator may never re-dispatch to the same area if the gap was partially addressed by the failed worker's partial results.

**Recommendation:** Add to `tasks` table: `retry_count INT DEFAULT 0`, `max_retries INT DEFAULT 3`, `failure_type TEXT` (`transient`, `permanent`, `auth`). Supervisor retries transient failures with exponential backoff. Permanent failures (validation error, auth expired) are not retried.

---

### 3.6 Edge Cases & Failure Modes

#### GAP-E1: Auto-created entities default to wrong type

**Story #116:** As a user, I want to understand when the system auto-created an entity with minimal info so I can correct it.

**Analysis:** `GraphWriter._resolve_entity()` in `runtime_component_specs.md` (line 1376-1382) auto-creates entities with `entity_type='service'` as a hard-coded default when a relationship references an unknown entity name. This is wrong for databases, teams, policies, people, etc. No observation or event notifies the user that an entity was auto-created with a guessed type.

**Impact:** Silent data quality degradation. Auto-created "service" entities that are actually databases or teams will have incorrect types until manually corrected (if the user even notices).

**Recommendation:** Change `_resolve_entity` to use `entity_type='unknown'`. Add `metadata: {"auto_created": true}` to the entity properties. Emit an observation noting the auto-creation. Coordinator gap detection should surface entities with `entity_type='unknown'` as a data quality gap.

---

#### GAP-E2: No engagement deletion with cascade

**Story #119:** As a user, I want to delete an engagement entirely and have all associated data cleaned up.

**Analysis:** The engagement status includes 'archived' but there is no DELETE endpoint. Given the number of dependent tables (observations, entities, relationships, alignments, tasks, coordinator_instances, knowledge_items, consolidated_units, convergence_log, source_configs, code_assets, code_executions, prompt_proposals, engagement_schema), deletion requires cascade logic that isn't specified.

**Impact:** Engagements accumulate indefinitely. Test engagements, failed experiments, and abandoned discoveries consume storage and clutter the UI.

**Recommendation:** Add `DELETE /api/engagements/:id` with confirmation. Implement cascading delete across all engagement-scoped tables. Consider a "soft delete" (status='deleted') with delayed hard delete for safety.

---

#### GAP-E3: No source outage resilience strategy

**Story #125:** As a user, I want the system to continue operating when one source goes down.

**Analysis:** Workers would fail with an error if a source is unreachable, and the supervisor records the failure. But there's no strategy for: source-level health tracking (consecutive failures → quarantine), redirecting workers to healthy sources, automatic re-enabling when the source recovers, or user notification.

**Impact:** A single unhealthy source causes repeated worker failures, wasting budget and coordinator cycles dispatching doomed tasks.

**Recommendation:** Add source health tracking to the supervisor:
- Track consecutive failures per source
- After N consecutive failures (default: 3), quarantine the source (skip in coordinator gap detection)
- Periodically probe quarantined sources (every 5 minutes)
- Re-enable automatically when probe succeeds
- Emit `SourceQuarantined` and `SourceRecovered` events

---

#### GAP-E4: Graph visualization at scale

**Story #129:** As a user, I want the knowledge graph visualization to be useful at 50, 500, and 5,000 entities.

**Analysis:** The design acknowledges this as one of the "four hardest UI components" but provides no solution. Force-directed graphs become unreadable beyond ~100 nodes.

**Impact:** The alignment map — the primary deliverable of the system — becomes unusable at realistic engagement sizes.

**Recommendation:** Specify a multi-scale visualization strategy:
- **Small (<100 entities):** Full force-directed graph, all nodes visible
- **Medium (100-500):** Model-scoped views (show one model at a time with cross-model edges), entity type filtering, search-to-navigate
- **Large (500+):** Hierarchical layout by model, collapsed clusters, semantic zoom (click to expand), list-based navigation with graph detail panel
- Consider: model-pair alignment view (Sankey/alluvial diagram) as an alternative to full graph

---

#### GAP-E5: Entity belongs to single model only

**Story #140:** As a user, I want the system to handle entities that appear in multiple models from the same source.

**Analysis:** The `entities` table has a single `model_id` column (nullable UUID). An entity can belong to zero or one model. The design handles cross-model relationships via the `alignments` table, but the entity itself is single-homed. The intended pattern — create separate entity records in each model and then align them via `equivalent` — is implicit, not documented.

**Impact:** Ambiguity in implementation. Workers may try to assign an entity to multiple models and fail, or may not create the entity in a second model because it already exists (name-based dedup in `_add_entity`). The entity name dedup in `GraphWriter._add_entity` (line 1244-1251) queries by name within the engagement, not within a model, so it would find the existing entity and update it rather than creating a second record in a different model.

**Recommendation:** Document the intended pattern explicitly: entities are model-scoped; the same real-world thing has separate entity records per model, linked by `equivalent` alignments. Change the entity name dedup query to scope by `model_id` as well as `engagement_id`. Or: make `model_id` an array and support multi-model membership directly.

---

#### GAP-E6: No cycle detection in graph queries

**Story #143:** As a user, I want the system to handle circular relationships without infinite loops in path-finding queries.

**Analysis:** The `GET /api/engagements/:id/graph/paths` endpoint finds paths between two entities. The design provides no specification for this query. Circular dependencies (A→B→C→A) are valid in the real world, but path-finding queries without cycle detection can loop infinitely.

**Impact:** Path queries on cyclic graphs could hang or produce unbounded results.

**Recommendation:** Specify path-finding with depth limit (max 5 hops) and visited-node tracking. Use recursive CTE with `UNION` (not `UNION ALL`) and `WHERE depth < max_depth` to prevent cycles.

---

#### GAP-E7: No entity migration strategy for schema evolution

**Story #145:** As a user, I want to understand what happens to existing entities when their type is deprecated.

**Analysis:** The Ontology Agent can propose deprecating, merging, or splitting types via `SchemaEvolution` actions. But the design doesn't specify what happens to existing entities of the affected type. Options: reclassify to a new type (requires mapping), mark as deprecated (requires entity-level status change), leave orphaned (data quality issue), or prompt the user to resolve each one.

**Impact:** Schema evolution creates data integrity issues. Deprecated types leave entities in limbo. Merged types require bulk reclassification. Split types require per-entity decisions.

**Recommendation:** Specify migration strategy per action:
- `deprecate_type`: Existing entities keep their type but are flagged. Add `deprecated_type` flag to entities. Coordinator surfaces them as a data quality gap.
- `merge_types`: Bulk update all entities of the old type to the new type. Log as observation.
- `split_type`: Queue entities of the old type for reclassification. Ontology Agent or user assigns each to one of the new types.

---

#### GAP-E8: No empty state UX specification

**Story #149:** As a user, I want a useful experience when the engagement has just started and the graph is empty.

**Analysis:** No specification for what the UI shows when: engagement just created (no entities), graph tab opened with nothing to visualize, convergence gauge at 0%, activity feed empty, no consolidated knowledge yet.

**Impact:** First-run experience is undefined. Users may see broken visualizations, empty tables with no guidance, or confusing zero-state metrics.

**Recommendation:** Specify empty states for each UI page:
- **Dashboard:** "Discovery starting. Workers dispatched to N sources. First results expected in ~2 minutes."
- **Graph:** "No entities discovered yet. The graph will populate as workers explore your sources."
- **Convergence:** "Not enough data for convergence measurement. Minimum 3 coordinator cycles required."
- **Query:** "The knowledge graph is still building. Try asking questions after the first coordinator cycle completes."

---

#### GAP-E9: Query Agent on unexplored topics

**Story #150:** As a user, I want to understand what the Query Agent says when asked about a topic the system hasn't explored yet.

**Analysis:** The Query Agent is described as LLM-heavy but no prompt guidance specifies handling of knowledge gaps. Related to GAP-O1 (uncertainty handling) but more specific: what happens when the topic hasn't been explored at all (zero entities matching the query)?

**Impact:** User may receive "I don't know" with no actionable next step, or worse, the LLM may hallucinate an answer not grounded in the graph.

**Recommendation:** Query Agent prompt should include: "If the knowledge graph has no information about the topic, say so explicitly and suggest: (1) which sources might contain relevant information, (2) whether to dispatch a focused exploration task. Offer to create a gap observation so the coordinator prioritizes this area."

---

#### GAP-E10: No multi-user access model

**Story #155:** As a user, I want multiple people to access the same engagement.

**Analysis:** No authentication or authorization system described anywhere in the design. No user accounts, roles, or permissions. The design assumes a single user. The "Day 15: new team member joins" scenario in Section 5 describes the aspiration but no mechanism.

**Impact:** The system cannot be shared across a team. Every user has full access to everything. No audit attribution to individuals (who approved this proposal?). Blocks the consulting use case where multiple team members need access.

**Recommendation:** Design in phases:
- **v1 (MVP):** Single-user, no auth (current implicit assumption). Document this as a limitation.
- **v2:** Basic auth (API key or SSO). All authenticated users have full access to all engagements. `reviewed_by`, `created_by`, `approved_by` fields populate with user identity.
- **v3:** Role-based access: `admin` (full control), `editor` (approve proposals, add sources, create entities), `viewer` (read-only graph access, query agent). Per-engagement permissions.

---

#### GAP-E11: Convergence metric penalizes permanent contradictions

> **Status: ADDRESSED in design (2026-02-20).** The enhanced convergence metric in `runtime_component_specs.md` Section 1.4 now uses `reinforcement / (expansion + unacknowledged_challenge + 1)`, exactly as recommended. Expected contradictions (via `metadata->>'expected_contradiction'`) are excluded from the denominator. Additionally, novelty decay weighting and expansion deceleration provide secondary convergence signals. See Section 8.1 below.

**Story #133:** As a user, I want the system to converge even when some contradictions are genuinely unresolvable.

**Analysis:** The convergence ratio is `reinforcement / (expansion + challenge + 1)`. Challenges (contradictions) count against convergence. If contradictions are genuinely unresolvable (code reality vs documentation is a permanent state), convergence may never be reached even though the picture is actually complete.

**Impact:** Engagements with inherent contradictions (common in enterprise landscapes) may never converge, forcing users to manually pause.

**Recommendation:** Relate to GAP-G3 (mark divergence as expected). Contradictions classified as `expected` or `acknowledged` should not count as challenges in the convergence ratio. The formula becomes: `reinforcement / (expansion + unacknowledged_challenges + 1)`.

---

## 4. Partial Gaps

These scenarios are addressed in the design but lack complete specification.

### 4.1 Inputs

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 4 | Edit problem statement mid-engagement | Engagement table has `problem_statement`; coordinator reads it fresh each cycle | No specification for consequences: should convergence state reset? Should existing knowledge be re-evaluated? Should the user be warned that changing the problem statement may invalidate previous exploration direction? |
| 15 | Disable source temporarily | `source_configs.status` includes 'disabled' | No endpoint to toggle status. Coordinator gap detection doesn't explicitly filter disabled sources from dispatch. |
| 24 | Merge entities | `POST /api/entities/:id/merge` endpoint exists | Implementation not specified. What happens to: relationships pointing to merged-away entity? Observations referencing it? Alignments? Consolidated units? Aliases? |

### 4.2 Outputs

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 33 | Query Agent uncertainty | Progressive disclosure allows drilling to evidence | No prompt guidance for expressing uncertainty. No `confidence` field on query responses. No specified behavior for "I don't have enough data." |
| 41 | Source contribution stats | `source_ref` tracked on observations | No aggregation query, endpoint, or UI element. Data exists but isn't surfaced. |

### 4.3 Governance

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 68 | Copy agent configs between engagements | Listed in Agent Library UI surface area | No API endpoint. Scope relationship (global agent_types vs engagement-specific learned sections) unspecified. |

### 4.4 Configuration

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 82 | Set convergence thresholds | `ConvergenceConfig` exists with defaults in `engagement.config` JSONB | No UI element or specific endpoint exposes this for user modification. Users must know the JSONB structure to change defaults. |

### 4.5 Operational Oversight

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 99 | Coordinator handoff history | `coordinator_instances` table tracks instances with status and cycle count | No endpoint or UI element surfaces the handoff timeline or reasons. |
| 102 | Per-source API usage stats | `rate_limiter.py` tracks calls internally | No endpoint exposes usage data to UI. Data exists in-memory but isn't queryable. |
| 118 | Archive and restore engagement | Status includes 'archived' | No restore mechanism (archived→active). Supervisor doesn't handle this transition. |

### 4.6 Edge Cases

| # | Story | What's Covered | What's Missing |
|---|---|---|---|
| 114 | Empty survey results | Workers handle scope overflow; supervisor records failures | No explicit handling for zero-result surveys. No "source is empty" detection or notification. |
| 127 | MCP server unavailable | Falls under general source failure | No MCP-specific handling: reconnection, server restart detection, tool list refresh. |
| 130 | Very large source prioritization | Coordinator ranks gaps by reference_count | No "budget allocation per source" or "diminishing returns per source" to prevent one large source from monopolizing workers. |
| 131 | Long-running engagement (30+ days) | Consolidation synthesizes Tier 2→3 | No archival strategy for Tier 1 observations (append-only, grows indefinitely). Stale entity detection uses `ILIKE '%' || name || '%'` which degrades with observation volume. |
| 132 | Convergence never reached | Budget exhaustion provides hard stop; user can pause | No escalating strategy: relax thresholds after N cycles, notify user that convergence is unlikely, suggest switching to "report what we have" mode. |
| 144 | Two models claim same entity | Handled via alignments (cross-model edges) | `entity.model_id` forces single-model ownership. Intended pattern (separate records + alignment) is implicit, not documented. Same issue as GAP-E5. |
| 146 | Ontology Agent proposes duplicate type | PK prevents exact name duplicates | Semantically similar types with different names (e.g., "sla" vs "service_level_agreement") aren't caught. No embedding similarity check on schema proposals. |
| 147 | Template mismatch with sources | Ontology Agent can evolve schema at runtime | No proactive detection of template mismatch. No template-switching mechanism after creation. |

---

## 5. Design Strengths

Areas where the design exceeds the coverage needed by the user stories:

### 5.1 Core Runtime Architecture

The coordinator cycle (Sections 3, 5 + runtime_component_specs) is specified to implementation level: SQL queries for projection building, gap detection, contradiction detection, and alignment opportunity detection; Python dataclasses for all intermediate types; complete LLM prompt with system message and user message assembly; response parsing; decision recording. This is buildable directly from the spec.

### 5.2 Three-Tier Memory

The observation → knowledge_item → consolidated_unit pipeline (Section 4) is fully specified with: SQL schemas, cost estimates, consolidation trigger logic, stale entity detection queries, material gathering queries, synthesis prompt, cross-link detection algorithm, and complete Python implementation of the consolidation run.

### 5.3 Four-Layer Safety Model

The safety architecture (Section 7) is the most defensible part of the design: read-only connectors by protocol construction, static analysis validators with specific banned keywords, execution sandbox with resource limits, and output validation with PII scanning. Each layer is independent — all four must pass.

### 5.4 Worker Tool-Use Loop

The worker specification (runtime_component_specs Section 2) is implementation-ready: tool definitions with JSON schema, graph writer with entity resolution and relationship upsert, prompt assembly from base + learned + directive, scope overflow handling, and complete main loop with budget tracking.

### 5.5 Prompt Governance

The APR and prompt versioning system (Section 8) covers: agent types with versioned prompts, immutable version snapshots, parent version tracking, learned sections with provenance, proposals with evidence and confidence, auto-apply vs human-review boundary with clear rules, and specialization detection.

### 5.6 Ontology Alignment

The model-centric knowledge graph (Section 12) provides: models with purpose/perspective metadata, cross-model alignment types, purpose-based divergence classification, and the architectural insight that contradictions are features. The engagement template system (Section 13) and Ontology Agent (Section 14) provide schema flexibility without sacrificing the initial user experience.

---

## 6. Prioritized Recommendations

### 6.1 Critical — Blocks First Engagement

| Gap | Impact | Effort | Recommendation |
|---|---|---|---|
| GAP-I1, I2 | Cannot seed graph with known topology | Low | Add POST endpoints for entities and relationships |
| GAP-E1 | Auto-created entities default to 'service' | Low | Change default to 'unknown', add metadata flag |
| GAP-I6 | Cannot share discoveries with stakeholders | Medium | Add JSON/CSV export endpoint |
| GAP-E8 | First-run experience undefined | Low | Specify empty state text for each UI page |

### 6.2 Important — Blocks Multi-Session / Team Use

| Gap | Impact | Effort | Recommendation |
|---|---|---|---|
| GAP-E10 | System cannot be shared across a team | High | Design basic auth + roles (v2/v3 phased) |
| GAP-G6 | Regulated customers can't assess data residency | Low | Create data flow diagram documenting what goes where |
| GAP-G2 | Cannot adjust governance strictness | Low | Move auto-apply thresholds to engagement config |
| GAP-OP2 | Transient failures cause permanent task loss | Medium | Add retry logic with failure type classification |
| GAP-I3 | Cannot fix incorrect graph data | Low | Add status field and DELETE endpoint for relationships |
| GAP-E3 | One bad source wastes budget on doomed tasks | Medium | Add source quarantine logic to supervisor |
| GAP-G3 | Known contradictions block convergence | Low | Add classification field to alignments, update convergence formula |
| GAP-E11 | Engagements with inherent contradictions never converge | Low | Exclude acknowledged contradictions from convergence ratio |

### 6.3 Nice-to-Have — Quality of Life

| Gap | Impact | Effort | Recommendation |
|---|---|---|---|
| GAP-I4 | Manual re-setup for similar engagements | Medium | Add clone endpoint |
| GAP-I5 | Cannot explore disconnected documents | Medium | Add file upload source type |
| GAP-O2 | Compliance teams can't export audit data | Medium | Add audit export endpoint |
| GAP-C2 | Cannot optimize cost/quality per agent | Low | Add model field to agent_types |
| GAP-E7 | Schema evolution leaves orphaned entities | Medium | Specify migration strategy per evolution action |
| GAP-E4 | Primary deliverable unusable at scale | High | Design multi-scale visualization strategy |
| GAP-E5 | Ambiguous entity-model ownership pattern | Low | Document intended pattern; scope dedup by model_id |
| GAP-C1, C4 | No proactive notifications for unattended operation | Medium | Add AlertService with WebSocket + webhook delivery |
| GAP-G4 | Cannot proactively manage schema | Low | Add schema CRUD endpoints |
| GAP-O1 | Query Agent uncertainty handling | Low | Add prompt guidance and confidence field |
| GAP-E9 | Query Agent on unexplored topics | Low | Add prompt guidance for knowledge gaps |
| GAP-G1 | Auto-apply is a one-way door | Low | Link proposals to versions, add revert action |
| GAP-E2 | Test engagements accumulate forever | Medium | Add DELETE with cascade |
| GAP-E6 | Path queries may loop on cyclic graphs | Low | Add depth limit and visited tracking |
| GAP-G5 | Learned sections trapped in engagements | Medium | Clarify scope, add import mechanism |
| GAP-C3 | Cannot swap embedding provider | Low | Define EmbeddingService protocol |
| GAP-O3 | Cannot assess ROI per source | Low | Add source-level aggregation query |
| GAP-O4 | No single "finalize" action | Low | Add finalize endpoint combining pause + consolidation |

---

## 7. User Story Reference

The complete set of 155 user stories used for this validation. Stories marked with gap references indicate identified issues.

### 7.1 Inputs (25 stories)

1. As a user, I want to create an engagement with a problem statement so that the system knows what to discover.
2. As a user, I want to select an engagement template so I don't have to configure the schema from scratch.
3. As a user, I want to create an engagement without a template and define my own entity/relationship types.
4. As a user, I want to edit my problem statement after discovery has started because my understanding has evolved. *[PARTIAL]*
5. As a user, I want to clone an existing engagement's configuration to start a similar discovery. *[GAP-I4]*
6. As a user, I want to add a Confluence source through a guided conversation so I don't have to write YAML.
7. As a user, I want to paste an API token during setup and have the system test it immediately.
8. As a user, I want to select which Confluence spaces/Jira projects/GitHub repos are relevant.
9. As a user, I want to provide navigation hints about a source so workers explore efficiently.
10. As a user, I want to add a source via MCP when direct API access fails.
11. As a user, I want to add a source mid-engagement and have existing coordinators pick up the new data.
12. As a user, I want to add an arbitrary URL as a source even if it has no structured API.
13. As a user, I want to add a database as a source with just a connection string.
14. As a user, I want to re-authenticate a source when its token expires without losing progress.
15. As a user, I want to disable a source temporarily without deleting it. *[PARTIAL]*
16. As a user, I want to provide source credentials via environment variables.
17. As a user, I want the system to tell me what capabilities a source connector supports.
18. As a user, I want to add a manual observation so human-gathered knowledge enters the graph.
19. As a user, I want to create an entity manually so my proposed architecture appears in the graph. *[GAP-I1]*
20. As a user, I want to create a relationship manually when I know the connection but no source documents it. *[GAP-I2]*
21. As a user, I want to create a model manually and have the system map existing entities onto it.
22. As a user, I want to upload a document that isn't in any connected source and have it explored. *[GAP-I5]*
23. As a user, I want to correct an entity's name/type/aliases when the system got it wrong.
24. As a user, I want to merge two entities that the system thinks are different but are actually the same. *[PARTIAL]*
25. As a user, I want to mark a relationship as incorrect so it's removed from the graph. *[GAP-I3]*

### 7.2 Outputs (23 stories)

26. As a user, I want to ask natural language questions and get answers grounded in the knowledge graph.
27. As a user, I want to ask "What do we know about X?" and get a consolidated summary with attribution.
28. As a user, I want to ask "What gaps remain?" and see unexplored areas.
29. As a user, I want to drill down from a consolidated summary to the raw observations that support it.
30. As a user, I want to ask comparative questions and get cross-model analysis.
31. As a user, I want to ask "What contradictions exist?" and see a prioritized list.
32. As a user, I want to ask a question that requires a novel dynamic query and have it generated safely.
33. As a user, I want the Query Agent to tell me when it's uncertain or data is insufficient. *[PARTIAL — GAP-O1]*
34. As a user, I want to generate a dependency map color-coded by documentation status.
35. As a user, I want to generate a compliance report showing assets in code but not in governance.
36. As a user, I want to generate stakeholder-specific views framing the same data differently.
37. As a user, I want to export the knowledge graph to share with others who don't have ALEC access. *[GAP-I6]*
38. As a user, I want to see the alignment map showing how entities in different models relate.
39. As a user, I want a divergence report distinguishing expected from unexpected divergences.
40. As a user, I want to see the convergence trajectory over time.
41. As a user, I want to see which sources contributed the most entities/relationships. *[PARTIAL — GAP-O3]*
42. As a user, I want to browse entities filtered by model, type, and status.
43. As a user, I want to see all cross-model appearances of a single entity.
44. As a user, I want to search entities semantically, not just by name.
45. As a user, I want to see N-hop neighborhoods of an entity.
46. As a user, I want to find paths between two entities.
47. As a user, I want interactive graph visualization with zoom/filter by model, type, or confidence.
48. As a user, I want to see which entities are orphans — referenced in one source with no counterpart.

### 7.3 Governance (28 stories)

49. As a user, I want to see a queue of pending APR proposals.
50. As a user, I want to see the evidence behind each proposal.
51. As a user, I want to modify a proposal before approving it.
52. As a user, I want to reject a proposal with a reason so the APR can learn.
53. As a user, I want to see which changes were auto-applied and when.
54. As a user, I want to override an auto-applied change if I disagree. *[GAP-G1]*
55. As a user, I want to change the auto-apply thresholds. *[GAP-G2]*
56. As a user, I want to see what entity types and relationship types are active.
57. As a user, I want to approve/reject when the Ontology Agent proposes a new entity type.
58. As a user, I want to approve/reject when the Ontology Agent proposes merging types.
59. As a user, I want to manually add an entity type that I know is important. *[GAP-G4]*
60. As a user, I want to deprecate an entity type that's no longer relevant. *[GAP-G4]*
61. As a user, I want to see why a schema change was proposed.
62. As a user, I want to view the current assembled prompt for any agent type.
63. As a user, I want to diff two prompt versions side-by-side.
64. As a user, I want to see the full version history of any prompt with change rationale.
65. As a user, I want to manually edit a prompt section.
66. As a user, I want to rollback to a previous prompt version.
67. As a user, I want to create a specialized agent type with custom extraction rules.
68. As a user, I want to copy agent configurations from one engagement to another. *[PARTIAL — GAP-G5]*
69. As a user, I want to manually create an alignment between two entities across models.
70. As a user, I want to edit an alignment's type when the system got the classification wrong.
71. As a user, I want to mark a contradiction as "expected divergence." *[GAP-G3]*
72. As a user, I want to see who or what created each alignment for audit purposes.
73. As a user, I want a full audit trail of every prompt change, schema change, and alignment decision.
74. As a user, I want to trace any knowledge claim back through consolidated unit to source document.
75. As a user, I want to see which agent, prompt version, and source produced each observation.
76. As a user, I want to export the audit trail for compliance documentation. *[GAP-O2]*

### 7.4 Configuration (16 stories)

77. As a user, I want to set a total token/cost budget for an engagement.
78. As a user, I want to see real-time cost tracking broken down by agent type.
79. As a user, I want to be notified when budget reaches 80%. *[GAP-C1]*
80. As a user, I want to set per-worker token budgets.
81. As a user, I want the system to pause gracefully when budget is exhausted.
82. As a user, I want to set convergence thresholds. *[PARTIAL]*
83. As a user, I want to manually trigger synthesis even if convergence isn't met. *[GAP-O4]*
84. As a user, I want to tell the system "go deeper on governance" and spawn a focused coordinator.
85. As a user, I want to adjust how many consecutive stable cycles are required for convergence.
86. As a user, I want to resume a paused engagement from where it left off.
87. As a user, I want to adjust worker concurrency based on my API rate limits.
88. As a user, I want to set per-source rate limits.
89. As a user, I want to set the coordinator cycle interval.
90. As a user, I want to choose which LLM model powers each agent type. *[GAP-C2]*
91. As a user, I want to point the system at an enterprise LLM gateway.
92. As a user, I want to configure different embedding providers. *[GAP-C3]*

### 7.5 Operational Oversight (20 stories)

93. As a user, I want a real-time dashboard showing active coordinators and workers.
94. As a user, I want to see what each active worker is currently doing.
95. As a user, I want to see worker completion statistics.
96. As a user, I want to kill a specific worker that appears stuck.
97. As a user, I want to force a coordinator cycle immediately.
98. As a user, I want to see the coordinator's decision log.
99. As a user, I want to see how many coordinator handoffs have occurred and why. *[PARTIAL]*
100. As a user, I want to see the health status of all configured sources.
101. As a user, I want to be alerted when a source's authentication expires. *[GAP-OP1]*
102. As a user, I want to see per-source API usage rates. *[PARTIAL]*
103. As a user, I want to see which sources have never been successfully surveyed.
104. As a user, I want a real-time activity feed filterable by type.
105. As a user, I want the activity feed to update via WebSocket.
106. As a user, I want to filter the activity feed to show only errors and warnings.
107. As a user, I want to see which entities need reconsolidation.
108. As a user, I want to trigger consolidation manually.
109. As a user, I want to see cross-link discoveries.
110. As a user, I want to see the code asset library.
111. As a user, I want to see the execution audit trail for generated queries.
112. As a user, I want to see which queries failed validation and why.

### 7.6 Edge Cases & Failure Modes (43 stories)

113. As a user, I want the system to handle inconsistent naming across sources.
114. As a user, I want the system to handle sources with empty survey results. *[PARTIAL]*
115. As a user, I want the system to handle extremely large pages with truncation.
116. As a user, I want to know when the system auto-created an entity with guessed type. *[GAP-E1]*
117. As a user, I want to understand how conflicting relationships from multiple workers accumulate evidence.
118. As a user, I want to archive and later restore an engagement. *[PARTIAL]*
119. As a user, I want to delete an engagement with full cascade cleanup. *[GAP-E2]*
120. As a user, I want to run multiple engagements simultaneously against overlapping sources.
121. As a user, I want to let the system run overnight while I sleep.
122. As a user, I want the system to survive a crash/restart without losing progress.
123. As a user, I want partial results preserved when a worker dies mid-task.
124. As a user, I want coordinator handoff to be invisible to me.
125. As a user, I want the system to continue when one source goes down. *[GAP-E3]*
126. As a user, I want failed tasks to be retried when the failure was transient. *[GAP-OP2]*
127. As a user, I want the system to handle MCP server unavailability. *[PARTIAL]*
128. As a user, I want the system to handle API rate limiting gracefully.
129. As a user, I want the graph visualization to work at 50, 500, and 5,000 entities. *[GAP-E4]*
130. As a user, I want to understand how the coordinator prioritizes within very large sources. *[PARTIAL]*
131. As a user, I want long-running engagements (30 days) to remain manageable. *[PARTIAL]*
132. As a user, I want to understand what happens when convergence is never reached. *[PARTIAL]*
133. As a user, I want the system to converge even when contradictions are unresolvable. *[GAP-E11]*
134. As a user, I want assurance that workers can never write to external sources.
135. As a user, I want assurance that generated queries are validated as read-only.
136. As a user, I want assurance that sandboxed execution has resource limits.
137. As a user, I want assurance that PII in results is flagged.
138. As a user, I want credentials stored securely via env vars.
139. As a user, I want to understand what data leaves my environment. *[GAP-G6]*
140. As a user, I want entities that appear in multiple models handled correctly. *[GAP-E5]*
141. As a user, I want entities without a model assignment handled.
142. As a user, I want models with zero entities handled.
143. As a user, I want circular relationships handled without infinite loops. *[GAP-E6]*
144. As a user, I want to understand when two models both claim the same entity. *[PARTIAL]*
145. As a user, I want to understand what happens to entities when their type is deprecated. *[GAP-E7]*
146. As a user, I want the Ontology Agent to detect semantically duplicate types. *[PARTIAL]*
147. As a user, I want the system to handle template mismatch with actual sources. *[PARTIAL]*
148. As a user, I want a useful experience with just one source configured.
149. As a user, I want to understand what the UI shows when the graph is empty. *[GAP-E8]*
150. As a user, I want the Query Agent to handle questions about unexplored topics. *[GAP-E9]*
151. As a user, I want consolidation to handle engagements with minimal observations.
152. As a user, I want to query the graph while the runtime is actively running.
153. As a user, I want to approve proposals while workers are running.
154. As a user, I want to add a source while the engagement is active.
155. As a user, I want multiple users to view the same engagement. *[GAP-E10]*

---

*This document captures a point-in-time validation of the v5 design. Gaps should be addressed during implementation planning, not necessarily before implementation begins — many are incremental additions that can be built after the core runtime is functional.*

---

## 8. Design Decisions from Market & Architecture Validation (2026-02-20)

Market research and architecture validation identified the convergence metric as the weakest design element and the worker tool-use loop as missing guardrails. These findings led to four design enhancements, detailed below.

### 8.1 Convergence Enhancement

**Gaps addressed:** GAP-E11 (convergence penalizes permanent contradictions), GAP-G3 (cannot mark divergence as expected)

**What was decided:**
- Replace the simple `reinforcement / (expansion + challenge + 1)` ratio with a multi-signal metric
- Add novelty decay weighting: `1/log2(observation_count + 1)` diminishes repeat-entity reinforcement
- Add anti-gaming cap: max 3 reinforcement credits per entity per cycle
- Exclude expected contradictions from convergence denominator (resolves GAP-E11)
- Add expansion deceleration as a secondary convergence signal
- Track per-source reinforcement ratios to detect single-source dominance

**Spec cross-reference:** `runtime_component_specs.md` Section 1.4, `ALEC_v5_design.md` Section 3 (Convergence Criteria)

### 8.2 Worker Drift Detection

**Gaps addressed:** No specific GAP (identified during architecture review as missing guardrail)

**What was decided:**
- Add `WorkerLoopState` dataclass to track tool call history, errors, and entity type distribution
- Tool call deduplication via hash of `(tool_name, sorted params)` — cached results returned on repeat
- Per-tool error retry limit: max 3 per unique `(tool, args)` pair
- Scope drift detection: flag when entity type distribution diverges from directive scope
- New fields on `WorkerResult`: `drift_detected`, `duplicate_calls_skipped`, `retries_exhausted`

**Spec cross-reference:** `runtime_component_specs.md` Section 2.7

### 8.3 Community Detection

**Gaps addressed:** No specific GAP (identified during architecture review as missing structural insight)

**What was decided:**
- Post-cycle community detection step in supervisor using graph algorithms
- Algorithm: networkx Louvain for <500 entities, igraph Leiden for larger graphs
- Identifies topic clusters, hub entities, bridge entities, and isolated clusters
- Results stored in `community_analysis` table and fed into coordinator projection
- Runs in executor (CPU-bound, same pattern as embeddings)

**Spec cross-reference:** `runtime_component_specs.md` Section 5, Schema in Section 4.4

### 8.4 Competitive Positioning

**Gaps addressed:** Open Question #12 (competitive positioning) moved from DEFERRED to PARTIALLY RESOLVED

**What was decided:**
- No direct competitor in ALEC's exact niche (multi-agent coordinated exploration + persistent knowledge graph + convergence + full provenance)
- Closest analogs: Zep/Graphiti (architecture), Hebbia (market), Glean (scale)
- Positioning: lead with compliance/provenance, not "knowledge graphs"
- Beachhead verticals: M&A due diligence, compliance auditing
- EU AI Act (August 2026) creates regulatory forcing function for ALEC's core capabilities
- MCP integration added as open question #16

**Spec cross-reference:** `docs/design/market_validation.md`, `ALEC_v5_design.md` Appendix A and Open Questions
