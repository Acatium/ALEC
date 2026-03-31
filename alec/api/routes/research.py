"""Research workspace routes — source management, annotations, questions, snapshots, reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from alec.api.dependencies import get_pool, get_settings
from alec.api.schemas import (
    AnnotationCreate,
    AnnotationResponse,
    ApplyTemplateRequest,
    DirectiveCreate,
    EngagementResponse,
    EngagementUpdate,
    EntityMergeRequest,
    EntityResponse,
    EntityUpdate,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
    ReportResponse,
    SchemaEntryCreate,
    SchemaEntryResponse,
    SchemaProposalResponse,
    SnapshotCreate,
    SnapshotResponse,
    SourceAdd,
    SourceConfigResponse,
    SourceUpdate,
    TaskResponse,
    TemplateResponse,
)
from alec.config.settings import Settings
from alec.connectors.source_config import parse_source_spec
from alec.knowledge.templates import get_template, list_templates, populate_schema

logger = structlog.get_logger()
router = APIRouter()


def _parse_config(raw: Any) -> dict[str, object]:
    if isinstance(raw, str):
        result: dict[str, object] = json.loads(raw)
        return result
    return dict(raw) if raw else {}


# ── Engagement editing ──────────────────────────────────────────


@router.patch("/engagements/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(
    engagement_id: str,
    body: EngagementUpdate,
    pool: Any = Depends(get_pool),
) -> EngagementResponse:
    """Update engagement name and/or problem_statement."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM engagements WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Engagement not found")

        sets: list[str] = []
        vals: list[Any] = []
        idx = 2
        if body.name is not None:
            sets.append(f"name = ${idx}")
            vals.append(body.name)
            idx += 1
        if body.problem_statement is not None:
            sets.append(f"problem_statement = ${idx}")
            vals.append(body.problem_statement)
            idx += 1
        if body.summary is not None:
            sets.append(f"summary = ${idx}")
            vals.append(body.summary)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No fields to update")

        sets.append(f"updated_at = ${idx}")
        vals.append(datetime.now(timezone.utc))

        await conn.execute(
            f"UPDATE engagements SET {', '.join(sets)} WHERE engagement_id = $1::uuid",  # noqa: S608
            engagement_id,
            *vals,
        )

        updated = await conn.fetchrow(
            "SELECT * FROM engagements WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        entity_count = await conn.fetchval(
            "SELECT COUNT(*) FROM entities WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        rel_count = await conn.fetchval(
            "SELECT COUNT(*) FROM relationships WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        obs_count = await conn.fetchval(
            "SELECT COUNT(*) FROM observations WHERE engagement_id = $1::uuid",
            engagement_id,
        )

    config = _parse_config(updated.get("config"))
    return EngagementResponse(
        engagement_id=str(updated["engagement_id"]),
        name=updated["name"],
        status=updated["status"],
        entity_count=entity_count,
        relationship_count=rel_count,
        observation_count=obs_count,
        problem_statement=updated.get("problem_statement") or "",
        summary=updated.get("summary") or "",
        config=config,
        created_at=updated["created_at"].isoformat() if updated.get("created_at") else None,
        updated_at=updated["updated_at"].isoformat() if updated.get("updated_at") else None,
    )


# ── Source management ───────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/sources",
    response_model=list[SourceConfigResponse],
)
async def list_sources(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[SourceConfigResponse]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT source_id, source_type, config, status, priority, trust_tier
            FROM source_configs
            WHERE engagement_id = $1::uuid
            ORDER BY priority DESC, created_at ASC
            """,
            engagement_id,
        )
    return [
        SourceConfigResponse(
            source_config_id=str(r["source_id"]),
            source_type=r["source_type"],
            config=_parse_config(r["config"]),
            status=r["status"],
            priority=r["priority"],
            trust_tier=r["trust_tier"],
        )
        for r in rows
    ]


@router.post(
    "/engagements/{engagement_id}/sources",
    response_model=SourceConfigResponse,
)
async def add_source(
    engagement_id: str,
    body: SourceAdd,
    pool: Any = Depends(get_pool),
) -> SourceConfigResponse:
    spec = parse_source_spec(body.source)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO source_configs
                (engagement_id, source_type, config, status, priority, trust_tier)
            VALUES ($1::uuid, $2, $3::jsonb, 'verified', 50, 'reference')
            RETURNING source_id, source_type, config, status, priority, trust_tier
            """,
            engagement_id,
            spec.source_type,
            json.dumps(spec.config),
        )
    return SourceConfigResponse(
        source_config_id=str(row["source_id"]),
        source_type=row["source_type"],
        config=_parse_config(row["config"]),
        status=row["status"],
        priority=row["priority"],
        trust_tier=row["trust_tier"],
    )


@router.patch(
    "/engagements/{engagement_id}/sources/{source_config_id}",
    response_model=SourceConfigResponse,
)
async def update_source(
    engagement_id: str,
    source_config_id: str,
    body: SourceUpdate,
    pool: Any = Depends(get_pool),
) -> SourceConfigResponse:
    valid_tiers = ("authoritative", "analytical", "reference")
    if body.trust_tier is not None and body.trust_tier not in valid_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"trust_tier must be one of {valid_tiers}",
        )

    async with pool.acquire() as conn:
        sets: list[str] = []
        vals: list[Any] = []
        idx = 3
        if body.status is not None:
            sets.append(f"status = ${idx}")
            vals.append(body.status)
            idx += 1
        if body.priority is not None:
            sets.append(f"priority = ${idx}")
            vals.append(body.priority)
            idx += 1
        if body.trust_tier is not None:
            sets.append(f"trust_tier = ${idx}")
            vals.append(body.trust_tier)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No fields to update")

        row = await conn.fetchrow(
            f"UPDATE source_configs SET {', '.join(sets)} "  # noqa: S608
            f"WHERE source_id = $1::uuid AND engagement_id = $2::uuid "
            f"RETURNING source_id, source_type, config, status, priority, trust_tier",
            source_config_id,
            engagement_id,
            *vals,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Source config not found")

    return SourceConfigResponse(
        source_config_id=str(row["source_id"]),
        source_type=row["source_type"],
        config=_parse_config(row["config"]),
        status=row["status"],
        priority=row["priority"],
        trust_tier=row["trust_tier"],
    )


@router.delete(
    "/engagements/{engagement_id}/sources/{source_config_id}",
    status_code=204,
)
async def delete_source(
    engagement_id: str,
    source_config_id: str,
    pool: Any = Depends(get_pool),
) -> None:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM source_configs "
            "WHERE source_id = $1::uuid AND engagement_id = $2::uuid",
            source_config_id,
            engagement_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Source config not found")


# ── Annotations ─────────────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/annotations",
    response_model=list[AnnotationResponse],
)
async def list_annotations(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[AnnotationResponse]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT annotation_id, entity_id, annotation_type, content, created_at
            FROM user_annotations
            WHERE engagement_id = $1::uuid
            ORDER BY created_at DESC
            """,
            engagement_id,
        )
    return [
        AnnotationResponse(
            annotation_id=str(r["annotation_id"]),
            entity_id=str(r["entity_id"]),
            annotation_type=r["annotation_type"],
            content=r["content"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post(
    "/engagements/{engagement_id}/annotations",
    response_model=AnnotationResponse,
)
async def create_annotation(
    engagement_id: str,
    body: AnnotationCreate,
    pool: Any = Depends(get_pool),
) -> AnnotationResponse:
    valid_types = ("correction", "important", "explore_more", "note", "dismiss")
    if body.annotation_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"annotation_type must be one of {valid_types}",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO user_annotations
                (engagement_id, entity_id, annotation_type, content)
            VALUES ($1::uuid, $2::uuid, $3, $4)
            RETURNING annotation_id, entity_id, annotation_type, content, created_at
            """,
            engagement_id,
            body.entity_id,
            body.annotation_type,
            body.content,
        )
    return AnnotationResponse(
        annotation_id=str(row["annotation_id"]),
        entity_id=str(row["entity_id"]),
        annotation_type=row["annotation_type"],
        content=row["content"],
        created_at=row["created_at"].isoformat(),
    )


@router.delete(
    "/engagements/{engagement_id}/annotations/{annotation_id}",
    status_code=204,
)
async def delete_annotation(
    engagement_id: str,
    annotation_id: str,
    pool: Any = Depends(get_pool),
) -> None:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_annotations "
            "WHERE annotation_id = $1::uuid AND engagement_id = $2::uuid",
            annotation_id,
            engagement_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Annotation not found")


# ── Entity corrections ──────────────────────────────────────────


@router.patch(
    "/engagements/{engagement_id}/entities/{entity_id}",
    response_model=EntityResponse,
)
async def update_entity(
    engagement_id: str,
    entity_id: str,
    body: EntityUpdate,
    pool: Any = Depends(get_pool),
) -> EntityResponse:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM entities WHERE entity_id = $1::uuid AND engagement_id = $2::uuid",
            entity_id,
            engagement_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Entity not found")

        sets: list[str] = []
        vals: list[Any] = []
        idx = 3
        if body.name is not None:
            sets.append(f"name = ${idx}")
            vals.append(body.name)
            idx += 1
        if body.entity_type is not None:
            sets.append(f"entity_type = ${idx}")
            vals.append(body.entity_type)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No fields to update")

        sets.append(f"last_referenced = ${idx}")
        vals.append(datetime.now(timezone.utc))

        updated = await conn.fetchrow(
            f"UPDATE entities SET {', '.join(sets)} "  # noqa: S608
            f"WHERE entity_id = $1::uuid AND engagement_id = $2::uuid "
            f"RETURNING entity_id, name, entity_type, observation_count, properties",
            entity_id,
            engagement_id,
            *vals,
        )

        # Track correction as an observation
        changes = []
        if body.name is not None:
            changes.append(f"renamed from '{row['name']}' to '{body.name}'")
        if body.entity_type is not None:
            changes.append(f"reclassified from '{row['entity_type']}' to '{body.entity_type}'")
        await conn.execute(
            """
            INSERT INTO observations
                (engagement_id, source_ref, raw_text, observation_type, metadata)
            VALUES ($1::uuid, 'user_correction', $2, 'correction', $3::jsonb)
            """,
            engagement_id,
            f"Entity '{row['name']}': {', '.join(changes)}",
            json.dumps({"entity_id": entity_id}),
        )

    props = updated["properties"]
    properties = json.loads(props) if isinstance(props, str) else (props or {})
    return EntityResponse(
        entity_id=str(updated["entity_id"]),
        name=updated["name"],
        entity_type=updated["entity_type"],
        observation_count=updated["observation_count"],
        properties=properties,
    )


@router.post(
    "/engagements/{engagement_id}/entities/{entity_id}/merge",
    response_model=EntityResponse,
)
async def merge_entity(
    engagement_id: str,
    entity_id: str,
    body: EntityMergeRequest,
    pool: Any = Depends(get_pool),
) -> EntityResponse:
    """Merge source_entity INTO target entity (entity_id). Source is deleted."""
    from alec.knowledge.merge import merge_entities

    target_id = entity_id
    source_id = body.source_entity_id

    if target_id == source_id:
        raise HTTPException(status_code=400, detail="Cannot merge entity into itself")

    async with pool.acquire() as conn:
        # Validate both entities exist before merge
        target = await conn.fetchrow(
            "SELECT entity_id FROM entities"
            " WHERE entity_id = $1::uuid"
            " AND engagement_id = $2::uuid",
            target_id, engagement_id,
        )
        source = await conn.fetchrow(
            "SELECT entity_id FROM entities"
            " WHERE entity_id = $1::uuid"
            " AND engagement_id = $2::uuid",
            source_id, engagement_id,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="Target entity not found")
        if source is None:
            raise HTTPException(status_code=404, detail="Source entity not found")

        async with conn.transaction():
            updated = await merge_entities(conn, engagement_id, target_id, source_id)

    props: Any = updated["properties"]
    properties: dict[str, object] = (
        json.loads(props) if isinstance(props, str) else (props or {})
    )
    obs_count: Any = updated["observation_count"]
    return EntityResponse(
        entity_id=str(updated["entity_id"]),
        name=str(updated["name"]),
        entity_type=str(updated["entity_type"]),
        observation_count=int(obs_count),
        properties=properties,
    )


# ── Manual directives ───────────────────────────────────────────


@router.post(
    "/engagements/{engagement_id}/directives",
    response_model=TaskResponse,
)
async def create_directive(
    engagement_id: str,
    body: DirectiveCreate,
    pool: Any = Depends(get_pool),
) -> TaskResponse:
    source_type = "unknown"
    source_ref = body.source_ref or ""

    if body.source_ref:
        try:
            spec = parse_source_spec(body.source_ref)
            source_type = spec.source_type
            source_ref = next(iter(spec.config.values()), body.source_ref)
        except Exception:
            source_ref = body.source_ref

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tasks
                (engagement_id, directive, source_type, source_ref, max_scope, is_manual, status)
            VALUES ($1::uuid, $2, $3, $4, $5, TRUE, 'queued')
            RETURNING task_id, directive, source_type, source_ref, max_scope, status,
                      assigned_worker, result_summary, created_at, started_at, completed_at
            """,
            engagement_id,
            body.directive,
            source_type,
            source_ref,
            body.max_scope,
        )
    return TaskResponse(
        task_id=str(row["task_id"]),
        directive=row["directive"],
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        max_scope=row["max_scope"],
        status=row["status"],
        assigned_worker=row["assigned_worker"],
        result_summary=None,
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        started_at=None,
        completed_at=None,
    )


# ── Questions ───────────────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/questions",
    response_model=list[QuestionResponse],
)
async def list_questions(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[QuestionResponse]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT question_id, question_text, status, answer, created_at, answered_at
            FROM questions
            WHERE engagement_id = $1::uuid
            ORDER BY
                CASE WHEN status = 'open' THEN 0
                     WHEN status = 'answered' THEN 1
                     ELSE 2 END,
                created_at DESC
            """,
            engagement_id,
        )
    return [
        QuestionResponse(
            question_id=str(r["question_id"]),
            question_text=r["question_text"],
            status=r["status"],
            answer=r["answer"],
            created_at=r["created_at"].isoformat(),
            answered_at=r["answered_at"].isoformat() if r["answered_at"] else None,
        )
        for r in rows
    ]


@router.post(
    "/engagements/{engagement_id}/questions",
    response_model=QuestionResponse,
)
async def create_question(
    engagement_id: str,
    body: QuestionCreate,
    pool: Any = Depends(get_pool),
) -> QuestionResponse:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO questions (engagement_id, question_text)
            VALUES ($1::uuid, $2)
            RETURNING question_id, question_text, status, answer, created_at, answered_at
            """,
            engagement_id,
            body.question_text,
        )
    return QuestionResponse(
        question_id=str(row["question_id"]),
        question_text=row["question_text"],
        status=row["status"],
        answer=row["answer"],
        created_at=row["created_at"].isoformat(),
        answered_at=None,
    )


@router.patch(
    "/engagements/{engagement_id}/questions/{question_id}",
    response_model=QuestionResponse,
)
async def update_question(
    engagement_id: str,
    question_id: str,
    body: QuestionUpdate,
    pool: Any = Depends(get_pool),
) -> QuestionResponse:
    async with pool.acquire() as conn:
        sets: list[str] = []
        vals: list[Any] = []
        idx = 3
        if body.status is not None:
            sets.append(f"status = ${idx}")
            vals.append(body.status)
            idx += 1
            if body.status == "answered":
                sets.append(f"answered_at = ${idx}")
                vals.append(datetime.now(timezone.utc))
                idx += 1
        if body.answer is not None:
            sets.append(f"answer = ${idx}")
            vals.append(body.answer)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No fields to update")

        row = await conn.fetchrow(
            f"UPDATE questions SET {', '.join(sets)} "  # noqa: S608
            f"WHERE question_id = $1::uuid AND engagement_id = $2::uuid "
            f"RETURNING question_id, question_text, status, answer, created_at, answered_at",
            question_id,
            engagement_id,
            *vals,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Question not found")

    return QuestionResponse(
        question_id=str(row["question_id"]),
        question_text=row["question_text"],
        status=row["status"],
        answer=row["answer"],
        created_at=row["created_at"].isoformat(),
        answered_at=row["answered_at"].isoformat() if row["answered_at"] else None,
    )


@router.delete(
    "/engagements/{engagement_id}/questions/{question_id}",
    status_code=204,
)
async def delete_question(
    engagement_id: str,
    question_id: str,
    pool: Any = Depends(get_pool),
) -> None:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM questions "
            "WHERE question_id = $1::uuid AND engagement_id = $2::uuid",
            question_id,
            engagement_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Question not found")


# ── Snapshots ───────────────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/snapshots",
    response_model=list[SnapshotResponse],
)
async def list_snapshots(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[SnapshotResponse]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT snapshot_id, name, description, entity_count, relationship_count,
                   observation_count, cycle_count, convergence_ratio, created_at
            FROM snapshots
            WHERE engagement_id = $1::uuid
            ORDER BY created_at DESC
            """,
            engagement_id,
        )
    return [
        SnapshotResponse(
            snapshot_id=str(r["snapshot_id"]),
            name=r["name"],
            description=r["description"],
            entity_count=r["entity_count"],
            relationship_count=r["relationship_count"],
            observation_count=r["observation_count"],
            cycle_count=r["cycle_count"],
            convergence_ratio=r["convergence_ratio"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post(
    "/engagements/{engagement_id}/snapshots",
    response_model=SnapshotResponse,
)
async def create_snapshot(
    engagement_id: str,
    body: SnapshotCreate,
    pool: Any = Depends(get_pool),
) -> SnapshotResponse:
    async with pool.acquire() as conn:
        entity_count = await conn.fetchval(
            "SELECT COUNT(*) FROM entities WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        rel_count = await conn.fetchval(
            "SELECT COUNT(*) FROM relationships WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        obs_count = await conn.fetchval(
            "SELECT COUNT(*) FROM observations WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        cycle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM convergence_log WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        latest_ratio = await conn.fetchval(
            "SELECT ratio FROM convergence_log "
            "WHERE engagement_id = $1::uuid ORDER BY cycle_number DESC LIMIT 1",
            engagement_id,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO snapshots
                (engagement_id, name, description, entity_count, relationship_count,
                 observation_count, cycle_count, convergence_ratio)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
            RETURNING snapshot_id, name, description, entity_count, relationship_count,
                      observation_count, cycle_count, convergence_ratio, created_at
            """,
            engagement_id,
            body.name,
            body.description,
            entity_count,
            rel_count,
            obs_count,
            cycle_count,
            latest_ratio,
        )

    return SnapshotResponse(
        snapshot_id=str(row["snapshot_id"]),
        name=row["name"],
        description=row["description"],
        entity_count=row["entity_count"],
        relationship_count=row["relationship_count"],
        observation_count=row["observation_count"],
        cycle_count=row["cycle_count"],
        convergence_ratio=row["convergence_ratio"],
        created_at=row["created_at"].isoformat(),
    )


# ── Schema ─────────────────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/schema",
    response_model=list[SchemaEntryResponse],
)
async def list_schema(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[SchemaEntryResponse]:
    """List active schema entries for an engagement."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT schema_entry_id, kind, name, description, examples,
                   parent_category, is_active
            FROM engagement_schema
            WHERE engagement_id = $1::uuid AND is_active = TRUE
            ORDER BY kind, name
            """,
            engagement_id,
        )
    return [
        SchemaEntryResponse(
            schema_entry_id=str(r["schema_entry_id"]),
            kind=r["kind"],
            name=r["name"],
            description=r["description"],
            examples=list(r["examples"]) if r["examples"] else [],
            parent_category=r["parent_category"],
            is_active=r["is_active"],
        )
        for r in rows
    ]


@router.post(
    "/engagements/{engagement_id}/schema",
    response_model=SchemaEntryResponse,
)
async def add_schema_entry(
    engagement_id: str,
    body: SchemaEntryCreate,
    pool: Any = Depends(get_pool),
) -> SchemaEntryResponse:
    """Add a type to the engagement schema."""
    if body.kind not in ("entity_type", "relationship_type"):
        raise HTTPException(
            status_code=400,
            detail="kind must be 'entity_type' or 'relationship_type'",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO engagement_schema
                (engagement_id, kind, name, description, examples, parent_category)
            VALUES ($1::uuid, $2, $3, $4, $5, $6)
            ON CONFLICT (engagement_id, kind, name) DO UPDATE
                SET description = EXCLUDED.description,
                    examples = EXCLUDED.examples,
                    parent_category = EXCLUDED.parent_category,
                    is_active = TRUE
            RETURNING schema_entry_id, kind, name, description, examples,
                      parent_category, is_active
            """,
            engagement_id,
            body.kind,
            body.name,
            body.description,
            body.examples,
            body.parent_category,
        )
    return SchemaEntryResponse(
        schema_entry_id=str(row["schema_entry_id"]),
        kind=row["kind"],
        name=row["name"],
        description=row["description"],
        examples=list(row["examples"]) if row["examples"] else [],
        parent_category=row["parent_category"],
        is_active=row["is_active"],
    )


@router.post(
    "/engagements/{engagement_id}/schema/apply-template",
    response_model=list[SchemaEntryResponse],
)
async def apply_template(
    engagement_id: str,
    body: ApplyTemplateRequest,
    pool: Any = Depends(get_pool),
) -> list[SchemaEntryResponse]:
    """Apply a template to the engagement schema."""
    template = get_template(body.template_id)
    if template is None:
        raise HTTPException(status_code=400, detail=f"Unknown template: {body.template_id}")

    eid = UUID(engagement_id)
    await populate_schema(pool, eid, body.template_id)

    # Return the updated schema
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT schema_entry_id, kind, name, description, examples,
                   parent_category, is_active
            FROM engagement_schema
            WHERE engagement_id = $1::uuid AND is_active = TRUE
            ORDER BY kind, name
            """,
            engagement_id,
        )
    return [
        SchemaEntryResponse(
            schema_entry_id=str(r["schema_entry_id"]),
            kind=r["kind"],
            name=r["name"],
            description=r["description"],
            examples=list(r["examples"]) if r["examples"] else [],
            parent_category=r["parent_category"],
            is_active=r["is_active"],
        )
        for r in rows
    ]


@router.get(
    "/templates",
    response_model=list[TemplateResponse],
)
async def get_templates() -> list[TemplateResponse]:
    """List available schema templates."""
    return [
        TemplateResponse(**t)
        for t in list_templates()
    ]


@router.post(
    "/engagements/{engagement_id}/schema/propose",
    response_model=SchemaProposalResponse,
)
async def propose_schema(
    engagement_id: str,
    pool: Any = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> SchemaProposalResponse:
    """LLM-based schema proposal for an engagement."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="No API key configured")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT problem_statement FROM engagements WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Engagement not found")

        source_rows = await conn.fetch(
            "SELECT source_type, config FROM source_configs WHERE engagement_id = $1::uuid",
            engagement_id,
        )

    problem = row["problem_statement"] or ""
    sources = []
    for sr in source_rows:
        cfg = _parse_config(sr["config"])
        ref = cfg.get("base_path") or cfg.get("seed_url") or sr["source_type"]
        sources.append(f"{sr['source_type']}:{ref}")

    from alec.agents.llm_client import AnthropicLLMClient
    from alec.services.schema_proposer import SchemaProposer

    llm = AnthropicLLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.default_model,
    )
    proposer = SchemaProposer(llm)
    result = await proposer.propose(problem, sources)

    return SchemaProposalResponse(
        template_base=result.get("template_base", "general_discovery"),
        entity_types=result.get("entity_types", []),
        relationship_types=result.get("relationship_types", []),
        reasoning=result.get("reasoning", ""),
    )


# ── Report ──────────────────────────────────────────────────────


@router.get(
    "/engagements/{engagement_id}/report",
    response_model=ReportResponse,
)
async def get_report(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> ReportResponse:
    """Generate a markdown report from the engagement data."""
    eid: UUID = UUID(engagement_id)

    async with pool.acquire() as conn:
        eng = await conn.fetchrow(
            "SELECT name, problem_statement, status, created_at "
            "FROM engagements WHERE engagement_id = $1",
            eid,
        )
        if eng is None:
            raise HTTPException(status_code=404, detail="Engagement not found")

        entities = await conn.fetch(
            "SELECT name, entity_type, observation_count, properties "
            "FROM entities WHERE engagement_id = $1 AND status = 'active' "
            "ORDER BY observation_count DESC LIMIT 50",
            eid,
        )

        relationships = await conn.fetch(
            "SELECT e1.name AS from_name, e2.name AS to_name, "
            "r.relationship_type, r.confidence "
            "FROM relationships r "
            "JOIN entities e1 ON r.from_entity = e1.entity_id "
            "JOIN entities e2 ON r.to_entity = e2.entity_id "
            "WHERE r.engagement_id = $1 ORDER BY r.confidence DESC LIMIT 50",
            eid,
        )

        consolidated = await conn.fetch(
            "SELECT cu.summary, e.name AS entity_name "
            "FROM consolidated_units cu "
            "LEFT JOIN entities e ON cu.subject_entity = e.entity_id "
            "WHERE cu.engagement_id = $1 AND cu.status = 'current' "
            "ORDER BY cu.freshness DESC LIMIT 20",
            eid,
        )

        convergence = await conn.fetch(
            "SELECT cycle_number, ratio FROM convergence_log "
            "WHERE engagement_id = $1 ORDER BY cycle_number ASC",
            eid,
        )

        sources = await conn.fetch(
            "SELECT source_type, config, status, trust_tier "
            "FROM source_configs WHERE engagement_id = $1",
            eid,
        )

        counts = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM entities WHERE engagement_id = $1) AS entities,
                (SELECT COUNT(*) FROM relationships WHERE engagement_id = $1) AS rels,
                (SELECT COUNT(*) FROM observations WHERE engagement_id = $1) AS obs
            """,
            eid,
        )

    # Build markdown
    lines: list[str] = []
    title = eng["name"]
    lines.append(f"# {title}")
    lines.append("")
    if eng["problem_statement"]:
        lines.append(f"**Problem Statement:** {eng['problem_statement']}")
        lines.append("")
    lines.append(f"**Status:** {eng['status']}")
    lines.append(
        f"**Created:** {eng['created_at'].isoformat() if eng['created_at'] else 'N/A'}"
    )
    lines.append("")

    # Stats
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Entities:** {counts['entities']}")
    lines.append(f"- **Relationships:** {counts['rels']}")
    lines.append(f"- **Observations:** {counts['obs']}")
    lines.append(f"- **Cycles:** {len(convergence)}")
    lines.append("")

    # Sources
    if sources:
        lines.append("## Sources")
        lines.append("")
        for s in sources:
            cfg = _parse_config(s["config"])
            ref = cfg.get("base_path") or cfg.get("seed_url") or s["source_type"]
            lines.append(
                f"- **{s['source_type']}** — {ref} "
                f"(trust: {s['trust_tier']}, status: {s['status']})"
            )
        lines.append("")

    # Convergence
    if convergence:
        lines.append("## Convergence History")
        lines.append("")
        lines.append("| Cycle | Ratio |")
        lines.append("|-------|-------|")
        for c in convergence:
            ratio_str = f"{c['ratio']:.2f}" if c["ratio"] is not None else "N/A"
            lines.append(f"| {c['cycle_number']} | {ratio_str} |")
        lines.append("")

    # Key findings
    if consolidated:
        lines.append("## Key Findings")
        lines.append("")
        for cu in consolidated:
            entity_label = f"**{cu['entity_name']}**: " if cu["entity_name"] else ""
            lines.append(f"- {entity_label}{cu['summary']}")
        lines.append("")

    # Entities
    if entities:
        lines.append("## Top Entities")
        lines.append("")
        lines.append("| Entity | Type | Observations |")
        lines.append("|--------|------|-------------|")
        for e in entities[:30]:
            lines.append(
                f"| {e['name']} | {e['entity_type']} | {e['observation_count']} |"
            )
        lines.append("")

    # Relationships
    if relationships:
        lines.append("## Key Relationships")
        lines.append("")
        for r in relationships[:30]:
            conf = f"{r['confidence'] * 100:.0f}%"
            lines.append(
                f"- {r['from_name']} **{r['relationship_type']}** {r['to_name']} ({conf})"
            )
        lines.append("")

    markdown = "\n".join(lines)
    return ReportResponse(
        markdown=markdown,
        title=title,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
