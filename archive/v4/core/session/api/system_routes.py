"""System API routes (v3).

Endpoints for system administration, reset, and diagnostics.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from core.common.observability import setup_logging
from core.session.api.models import (
    ClusterListResponse,
    ClusterResponse,
    EdgeListResponse,
    EdgeResponse,
    GraphHealthResponse,
    LearningStatsResponse,
)

router = APIRouter()
logger = setup_logging("system-routes")


@router.get("/health")
async def get_health() -> dict:
    """Get system health status."""
    from core.session.main import service
    return await service.health_check()


def get_deps():
    """Get dependencies from global service."""
    from core.session.main import service
    return {
        "pool": service.pool,
        "redis": service.redis,
    }


@router.post("/reset")
async def reset_all(confirm: bool = False) -> dict[str, Any]:
    """Reset all learning data."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm=true to reset")

    deps = get_deps()
    pool = deps["pool"]
    redis = deps["redis"]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Clear in order of dependencies
            await conn.execute("DELETE FROM session_turns")
            await conn.execute("DELETE FROM session_outcomes")
            await conn.execute("DELETE FROM sessions")
            await conn.execute("DELETE FROM evaluation_task_results")
            await conn.execute("DELETE FROM evaluation_experiments")
            await conn.execute("DELETE FROM knowledge_edges")
            await conn.execute("DELETE FROM turn_clusters")
            await conn.execute("DELETE FROM problem_clusters")

    # Flush Redis
    await redis.flushdb()

    logger.warning("system_reset_complete")

    return {"status": "reset", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/reset/counters")
async def reset_counters() -> dict[str, Any]:
    """Reset bullet effectiveness counters."""
    deps = get_deps()
    pool = deps["pool"]

    await pool.execute(
        """
        UPDATE playbook_bullets
        SET helpful_count = 0, harmful_count = 0, neutral_count = 0,
            updated_at = NOW()
        """
    )

    logger.warning("counters_reset")

    return {"status": "reset", "target": "counters"}


@router.post("/reset/sessions")
async def reset_sessions() -> dict[str, Any]:
    """Clear all sessions."""
    deps = get_deps()
    pool = deps["pool"]

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM session_turns")
            await conn.execute("DELETE FROM session_outcomes")
            await conn.execute("DELETE FROM sessions")

    logger.warning("sessions_reset")

    return {"status": "reset", "target": "sessions"}


@router.post("/reset/evaluations")
async def reset_evaluations() -> dict[str, Any]:
    """Clear all evaluation data."""
    deps = get_deps()
    pool = deps["pool"]

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM evaluation_task_results")
            await conn.execute("DELETE FROM evaluation_experiments")

    logger.warning("evaluations_reset")

    return {"status": "reset", "target": "evaluations"}


@router.post("/reset/redis")
async def reset_redis() -> dict[str, Any]:
    """Flush Redis cache."""
    deps = get_deps()
    redis = deps["redis"]

    await redis.flushdb()

    logger.warning("redis_reset")

    return {"status": "reset", "target": "redis"}


@router.post("/reset/bullets")
async def reset_bullets(confirm: bool = False) -> dict[str, Any]:
    """Delete all bullets (destructive)."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm=true to delete bullets")

    deps = get_deps()
    pool = deps["pool"]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Clear edges first
            await conn.execute("DELETE FROM knowledge_edges")
            await conn.execute("DELETE FROM playbook_bullets")

    logger.warning("bullets_reset")

    return {"status": "reset", "target": "bullets"}


@router.get("/learning-stats", response_model=LearningStatsResponse)
async def get_learning_stats() -> LearningStatsResponse:
    """Get learning effectiveness dashboard data."""
    deps = get_deps()
    pool = deps["pool"]

    # Get bullet counts
    bullet_counts = await pool.fetchrow(
        """
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'active') as active
        FROM playbook_bullets
        """
    )

    # Get session counts
    session_counts = await pool.fetchrow(
        """
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'completed') as successful
        FROM sessions
        """
    )

    # Get average effectiveness
    avg_eff = await pool.fetchval(
        """
        SELECT AVG(
            CASE WHEN helpful_count + harmful_count > 0
            THEN helpful_count::float / (helpful_count + harmful_count)
            ELSE 0.5 END
        ) FROM playbook_bullets WHERE status = 'active'
        """
    )

    # Get top bullets
    top_rows = await pool.fetch(
        """
        SELECT bullet_id, assertion, helpful_count, harmful_count
        FROM playbook_bullets
        WHERE status = 'active' AND helpful_count > 0
        ORDER BY helpful_count DESC
        LIMIT 10
        """
    )

    top_bullets = [
        {
            "id": str(row["bullet_id"]),
            "content": row["assertion"][:100],
            "helpful": row["helpful_count"],
            "harmful": row["harmful_count"],
        }
        for row in top_rows
    ]

    # Get recent changes (status transitions)
    recent_rows = await pool.fetch(
        """
        SELECT bullet_id, assertion, status, updated_at
        FROM playbook_bullets
        ORDER BY updated_at DESC
        LIMIT 10
        """
    )

    recent_changes = [
        {
            "id": str(row["bullet_id"]),
            "content": row["assertion"][:50] if row.get("assertion") else "",
            "status": row["status"],
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
        }
        for row in recent_rows
    ]

    return LearningStatsResponse(
        total_bullets=bullet_counts["total"] or 0,
        active_bullets=bullet_counts["active"] or 0,
        total_sessions=session_counts["total"] or 0,
        successful_sessions=session_counts["successful"] or 0,
        avg_effectiveness=float(avg_eff or 0.5),
        top_bullets=top_bullets,
        recent_changes=recent_changes,
    )


@router.get("/graph-health", response_model=GraphHealthResponse)
async def get_graph_health() -> GraphHealthResponse:
    """Get knowledge graph health metrics."""
    deps = get_deps()
    pool = deps["pool"]

    stats = await pool.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM problem_clusters) as total_clusters,
            (SELECT COUNT(*) FROM problem_clusters) as active_clusters,
            (SELECT COUNT(*) FROM knowledge_edges) as total_edges,
            (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'solved_by') as solved_by_edges,
            (SELECT COUNT(*) FROM knowledge_edges WHERE edge_type = 'caused_failure') as caused_failure_edges,
            COALESCE(
                (SELECT AVG(100.0 * success_count / NULLIF(success_count + failure_count, 0))
                 FROM problem_clusters WHERE success_count + failure_count > 0),
                0
            ) as avg_cluster_success_rate
        """
    )

    return GraphHealthResponse(
        total_clusters=stats["total_clusters"] or 0,
        active_clusters=stats["active_clusters"] or 0,
        total_edges=stats["total_edges"] or 0,
        solved_by_edges=stats["solved_by_edges"] or 0,
        caused_failure_edges=stats["caused_failure_edges"] or 0,
        avg_cluster_success_rate=float(stats["avg_cluster_success_rate"] or 0),
    )


@router.get("/clusters", response_model=ClusterListResponse)
async def get_clusters(
    page: int = 1,
    page_size: int = 50,
) -> ClusterListResponse:
    """Get problem clusters with edge counts."""
    deps = get_deps()
    pool = deps["pool"]

    offset = (page - 1) * page_size

    # Get total count
    total = await pool.fetchval("SELECT COUNT(*) FROM problem_clusters")

    # Get clusters with edge counts
    # turn_count is derived from success_count + failure_count
    query = """
        SELECT
            pc.cluster_id::text,
            pc.label,
            pc.domain,
            pc.success_count,
            pc.failure_count,
            (pc.success_count + pc.failure_count) as turn_count,
            pc.created_at,
            pc.updated_at,
            COUNT(DISTINCT ke_s.edge_id) FILTER (WHERE ke_s.edge_type = 'solved_by') as solved_by_edges,
            COUNT(DISTINCT ke_f.edge_id) FILTER (WHERE ke_f.edge_type = 'caused_failure') as caused_failure_edges
        FROM problem_clusters pc
        LEFT JOIN knowledge_edges ke_s ON ke_s.source_id = pc.cluster_id
        LEFT JOIN knowledge_edges ke_f ON ke_f.source_id = pc.cluster_id
        GROUP BY pc.cluster_id
        ORDER BY (pc.success_count + pc.failure_count) DESC
        LIMIT $1 OFFSET $2
    """

    rows = await pool.fetch(query, page_size, offset)

    clusters = [
        ClusterResponse(
            cluster_id=row["cluster_id"],
            label=row["label"] or "Unknown cluster",
            description=row["domain"],  # Use domain as description
            turn_count=row["turn_count"] or 0,
            success_count=row["success_count"] or 0,
            failure_count=row["failure_count"] or 0,
            status="active",  # All clusters are active (no status column)
            solved_by_edges=row["solved_by_edges"] or 0,
            caused_failure_edges=row["caused_failure_edges"] or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]

    return ClusterListResponse(
        clusters=clusters,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/edges", response_model=EdgeListResponse)
async def get_edges(
    edge_type: Optional[str] = None,
    limit: int = 500,
) -> EdgeListResponse:
    """Get knowledge edges for graph visualization."""
    deps = get_deps()
    pool = deps["pool"]

    # Build WHERE clause
    where_parts = ["ke.edge_type IN ('solved_by', 'caused_failure')"]
    params: list = []
    if edge_type:
        where_parts.append(f"ke.edge_type = ${len(params) + 1}")
        params.append(edge_type)

    where_clause = "WHERE " + " AND ".join(where_parts)

    # Get total count
    count_query = f"SELECT COUNT(*) FROM knowledge_edges ke {where_clause}"
    total = await pool.fetchval(count_query, *params)

    # Get edges - source is cluster, target is bullet
    query = f"""
        SELECT
            ke.edge_id::text,
            ke.source_id::text,
            ke.target_id::text,
            ke.edge_type,
            ke.weight,
            ke.evidence_count,
            ke.created_at
        FROM knowledge_edges ke
        {where_clause}
        ORDER BY ke.evidence_count DESC, ke.created_at DESC
        LIMIT ${len(params) + 1}
    """
    params.append(limit)

    rows = await pool.fetch(query, *params)

    edges = [
        EdgeResponse(
            edge_id=row["edge_id"],
            source_type="cluster",  # All edges are cluster->bullet
            source_id=row["source_id"],
            target_type="bullet",
            target_id=row["target_id"],
            edge_type=row["edge_type"],
            weight=float(row["weight"] or 0),
            evidence_count=row["evidence_count"] or 0,
            created_at=row["created_at"],
        )
        for row in rows
    ]

    return EdgeListResponse(
        edges=edges,
        total=total or 0,
    )


@router.get("/intelligence")
async def get_intelligence_report() -> dict[str, Any]:
    """Get combined LIBRARIAN + STRATEGIST analysis report."""
    deps = get_deps()
    pool = deps["pool"]

    # Knowledge gaps (clusters with failures but no solutions)
    gaps = await pool.fetch(
        """
        SELECT pc.cluster_id, pc.label, pc.failure_count, pc.success_count
        FROM problem_clusters pc
        LEFT JOIN knowledge_edges ke ON ke.source_id = pc.cluster_id
            AND ke.edge_type = 'solved_by'
        WHERE pc.failure_count >= 3
        GROUP BY pc.cluster_id, pc.label, pc.failure_count, pc.success_count
        HAVING COUNT(ke.edge_id) = 0
        ORDER BY pc.failure_count DESC
        LIMIT 10
        """
    )

    # Struggling clusters (have solutions but poor success rate)
    # turn_count is computed as success_count + failure_count
    struggling = await pool.fetch(
        """
        SELECT pc.cluster_id, pc.label,
               (pc.success_count + pc.failure_count) as turn_count,
               pc.success_count,
               ROUND(100.0 * pc.success_count / NULLIF(pc.success_count + pc.failure_count, 0), 1) as success_rate
        FROM problem_clusters pc
        WHERE (pc.success_count + pc.failure_count) >= 5
        ORDER BY success_rate ASC
        LIMIT 10
        """
    )

    # Harmful bullets
    harmful = await pool.fetch(
        """
        SELECT bullet_id, assertion, harmful_count, helpful_count
        FROM playbook_bullets
        WHERE harmful_count >= 5 AND harmful_count > helpful_count
          AND status NOT IN ('archived', 'banned')
        ORDER BY harmful_count DESC
        LIMIT 10
        """
    )

    return {
        "knowledge_gaps": [
            {
                "cluster_id": str(row["cluster_id"]),
                "label": row["label"],
                "failures": row["failure_count"],
                "successes": row["success_count"],
            }
            for row in gaps
        ],
        "struggling_clusters": [
            {
                "cluster_id": str(row["cluster_id"]),
                "label": row["label"],
                "turns": row["turn_count"],
                "success_rate": float(row["success_rate"] or 0),
            }
            for row in struggling
        ],
        "harmful_bullets": [
            {
                "id": str(row["bullet_id"]),
                "content": row["assertion"][:100] if row.get("assertion") else "",
                "harmful": row["harmful_count"],
                "helpful": row["helpful_count"],
            }
            for row in harmful
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/intelligence/run")
async def run_intelligence_analysis() -> dict[str, Any]:
    """Trigger intelligence analysis (archives harmful bullets)."""
    deps = get_deps()
    pool = deps["pool"]

    # Archive harmful bullets
    result = await pool.execute(
        """
        UPDATE playbook_bullets
        SET status = 'archived', updated_at = NOW()
        WHERE harmful_count >= 10 AND harmful_count > helpful_count * 2
          AND status NOT IN ('archived', 'banned')
        """
    )

    archived_count = int(result.split()[-1]) if result else 0

    logger.info("intelligence_run_complete", archived=archived_count)

    return {
        "status": "complete",
        "bullets_archived": archived_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/diagnostic/learning-health")
async def get_learning_health() -> dict[str, Any]:
    """Get learning system health diagnostics.

    Returns event drop metrics and processing health for observability.
    This endpoint helps identify silent failures in the learning pipeline.
    """
    from prometheus_client import REGISTRY

    # Import metrics to ensure they're registered before we collect them
    from core.common.observability import EVENTS_DROPPED, EVENTS_PROCESSED  # noqa: F401

    # Collect drop metrics from Prometheus
    drop_metrics: dict[str, dict[str, int]] = {}
    try:
        for metric in REGISTRY.collect():
            if metric.name == "alec_events_dropped_total":
                for sample in metric.samples:
                    if sample.name == "alec_events_dropped_total":
                        service = sample.labels.get("service", "unknown")
                        reason = sample.labels.get("drop_reason", "unknown")
                        if service not in drop_metrics:
                            drop_metrics[service] = {}
                        drop_metrics[service][reason] = int(sample.value)
    except Exception as e:
        logger.warning("metrics_collection_failed", error=str(e))

    # Collect processing metrics
    processed_metrics: dict[str, dict[str, int]] = {}
    try:
        for metric in REGISTRY.collect():
            if metric.name == "alec_events_processed_total":
                for sample in metric.samples:
                    if sample.name == "alec_events_processed_total":
                        service = sample.labels.get("service", "unknown")
                        status = sample.labels.get("status", "unknown")
                        if service not in processed_metrics:
                            processed_metrics[service] = {}
                        processed_metrics[service][status] = int(sample.value)
    except Exception as e:
        logger.warning("metrics_collection_failed", error=str(e))

    # Calculate health summary
    total_drops = sum(sum(v.values()) for v in drop_metrics.values())
    total_processed = sum(
        v.get("success", 0) for v in processed_metrics.values()
    )
    total_errors = sum(
        v.get("error", 0) for v in processed_metrics.values()
    )

    # Determine health status
    drop_rate = total_drops / max(total_processed + total_drops, 1)
    error_rate = total_errors / max(total_processed + total_errors, 1)

    if drop_rate > 0.05 or error_rate > 0.1:
        health_status = "unhealthy"
    elif drop_rate > 0.01 or error_rate > 0.05:
        health_status = "degraded"
    else:
        health_status = "healthy"

    return {
        "status": health_status,
        "summary": {
            "total_processed": total_processed,
            "total_dropped": total_drops,
            "total_errors": total_errors,
            "drop_rate": round(drop_rate * 100, 2),
            "error_rate": round(error_rate * 100, 2),
        },
        "drops_by_service": drop_metrics,
        "processed_by_service": processed_metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
