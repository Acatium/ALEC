"""Tests for HTML report generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader

from alec.reports.html_report import _json, _UUIDEncoder

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "alec" / "reports" / "templates"


def _sample_data(
    entity_count: int = 3,
    rel_count: int = 2,
    cycles: int = 2,
) -> dict:
    """Build a realistic sample data dict for template rendering."""
    eid = uuid4()
    entities = {}
    nodes = []
    for i in range(entity_count):
        uid = uuid4()
        entities[str(uid)] = {
            "entity_id": str(uid),
            "name": f"Entity_{i}",
            "entity_type": "service" if i % 2 == 0 else "database",
            "aliases": [f"alias_{i}"] if i == 0 else [],
            "observation_count": 3 + i,
            "properties": {},
        }
        nodes.append({
            "id": str(uid),
            "name": f"Entity_{i}",
            "type": "service" if i % 2 == 0 else "database",
            "observation_count": 3 + i,
        })

    links = []
    node_ids = [n["id"] for n in nodes]
    for i in range(min(rel_count, entity_count - 1)):
        links.append({
            "source": node_ids[i],
            "target": node_ids[i + 1],
            "type": "depends_on",
            "confidence": 0.8,
            "from_name": f"Entity_{i}",
            "to_name": f"Entity_{i + 1}",
        })

    obs_by_entity = {}
    rels_by_entity = {}
    for i, nid in enumerate(node_ids):
        obs_by_entity[nid] = [{
            "observation_id": str(uuid4()),
            "source_ref": "./docs/design",
            "raw_text": f"Discovered entity {i} in design docs",
            "observation_type": "entity",
            "worker_id": "worker-abc",
            "impact_type": "expansion" if i == 0 else "reinforcement",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }]

    for link in links:
        rel = {
            "type": link["type"],
            "confidence": link["confidence"],
            "from_name": link["from_name"],
            "to_name": link["to_name"],
            "from_id": link["source"],
            "to_id": link["target"],
        }
        rels_by_entity.setdefault(link["source"], []).append(rel)
        rels_by_entity.setdefault(link["target"], []).append(rel)

    convergence = []
    for c in range(1, cycles + 1):
        convergence.append({
            "cycle": c,
            "reinforcement": c * 5,
            "expansion": max(1, 10 - c * 3),
            "challenge": 0,
            "ratio": (c * 5) / (max(1, 10 - c * 3) + 1),
        })

    tasks = [{
        "task_id": str(uuid4()),
        "directive": "Survey the design docs for architecture entities",
        "source_type": "local_files",
        "source_ref": "./docs/design",
        "max_scope": "survey",
        "status": "completed",
        "worker_id": "worker-abc",
        "result": {
            "entities_written": 3,
            "relationships_written": 2,
            "observations_written": 5,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }]

    return {
        "engagement": {
            "engagement_id": str(eid),
            "name": "Test Discovery",
            "problem_statement": "Discover architecture from design docs",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "stats": {
            "entity_count": entity_count,
            "relationship_count": rel_count,
            "observation_count": entity_count * 2,
            "cycle_count": cycles,
            "source_count": 1,
            "type_counts": {"service": 2, "database": 1},
            "impact_counts": {"reinforcement": 3, "expansion": 5, "challenge": 0},
            "converged": False,
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
            },
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def test_uuid_encoder():
    uid = UUID("12345678-1234-5678-1234-567812345678")
    result = json.dumps({"id": uid}, cls=_UUIDEncoder)
    assert "12345678-1234-5678-1234-567812345678" in result


def test_uuid_encoder_datetime():
    dt = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
    result = json.dumps({"ts": dt}, cls=_UUIDEncoder)
    assert "2026-02-20" in result


def test_json_helper():
    data = {"id": uuid4(), "ts": datetime.now(timezone.utc)}
    result = _json(data)
    parsed = json.loads(result)
    assert isinstance(parsed["id"], str)
    assert isinstance(parsed["ts"], str)


def test_template_renders_with_sample_data():
    data = _sample_data()
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")
    html = template.render(data=data, data_json=_json(data))

    assert "ALEC Discovery Report" in html
    assert "Knowledge Graph" in html
    assert "Convergence" in html
    assert "Entity Detail" in html
    assert "Exploration Timeline" in html
    assert "Test Discovery" in html


def test_template_contains_graph_data():
    data = _sample_data(entity_count=5, rel_count=4)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")
    html = template.render(data=data, data_json=_json(data))

    # The JSON data should be embedded in the HTML
    assert '"Entity_0"' in html
    assert '"Entity_4"' in html
    assert '"depends_on"' in html


def test_template_renders_empty_engagement():
    data = _sample_data(entity_count=0, rel_count=0, cycles=0)
    data["convergence"] = []
    data["tasks"] = []
    data["graph"] = {"nodes": [], "links": []}
    data["entities"] = {}
    data["stats"]["entity_count"] = 0
    data["stats"]["relationship_count"] = 0

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")
    html = template.render(data=data, data_json=_json(data))

    assert "ALEC Discovery Report" in html
    assert ">0<" in html  # zero stats rendered


def test_template_renders_converged():
    data = _sample_data(cycles=5)
    data["stats"]["converged"] = True
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")
    html = template.render(data=data, data_json=_json(data))

    assert "Converged" in html


def test_template_file_exists():
    assert (TEMPLATE_DIR / "report.html").is_file()
