"""Shared entity merge logic — used by both API and dedup sweep."""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()


async def merge_entities(
    conn: asyncpg.Connection,
    engagement_id: str | UUID,
    target_id: str | UUID,
    source_id: str | UUID,
) -> dict[str, object]:
    """Merge source_entity INTO target entity. Source is deleted.

    Must be called inside a transaction. Returns the updated target row dict.
    """
    eid = str(engagement_id)
    tid = str(target_id)
    sid = str(source_id)

    target = await conn.fetchrow(
        "SELECT * FROM entities WHERE entity_id = $1::uuid AND engagement_id = $2::uuid",
        tid, eid,
    )
    source = await conn.fetchrow(
        "SELECT * FROM entities WHERE entity_id = $1::uuid AND engagement_id = $2::uuid",
        sid, eid,
    )
    if target is None:
        raise ValueError(f"Target entity {tid} not found")
    if source is None:
        raise ValueError(f"Source entity {sid} not found")

    # Delete relationships that would become self-referencing after reassignment
    # (source → target or target → source becomes target → target)
    await conn.execute(
        """
        DELETE FROM relationships
        WHERE engagement_id = $3::uuid
          AND (
              (from_entity = $2::uuid AND to_entity = $1::uuid)
              OR (from_entity = $1::uuid AND to_entity = $2::uuid)
          )
        """,
        tid, sid, eid,
    )

    # Merge conflicting relationship triples (from_entity side)
    await conn.execute(
        """
        UPDATE relationships tgt SET
            evidence = tgt.evidence || src.evidence,
            confidence = GREATEST(tgt.confidence, src.confidence),
            last_confirmed = GREATEST(tgt.last_confirmed, src.last_confirmed)
        FROM relationships src
        WHERE src.engagement_id = $3::uuid
          AND tgt.engagement_id = $3::uuid
          AND src.from_entity = $2::uuid
          AND tgt.from_entity = $1::uuid
          AND src.to_entity = tgt.to_entity
          AND src.relationship_type = tgt.relationship_type
        """,
        tid, sid, eid,
    )
    await conn.execute(
        """
        DELETE FROM relationships src
        USING relationships tgt
        WHERE src.engagement_id = $3::uuid
          AND tgt.engagement_id = $3::uuid
          AND src.from_entity = $2::uuid
          AND tgt.from_entity = $1::uuid
          AND src.to_entity = tgt.to_entity
          AND src.relationship_type = tgt.relationship_type
        """,
        tid, sid, eid,
    )

    # Merge conflicting relationship triples (to_entity side)
    await conn.execute(
        """
        UPDATE relationships tgt SET
            evidence = tgt.evidence || src.evidence,
            confidence = GREATEST(tgt.confidence, src.confidence),
            last_confirmed = GREATEST(tgt.last_confirmed, src.last_confirmed)
        FROM relationships src
        WHERE src.engagement_id = $3::uuid
          AND tgt.engagement_id = $3::uuid
          AND src.to_entity = $2::uuid
          AND tgt.to_entity = $1::uuid
          AND src.from_entity = tgt.from_entity
          AND src.relationship_type = tgt.relationship_type
        """,
        tid, sid, eid,
    )
    await conn.execute(
        """
        DELETE FROM relationships src
        USING relationships tgt
        WHERE src.engagement_id = $3::uuid
          AND tgt.engagement_id = $3::uuid
          AND src.to_entity = $2::uuid
          AND tgt.to_entity = $1::uuid
          AND src.from_entity = tgt.from_entity
          AND src.relationship_type = tgt.relationship_type
        """,
        tid, sid, eid,
    )

    # Reassign remaining relationships
    await conn.execute(
        "UPDATE relationships SET from_entity = $1::uuid "
        "WHERE from_entity = $2::uuid AND engagement_id = $3::uuid",
        tid, sid, eid,
    )
    await conn.execute(
        "UPDATE relationships SET to_entity = $1::uuid "
        "WHERE to_entity = $2::uuid AND engagement_id = $3::uuid",
        tid, sid, eid,
    )

    # Clean up any remaining self-referencing relationships
    await conn.execute(
        "DELETE FROM relationships WHERE from_entity = to_entity "
        "AND engagement_id = $1::uuid",
        eid,
    )

    # Reassign annotations
    await conn.execute(
        "UPDATE user_annotations SET entity_id = $1::uuid "
        "WHERE entity_id = $2::uuid AND engagement_id = $3::uuid",
        tid, sid, eid,
    )

    # Reassign consolidated units
    await conn.execute(
        "UPDATE consolidated_units SET subject_entity = $1::uuid "
        "WHERE subject_entity = $2::uuid AND engagement_id = $3::uuid",
        tid, sid, eid,
    )

    # Merge aliases
    source_aliases = list(source["aliases"]) if source["aliases"] else []
    source_aliases.append(source["name"])
    target_aliases = list(target["aliases"]) if target["aliases"] else []
    merged_aliases = list(set(target_aliases + source_aliases))

    # Merge properties
    target_props = target["properties"] if isinstance(target["properties"], dict) else {}
    source_props = source["properties"] if isinstance(source["properties"], dict) else {}
    merged_props = {**source_props, **target_props}

    # Update target with merged data
    updated = await conn.fetchrow(
        """
        UPDATE entities SET
            aliases = $3,
            properties = $4::jsonb,
            observation_count = observation_count + $5,
            last_referenced = NOW()
        WHERE entity_id = $1::uuid AND engagement_id = $2::uuid
        RETURNING entity_id, name, entity_type, observation_count, properties
        """,
        tid, eid, merged_aliases, json.dumps(merged_props),
        source["observation_count"],
    )

    # Delete the source entity
    await conn.execute(
        "DELETE FROM entities WHERE entity_id = $1::uuid AND engagement_id = $2::uuid",
        sid, eid,
    )

    logger.info(
        "merge.completed",
        target=target["name"],
        source=source["name"],
        engagement_id=eid,
    )

    return dict(updated)
