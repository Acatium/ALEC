"""Library (AKU) API routes (v4).

Endpoints for viewing and managing AKUs.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from core.common.observability import setup_logging
from core.session.api.models import BulletListResponse, BulletResponse, BulletUpdate

router = APIRouter()
logger = setup_logging("library-routes")


def get_pool():
    """Get database pool from global service."""
    from core.session.main import service
    return service.pool


@router.get("", response_model=BulletListResponse)
async def list_bullets(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> BulletListResponse:
    """List bullets with pagination and filters."""
    pool = get_pool()

    offset = (page - 1) * page_size

    # Build query
    conditions: list[str] = []
    params: list[str | int] = []
    param_idx = 1

    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    # category filter removed in v4 (no polarity column)

    if search:
        conditions.append(f"(situation ILIKE ${param_idx} OR assertion ILIKE ${param_idx})")
        params.append(f"%{search}%")
        param_idx += 1

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Validate sort column
    valid_sorts = ["created_at", "helpful_count", "harmful_count", "status"]
    if sort_by not in valid_sorts:
        sort_by = "created_at"

    order = "DESC" if sort_order.lower() == "desc" else "ASC"

    query = f"""
        SELECT aku_id, situation, assertion,
               helpful_count, harmful_count, neutral_count, status, created_at
        FROM akus {where_clause}
        ORDER BY {sort_by} {order}
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([page_size, offset])

    count_query = f"SELECT COUNT(*) FROM akus {where_clause}"

    rows = await pool.fetch(query, *params)
    total = await pool.fetchval(count_query, *params[:len(conditions)])

    bullets = [
        BulletResponse(
            id=str(row["aku_id"]),
            situation=row["situation"] or "",
            assertion=row["assertion"] or "",
            helpful_count=row.get("helpful_count", 0),
            harmful_count=row.get("harmful_count", 0),
            neutral_count=row.get("neutral_count", 0),
            status=row["status"],
            created_at=row["created_at"].isoformat() if row.get("created_at") else "",
        )
        for row in rows
    ]

    return BulletListResponse(
        bullets=bullets,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/{aku_id}", response_model=BulletResponse)
async def get_aku(aku_id: UUID) -> BulletResponse:
    """Get AKU by ID."""
    pool = get_pool()

    row = await pool.fetchrow(
        """
        SELECT aku_id, situation, assertion,
               helpful_count, harmful_count, neutral_count, status, created_at
        FROM akus WHERE aku_id = $1
        """,
        aku_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="AKU not found")

    return BulletResponse(
        id=str(row["aku_id"]),
        situation=row["situation"] or "",
        assertion=row["assertion"] or "",
        helpful_count=row.get("helpful_count", 0),
        harmful_count=row.get("harmful_count", 0),
        neutral_count=row.get("neutral_count", 0),
        status=row["status"],
        created_at=row["created_at"].isoformat() if row.get("created_at") else "",
    )


@router.patch("/{aku_id}", response_model=BulletResponse)
async def update_aku(aku_id: UUID, update: BulletUpdate) -> BulletResponse:
    """Update an AKU."""
    pool = get_pool()

    # Check exists
    existing = await pool.fetchrow(
        "SELECT aku_id FROM akus WHERE aku_id = $1",
        aku_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="AKU not found")

    # Build update
    updates: list[str] = []
    params: list[Any] = []
    param_idx = 1

    if update.content is not None:
        updates.append(f"assertion = ${param_idx}")
        params.append(update.content)
        param_idx += 1

    if update.status is not None:
        updates.append(f"status = ${param_idx}")
        params.append(update.status)
        param_idx += 1

    # category field ignored in v4 (no polarity column)

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    params.append(aku_id)

    query = f"""
        UPDATE akus
        SET {", ".join(updates)}
        WHERE aku_id = ${param_idx}
        RETURNING aku_id, situation, assertion,
                  helpful_count, harmful_count, neutral_count, status, created_at
    """

    row = await pool.fetchrow(query, *params)

    logger.info("aku_updated", aku_id=str(aku_id))

    return BulletResponse(
        id=str(row["aku_id"]),
        situation=row["situation"] or "",
        assertion=row["assertion"] or "",
        helpful_count=row.get("helpful_count", 0),
        harmful_count=row.get("harmful_count", 0),
        neutral_count=row.get("neutral_count", 0),
        status=row["status"],
        created_at=row["created_at"].isoformat() if row.get("created_at") else "",
    )


@router.delete("/{aku_id}")
async def archive_aku(aku_id: UUID) -> dict[str, Any]:
    """Archive an AKU (soft delete)."""
    pool = get_pool()

    result = await pool.execute(
        """
        UPDATE akus
        SET status = 'archived'
        WHERE aku_id = $1
        """,
        aku_id,
    )

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="AKU not found")

    logger.info("aku_archived", aku_id=str(aku_id))

    return {"status": "archived", "aku_id": str(aku_id)}
