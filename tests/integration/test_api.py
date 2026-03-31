"""Integration tests for the FastAPI API layer."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = pytest.mark.db

SKIP_DB = os.environ.get("SKIP_DB_TESTS", "").lower() in ("1", "true", "yes")


@pytest.fixture
def settings():
    from alec.config.settings import Settings

    return Settings(
        anthropic_api_key="",
        database_url=os.environ.get(
            "ALEC_DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec",
        ),
    )


@pytest_asyncio.fixture
async def client(settings, db_pool):
    """Async test client backed by real Postgres.

    We bypass FastAPI lifespan and inject app state directly.
    Tracks engagements created during the test and cleans them up on teardown.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from httpx import ASGITransport, AsyncClient

    from alec.api.routes.engagements import router as engagements_router
    from alec.api.routes.knowledge import router as knowledge_router
    from alec.api.routes.research import router as research_router
    from alec.events.bus import EventBus

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(engagements_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(research_router, prefix="/api")

    # Inject state directly (no lifespan needed)
    app.state.pool = db_pool
    app.state.settings = settings
    app.state.event_bus = EventBus()

    # Snapshot existing engagement IDs so we only clean up test-created ones
    async with db_pool.acquire() as conn:
        pre_existing = {
            r["engagement_id"]
            for r in await conn.fetch("SELECT engagement_id FROM engagements")
        }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Clean up only engagements created during this test
    from tests.conftest import _delete_engagement_data

    async with db_pool.acquire() as conn:
        all_rows = await conn.fetch("SELECT engagement_id FROM engagements")
    for row in all_rows:
        if row["engagement_id"] not in pre_existing:
            await _delete_engagement_data(db_pool, row["engagement_id"])


async def _create_engagement(client) -> str:
    """POST an engagement and return the engagement_id string."""
    resp = await client.post(
        "/api/engagements",
        json={"sources": ["./docs/design"], "max_cycles": 1},
    )
    assert resp.status_code == 200
    return resp.json()["engagement_id"]


async def _insert_entity(pool, eid: str, name: str, entity_type: str, obs_count: int = 1) -> str:
    """Insert an entity via direct SQL and return its entity_id string."""
    async with pool.acquire() as conn:
        entity_id = await conn.fetchval(
            """
            INSERT INTO entities (engagement_id, name, entity_type, observation_count, status)
            VALUES ($1::uuid, $2, $3, $4, 'active')
            RETURNING entity_id
            """,
            eid,
            name,
            entity_type,
            obs_count,
        )
    return str(entity_id)


async def _insert_relationship(
    pool,
    eid: str,
    from_entity: str,
    to_entity: str,
    rel_type: str,
    confidence: float = 0.8,
    evidence: list[str] | None = None,
) -> str:
    """Insert a relationship via direct SQL and return its relationship_id string."""
    ev = evidence or []
    async with pool.acquire() as conn:
        rel_id = await conn.fetchval(
            """
            INSERT INTO relationships
                (engagement_id, from_entity, to_entity, relationship_type, confidence, evidence)
            VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6::uuid[])
            RETURNING relationship_id
            """,
            eid,
            from_entity,
            to_entity,
            rel_type,
            confidence,
            ev,
        )
    return str(rel_id)


# ── Existing engagement + knowledge tests ────────────────────────


@pytest.mark.asyncio
async def test_list_engagements(client):
    resp = await client.get("/api/engagements")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_engagement(client):
    resp = await client.post(
        "/api/engagements",
        json={"sources": ["./docs/design"], "max_cycles": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert "engagement_id" in data


@pytest.mark.asyncio
async def test_get_engagement(client):
    # Create first
    create_resp = await client.post(
        "/api/engagements",
        json={"sources": ["./docs/design"], "max_cycles": 1},
    )
    eid = create_resp.json()["engagement_id"]

    # Get detail
    resp = await client.get(f"/api/engagements/{eid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["engagement_id"] == eid
    assert data["entity_count"] == 0


@pytest.mark.asyncio
async def test_get_engagement_not_found(client):
    fake_id = str(uuid4())
    resp = await client.get(f"/api/engagements/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_entities_empty(client):
    create_resp = await client.post(
        "/api/engagements",
        json={"sources": ["./test"], "max_cycles": 1},
    )
    eid = create_resp.json()["engagement_id"]

    resp = await client.get(f"/api/engagements/{eid}/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_relationships_empty(client):
    create_resp = await client.post(
        "/api/engagements",
        json={"sources": ["./test"], "max_cycles": 1},
    )
    eid = create_resp.json()["engagement_id"]

    resp = await client.get(f"/api/engagements/{eid}/relationships")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_observations_empty(client):
    create_resp = await client.post(
        "/api/engagements",
        json={"sources": ["./test"], "max_cycles": 1},
    )
    eid = create_resp.json()["engagement_id"]

    resp = await client.get(f"/api/engagements/{eid}/observations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_graph_empty(client):
    create_resp = await client.post(
        "/api/engagements",
        json={"sources": ["./test"], "max_cycles": 1},
    )
    eid = create_resp.json()["engagement_id"]

    resp = await client.get(f"/api/engagements/{eid}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == []
    assert data["edges"] == []


# ── Source management tests (P2.3) ──────────────────────────────


@pytest.mark.asyncio
async def test_list_sources_empty(client):
    eid = await _create_engagement(client)
    resp = await client.get(f"/api/engagements/{eid}/sources")
    assert resp.status_code == 200
    # engagements.py creates source_configs on create, so filter to only ones
    # we explicitly add via the research router — or just check it's a list
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_add_source_local(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "local_files"
    assert data["status"] == "verified"
    assert data["priority"] == 50
    assert data["trust_tier"] == "reference"
    assert "source_config_id" in data


@pytest.mark.asyncio
async def test_add_source_web(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "web:https://example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "web"


@pytest.mark.asyncio
async def test_update_source_priority(client):
    eid = await _create_engagement(client)
    add_resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    sid = add_resp.json()["source_config_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/sources/{sid}",
        json={"priority": 80},
    )
    assert resp.status_code == 200
    assert resp.json()["priority"] == 80


@pytest.mark.asyncio
async def test_update_source_trust_tier(client):
    eid = await _create_engagement(client)
    add_resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    sid = add_resp.json()["source_config_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/sources/{sid}",
        json={"trust_tier": "authoritative"},
    )
    assert resp.status_code == 200
    assert resp.json()["trust_tier"] == "authoritative"


@pytest.mark.asyncio
async def test_update_source_invalid_trust_tier(client):
    eid = await _create_engagement(client)
    add_resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    sid = add_resp.json()["source_config_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/sources/{sid}",
        json={"trust_tier": "bogus"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_source_no_fields(client):
    eid = await _create_engagement(client)
    add_resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    sid = add_resp.json()["source_config_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/sources/{sid}",
        json={},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_source_not_found(client):
    eid = await _create_engagement(client)
    fake_sid = str(uuid4())
    resp = await client.patch(
        f"/api/engagements/{eid}/sources/{fake_sid}",
        json={"priority": 90},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source(client):
    eid = await _create_engagement(client)
    add_resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={"source": "./docs"},
    )
    sid = add_resp.json()["source_config_id"]

    del_resp = await client.delete(f"/api/engagements/{eid}/sources/{sid}")
    assert del_resp.status_code == 204

    # Verify it no longer appears when we list sources
    list_resp = await client.get(f"/api/engagements/{eid}/sources")
    source_ids = [s["source_config_id"] for s in list_resp.json()]
    assert sid not in source_ids


@pytest.mark.asyncio
async def test_delete_source_not_found(client):
    eid = await _create_engagement(client)
    fake_sid = str(uuid4())
    resp = await client.delete(f"/api/engagements/{eid}/sources/{fake_sid}")
    assert resp.status_code == 404


# ── Annotation tests (P2.2a) ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_annotation(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "TestEntity", "service")

    resp = await client.post(
        f"/api/engagements/{eid}/annotations",
        json={
            "entity_id": entity_id,
            "annotation_type": "important",
            "content": "This is critical",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["annotation_type"] == "important"
    assert data["content"] == "This is critical"
    assert "annotation_id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_annotations(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "TestEntity", "service")

    await client.post(
        f"/api/engagements/{eid}/annotations",
        json={
            "entity_id": entity_id,
            "annotation_type": "note",
            "content": "A note",
        },
    )

    resp = await client.get(f"/api/engagements/{eid}/annotations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["annotation_type"] == "note"


@pytest.mark.asyncio
async def test_delete_annotation(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "TestEntity", "service")

    create_resp = await client.post(
        f"/api/engagements/{eid}/annotations",
        json={
            "entity_id": entity_id,
            "annotation_type": "dismiss",
            "content": "",
        },
    )
    aid = create_resp.json()["annotation_id"]

    del_resp = await client.delete(f"/api/engagements/{eid}/annotations/{aid}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/engagements/{eid}/annotations")
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_annotation_not_found(client):
    eid = await _create_engagement(client)
    fake_aid = str(uuid4())
    resp = await client.delete(f"/api/engagements/{eid}/annotations/{fake_aid}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_annotation_invalid_type(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "TestEntity", "service")

    resp = await client.post(
        f"/api/engagements/{eid}/annotations",
        json={
            "entity_id": entity_id,
            "annotation_type": "bogus",
            "content": "",
        },
    )
    assert resp.status_code == 400


# ── Question tests (P2.2b) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_question(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "What is the deployment model?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "open"
    assert data["answer"] is None
    assert data["question_text"] == "What is the deployment model?"
    assert "question_id" in data


@pytest.mark.asyncio
async def test_list_questions_empty(client):
    eid = await _create_engagement(client)
    resp = await client.get(f"/api/engagements/{eid}/questions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_questions_open_first(client):
    eid = await _create_engagement(client)

    # Create two questions
    r1 = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "First question"},
    )
    _r2 = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "Second question"},
    )
    qid1 = r1.json()["question_id"]

    # Answer the first one
    await client.patch(
        f"/api/engagements/{eid}/questions/{qid1}",
        json={"status": "answered", "answer": "Done"},
    )

    # List — open question should come first
    resp = await client.get(f"/api/engagements/{eid}/questions")
    data = resp.json()
    assert len(data) == 2
    assert data[0]["status"] == "open"
    assert data[1]["status"] == "answered"


@pytest.mark.asyncio
async def test_update_question_answer(client):
    eid = await _create_engagement(client)
    create_resp = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "How does auth work?"},
    )
    qid = create_resp.json()["question_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/questions/{qid}",
        json={"status": "answered", "answer": "Via JWT tokens"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "answered"
    assert data["answer"] == "Via JWT tokens"
    assert data["answered_at"] is not None


@pytest.mark.asyncio
async def test_update_question_not_found(client):
    eid = await _create_engagement(client)
    fake_qid = str(uuid4())
    resp = await client.patch(
        f"/api/engagements/{eid}/questions/{fake_qid}",
        json={"status": "answered", "answer": "N/A"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_question(client):
    eid = await _create_engagement(client)
    create_resp = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "Temp question"},
    )
    qid = create_resp.json()["question_id"]

    del_resp = await client.delete(f"/api/engagements/{eid}/questions/{qid}")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_question_not_found(client):
    eid = await _create_engagement(client)
    fake_qid = str(uuid4())
    resp = await client.delete(f"/api/engagements/{eid}/questions/{fake_qid}")
    assert resp.status_code == 404


# ── Directive tests (P2.2c) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_create_directive(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/directives",
        json={"directive": "Investigate the auth module in depth"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["max_scope"] == "focused"
    assert data["directive"] == "Investigate the auth module in depth"
    assert "task_id" in data


@pytest.mark.asyncio
async def test_create_directive_with_source_ref(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/directives",
        json={
            "directive": "Check this source",
            "source_ref": "./docs/design",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "local_files"


# ── Entity corrections + merge tests (P2.1) ─────────────────────


@pytest.mark.asyncio
async def test_update_entity_rename(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "OldName", "service")

    resp = await client.patch(
        f"/api/engagements/{eid}/entities/{entity_id}",
        json={"name": "NewName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"

    # Verify correction observation was created
    async with db_pool.acquire() as conn:
        obs = await conn.fetch(
            """
            SELECT raw_text FROM observations
            WHERE engagement_id = $1::uuid AND observation_type = 'correction'
            """,
            eid,
        )
    assert len(obs) == 1
    assert "OldName" in obs[0]["raw_text"]
    assert "NewName" in obs[0]["raw_text"]


@pytest.mark.asyncio
async def test_update_entity_not_found(client):
    eid = await _create_engagement(client)
    fake_entity_id = str(uuid4())
    resp = await client.patch(
        f"/api/engagements/{eid}/entities/{fake_entity_id}",
        json={"name": "Whatever"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_entity_no_fields(client, db_pool):
    eid = await _create_engagement(client)
    entity_id = await _insert_entity(db_pool, eid, "SomeEntity", "service")

    resp = await client.patch(
        f"/api/engagements/{eid}/entities/{entity_id}",
        json={},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_entity(client, db_pool):
    eid = await _create_engagement(client)
    # Create entities A, B, C
    a_id = await _insert_entity(db_pool, eid, "EntityA", "service", obs_count=3)
    b_id = await _insert_entity(db_pool, eid, "EntityB", "service", obs_count=2)
    c_id = await _insert_entity(db_pool, eid, "EntityC", "database", obs_count=1)

    # Create relationship B→C
    await _insert_relationship(db_pool, eid, b_id, c_id, "reads_from")

    # Create annotation on B
    await client.post(
        f"/api/engagements/{eid}/annotations",
        json={
            "entity_id": b_id,
            "annotation_type": "important",
            "content": "B is important",
        },
    )

    # Merge B into A
    resp = await client.post(
        f"/api/engagements/{eid}/entities/{a_id}/merge",
        json={"source_entity_id": b_id},
    )
    assert resp.status_code == 200
    data = resp.json()

    # A's observation_count should sum: 3 + 2 = 5
    assert data["observation_count"] == 5

    # B should be deleted (knowledge endpoint returns 404)
    b_resp = await client.get(f"/api/engagements/{eid}/entities/{b_id}")
    assert b_resp.status_code == 404

    # Relationship should be reassigned to A→C
    async with db_pool.acquire() as conn:
        rels = await conn.fetch(
            "SELECT from_entity, to_entity, relationship_type FROM relationships "
            "WHERE engagement_id = $1::uuid",
            eid,
        )
    assert len(rels) == 1
    assert str(rels[0]["from_entity"]) == a_id
    assert str(rels[0]["to_entity"]) == c_id

    # Annotation should be reassigned to A
    ann_resp = await client.get(f"/api/engagements/{eid}/annotations")
    annotations = ann_resp.json()
    assert len(annotations) == 1
    assert annotations[0]["entity_id"] == a_id

    # B's name should be in A's aliases
    async with db_pool.acquire() as conn:
        aliases = await conn.fetchval(
            "SELECT aliases FROM entities WHERE entity_id = $1::uuid",
            a_id,
        )
    assert "EntityB" in (aliases or [])


@pytest.mark.asyncio
async def test_merge_entity_self(client, db_pool):
    eid = await _create_engagement(client)
    a_id = await _insert_entity(db_pool, eid, "EntityA", "service")

    resp = await client.post(
        f"/api/engagements/{eid}/entities/{a_id}/merge",
        json={"source_entity_id": a_id},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_merge_entity_target_not_found(client, db_pool):
    eid = await _create_engagement(client)
    b_id = await _insert_entity(db_pool, eid, "EntityB", "service")
    fake_target = str(uuid4())

    resp = await client.post(
        f"/api/engagements/{eid}/entities/{fake_target}/merge",
        json={"source_entity_id": b_id},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_entity_source_not_found(client, db_pool):
    eid = await _create_engagement(client)
    a_id = await _insert_entity(db_pool, eid, "EntityA", "service")
    fake_source = str(uuid4())

    resp = await client.post(
        f"/api/engagements/{eid}/entities/{a_id}/merge",
        json={"source_entity_id": fake_source},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_merge_entity_dedup_relationships(client, db_pool):
    eid = await _create_engagement(client)
    a_id = await _insert_entity(db_pool, eid, "EntityA", "service")
    b_id = await _insert_entity(db_pool, eid, "EntityB", "service")
    c_id = await _insert_entity(db_pool, eid, "EntityC", "database")

    # Create observations to use as evidence UUIDs
    async with db_pool.acquire() as conn:
        obs_a = await conn.fetchval(
            """
            INSERT INTO observations (engagement_id, source_ref, raw_text, observation_type)
            VALUES ($1::uuid, 'src-a', 'A reads C', 'relationship')
            RETURNING observation_id
            """,
            eid,
        )
        obs_b = await conn.fetchval(
            """
            INSERT INTO observations (engagement_id, source_ref, raw_text, observation_type)
            VALUES ($1::uuid, 'src-b', 'B reads C', 'relationship')
            RETURNING observation_id
            """,
            eid,
        )

    # Both A and B have "reads_from" relationship to C, with different
    # evidence and confidence
    await _insert_relationship(
        db_pool, eid, a_id, c_id, "reads_from",
        confidence=0.6, evidence=[str(obs_a)],
    )
    await _insert_relationship(
        db_pool, eid, b_id, c_id, "reads_from",
        confidence=0.9, evidence=[str(obs_b)],
    )

    # Merge B into A — should deduplicate and merge evidence + confidence
    resp = await client.post(
        f"/api/engagements/{eid}/entities/{a_id}/merge",
        json={"source_entity_id": b_id},
    )
    assert resp.status_code == 200

    async with db_pool.acquire() as conn:
        rels = await conn.fetch(
            "SELECT from_entity, to_entity, relationship_type, confidence, evidence "
            "FROM relationships "
            "WHERE engagement_id = $1::uuid AND relationship_type = 'reads_from'",
            eid,
        )
    # Only one reads_from relationship to C should remain
    assert len(rels) == 1
    assert str(rels[0]["from_entity"]) == a_id
    assert str(rels[0]["to_entity"]) == c_id
    # Confidence should be the max of 0.6 and 0.9
    assert rels[0]["confidence"] == 0.9
    # Evidence should contain both observation UUIDs
    assert len(rels[0]["evidence"]) == 2
    assert obs_a in rels[0]["evidence"]
    assert obs_b in rels[0]["evidence"]


# ── Snapshot + report tests (P2.4) ──────────────────────────────


@pytest.mark.asyncio
async def test_create_snapshot(client, db_pool):
    eid = await _create_engagement(client)
    # Insert 3 entities via SQL
    await _insert_entity(db_pool, eid, "E1", "service")
    await _insert_entity(db_pool, eid, "E2", "database")
    await _insert_entity(db_pool, eid, "E3", "api")

    resp = await client.post(
        f"/api/engagements/{eid}/snapshots",
        json={"name": "Checkpoint 1", "description": "First snapshot"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_count"] == 3
    assert data["name"] == "Checkpoint 1"
    assert "snapshot_id" in data


@pytest.mark.asyncio
async def test_list_snapshots_empty(client):
    eid = await _create_engagement(client)
    resp = await client.get(f"/api/engagements/{eid}/snapshots")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_snapshots_ordering(client, db_pool):
    eid = await _create_engagement(client)

    await client.post(
        f"/api/engagements/{eid}/snapshots",
        json={"name": "First"},
    )
    await client.post(
        f"/api/engagements/{eid}/snapshots",
        json={"name": "Second"},
    )

    resp = await client.get(f"/api/engagements/{eid}/snapshots")
    data = resp.json()
    assert len(data) == 2
    # Newest first (ORDER BY created_at DESC)
    assert data[0]["name"] == "Second"
    assert data[1]["name"] == "First"


@pytest.mark.asyncio
async def test_get_report(client):
    eid = await _create_engagement(client)
    resp = await client.get(f"/api/engagements/{eid}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "markdown" in data
    assert "Summary" in data["markdown"]


@pytest.mark.asyncio
async def test_get_report_not_found(client):
    fake_eid = str(uuid4())
    resp = await client.get(f"/api/engagements/{fake_eid}/report")
    assert resp.status_code == 404


# ── Negative path tests (P2.5) ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_engagement_missing_sources(client):
    resp = await client.post("/api/engagements", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_annotation_missing_entity_id(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/annotations",
        json={"annotation_type": "important"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_question_missing_text(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/questions",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_source_missing_field(client):
    eid = await _create_engagement(client)
    resp = await client.post(
        f"/api/engagements/{eid}/sources",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_question_no_fields(client):
    eid = await _create_engagement(client)
    create_resp = await client.post(
        f"/api/engagements/{eid}/questions",
        json={"question_text": "Temp"},
    )
    qid = create_resp.json()["question_id"]

    resp = await client.patch(
        f"/api/engagements/{eid}/questions/{qid}",
        json={},
    )
    assert resp.status_code == 400
