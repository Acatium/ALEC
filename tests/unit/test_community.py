"""Unit tests for community detection module."""

from __future__ import annotations

from uuid import uuid4

from alec.knowledge.community import _detect_communities, format_community_summary
from alec.knowledge.domain import CommunityResult

# ── _detect_communities tests ─────────────────────────────────


def test_detect_communities_too_few_entities():
    """Returns None when fewer than 5 entities."""
    entities = [(str(uuid4()), f"e{i}") for i in range(4)]
    result = _detect_communities(entities, [])
    assert result is None


def test_detect_communities_no_relationships():
    """All entities are isolated when there are no relationships."""
    entities = [(str(uuid4()), f"entity_{i}") for i in range(6)]
    result = _detect_communities(entities, [])
    assert result is not None
    assert result.community_count == 0
    assert result.communities == {}
    assert len(result.isolated_entities) == 6
    assert result.hub_entities == []
    assert result.bridge_entities == []


def test_detect_communities_two_clusters():
    """Two clear clusters should be detected."""
    # Cluster 1: a-b-c fully connected
    ids = [str(uuid4()) for _ in range(6)]
    entities = [(ids[i], f"node_{i}") for i in range(6)]
    relationships = [
        # Cluster 1
        (ids[0], ids[1], 0.9),
        (ids[1], ids[2], 0.9),
        (ids[0], ids[2], 0.9),
        # Cluster 2
        (ids[3], ids[4], 0.9),
        (ids[4], ids[5], 0.9),
        (ids[3], ids[5], 0.9),
    ]

    result = _detect_communities(entities, relationships)
    assert result is not None
    assert result.community_count == 2
    assert result.entity_count == 6
    assert result.modularity is not None
    assert result.modularity > 0  # Two clear clusters should have positive modularity


def test_detect_communities_hub_detection():
    """A node connected to many others should be detected as a hub."""
    # Star graph: center connected to 9 others
    ids = [str(uuid4()) for _ in range(10)]
    entities = [(ids[i], f"node_{i}") for i in range(10)]
    center = ids[0]
    relationships = [(center, ids[i], 0.8) for i in range(1, 10)]

    result = _detect_communities(entities, relationships)
    assert result is not None
    assert "node_0" in result.hub_entities


def test_detect_communities_bridge_detection():
    """A node connecting two clusters should be detected as a bridge."""
    # Two clusters connected by a bridge node
    ids = [str(uuid4()) for _ in range(7)]
    entities = [(ids[i], f"node_{i}") for i in range(7)]
    relationships = [
        # Cluster 1: 0-1-2
        (ids[0], ids[1], 0.9),
        (ids[1], ids[2], 0.9),
        (ids[0], ids[2], 0.9),
        # Cluster 2: 4-5-6
        (ids[4], ids[5], 0.9),
        (ids[5], ids[6], 0.9),
        (ids[4], ids[6], 0.9),
        # Bridge: 3 connects to both
        (ids[3], ids[0], 0.5),
        (ids[3], ids[4], 0.5),
    ]

    result = _detect_communities(entities, relationships)
    assert result is not None
    # node_3 should be a bridge (connects to nodes in different communities)
    assert "node_3" in result.bridge_entities


def test_detect_communities_entity_count():
    """entity_count should match the number of input entities."""
    ids = [str(uuid4()) for _ in range(8)]
    entities = [(ids[i], f"e_{i}") for i in range(8)]
    rels = [(ids[0], ids[1], 0.5)]

    result = _detect_communities(entities, rels)
    assert result is not None
    assert result.entity_count == 8


# ── format_community_summary tests ───────────────────────────


def test_format_community_summary_basic():
    """Format summary includes key information."""
    result = CommunityResult(
        entity_count=10,
        community_count=2,
        modularity=0.45,
        communities={0: ["Alice", "Bob"], 1: ["Carol", "Dave"]},
        hub_entities=["Alice"],
        bridge_entities=["Eve"],
        isolated_entities=["Frank"],
    )
    text = format_community_summary(result)
    assert "Community Structure" in text
    assert "2 communities" in text
    assert "10 entities" in text
    assert "0.450" in text
    assert "Alice" in text
    assert "Hubs:" in text
    assert "Bridges:" in text
    assert "Isolated" in text


def test_format_community_summary_empty():
    """Format summary handles empty communities."""
    result = CommunityResult(
        entity_count=5,
        community_count=0,
        modularity=None,
        communities={},
        hub_entities=[],
        bridge_entities=[],
        isolated_entities=["a", "b", "c", "d", "e"],
    )
    text = format_community_summary(result)
    assert "0 communities" in text
    assert "Isolated (5)" in text
    assert "Hubs" not in text
    assert "Bridges" not in text


def test_format_community_summary_large_cluster():
    """Large clusters show preview with count."""
    result = CommunityResult(
        entity_count=20,
        community_count=1,
        modularity=0.0,
        communities={0: [f"entity_{i}" for i in range(15)]},
        hub_entities=[],
        bridge_entities=[],
        isolated_entities=[],
    )
    text = format_community_summary(result)
    assert "+10 more" in text
