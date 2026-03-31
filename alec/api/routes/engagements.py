"""Engagement CRUD routes."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from alec.agents.llm_client import AnthropicLLMClient
from alec.api.dependencies import get_event_bus, get_pool, get_settings
from alec.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    EngagementCreate,
    EngagementResponse,
    SuggestedSource,
    TopicCoverage,
)
from alec.config.settings import Settings
from alec.events.bus import EventBus
from alec.runtime.supervisor import Supervisor
from alec.services.setup_analyzer import SetupAnalyzer

STALE_HEARTBEAT_SECONDS = 60

logger = structlog.get_logger()
router = APIRouter()


def _compute_status(row: Any) -> str:
    """Return 'stalled' if engagement is active but heartbeat is stale."""
    status: str = row["status"]
    if status != "active":
        return status
    heartbeat = row.get("last_heartbeat")
    if heartbeat is None:
        return "stalled"
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    if age > STALE_HEARTBEAT_SECONDS:
        return "stalled"
    return status


def _engagement_response(row: Any, **counts: int) -> EngagementResponse:
    """Build EngagementResponse from a DB row with optional count overrides."""
    config_raw = row.get("config")
    config = json.loads(config_raw) if isinstance(config_raw, str) else (config_raw or {})
    return EngagementResponse(
        engagement_id=str(row["engagement_id"]),
        name=row["name"],
        status=_compute_status(row),
        entity_count=counts.get("entity_count", 0),
        relationship_count=counts.get("relationship_count", 0),
        observation_count=counts.get("observation_count", 0),
        problem_statement=row.get("problem_statement") or "",
        summary=row.get("summary") or "",
        config=config,
        created_at=row["created_at"].isoformat() if row.get("created_at") else None,
        updated_at=row["updated_at"].isoformat() if row.get("updated_at") else None,
    )


@router.post("/engagements", response_model=EngagementResponse)
async def create_engagement(
    body: EngagementCreate,
    pool: Any = Depends(get_pool),
    settings: Settings = Depends(get_settings),
    event_bus: EventBus = Depends(get_event_bus),
) -> EngagementResponse:
    """Create an engagement and launch supervisor as a background task."""
    sources_desc = ", ".join(body.sources)
    problem = body.problem_statement or f"Discover and map knowledge from sources: {sources_desc}"
    name = body.name.strip() if body.name.strip() else f"Discovery: {sources_desc[:200]}"
    summary = body.summary.strip() if body.summary.strip() else problem

    config = json.dumps({"sources": body.sources, "max_cycles": body.max_cycles})

    async with pool.acquire() as conn:
        engagement_id = await conn.fetchval(
            """
            INSERT INTO engagements (name, problem_statement, summary, status, config)
            VALUES ($1, $2, $3, 'active', $4::jsonb)
            RETURNING engagement_id
            """,
            name,
            problem,
            summary,
            config,
        )

    # Launch supervisor in background
    supervisor = Supervisor(settings)

    async def _run_supervisor() -> None:
        try:
            await supervisor.run(
                sources=body.sources,
                problem_statement=problem,
                max_cycles=body.max_cycles,
                pool=pool,
                event_bus=event_bus,
                engagement_id=engagement_id,
            )
        except Exception:
            logger.error("api.supervisor_error", engagement_id=str(engagement_id), exc_info=True)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE engagements SET status = 'error' WHERE engagement_id = $1",
                    engagement_id,
                )

    asyncio.create_task(_run_supervisor())

    return EngagementResponse(
        engagement_id=str(engagement_id),
        name=name,
        status="active",
        summary=summary,
    )


@router.get("/engagements", response_model=list[EngagementResponse])
async def list_engagements(
    pool: Any = Depends(get_pool),
) -> list[EngagementResponse]:
    """List all engagements with counts."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                e.*,
                COALESCE(ent.cnt, 0) AS entity_count,
                COALESCE(rel.cnt, 0) AS relationship_count,
                COALESCE(obs.cnt, 0) AS observation_count
            FROM engagements e
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM entities WHERE engagement_id = e.engagement_id
            ) ent ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM relationships WHERE engagement_id = e.engagement_id
            ) rel ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM observations WHERE engagement_id = e.engagement_id
            ) obs ON true
            ORDER BY e.created_at DESC
            """
        )

    return [
        _engagement_response(
            r,
            entity_count=r["entity_count"],
            relationship_count=r["relationship_count"],
            observation_count=r["observation_count"],
        )
        for r in rows
    ]


@router.post("/engagements/analyze", response_model=AnalyzeResponse)
async def analyze_engagement(
    body: AnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """Analyze problem statement vs source coverage without creating an engagement."""
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="No API key configured")

    llm = AnthropicLLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.default_model,
    )
    analyzer = SetupAnalyzer(llm)
    result = await analyzer.analyze(body.problem_statement, body.sources)

    return AnalyzeResponse(
        topics=[TopicCoverage(**t) for t in result.get("topics", [])],
        gaps=result.get("gaps", []),
        suggested_sources=[SuggestedSource(**s) for s in result.get("suggested_sources", [])],
        search_queries=result.get("search_queries", []),
        overall_assessment=result.get("overall_assessment", ""),
    )


@router.get("/engagements/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> EngagementResponse:
    """Get engagement detail with counts."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
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

    if row is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    return _engagement_response(
        row,
        entity_count=entity_count,
        relationship_count=rel_count,
        observation_count=obs_count,
    )


# Tables with engagement_id FK, ordered to respect nested FKs.
# Tables with engagement_id column, ordered to respect nested FKs.
# code_executions has no engagement_id (references code_assets.asset_id).
_CHILD_TABLES = [
    "engagement_schema",
    "user_annotations",
    "questions",
    "snapshots",
    "code_assets",
    "convergence_log",
    "source_configs",
    "tasks",
    "coordinator_instances",
    "prompt_proposals",
    "consolidated_units",
    "knowledge_items",
    "alignments",
    "relationships",
    "observations",
    "entities",
    "models",
]


@router.delete("/engagements/{engagement_id}", status_code=204)
async def delete_engagement(
    engagement_id: str,
    pool: Any = Depends(get_pool),
) -> None:
    """Delete an engagement and all its data."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM engagements WHERE engagement_id = $1::uuid",
            engagement_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Engagement not found")
        if row["status"] == "active":
            raise HTTPException(status_code=409, detail="Cannot delete an active engagement")

        # Filter to tables that exist (handles partially-migrated DBs)
        existing = {
            r["tablename"]
            for r in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        async with conn.transaction():
            for table in _CHILD_TABLES:
                if table not in existing:
                    continue
                await conn.execute(
                    f"DELETE FROM {table} WHERE engagement_id = $1::uuid",  # noqa: S608
                    engagement_id,
                )
            await conn.execute(
                "DELETE FROM engagements WHERE engagement_id = $1::uuid",
                engagement_id,
            )


@router.post("/engagements/{engagement_id}/restart", response_model=EngagementResponse)
async def restart_engagement(
    engagement_id: str,
    pool: Any = Depends(get_pool),
    settings: Settings = Depends(get_settings),
    event_bus: EventBus = Depends(get_event_bus),
) -> EngagementResponse:
    """Restart a failed or completed engagement."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM engagements WHERE engagement_id = $1::uuid",
            engagement_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    computed_status = _compute_status(row)
    if row["status"] == "active" and computed_status != "stalled":
        raise HTTPException(status_code=409, detail="Engagement is already active")

    config_raw = row["config"]
    config = json.loads(config_raw) if isinstance(config_raw, str) else (config_raw or {})
    sources = config.get("sources", [])
    max_cycles = config.get("max_cycles", 3)

    # Fallback: parse sources from engagement name for legacy engagements
    if not sources:
        name_str = row["name"].removeprefix("Discovery: ")
        sources = [s.strip() for s in name_str.split(",") if s.strip()]
    if not sources:
        raise HTTPException(status_code=400, detail="No sources found for this engagement")

    name = row["name"]
    problem = row["problem_statement"]

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE engagements SET status = 'active', updated_at = NOW() "
            "WHERE engagement_id = $1::uuid",
            engagement_id,
        )

    supervisor = Supervisor(settings)

    async def _run_supervisor() -> None:
        try:
            await supervisor.run(
                sources=sources,
                problem_statement=problem,
                max_cycles=max_cycles,
                pool=pool,
                event_bus=event_bus,
                engagement_id=row["engagement_id"],
            )
        except Exception:
            logger.error("api.supervisor_error", engagement_id=engagement_id, exc_info=True)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE engagements SET status = 'error' WHERE engagement_id = $1::uuid",
                    engagement_id,
                )

    asyncio.create_task(_run_supervisor())

    return EngagementResponse(
        engagement_id=str(row["engagement_id"]),
        name=name,
        status="active",
        summary=row.get("summary") or "",
    )
