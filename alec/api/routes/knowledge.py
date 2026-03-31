"""Knowledge graph query routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from alec.api.dependencies import get_pool
from alec.api.schemas import (
    ConsolidatedUnitResponse,
    ConvergenceEntry,
    EngagementStatsResponse,
    EntityDetailResponse,
    EntityObservation,
    EntityRelationship,
    EntityResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    ObservationResponse,
    PaginatedResponse,
    RelationshipResponse,
    SourceConfigEntry,
    TaskResponse,
)

router = APIRouter()


@router.get(
    "/engagements/{engagement_id}/entities",
    response_model=PaginatedResponse,
)
async def list_entities(
    engagement_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    pool: Any = Depends(get_pool),
) -> PaginatedResponse:
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM entities WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        rows = await conn.fetch(
            """
            SELECT entity_id, name, entity_type, observation_count, properties
            FROM entities
            WHERE engagement_id = $1::uuid AND status = 'active'
            ORDER BY observation_count DESC
            OFFSET $2 LIMIT $3
            """,
            engagement_id,
            offset,
            limit,
        )

    items = [
        EntityResponse(
            entity_id=str(r["entity_id"]),
            name=r["name"],
            entity_type=r["entity_type"],
            observation_count=r["observation_count"],
            properties=(
                r["properties"]
                if isinstance(r["properties"], dict)
                else (
                    json.loads(r["properties"])
                    if r["properties"]
                    else {}
                )
            ),
        )
        for r in rows
    ]
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/engagements/{engagement_id}/relationships",
    response_model=PaginatedResponse,
)
async def list_relationships(
    engagement_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    pool: Any = Depends(get_pool),
) -> PaginatedResponse:
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM relationships WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        rows = await conn.fetch(
            """
            SELECT relationship_id, from_entity, to_entity, relationship_type, confidence
            FROM relationships
            WHERE engagement_id = $1::uuid
            ORDER BY last_confirmed DESC
            OFFSET $2 LIMIT $3
            """,
            engagement_id,
            offset,
            limit,
        )

    items = [
        RelationshipResponse(
            relationship_id=str(r["relationship_id"]),
            from_entity=str(r["from_entity"]),
            to_entity=str(r["to_entity"]),
            relationship_type=r["relationship_type"],
            confidence=r["confidence"],
        )
        for r in rows
    ]
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/engagements/{engagement_id}/observations",
    response_model=PaginatedResponse,
)
async def list_observations(
    engagement_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    pool: Any = Depends(get_pool),
) -> PaginatedResponse:
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM observations WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        rows = await conn.fetch(
            """
            SELECT observation_id, source_ref, raw_text, observation_type, created_at
            FROM observations
            WHERE engagement_id = $1::uuid
            ORDER BY created_at DESC
            OFFSET $2 LIMIT $3
            """,
            engagement_id,
            offset,
            limit,
        )

    items = [
        ObservationResponse(
            observation_id=str(r["observation_id"]),
            source_ref=r["source_ref"],
            raw_text=r["raw_text"],
            observation_type=r["observation_type"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/engagements/{engagement_id}/graph",
    response_model=GraphResponse,
)
async def get_graph(
    engagement_id: str,
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    min_observations: int = Query(0, ge=0),
    pool: Any = Depends(get_pool),
) -> GraphResponse:
    """Return nodes + edges for visualization with optional filters."""
    type_filter = (
        [t.strip() for t in entity_types.split(",") if t.strip()]
        if entity_types
        else None
    )

    async with pool.acquire() as conn:
        if type_filter:
            entity_rows = await conn.fetch(
                """
                SELECT entity_id, name, entity_type, observation_count
                FROM entities
                WHERE engagement_id = $1::uuid
                  AND status = 'active'
                  AND entity_type = ANY($2)
                  AND observation_count >= $3
                ORDER BY observation_count DESC
                LIMIT 500
                """,
                engagement_id,
                type_filter,
                min_observations,
            )
        else:
            entity_rows = await conn.fetch(
                """
                SELECT entity_id, name, entity_type, observation_count
                FROM entities
                WHERE engagement_id = $1::uuid
                  AND status = 'active'
                  AND observation_count >= $2
                ORDER BY observation_count DESC
                LIMIT 500
                """,
                engagement_id,
                min_observations,
            )

        entity_ids = [r["entity_id"] for r in entity_rows]

        if entity_ids:
            rel_rows = await conn.fetch(
                """
                SELECT r.from_entity, r.to_entity, r.relationship_type, r.confidence,
                       fe.name AS from_name, te.name AS to_name
                FROM relationships r
                JOIN entities fe ON fe.entity_id = r.from_entity
                JOIN entities te ON te.entity_id = r.to_entity
                WHERE r.engagement_id = $1::uuid
                  AND r.from_entity = ANY($2::uuid[])
                  AND r.to_entity = ANY($2::uuid[])
                LIMIT 1000
                """,
                engagement_id,
                entity_ids,
            )
        else:
            rel_rows = []

        # Fetch latest community analysis for community coloring
        community_row = await conn.fetchrow(
            """
            SELECT communities, hub_entities, bridge_entities
            FROM community_analysis
            WHERE engagement_id = $1::uuid
            ORDER BY cycle_number DESC
            LIMIT 1
            """,
            engagement_id,
        )

    # Build name → community lookup from community_analysis
    name_to_community: dict[str, int] = {}
    hub_names: set[str] = set()
    bridge_names: set[str] = set()
    if community_row:
        communities_data = community_row["communities"]
        if isinstance(communities_data, str):
            communities_data = json.loads(communities_data)
        for comm_id_str, members in communities_data.items():
            comm_id = int(comm_id_str)
            for name in members:
                name_to_community[name] = comm_id

        hub_data = community_row["hub_entities"]
        if isinstance(hub_data, str):
            hub_data = json.loads(hub_data)
        hub_names = set(hub_data) if hub_data else set()

        bridge_data = community_row["bridge_entities"]
        if isinstance(bridge_data, str):
            bridge_data = json.loads(bridge_data)
        bridge_names = set(bridge_data) if bridge_data else set()

    nodes = [
        GraphNode(
            id=str(r["entity_id"]),
            name=r["name"],
            entity_type=r["entity_type"],
            observation_count=r["observation_count"],
            community_id=name_to_community.get(r["name"]),
            is_hub=r["name"] in hub_names,
            is_bridge=r["name"] in bridge_names,
        )
        for r in entity_rows
    ]
    edges = [
        GraphEdge(
            source=str(r["from_entity"]),
            target=str(r["to_entity"]),
            relationship_type=r["relationship_type"],
            confidence=r["confidence"],
            from_name=r["from_name"],
            to_name=r["to_name"],
        )
        for r in rel_rows
    ]
    return GraphResponse(nodes=nodes, edges=edges)


# --- New endpoints ---


@router.get(
    "/engagements/{engagement_id}/timeline",
    response_model=list[TaskResponse],
)
async def get_timeline(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[TaskResponse]:
    """Tasks ordered chronologically — the activity timeline."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT task_id, directive, source_type, source_ref, max_scope,
                   status, assigned_worker, result_summary,
                   created_at, started_at, completed_at
            FROM tasks
            WHERE engagement_id = $1::uuid
            ORDER BY created_at ASC
            """,
            engagement_id,
        )

    return [
        TaskResponse(
            task_id=str(r["task_id"]),
            directive=r["directive"],
            source_type=r["source_type"],
            source_ref=r["source_ref"],
            max_scope=r["max_scope"] or "survey",
            status=r["status"],
            assigned_worker=r["assigned_worker"],
            result_summary=(
                json.loads(r["result_summary"])
                if isinstance(r["result_summary"], str)
                else r["result_summary"]
            ),
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
            started_at=r["started_at"].isoformat() if r["started_at"] else None,
            completed_at=r["completed_at"].isoformat() if r["completed_at"] else None,
        )
        for r in rows
    ]


@router.get(
    "/engagements/{engagement_id}/stats",
    response_model=EngagementStatsResponse,
)
async def get_stats(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> EngagementStatsResponse:
    """Aggregated engagement metrics."""
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
        task_count = await conn.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE engagement_id = $1::uuid",
            engagement_id,
        )

        # Entity type breakdown
        type_rows = await conn.fetch(
            """
            SELECT entity_type, COUNT(*) AS cnt
            FROM entities WHERE engagement_id = $1::uuid AND status = 'active'
            GROUP BY entity_type ORDER BY cnt DESC
            """,
            engagement_id,
        )
        entity_type_breakdown = {r["entity_type"]: r["cnt"] for r in type_rows}

        # Observation type breakdown
        obs_type_rows = await conn.fetch(
            """
            SELECT observation_type, COUNT(*) AS cnt
            FROM observations WHERE engagement_id = $1::uuid
            GROUP BY observation_type ORDER BY cnt DESC
            """,
            engagement_id,
        )
        observation_type_breakdown = {r["observation_type"]: r["cnt"] for r in obs_type_rows}

        # Task status breakdown
        task_status_rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS cnt
            FROM tasks WHERE engagement_id = $1::uuid
            GROUP BY status ORDER BY cnt DESC
            """,
            engagement_id,
        )
        task_status_breakdown = {r["status"]: r["cnt"] for r in task_status_rows}

        # Convergence history (use DISTINCT ON to handle legacy duplicate cycle numbers)
        conv_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (cycle_number)
                   cycle_number, reinforcement_count, expansion_count,
                   challenge_count, ratio, weighted_ratio
            FROM convergence_log
            WHERE engagement_id = $1::uuid
            ORDER BY cycle_number ASC, created_at DESC
            """,
            engagement_id,
        )
        convergence_history = [
            ConvergenceEntry(
                cycle_number=r["cycle_number"],
                reinforcement_count=r["reinforcement_count"],
                expansion_count=r["expansion_count"],
                challenge_count=r["challenge_count"],
                ratio=r["ratio"],
                weighted_ratio=r["weighted_ratio"],
            )
            for r in conv_rows
        ]

        # Use max cycle number (not row count) — handles legacy duplicate entries
        cycle_count = max((r["cycle_number"] for r in conv_rows), default=0)

        # Source configs
        sc_rows = await conn.fetch(
            """
            SELECT source_type, config, status
            FROM source_configs
            WHERE engagement_id = $1::uuid
            """,
            engagement_id,
        )
        source_configs = [
            SourceConfigEntry(
                source_type=r["source_type"],
                config=(
                    json.loads(r["config"])
                    if isinstance(r["config"], str)
                    else (r["config"] or {})
                ),
                status=r["status"],
            )
            for r in sc_rows
        ]

    return EngagementStatsResponse(
        entity_count=entity_count,
        relationship_count=rel_count,
        observation_count=obs_count,
        task_count=task_count,
        cycle_count=cycle_count,
        entity_type_breakdown=entity_type_breakdown,
        observation_type_breakdown=observation_type_breakdown,
        task_status_breakdown=task_status_breakdown,
        convergence_history=convergence_history,
        source_configs=source_configs,
    )


@router.get(
    "/engagements/{engagement_id}/consolidated",
    response_model=list[ConsolidatedUnitResponse],
)
async def get_consolidated(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> list[ConsolidatedUnitResponse]:
    """Consolidated knowledge units with entity names."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cu.unit_id, cu.subject_entity, e.name AS subject_entity_name,
                   cu.summary, cu.token_count, cu.version, cu.freshness, cu.status
            FROM consolidated_units cu
            LEFT JOIN entities e ON e.entity_id = cu.subject_entity
            WHERE cu.engagement_id = $1::uuid AND cu.status = 'current'
            ORDER BY cu.freshness DESC
            """,
            engagement_id,
        )

    return [
        ConsolidatedUnitResponse(
            unit_id=str(r["unit_id"]),
            subject_entity_id=str(r["subject_entity"]) if r["subject_entity"] else None,
            subject_entity_name=r["subject_entity_name"],
            summary=r["summary"],
            token_count=r["token_count"],
            version=r["version"],
            freshness=r["freshness"].isoformat() if r["freshness"] else None,
            status=r["status"],
        )
        for r in rows
    ]


@router.get(
    "/engagements/{engagement_id}/entities/{entity_id}",
    response_model=EntityDetailResponse,
)
async def get_entity_detail(
    engagement_id: str,
    entity_id: str,
    pool: Any = Depends(get_pool),
) -> EntityDetailResponse:
    """Full entity detail with observations, relationships, and consolidated summary."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT entity_id, name, entity_type, aliases, observation_count,
                   properties, first_seen, last_referenced
            FROM entities
            WHERE entity_id = $1::uuid AND engagement_id = $2::uuid
            """,
            entity_id,
            engagement_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Entity not found")

        # Observations for this entity (via text match on entity name in raw_text,
        # or via the observation_id references in entity properties)
        obs_rows = await conn.fetch(
            """
            SELECT o.observation_id, o.source_ref, o.raw_text, o.observation_type, o.created_at
            FROM observations o
            WHERE o.engagement_id = $1::uuid
              AND o.raw_text ILIKE '%' || $2 || '%'
            ORDER BY o.created_at DESC
            LIMIT 50
            """,
            engagement_id,
            row["name"],
        )

        # Outgoing relationships
        out_rows = await conn.fetch(
            """
            SELECT r.relationship_id, r.to_entity AS entity_id,
                   e.name AS entity_name, r.relationship_type, r.confidence
            FROM relationships r
            JOIN entities e ON e.entity_id = r.to_entity
            WHERE r.from_entity = $1::uuid AND r.engagement_id = $2::uuid
            """,
            entity_id,
            engagement_id,
        )

        # Incoming relationships
        in_rows = await conn.fetch(
            """
            SELECT r.relationship_id, r.from_entity AS entity_id,
                   e.name AS entity_name, r.relationship_type, r.confidence
            FROM relationships r
            JOIN entities e ON e.entity_id = r.from_entity
            WHERE r.to_entity = $1::uuid AND r.engagement_id = $2::uuid
            """,
            entity_id,
            engagement_id,
        )

        # Consolidated summary
        cons_row = await conn.fetchrow(
            """
            SELECT summary FROM consolidated_units
            WHERE subject_entity = $1::uuid AND status = 'current'
            ORDER BY freshness DESC LIMIT 1
            """,
            entity_id,
        )

    props = row["properties"]
    properties = json.loads(props) if isinstance(props, str) else (props or {})

    return EntityDetailResponse(
        entity_id=str(row["entity_id"]),
        name=row["name"],
        entity_type=row["entity_type"],
        aliases=list(row["aliases"] or []),
        observation_count=row["observation_count"],
        properties=properties,
        first_seen=row["first_seen"].isoformat() if row["first_seen"] else None,
        last_referenced=row["last_referenced"].isoformat() if row["last_referenced"] else None,
        observations=[
            EntityObservation(
                observation_id=str(r["observation_id"]),
                source_ref=r["source_ref"],
                raw_text=r["raw_text"],
                observation_type=r["observation_type"],
                created_at=r["created_at"].isoformat(),
            )
            for r in obs_rows
        ],
        relationships_outgoing=[
            EntityRelationship(
                relationship_id=str(r["relationship_id"]),
                entity_id=str(r["entity_id"]),
                entity_name=r["entity_name"],
                relationship_type=r["relationship_type"],
                confidence=r["confidence"],
                direction="outgoing",
            )
            for r in out_rows
        ],
        relationships_incoming=[
            EntityRelationship(
                relationship_id=str(r["relationship_id"]),
                entity_id=str(r["entity_id"]),
                entity_name=r["entity_name"],
                relationship_type=r["relationship_type"],
                confidence=r["confidence"],
                direction="incoming",
            )
            for r in in_rows
        ],
        consolidated_summary=cons_row["summary"] if cons_row else None,
    )
