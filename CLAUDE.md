# ALEC v5 Development Context

## Project Overview

**ALEC** (Adaptive Learning & Execution Core) is a **living research workspace** powered by coordinated AI agents. It explores sources, extracts structured knowledge into a shared graph, and lets users steer the discovery process in real time.

**Core Idea:** A Coordinator dispatches Worker agents to explore sources (files, APIs, wikis). Workers extract entities, relationships, and observations into a shared PostgreSQL + pgvector graph. The Coordinator uses SQL projections — enriched with user annotations, source trust tiers, and open questions — to detect gaps, contradictions, and alignment opportunities, then directs the next cycle of exploration. Users can annotate entities, ask questions, submit manual directives, manage sources, correct/merge entities, take snapshots, and generate reports — all while the system continues learning.

---

## Quick Reference

**Working Directory:** /home/matt/ALEC
**Platform:** Linux (WSL2)
**Branch:** v5
**v4 Archive:** All v4 code preserved in `archive/v4/`
**Design Docs:** See `docs/design/` — historical planning artifacts (see `docs/design/ARCHIVE_NOTE.md`)

---

## Architecture

```
User (browser)
  → Frontend (React + Vite + TailwindCSS)
    → FastAPI (4 route modules: engagements, knowledge, research, ws)
      → Supervisor (main async loop)
        → Manual directive dispatch (user-submitted tasks, dispatched first)
        → Coordinator (1 LLM call per cycle: projection → directives)
          → Workers (tool-use loop: source tools + graph tools)
            → GraphWriter (entity resolution → PostgreSQL)
      → Consolidation (post-cycle cross-source synthesis)
```

**Storage:** PostgreSQL 17 + pgvector (no Kafka, no Redis)
**LLM:** Anthropic Claude via raw SDK (prompt caching, streaming)
**Frontend:** React 19, React Router, TanStack Query, D3.js, TailwindCSS 4
**Event Bus:** In-process async pub/sub (no Kafka)
**Deployment:** Docker Compose (postgres + api + frontend)

---

## Architecture Decisions

| Decision | Status | Rationale |
|----------|--------|-----------|
| Blackboard pattern (shared knowledge graph) | Validated | arXiv multi-agent surveys confirm as dominant pattern for knowledge-intensive coordination |
| PostgreSQL-only (no Kafka/Redis) | Validated | Consistent with OpenAI production precedent; ACID needed for entity resolution |
| Stateless coordinator (per-cycle) | Validated | Avoids coordinator state drift, the most dangerous multi-agent failure mode |
| Single-process asyncio | Validated | Appropriate for I/O-bound LLM workloads at current scale |
| Living research workspace (human-in-the-loop) | Implemented | Users steer via annotations, questions, manual directives, source trust tiers |
| Source trust tiers in projections | Implemented | Coordinator sees authoritative/analytical/reference classification per source |
| User annotations in projections | Implemented | Coordinator respects important/explore_more/dismiss signals on entities |
| Open questions in projections | Implemented | Coordinator prioritizes directives that help answer user questions |
| Manual directive dispatch | Implemented | User-submitted tasks dispatched at cycle start before coordinator planning |
| Metadata-only snapshots | Implemented | Captures counts + convergence ratio; avoids expensive full data copies |
| Entity merge as atomic transaction | Implemented | Reassigns relationships/observations, sums counts, merges aliases/properties, deletes source |
| Engagement summary vs initial prompt | Implemented | Summary (display-only) evolves independently from problem_statement (LLM prompt) |
| Dynamic ontology schema | Implemented | Per-engagement entity/relationship type definitions, templates, LLM schema proposals |
| Enhanced convergence metric | Implemented | Novelty-weighted ratio + expansion deceleration + per-source tracking via settings |
| Worker drift detection | Implemented | Tool call dedup, retry limits, scope drift flags in runtime/drift.py |
| Community detection | Implemented | Post-cycle Louvain for topic clusters, hubs, bridges; stored in community_analysis table |

---

## Market Context

**Positioning:** Lead with compliance & provenance, not "knowledge graphs." Enterprise buyers search for audit trails, compliance documentation, and due diligence automation.

**Beachhead verticals:** M&A due diligence, compliance auditing, enterprise architecture discovery.

**Competitive landscape:** No direct competitor in ALEC's exact niche. Closest: Zep/Graphiti (architecture), Hebbia (market, $700M+), Glean (scale, $4.6B). None combine multi-agent exploration + persistent knowledge graph + convergence + full provenance.

**Forcing function:** EU AI Act high-risk AI obligations apply August 2026 — transparency and documentation requirements align with ALEC's provenance-tracked knowledge.

**Reference:** See `docs/design/market_validation.md` for full analysis.

---

## Development Commands

```bash
# Start all services (Postgres + API + Frontend)
docker-compose up -d

# Start Postgres only (for local development)
docker-compose up -d postgres

# Run API server locally
python -m alec.api.main

# Run frontend dev server
cd frontend && npm run dev

# Run ALEC CLI (multi-source, supports local paths and web URLs)
python -m alec --source ./docs/design --cycles 3
python -m alec --source "web:https://en.wikipedia.org/wiki/Apple_Inc." --source ./docs/design --cycles 3

# Run all tests (except smoke)
pytest tests/unit/ tests/integration/ tests/component/ -v

# Run smoke tests (requires real LLM API key)
pytest tests/smoke/ -v --run-smoke

# Frontend type check
cd frontend && npx tsc --noEmit

# Frontend production build
cd frontend && npx vite build

# Install optional real embeddings (sentence-transformers)
pip install -e ".[embeddings]"

# Format + lint
ruff check --fix .
ruff format .

# Type check
mypy alec/
```

---

## Code Standards

### Layered Architecture
```
domain/          # Pure Python. No DB imports. Business rules.
repositories/    # Thin async DB access. SQL queries only.
services/        # Orchestration. Wires domain + repositories.
```

### Python
- **Type hints:** Required on all functions
- **Protocols:** Use `typing.Protocol` for interfaces (not ABCs)
- **Logging:** structlog (JSON output, contextvars for request scope)
- **Errors:** Custom hierarchy in `alec/errors.py`
- **Async:** Required for all I/O
- **Line length:** 100 characters

### Frontend
- **React 19** with functional components and hooks
- **TanStack Query** for all server state (polling intervals: 3-10s depending on endpoint)
- **TailwindCSS 4** for styling (utility classes only, no CSS modules)
- **D3.js** for knowledge graph visualization

### Testing
- **Strategy:** Test-driven development
- **Mandate:** "All correct" (fix errors, don't alter tests unless proven inaccurate)
- **Unit tests:** No DB, no network (mock everything)
- **Integration tests:** Real Postgres via docker-compose
- **Component tests:** Mock LLM + real Postgres
- **Smoke tests:** Real LLM + real Postgres

---

## Key Files

### Backend — Core

| File | Purpose |
|------|---------|
| `alec/db/schema.sql` | PostgreSQL DDL (22 tables + pgvector) |
| `alec/config/settings.py` | Pydantic Settings (env prefix `ALEC_`) |
| `alec/errors.py` | Exception hierarchy |
| `alec/db/pool.py` | asyncpg pool with pgvector codec |
| `alec/db/embeddings.py` | EmbeddingService Protocol + MockEmbeddingService |
| `alec/db/embeddings_st.py` | SentenceTransformerEmbeddingService (real embeddings) |
| `alec/events/bus.py` | In-process async pub/sub |

### Backend — Knowledge Layer

| File | Purpose |
|------|---------|
| `alec/knowledge/domain.py` | Entity, Relationship, Observation dataclasses |
| `alec/knowledge/graph_writer.py` | Entity resolution + DB writes |
| `alec/knowledge/community.py` | Post-cycle Louvain community detection (hubs, bridges, clusters) |
| `alec/knowledge/templates.py` | Schema templates (general_discovery, etc.) + populate_schema() |
| `alec/knowledge/repositories/entities.py` | Entity SQL access |
| `alec/knowledge/repositories/relationships.py` | Relationship SQL access |
| `alec/knowledge/repositories/observations.py` | Observation SQL access |
| `alec/knowledge/repositories/projections.py` | Coordinator projections (coverage, gaps, trust tiers, annotations, questions) |
| `alec/knowledge/repositories/tasks.py` | Task SQL access |
| `alec/knowledge/repositories/consolidation.py` | Consolidation SQL access |
| `alec/knowledge/repositories/schema.py` | Engagement schema (entity/relationship type definitions) SQL access |

### Backend — Connectors

| File | Purpose |
|------|---------|
| `alec/connectors/protocol.py` | SourceConnector Protocol |
| `alec/connectors/local_files.py` | Filesystem connector |
| `alec/connectors/web.py` | Web page connector (aiohttp + BeautifulSoup) |
| `alec/connectors/source_config.py` | Source spec parser (CLI string → SourceSpec) |
| `alec/connectors/registry.py` | ConnectorRegistry (source type → factory) |

### Backend — Agents & Runtime

| File | Purpose |
|------|---------|
| `alec/agents/llm_client.py` | LLMClient Protocol + AnthropicLLMClient |
| `alec/agents/prompts/coordinator.py` | Coordinator system prompt (includes trust tier, annotation, question guidance) |
| `alec/agents/prompts/worker.py` | Worker system prompt |
| `alec/agents/tools/` | Tool JSON schemas (source + graph) |
| `alec/runtime/worker.py` | Worker tool-use loop |
| `alec/runtime/coordinator.py` | Coordinator cycle (projection → directives) |
| `alec/runtime/supervisor.py` | Main async loop (manual directive dispatch + coordinator cycles) |
| `alec/runtime/budget.py` | Token budget tracking |
| `alec/runtime/consolidation.py` | Post-cycle consolidation service |
| `alec/runtime/drift.py` | Worker drift detection (tool call dedup, retry limits, scope drift) |

### Backend — API Layer

| File | Purpose |
|------|---------|
| `alec/api/app.py` | FastAPI application factory (CORS, lifespan, routers) |
| `alec/api/main.py` | Uvicorn entry point |
| `alec/api/dependencies.py` | FastAPI dependency injection (pool, settings, event bus) |
| `alec/api/schemas.py` | All Pydantic request/response models (~40 schemas) |
| `alec/api/routes/engagements.py` | Engagement CRUD + restart + analyze + cascade delete |
| `alec/api/routes/knowledge.py` | Read-only knowledge graph queries (entities, relationships, graph, stats, timeline, consolidated, entity detail) |
| `alec/api/routes/research.py` | Research workspace endpoints (18 endpoints: source management, annotations, entity corrections/merge, directives, questions, snapshots, report) |
| `alec/api/routes/ws.py` | WebSocket event streaming |

### Backend — Services & Reports

| File | Purpose |
|------|---------|
| `alec/services/setup_analyzer.py` | LLM-based engagement setup analysis |
| `alec/services/schema_proposer.py` | LLM-based schema proposal (entity/relationship types for an engagement) |
| `alec/reports/html_report.py` | Post-run HTML report generation (Jinja2) |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/api/client.ts` | HTTP client (get, post, patch, del) |
| `frontend/src/api/types.ts` | TypeScript interfaces (~30 types) |
| `frontend/src/api/hooks.ts` | TanStack Query hooks (~38 hooks) |
| `frontend/src/App.tsx` | React Router setup (4 routes) |
| `frontend/src/pages/Home.tsx` | Home page (engagement list + create button) |
| `frontend/src/pages/Engagement.tsx` | Engagement page (dashboard wrapper) |
| `frontend/src/pages/NewEngagement.tsx` | New engagement page wrapper |
| `frontend/src/components/Layout.tsx` | App shell layout (header, navigation) |
| `frontend/src/components/EngagementDashboard.tsx` | Main dashboard (inline editing, panels layout) |
| `frontend/src/components/KnowledgeGraph.tsx` | D3 force graph with position caching for stability |
| `frontend/src/components/EntityDetailPanel.tsx` | Entity detail with annotations, corrections, merge |
| `frontend/src/components/EntityList.tsx` | Paginated entity table |
| `frontend/src/components/SourceManager.tsx` | Source CRUD, priority slider, trust tier dropdown |
| `frontend/src/components/SourceExplorer.tsx` | Source content browser |
| `frontend/src/components/SchemaEditor.tsx` | Ontology schema editor (types, templates, LLM proposals) |
| `frontend/src/components/DirectiveCreator.tsx` | Manual directive submission form |
| `frontend/src/components/QuestionsPanel.tsx` | User questions CRUD |
| `frontend/src/components/SnapshotsPanel.tsx` | Point-in-time snapshot capture |
| `frontend/src/components/ReportView.tsx` | Full-page markdown report viewer |
| `frontend/src/components/ConvergenceChart.tsx` | Convergence ratio line chart |
| `frontend/src/components/CycleProgress.tsx` | Cycle progress indicator |
| `frontend/src/components/ActivityTimeline.tsx` | Task/event timeline |
| `frontend/src/components/KeyFindings.tsx` | Consolidated knowledge display |
| `frontend/src/components/StatsBar.tsx` | Engagement metrics bar |
| `frontend/src/components/ObservationBreakdown.tsx` | Observation type pie chart |
| `frontend/src/components/NewEngagement.tsx` | Engagement creation with LLM analysis |
| `frontend/src/components/EngagementList.tsx` | Engagement list view |
| `frontend/src/components/StatusBadge.tsx` | Status indicator badge |

### Documentation

| File | Purpose |
|------|---------|
| `CLAUDE.md` | This file — development context for AI assistants |
| `README.md` | Project overview and setup instructions |
| `docs/design/ARCHIVE_NOTE.md` | Index of design docs with implementation status |
| `docs/design/ALEC_v5_design.md` | Original architectural vision (~3800 lines) |
| `docs/design/runtime_component_specs.md` | Buildable specs for coordinator, worker, consolidation (~2850 lines) |
| `docs/design/design_validation.md` | 155-story gap analysis |
| `docs/design/market_validation.md` | Market research, competitive landscape |

---

## Database

22 tables across 7 categories:

```
Engagement:       engagements
Knowledge Graph:  entities, relationships, alignments, observations, knowledge_items
Consolidated:     consolidated_units, models
Agent Governance: agent_types, prompt_versions, prompt_proposals
Runtime:          coordinator_instances, tasks, convergence_log, source_configs
Research:         user_annotations, questions, snapshots
Analytics:        community_analysis, engagement_schema
Developer:        code_assets, code_executions
```

Key columns:
- `engagements.summary` (TEXT, default '') — human-facing description, separate from problem_statement (LLM prompt)
- `source_configs.priority` (INT, default 50) — source priority ordering
- `source_configs.trust_tier` (TEXT, default 'reference') — 'authoritative', 'analytical', 'reference'
- `tasks.is_manual` (BOOLEAN, default FALSE) — user-submitted manual directives

```bash
# Connect
psql -h localhost -U alec -d alec

# Key queries
SELECT * FROM engagements;
SELECT name, entity_type, observation_count FROM entities WHERE engagement_id = '...';
SELECT from_entity, to_entity, relationship_type FROM relationships WHERE engagement_id = '...';
SELECT annotation_type, content FROM user_annotations WHERE engagement_id = '...';
SELECT question_text, status FROM questions WHERE engagement_id = '...';
SELECT name, entity_count, convergence_ratio FROM snapshots WHERE engagement_id = '...';
```

Migration for existing deployments:
```sql
ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 50;
ALTER TABLE source_configs ADD COLUMN IF NOT EXISTS trust_tier TEXT NOT NULL DEFAULT 'reference';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
UPDATE engagements SET summary = problem_statement WHERE summary = '';
-- Then run the CREATE TABLE statements for user_annotations, questions, snapshots,
-- community_analysis, engagement_schema from schema.sql
```

---

## API Endpoints

### Engagements (`engagements.py`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/engagements` | Create engagement + launch supervisor |
| GET | `/api/engagements` | List all engagements with counts |
| GET | `/api/engagements/{id}` | Get engagement detail |
| DELETE | `/api/engagements/{id}` | Delete engagement + cascade |
| POST | `/api/engagements/{id}/restart` | Restart stalled/completed engagement |
| POST | `/api/engagements/analyze` | LLM-based source coverage analysis |

### Knowledge (`knowledge.py`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/engagements/{id}/entities` | Paginated entity list |
| GET | `/api/engagements/{id}/relationships` | Paginated relationship list |
| GET | `/api/engagements/{id}/observations` | Paginated observation list |
| GET | `/api/engagements/{id}/graph` | Graph nodes + edges for D3 visualization |
| GET | `/api/engagements/{id}/timeline` | Task timeline (activity feed) |
| GET | `/api/engagements/{id}/stats` | Aggregated engagement metrics |
| GET | `/api/engagements/{id}/consolidated` | Consolidated knowledge units |
| GET | `/api/engagements/{id}/entities/{eid}` | Full entity detail with observations + relationships |

### Research Workspace (`research.py`)
| Method | Path | Purpose |
|--------|------|---------|
| PATCH | `/api/engagements/{id}` | Update name / problem_statement / summary |
| GET | `/api/engagements/{id}/sources` | List sources with priority + trust tier |
| POST | `/api/engagements/{id}/sources` | Add source (parses source spec string) |
| PATCH | `/api/engagements/{id}/sources/{sid}` | Update source status / priority / trust_tier |
| DELETE | `/api/engagements/{id}/sources/{sid}` | Remove source |
| GET | `/api/engagements/{id}/annotations` | List user annotations |
| POST | `/api/engagements/{id}/annotations` | Create annotation (important, explore_more, dismiss, note, correction) |
| DELETE | `/api/engagements/{id}/annotations/{aid}` | Delete annotation |
| PATCH | `/api/engagements/{id}/entities/{eid}` | Rename / reclassify entity |
| POST | `/api/engagements/{id}/entities/{eid}/merge` | Merge source entity into target (atomic transaction) |
| POST | `/api/engagements/{id}/directives` | Create manual directive (queued for next cycle) |
| GET | `/api/engagements/{id}/questions` | List questions (open first) |
| POST | `/api/engagements/{id}/questions` | Ask a question |
| PATCH | `/api/engagements/{id}/questions/{qid}` | Update question status / answer |
| DELETE | `/api/engagements/{id}/questions/{qid}` | Delete question |
| GET | `/api/engagements/{id}/snapshots` | List snapshots |
| POST | `/api/engagements/{id}/snapshots` | Capture current counts as snapshot |
| GET | `/api/engagements/{id}/schema` | List active schema entries |
| POST | `/api/engagements/{id}/schema` | Add schema entry (entity_type or relationship_type) |
| POST | `/api/engagements/{id}/schema/apply-template` | Apply a schema template |
| GET | `/templates` | List available schema templates |
| POST | `/api/engagements/{id}/schema/propose` | LLM-based schema proposal |
| GET | `/api/engagements/{id}/report` | Generate markdown report |

### WebSocket (`ws.py`)
| Method | Path | Purpose |
|--------|------|---------|
| WS | `/api/ws/{id}` | Real-time event streaming |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ALEC_ANTHROPIC_API_KEY` | `""` (required for LLM) | Anthropic API key |
| `ALEC_DATABASE_URL` | `postgresql://alec:alec-dev-password@localhost:5432/alec` | PostgreSQL connection |
| `ALEC_LOG_LEVEL` | `INFO` | Log level |
| `ALEC_LOG_FORMAT` | `json` | Log format (`json` or `console`) |
| `ALEC_DEFAULT_MODEL` | `claude-haiku-4-5-20251001` | Default LLM model |
| `ALEC_MAX_WORKERS` | `5` | Max concurrent workers per cycle |
| `ALEC_WORKER_MAX_TOKENS` | `250000` | Token budget per worker |
| `ALEC_WORKER_MAX_TURNS` | `30` | Max tool-use turns per worker |
| `ALEC_COORDINATOR_MAX_TOKENS` | `4096` | Max tokens for coordinator response |
| `ALEC_CONVERGENCE_THRESHOLD` | `3.0` | Reinforcement/expansion ratio threshold |
| `ALEC_CONSECUTIVE_CYCLES_REQUIRED` | `3` | Cycles above threshold to converge |
| `ALEC_CONVERGENCE_NOVELTY_DECAY` | `true` | Weight newer observations higher in convergence ratio |
| `ALEC_CONVERGENCE_MAX_REINFORCEMENT_PER_ENTITY` | `3` | Cap reinforcement count per entity per cycle |
| `ALEC_CONVERGENCE_EXPANSION_DECELERATION_CYCLES` | `4` | Cycles to check expansion deceleration |
| `ALEC_ENTITY_SIMILARITY_THRESHOLD` | `0.85` | Cosine similarity threshold for fuzzy entity resolution |
| `ALEC_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model name |
| `ALEC_EMBEDDING_DIMENSIONS` | `384` | Embedding vector dimensions |
| `ALEC_USE_REAL_EMBEDDINGS` | `true` | Use real ST embeddings (requires `.[embeddings]`) |
| `ALEC_DB_MIN_POOL_SIZE` | `2` | Minimum asyncpg pool connections |
| `ALEC_DB_MAX_POOL_SIZE` | `10` | Maximum asyncpg pool connections |
| `ALEC_API_HOST` | `0.0.0.0` | API server bind address |
| `ALEC_API_PORT` | `8000` | API server port |
| `ALEC_API_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins |

---

**Last Updated:** 2026-02-22 (v5 Phase 3 — Engagement summary/prompt separation, dynamic ontology schema with templates and LLM proposals, community detection, worker drift detection, enhanced convergence metrics, entity similarity resolution)
