"""Generate a preview report with sample data (no DB needed)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "alec" / "reports" / "templates"


class _UUIDEncoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        from uuid import UUID

        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def build_demo_data() -> dict:
    """Build a realistic demo dataset simulating ALEC analyzing its own design docs."""
    now = datetime.now(timezone.utc)

    # Entities that ALEC would discover from its own design docs
    raw_entities = [
        ("Supervisor", "service", 12),
        ("Coordinator", "service", 15),
        ("Worker", "service", 18),
        ("GraphWriter", "service", 9),
        ("PostgreSQL", "database", 11),
        ("pgvector", "database", 6),
        ("EventBus", "service", 5),
        ("BudgetTracker", "service", 4),
        ("SourceConnector", "api", 7),
        ("LocalFilesConnector", "service", 5),
        ("WebConnector", "service", 4),
        ("EntityRepository", "service", 6),
        ("ProjectionRepository", "service", 8),
        ("EmbeddingService", "api", 5),
        ("Anthropic Claude", "api", 10),
        ("Knowledge Graph", "domain", 14),
        ("Entity Resolution", "process", 7),
        ("Convergence Detection", "process", 9),
        ("Gap Detection", "process", 6),
        ("Contradiction Detection", "process", 5),
        ("LLMClient", "api", 6),
        ("Observation", "schema", 8),
        ("Entity", "schema", 10),
        ("Relationship", "schema", 9),
        ("Engagement", "domain", 7),
        ("CoordinatorProjection", "schema", 6),
        ("TaskRecord", "schema", 5),
        ("Prompt Governance", "process", 4),
        ("Safety Architecture", "policy", 3),
        ("Multi-Agent Coordination", "domain", 8),
    ]

    entities = {}
    nodes = []
    for name, etype, obs_count in raw_entities:
        uid = uuid4()
        entities[str(uid)] = {
            "entity_id": str(uid),
            "name": name,
            "entity_type": etype,
            "aliases": [],
            "observation_count": obs_count,
            "properties": {},
        }
        nodes.append({
            "id": str(uid),
            "name": name,
            "type": etype,
            "observation_count": obs_count,
        })

    # Relationships
    name_to_id = {}
    for n in nodes:
        name_to_id[n["name"]] = n["id"]

    raw_rels = [
        ("Supervisor", "Coordinator", "contains", 0.95),
        ("Supervisor", "Worker", "dispatches", 0.90),
        ("Supervisor", "BudgetTracker", "contains", 0.85),
        ("Coordinator", "ProjectionRepository", "reads_from", 0.90),
        ("Coordinator", "Anthropic Claude", "calls", 0.95),
        ("Coordinator", "Knowledge Graph", "reads_from", 0.85),
        ("Coordinator", "Gap Detection", "implements", 0.80),
        ("Coordinator", "Contradiction Detection", "implements", 0.80),
        ("Coordinator", "Convergence Detection", "implements", 0.90),
        ("Worker", "SourceConnector", "calls", 0.90),
        ("Worker", "GraphWriter", "calls", 0.95),
        ("Worker", "Anthropic Claude", "calls", 0.95),
        ("Worker", "BudgetTracker", "reads_from", 0.75),
        ("GraphWriter", "EntityRepository", "calls", 0.90),
        ("GraphWriter", "Entity Resolution", "implements", 0.85),
        ("GraphWriter", "PostgreSQL", "writes_to", 0.95),
        ("GraphWriter", "EmbeddingService", "calls", 0.80),
        ("LocalFilesConnector", "SourceConnector", "implements", 0.95),
        ("WebConnector", "SourceConnector", "implements", 0.95),
        ("EntityRepository", "PostgreSQL", "reads_from", 0.95),
        ("ProjectionRepository", "PostgreSQL", "reads_from", 0.95),
        ("EmbeddingService", "pgvector", "calls", 0.80),
        ("pgvector", "PostgreSQL", "contains", 0.90),
        ("Knowledge Graph", "Entity", "contains", 0.95),
        ("Knowledge Graph", "Relationship", "contains", 0.95),
        ("Knowledge Graph", "Observation", "contains", 0.95),
        ("Engagement", "Knowledge Graph", "contains", 0.85),
        ("Engagement", "Supervisor", "contains", 0.85),
        ("Multi-Agent Coordination", "Coordinator", "governs", 0.80),
        ("Multi-Agent Coordination", "Worker", "governs", 0.80),
        ("Safety Architecture", "Worker", "governs", 0.75),
        ("Prompt Governance", "Anthropic Claude", "governs", 0.70),
        ("CoordinatorProjection", "Gap Detection", "contains", 0.85),
        ("CoordinatorProjection", "Contradiction Detection", "contains", 0.85),
        ("Convergence Detection", "Observation", "reads_from", 0.80),
    ]

    links = []
    rels_by_entity: dict[str, list] = {}
    for from_name, to_name, rtype, conf in raw_rels:
        src = name_to_id.get(from_name)
        tgt = name_to_id.get(to_name)
        if src and tgt:
            link = {
                "source": src,
                "target": tgt,
                "type": rtype,
                "confidence": conf,
                "from_name": from_name,
                "to_name": to_name,
            }
            links.append(link)
            rel = {
                "type": rtype,
                "confidence": conf,
                "from_name": from_name,
                "to_name": to_name,
                "from_id": src,
                "to_id": tgt,
            }
            rels_by_entity.setdefault(src, []).append(rel)
            rels_by_entity.setdefault(tgt, []).append(rel)

    # Observations by entity (sample)
    obs_by_entity: dict[str, list] = {}
    sample_obs = [
        ("Supervisor", "expansion", "entity",
         "Discovered Supervisor as the main async loop that manages agent lifecycles"),
        ("Supervisor", "reinforcement", "entity",
         "Confirmed Supervisor handles signal handling (SIGINT, SIGTERM) for graceful shutdown"),
        ("Coordinator", "expansion", "entity",
         "Coordinator is a stateless service that runs one LLM call per cycle"),
        ("Coordinator", "reinforcement", "relationship",
         "Confirmed Coordinator reads from ProjectionRepository to build bounded view"),
        ("Worker", "expansion", "entity",
         "Workers are stateless, disposable async functions with tool-use loops"),
        ("Worker", "reinforcement", "insight",
         "Worker prompt enforces 'write early, write often' rhythm to prevent knowledge loss"),
        ("Knowledge Graph", "expansion", "entity",
         "Knowledge Graph is PostgreSQL + pgvector storing entities, relationships, observations"),
        ("Convergence Detection", "expansion", "entity",
         "Convergence measured by ratio of reinforcement to expansion+challenge observations"),
        ("Convergence Detection", "reinforcement", "insight",
         "Threshold of 3.0 for 3 consecutive cycles triggers convergence signal"),
        ("Entity Resolution", "expansion", "entity",
         "Entity resolution uses local cache + DB lookup by name/alias + auto-create"),
        ("Safety Architecture", "expansion", "entity",
         "Four-layer safety model: read-only connectors, static validators, sandboxed execution, output validation"),
    ]

    for ename, impact, otype, text in sample_obs:
        eid = name_to_id.get(ename)
        if eid:
            obs_by_entity.setdefault(eid, []).append({
                "observation_id": str(uuid4()),
                "source_ref": "./docs/design/ALEC_v5_design.md",
                "raw_text": text,
                "observation_type": otype,
                "worker_id": "worker-a1b2c3d4",
                "impact_type": impact,
                "created_at": now.isoformat(),
            })

    # Convergence data (5 cycles, converging)
    convergence = [
        {"cycle": 1, "reinforcement": 2, "expansion": 18, "challenge": 1, "ratio": 0.10},
        {"cycle": 2, "reinforcement": 8, "expansion": 12, "challenge": 0, "ratio": 0.62},
        {"cycle": 3, "reinforcement": 15, "expansion": 6, "challenge": 1, "ratio": 1.88},
        {"cycle": 4, "reinforcement": 22, "expansion": 4, "challenge": 0, "ratio": 4.40},
        {"cycle": 5, "reinforcement": 19, "expansion": 2, "challenge": 0, "ratio": 6.33},
    ]

    # Tasks
    tasks = [
        {
            "task_id": str(uuid4()),
            "directive": "Survey the design directory for architecture entities and patterns",
            "source_type": "local_files",
            "source_ref": "./docs/design",
            "max_scope": "survey",
            "status": "completed",
            "worker_id": "worker-a1b2c3d4",
            "result": {"entities_written": 12, "relationships_written": 8, "observations_written": 20},
            "created_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
        {
            "task_id": str(uuid4()),
            "directive": "Deep dive into runtime architecture: Supervisor, Coordinator, Worker lifecycle",
            "source_type": "local_files",
            "source_ref": "./docs/design",
            "max_scope": "deep",
            "status": "completed",
            "worker_id": "worker-e5f6g7h8",
            "result": {"entities_written": 8, "relationships_written": 12, "observations_written": 18},
            "created_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
        {
            "task_id": str(uuid4()),
            "directive": "Investigate knowledge graph storage model and entity resolution mechanism",
            "source_type": "local_files",
            "source_ref": "./docs/design",
            "max_scope": "focused",
            "status": "completed",
            "worker_id": "worker-i9j0k1l2",
            "result": {"entities_written": 6, "relationships_written": 10, "observations_written": 15},
            "created_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
        {
            "task_id": str(uuid4()),
            "directive": "Explore convergence detection, gap analysis, and contradiction resolution",
            "source_type": "local_files",
            "source_ref": "./docs/design",
            "max_scope": "focused",
            "status": "completed",
            "worker_id": "worker-m3n4o5p6",
            "result": {"entities_written": 4, "relationships_written": 6, "observations_written": 12},
            "created_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
        {
            "task_id": str(uuid4()),
            "directive": "Confirm safety architecture and prompt governance patterns",
            "source_type": "local_files",
            "source_ref": "./docs/design",
            "max_scope": "survey",
            "status": "completed",
            "worker_id": "worker-q7r8s9t0",
            "result": {"entities_written": 2, "relationships_written": 4, "observations_written": 8},
            "created_at": now.isoformat(),
            "completed_at": now.isoformat(),
        },
    ]

    type_counts: dict[str, int] = {}
    for _, etype, _ in raw_entities:
        type_counts[etype] = type_counts.get(etype, 0) + 1

    return {
        "engagement": {
            "engagement_id": str(uuid4()),
            "name": "Discovery: ./docs/design",
            "problem_statement": (
                "Discover and map the architecture, components, data flows, and design "
                "patterns of the ALEC v5 system from its design documentation."
            ),
            "status": "converged",
            "created_at": now.isoformat(),
        },
        "stats": {
            "entity_count": len(raw_entities),
            "relationship_count": len(raw_rels),
            "observation_count": 73,
            "cycle_count": 5,
            "source_count": 1,
            "type_counts": type_counts,
            "impact_counts": {"reinforcement": 42, "expansion": 28, "challenge": 3},
            "converged": True,
        },
        "graph": {"nodes": nodes, "links": links},
        "entities": entities,
        "observations_by_entity": obs_by_entity,
        "relationships_by_entity": rels_by_entity,
        "convergence": convergence,
        "tasks": tasks,
        "sources": [
            {
                "source_type": "local_files",
                "config": {"path": "./docs/design"},
                "status": "verified",
            }
        ],
        "generated_at": now.isoformat(),
    }


def main() -> None:
    data = build_demo_data()
    data_json = json.dumps(data, cls=_UUIDEncoder)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")
    html = template.render(data=data, data_json=data_json)

    out = Path("alec-report-preview.html")
    out.write_text(html, encoding="utf-8")
    print(f"Preview report written to: {out.resolve()}")


if __name__ == "__main__":
    main()
