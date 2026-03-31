# ALEC — Adaptive Learning & Execution Core

ALEC is a **multi-agent knowledge discovery system** built on the blackboard architecture pattern. It coordinates AI agents to explore complex information landscapes — documents, web sources, APIs — and build persistent knowledge graphs with full provenance tracking. The system demonstrates enterprise-grade architectural decisions: ACID consistency via PostgreSQL (no Kafka, no Redis), stateless coordination to eliminate the most dangerous multi-agent failure mode (coordinator state drift), and human-in-the-loop steering where users set source trust tiers, annotate entities, and ask questions that directly shape agent behavior. This is not a chatbot wrapper. It is a working prototype of how multi-agent systems should be built for regulated, knowledge-intensive environments.

## How It Works

A **Supervisor** runs cycles of exploration. Each cycle:

1. **Manual directives** submitted by users are dispatched first
2. The **Coordinator** (one LLM call) examines the knowledge graph — enriched with user annotations, source trust tiers, and open questions — and generates targeted exploration directives
3. **Workers** (parallel tool-use loops) explore sources, extract entities, relationships, and observations into the graph
4. **Consolidation** synthesizes cross-source knowledge

Users interact through a React frontend: editing engagement metadata, managing sources with priority and trust tiers, annotating entities, asking questions that guide exploration, submitting manual directives, taking snapshots, correcting and merging entities, and generating reports.

## Architecture

```
Browser (React 19 + D3.js + TanStack Query)
  → FastAPI (4 route modules, ~38 endpoints, WebSocket)
    → Supervisor (asyncio main loop)
      → Coordinator (LLM: projection → directives)
      → Workers (LLM: tool-use loops → GraphWriter → PostgreSQL)
      → Consolidation (post-cycle cross-source synthesis)
      → Community detection (post-cycle Louvain clustering)
```

**Stack:** PostgreSQL 17 + pgvector, Python asyncio, Anthropic Claude, React, Vite, TailwindCSS 4

**Key design choices:**
- Blackboard pattern — shared knowledge graph as coordination medium
- PostgreSQL-only — no Kafka/Redis; ACID for entity resolution
- Stateless coordinator — no state drift between cycles
- Human-in-the-loop — annotations, questions, and trust tiers feed into coordinator projections
- Separate summary vs initial prompt — display text evolves independently from LLM input

## Validation

238 unit tests passing across the full backend. Four-tier test pyramid:

| Tier | Scope | Infrastructure |
|------|-------|----------------|
| **Unit** | All domain logic, agents, runtime, API routes, knowledge layer | No DB, no network (fully mocked) |
| **Integration** | Database operations, schema migrations, repository queries | Real PostgreSQL via Docker |
| **Component** | Multi-layer flows: API → runtime → knowledge → DB | Mock LLM + real PostgreSQL |
| **Smoke** | End-to-end cycles with live LLM calls | Real LLM + real PostgreSQL |

Static analysis: clean mypy strict, clean ruff (lint + format). Frontend: clean TypeScript strict compilation.

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd ALEC
pip install -e .

# Start all services
docker-compose up -d

# Open the UI
open http://localhost:5173
```

This starts PostgreSQL 17 + pgvector, the FastAPI backend (port 8000), and the React frontend (port 5173).

**Requirements:** Docker, Python 3.12+, Node.js 20+, an Anthropic API key.

Set your API key:
```bash
export ALEC_ANTHROPIC_API_KEY=sk-ant-...
```

## Development

```bash
# Start only Postgres (for local dev)
docker-compose up -d postgres

# Run API server locally
python -m alec.api.main

# Run frontend dev server
cd frontend && npm install && npm run dev

# Run tests
pytest tests/unit/ -v

# Lint + format
ruff check --fix . && ruff format .

# Type check
mypy alec/
cd frontend && npx tsc --noEmit
```

## Project Structure

```
alec/
  api/              # FastAPI app, routes (engagements, knowledge, research, ws), ~40 schemas
  agents/           # LLM client, prompts (coordinator, worker), tool schemas
  config/           # Pydantic Settings (env prefix ALEC_, 23 settings)
  connectors/       # Source connectors (local_files, web), registry, spec parser
  db/               # Pool, schema.sql (22 tables), embeddings
  events/           # In-process async pub/sub
  knowledge/        # Domain models, GraphWriter, community detection, templates, repositories
  reports/          # HTML report generation
  runtime/          # Supervisor, coordinator, worker, budget, consolidation, drift detection
  services/         # Setup analyzer, schema proposer
frontend/
  src/api/          # HTTP client, ~30 TypeScript types, ~38 TanStack Query hooks
  src/components/   # 21 React components
  src/pages/        # Route pages (Home, Engagement, NewEngagement)
docs/design/        # Historical planning artifacts (see ARCHIVE_NOTE.md)
tests/              # unit, integration, component, smoke
```

## Configuration

All settings via environment variables with `ALEC_` prefix. See `alec/config/settings.py` for the full list, or `CLAUDE.md` for a reference table.

Key variables: `ALEC_ANTHROPIC_API_KEY`, `ALEC_DATABASE_URL`, `ALEC_DEFAULT_MODEL`, `ALEC_MAX_WORKERS`.

## Documentation

- **`CLAUDE.md`** — Full development context (architecture, key files, API endpoints, environment variables)
- **`docs/design/`** — Original design documents (architectural vision, buildable specs, 155-story validation, market research). These are planning artifacts — see `docs/design/ARCHIVE_NOTE.md` for implementation status.

## License

Proprietary. All rights reserved.
