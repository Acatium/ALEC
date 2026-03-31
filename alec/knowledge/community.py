"""Community detection on the knowledge graph using networkx."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from uuid import UUID

import asyncpg
import structlog

from alec.knowledge.domain import CommunityResult

logger = structlog.get_logger()


async def run_community_detection(
    engagement_id: UUID,
    cycle_number: int,
    pool: asyncpg.Pool,
) -> CommunityResult | None:
    """Query entities/relationships, detect communities, store results.

    Returns CommunityResult or None if too few entities.
    """
    async with pool.acquire() as conn:
        entity_rows = await conn.fetch(
            """
            SELECT entity_id, name FROM entities
            WHERE engagement_id = $1 AND status = 'active'
            """,
            engagement_id,
        )
        rel_rows = await conn.fetch(
            """
            SELECT from_entity, to_entity, confidence
            FROM relationships
            WHERE engagement_id = $1
            """,
            engagement_id,
        )

    entities = [(str(r["entity_id"]), r["name"]) for r in entity_rows]
    relationships = [
        (str(r["from_entity"]), str(r["to_entity"]), r["confidence"])
        for r in rel_rows
    ]

    # Run CPU-bound detection in executor
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, partial(_detect_communities, entities, relationships)
    )

    if result is None:
        return None

    result.engagement_id = engagement_id
    result.cycle_number = cycle_number

    # Store in database
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO community_analysis
                (engagement_id, cycle_number, algorithm, entity_count,
                 community_count, modularity, communities,
                 hub_entities, bridge_entities, isolated_entities)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            engagement_id,
            cycle_number,
            result.algorithm,
            result.entity_count,
            result.community_count,
            result.modularity,
            json.dumps(
                {str(k): v for k, v in result.communities.items()}
            ),
            json.dumps(result.hub_entities),
            json.dumps(result.bridge_entities),
            json.dumps(result.isolated_entities),
        )

    return result


def _detect_communities(
    entities: list[tuple[str, str]],
    relationships: list[tuple[str, str, float]],
) -> CommunityResult | None:
    """Sync community detection. Runs in executor.

    Args:
        entities: list of (entity_id, name)
        relationships: list of (from_id, to_id, confidence)

    Returns CommunityResult or None if <5 entities.
    """
    import networkx as nx

    if len(entities) < 5:
        return None

    id_to_name = {eid: name for eid, name in entities}

    graph = nx.Graph()
    for eid, name in entities:
        graph.add_node(eid, name=name)

    for from_id, to_id, confidence in relationships:
        if from_id in graph and to_id in graph:
            graph.add_edge(from_id, to_id, weight=confidence)

    # Handle no-edge case: all isolated
    if graph.number_of_edges() == 0:
        return CommunityResult(
            entity_count=len(entities),
            community_count=0,
            modularity=None,
            communities={},
            hub_entities=[],
            bridge_entities=[],
            isolated_entities=[id_to_name[eid] for eid, _ in entities],
        )

    # Louvain community detection
    communities_gen = nx.community.louvain_communities(graph, seed=42)
    community_sets = list(communities_gen)

    # Compute modularity
    modularity = nx.community.modularity(graph, community_sets)

    # Build community map: community_idx -> list of entity names
    communities: dict[int, list[str]] = {}
    node_to_community: dict[str, int] = {}
    for idx, comm_set in enumerate(community_sets):
        communities[idx] = [id_to_name[n] for n in comm_set if n in id_to_name]
        for n in comm_set:
            node_to_community[n] = idx

    # Hub detection: top 10% by degree, degree > 1
    degrees = dict(graph.degree())
    if degrees:
        sorted_degrees = sorted(degrees.values(), reverse=True)
        threshold_idx = max(1, len(sorted_degrees) // 10)
        degree_threshold = sorted_degrees[min(threshold_idx, len(sorted_degrees) - 1)]
        degree_threshold = max(degree_threshold, 2)
        hubs = [
            id_to_name[n]
            for n, d in degrees.items()
            if d >= degree_threshold and n in id_to_name
        ]
    else:
        hubs = []

    # Bridge detection: nodes whose neighbors span multiple communities
    bridges = []
    for node in graph.nodes():
        if node not in node_to_community:
            continue
        neighbor_comms = {
            node_to_community[nb]
            for nb in graph.neighbors(node)
            if nb in node_to_community
        }
        if len(neighbor_comms) > 1:
            bridges.append(id_to_name[node])

    # Isolated: degree-0 nodes
    isolated = [
        id_to_name[n]
        for n in graph.nodes()
        if degrees.get(n, 0) == 0 and n in id_to_name
    ]

    return CommunityResult(
        entity_count=len(entities),
        community_count=len(community_sets),
        modularity=modularity,
        communities=communities,
        hub_entities=hubs,
        bridge_entities=bridges,
        isolated_entities=isolated,
    )


def format_community_summary(result: CommunityResult) -> str:
    """Format CommunityResult into a text section for the coordinator projection."""
    lines = ["## Community Structure"]
    lines.append(
        f"  {result.community_count} communities detected "
        f"across {result.entity_count} entities"
    )
    if result.modularity is not None:
        lines.append(f"  Modularity: {result.modularity:.3f}")

    for idx, members in sorted(result.communities.items()):
        preview = ", ".join(members[:5])
        suffix = f" (+{len(members) - 5} more)" if len(members) > 5 else ""
        lines.append(f"  Cluster {idx}: {preview}{suffix}")

    if result.hub_entities:
        lines.append(f"  Hubs: {', '.join(result.hub_entities[:10])}")
    if result.bridge_entities:
        lines.append(f"  Bridges: {', '.join(result.bridge_entities[:10])}")
    if result.isolated_entities:
        lines.append(
            f"  Isolated ({len(result.isolated_entities)}): "
            f"{', '.join(result.isolated_entities[:5])}"
        )

    return "\n".join(lines)
