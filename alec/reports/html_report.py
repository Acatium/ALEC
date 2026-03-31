"""Post-run HTML report generator.

Queries the DB for an engagement's knowledge graph and renders
a self-contained interactive HTML report.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from jinja2 import Environment, FileSystemLoader

logger = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent / "templates"


class _UUIDEncoder(json.JSONEncoder):
    def default(self, o: object) -> Any:
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def _json(obj: Any) -> str:
    return json.dumps(obj, cls=_UUIDEncoder)


async def gather_report_data(pool: Any, engagement_id: UUID) -> dict[str, Any]:
    """Query all data needed for the report."""
    async with pool.acquire() as conn:
        # Engagement metadata
        eng = await conn.fetchrow(
            "SELECT name, problem_statement, status, created_at FROM engagements "
            "WHERE engagement_id = $1",
            engagement_id,
        )

        # Entities
        entities = await conn.fetch(
            "SELECT entity_id, name, entity_type, aliases, observation_count, "
            "status, properties, first_seen "
            "FROM entities WHERE engagement_id = $1 AND status = 'active' "
            "ORDER BY observation_count DESC",
            engagement_id,
        )

        # Relationships with entity names
        relationships = await conn.fetch(
            "SELECT r.relationship_id, r.relationship_type, r.confidence, "
            "e1.name AS from_name, e1.entity_type AS from_type, "
            "e2.name AS to_name, e2.entity_type AS to_type, "
            "r.from_entity, r.to_entity "
            "FROM relationships r "
            "JOIN entities e1 ON r.from_entity = e1.entity_id "
            "JOIN entities e2 ON r.to_entity = e2.entity_id "
            "WHERE r.engagement_id = $1 "
            "ORDER BY r.confidence DESC",
            engagement_id,
        )

        # Observations (most recent first, capped)
        observations = await conn.fetch(
            "SELECT observation_id, source_ref, raw_text, observation_type, "
            "worker_id, metadata, created_at "
            "FROM observations WHERE engagement_id = $1 "
            "ORDER BY created_at DESC LIMIT 500",
            engagement_id,
        )

        # Convergence log
        convergence = await conn.fetch(
            "SELECT cycle_number, reinforcement_count, expansion_count, "
            "challenge_count, ratio "
            "FROM convergence_log WHERE engagement_id = $1 "
            "ORDER BY cycle_number ASC",
            engagement_id,
        )

        # Tasks (directives)
        tasks = await conn.fetch(
            "SELECT task_id, directive, source_type, source_ref, max_scope, "
            "status, assigned_worker, result_summary, created_at, completed_at "
            "FROM tasks WHERE engagement_id = $1 "
            "ORDER BY created_at ASC",
            engagement_id,
        )

        # Source configs
        sources = await conn.fetch(
            "SELECT source_type, config, status FROM source_configs "
            "WHERE engagement_id = $1",
            engagement_id,
        )

    # Build entity lookup for observation linking
    entity_lookup: dict[str, dict[str, Any]] = {}
    for e in entities:
        entity_lookup[str(e["entity_id"])] = {
            "entity_id": str(e["entity_id"]),
            "name": e["name"],
            "entity_type": e["entity_type"],
            "aliases": list(e["aliases"]) if e["aliases"] else [],
            "observation_count": e["observation_count"],
            "properties": e["properties"] if isinstance(e["properties"], dict) else {},
        }

    # Build graph nodes and links for D3
    nodes = []
    node_ids = set()
    for e in entities:
        eid = str(e["entity_id"])
        nodes.append({
            "id": eid,
            "name": e["name"],
            "type": e["entity_type"],
            "observation_count": e["observation_count"],
        })
        node_ids.add(eid)

    links = []
    for r in relationships:
        src = str(r["from_entity"])
        tgt = str(r["to_entity"])
        if src in node_ids and tgt in node_ids:
            links.append({
                "source": src,
                "target": tgt,
                "type": r["relationship_type"],
                "confidence": float(r["confidence"]),
                "from_name": r["from_name"],
                "to_name": r["to_name"],
            })

    # Build observations by entity (for the detail panel)
    # Match observations to entities via metadata.entity_id or text mentions
    obs_by_entity: dict[str, list[dict[str, Any]]] = {}
    obs_list = []
    for o in observations:
        meta = o["metadata"] if isinstance(o["metadata"], dict) else {}
        obs_item = {
            "observation_id": str(o["observation_id"]),
            "source_ref": o["source_ref"],
            "raw_text": o["raw_text"][:500],
            "observation_type": o["observation_type"],
            "worker_id": o["worker_id"],
            "impact_type": meta.get("impact_type", "unknown"),
            "created_at": o["created_at"].isoformat() if o["created_at"] else "",
        }
        obs_list.append(obs_item)
        # Link to entity if metadata has entity_id
        obs_entity_id: str | None = meta.get("entity_id")
        if obs_entity_id:
            obs_by_entity.setdefault(str(obs_entity_id), []).append(obs_item)

    # Convergence data for chart
    conv_data = []
    for c in convergence:
        conv_data.append({
            "cycle": c["cycle_number"],
            "reinforcement": c["reinforcement_count"],
            "expansion": c["expansion_count"],
            "challenge": c["challenge_count"],
            "ratio": float(c["ratio"]) if c["ratio"] is not None else 0.0,
        })

    # Task timeline
    task_list = []
    for t in tasks:
        result = t["result_summary"] if isinstance(t["result_summary"], dict) else {}
        task_list.append({
            "task_id": str(t["task_id"]),
            "directive": t["directive"][:300],
            "source_type": t["source_type"],
            "source_ref": t["source_ref"],
            "max_scope": t["max_scope"],
            "status": t["status"],
            "worker_id": t["assigned_worker"],
            "result": result,
            "created_at": t["created_at"].isoformat() if t["created_at"] else "",
            "completed_at": t["completed_at"].isoformat() if t["completed_at"] else "",
        })

    source_list = []
    for s in sources:
        cfg = json.loads(s["config"]) if isinstance(s["config"], str) else (
            s["config"] if isinstance(s["config"], dict) else {}
        )
        source_list.append({
            "source_type": s["source_type"],
            "config": cfg,
            "status": s["status"],
        })

    # Relationships by entity for detail panel
    rels_by_entity: dict[str, list[dict[str, Any]]] = {}
    for r in relationships:
        src = str(r["from_entity"])
        tgt = str(r["to_entity"])
        rel_item = {
            "type": r["relationship_type"],
            "confidence": float(r["confidence"]),
            "from_name": r["from_name"],
            "to_name": r["to_name"],
            "from_id": src,
            "to_id": tgt,
        }
        rels_by_entity.setdefault(src, []).append(rel_item)
        rels_by_entity.setdefault(tgt, []).append(rel_item)

    # Entity type counts
    type_counts: dict[str, int] = {}
    for e in entities:
        t = e["entity_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # Impact type counts
    impact_counts: dict[str, int] = {"reinforcement": 0, "expansion": 0, "challenge": 0}
    for o in obs_list:
        it = o["impact_type"]
        if it in impact_counts:
            impact_counts[it] += 1

    return {
        "engagement": {
            "engagement_id": str(engagement_id),
            "name": eng["name"] if eng else "Unknown",
            "problem_statement": eng["problem_statement"] if eng else "",
            "status": eng["status"] if eng else "unknown",
            "created_at": eng["created_at"].isoformat() if eng and eng["created_at"] else "",
        },
        "stats": {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "observation_count": len(observations),
            "cycle_count": len(conv_data),
            "source_count": len(source_list),
            "type_counts": type_counts,
            "impact_counts": impact_counts,
            "converged": eng["status"] == "converged" if eng else False,
        },
        "graph": {"nodes": nodes, "links": links},
        "entities": entity_lookup,
        "observations_by_entity": obs_by_entity,
        "relationships_by_entity": rels_by_entity,
        "convergence": conv_data,
        "tasks": task_list,
        "sources": source_list,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def generate_report(
    pool: Any,
    engagement_id: UUID,
    output_path: str | None = None,
) -> str:
    """Generate HTML report and write to disk. Returns the file path."""
    data = await gather_report_data(pool, engagement_id)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
    )
    template = env.get_template("report.html")

    html = template.render(
        data=data,
        data_json=_json(data),
    )

    if output_path is None:
        output_path = f"alec-report-{engagement_id.hex[:12]}.html"

    Path(output_path).write_text(html, encoding="utf-8")
    logger.info("report.generated", path=output_path, entities=data["stats"]["entity_count"])
    return output_path
