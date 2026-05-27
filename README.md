# ALEC — Adaptive Learning & Execution Core

ALEC is a **multi-agent knowledge-discovery system** built on the blackboard architecture
pattern. It coordinates AI agents to explore information landscapes — documents, web
sources, APIs — and build a persistent, provenance-tracked knowledge graph that a human
steers in real time (source trust tiers, entity annotations, open questions, manual
directives).

> **What this is — read first.** This is a **learn-by-doing AI-engineering experiment**,
> written to understand how multi-agent systems should be built for regulated,
> knowledge-intensive work — not a finished product. It's the current (**v5**) line of the
> ALEC project. The earlier, more ambitious **v4** concept — a real-time *learning loop*
> over "atomic knowledge units" — now lives in its own repo:
> [**Acatium/alec-learning-loop**](https://github.com/Acatium/alec-learning-loop). The code
> here is a real working prototype (~11K Python + ~4.5K TypeScript); its **238 unit tests
> pass offline**, while the integration / component / smoke tiers need real infrastructure
> (see [Status & how to run](#status--how-to-run)).

---

## What this explores

How do you coordinate several LLM "workers" toward a shared, growing understanding without
the coordination itself becoming the failure point? ALEC's answers, each grounded in code:

- **Blackboard pattern.** There is no message-passing choreography between agents — the
  shared knowledge graph *is* the coordination medium. Workers write entities,
  relationships, and observations through a single `GraphWriter`
  (`alec/knowledge/graph_writer.py`, domain types in `alec/knowledge/domain.py`).

- **Stateless coordinator.** Each cycle the coordinator is rebuilt from a fresh SQL
  projection of the graph rather than carrying state forward — explicitly to avoid
  *coordinator state drift*, the dominant multi-agent failure mode
  (`alec/runtime/coordinator.py:36` — "Stateless coordinator cycle: projection → rank → LLM
  → directives"). The projection folds in user trust tiers, annotations, and open questions
  (`alec/knowledge/repositories/projections.py`).

- **PostgreSQL-only — no Kafka, no Redis.** Entity resolution needs ACID; the design uses
  Postgres + pgvector and an in-process async event bus instead of external brokers
  (`docker-compose.yml`, `alec/db/schema.sql` — 22 tables). This is a deliberate reaction
  to the heavier v4 stack.

- **Human-in-the-loop steering.** A `Supervisor` loop dispatches user-submitted manual
  directives *before* coordinator planning each cycle (`alec/runtime/supervisor.py:393`),
  so a person can redirect the agents mid-run.

- **Convergence, community detection, and drift.** Post-cycle Louvain community detection
  (`alec/knowledge/community.py:18`) surfaces clusters/hubs/bridges; worker drift detection
  dedups tool calls and flags scope drift (`alec/runtime/drift.py`).

## What I learned

- **Shared state beats choreography for knowledge work.** Letting the graph be the single
  source of truth removed whole classes of agent-to-agent coordination bugs — the
  interesting logic moved into *projection* (what to show the coordinator) and *entity
  resolution* (how writes merge), which is where it belongs.

- **Rebuild the coordinator every cycle.** Statelessness costs an extra projection query per
  cycle but eliminates the drift that made earlier iterations brittle.

- **Drop infrastructure you don't need.** v4 (see
  [alec-learning-loop](https://github.com/Acatium/alec-learning-loop)) ran on Kafka + Redis
  + Postgres and had no offline test path. v5 deliberately collapsed that to Postgres-only
  with an in-process bus — which is *why* this repo has a unit suite that runs green with no
  infrastructure at all.

## Status & how to run

**What runs offline (no DB, no network, fully mocked):**

```bash
pip install -e '.[dev]'      # dev extras (hypothesis, aioresponses, httpx) are REQUIRED
pytest tests/unit            # → 238 passed, 1 skipped
ruff check alec/ tests/      # clean
mypy alec/                   # strict — clean (no issues in 70 source files)
```

> Note: a plain `pip install -e .` (without `[dev]`) makes `pytest` **fail at collection**
> on three files that import `hypothesis` / `aioresponses`. CI installs `.[dev]` for this
> reason.

**What needs infrastructure (not run in CI):**

| Tier | Needs | Scope |
|------|-------|-------|
| **Integration** | real PostgreSQL (Docker) | DB ops, schema, repository queries |
| **Component** | mock LLM + real PostgreSQL | API → runtime → knowledge → DB flows |
| **Smoke** | real LLM key + real PostgreSQL | end-to-end cycles with live LLM calls |

**Run the whole app** (Postgres + pgvector, FastAPI backend, React frontend):

```bash
git clone <repo-url> && cd ALEC
pip install -e .
export ALEC_ANTHROPIC_API_KEY=sk-ant-...
docker-compose up -d                 # postgres :5432, api :8000, frontend :5173
open http://localhost:5173
```

**Requirements:** Docker, Python 3.11+, Node.js 20+, an Anthropic API key.

## How It Works

A **Supervisor** runs cycles of exploration. Each cycle:

1. **Manual directives** submitted by users are dispatched first.
2. The **Coordinator** (one LLM call) examines a projection of the knowledge graph —
   enriched with user annotations, source trust tiers, and open questions — and generates
   targeted exploration directives.
3. **Workers** (parallel tool-use loops) explore sources, extracting entities,
   relationships, and observations into the graph.
4. **Consolidation** synthesizes cross-source knowledge after the cycle.

Users interact through a React frontend: editing engagement metadata, managing sources with
priority and trust tiers, annotating entities, asking questions that guide exploration,
submitting directives, taking snapshots, correcting/merging entities, and generating
reports.

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

**Stack:** PostgreSQL 17 + pgvector · Python asyncio · Anthropic Claude · React · Vite ·
TailwindCSS 4.

## Project Structure

```
alec/
  api/              FastAPI app, routes (engagements, knowledge, research, ws), ~40 schemas
  agents/           LLM client, prompts (coordinator, worker), tool schemas
  config/           Pydantic Settings (env prefix ALEC_)
  connectors/       Source connectors (local_files, web), registry, spec parser
  db/               Pool, schema.sql (22 tables), embeddings (mock + sentence-transformers)
  events/           In-process async pub/sub
  knowledge/        Domain models, GraphWriter, community detection, templates, repositories
  reports/          HTML report generation
  runtime/          Supervisor, coordinator, worker, budget, consolidation, drift detection
  services/         Setup analyzer, schema proposer
frontend/
  src/api/          HTTP client, ~30 TypeScript types, ~38 TanStack Query hooks
  src/components/   21 React components
  src/pages/        Route pages (Home, Engagement, NewEngagement)
docs/design/        Historical planning artifacts (see ARCHIVE_NOTE.md)
tests/              unit (offline) · integration · component · smoke
```

## Development

```bash
docker-compose up -d postgres        # Postgres only, for local dev
python -m alec.api.main              # API server
cd frontend && npm install && npm run dev   # frontend dev server

pytest tests/unit -v                 # offline unit suite (238)
ruff check --fix . && ruff format .  # lint + format
mypy alec/                           # strict type check
cd frontend && npx tsc --noEmit      # frontend type check
```

## Configuration

All settings are environment variables with the `ALEC_` prefix — the full list (with
defaults and docstrings) lives in `alec/config/settings.py`.

Key variables: `ALEC_ANTHROPIC_API_KEY`, `ALEC_DATABASE_URL`, `ALEC_DEFAULT_MODEL`,
`ALEC_MAX_WORKERS`.

## Project history

- **v5 (this repo)** — multi-agent knowledge discovery, PostgreSQL-only, offline unit suite.
- **v4** — [Acatium/alec-learning-loop](https://github.com/Acatium/alec-learning-loop): the
  earlier real-time learning-loop experiment (Kafka/Redis/Postgres; needs infrastructure).
- `docs/design/` — original design documents (architectural vision, buildable specs,
  validation, market research). Planning artifacts — see `docs/design/ARCHIVE_NOTE.md` for
  implementation status.

## License

[Apache License 2.0](LICENSE)
