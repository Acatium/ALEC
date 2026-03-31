"""Tests for fuzzy entity resolution in GraphWriter."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from alec.knowledge.domain import Entity
from alec.knowledge.graph_writer import GraphWriter


@pytest.fixture
def engagement_id():
    return uuid4()


@pytest.fixture
def model_id():
    return uuid4()


@pytest.fixture
def mock_entities():
    return AsyncMock()


@pytest.fixture
def mock_relationships():
    return AsyncMock()


@pytest.fixture
def mock_observations():
    return AsyncMock()


@pytest.fixture
def mock_embedder():
    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 384)
    return embedder


@pytest.fixture
def writer(
    engagement_id,
    model_id,
    mock_entities,
    mock_relationships,
    mock_observations,
    mock_embedder,
):
    # Default: string similarity returns no candidates
    mock_entities.find_by_normalized_prefix = AsyncMock(return_value=[])
    return GraphWriter(
        engagement_id=engagement_id,
        model_id=model_id,
        worker_id="test-worker",
        source_ref="test-source",
        entities=mock_entities,
        relationships=mock_relationships,
        observations=mock_observations,
        embedder=mock_embedder,
        similarity_threshold=0.85,
    )


def _make_entity(engagement_id, name="TestEntity", entity_type="service"):
    return Entity(
        entity_id=uuid4(),
        engagement_id=engagement_id,
        name=name,
        entity_type=entity_type,
    )


# ---------------------------------------------------------------------------
# _add_entity tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_name_match_returns_existing_entity(
    writer, mock_entities, engagement_id
):
    """When find_by_name returns an entity, _add_entity should update it, not create new."""
    existing = _make_entity(engagement_id, name="AuthService")
    mock_entities.find_by_name = AsyncMock(return_value=existing)

    result = await writer.execute(
        "add_entity",
        {"name": "AuthService", "entity_type": "service"},
    )

    # Should update, not create
    mock_entities.update_on_rediscovery.assert_awaited_once_with(
        existing.entity_id, [], {}
    )
    mock_entities.create.assert_not_awaited()
    assert writer.entities_written == 0
    assert "Updated existing entity" in result
    assert str(existing.entity_id) in result


@pytest.mark.asyncio
async def test_fuzzy_match_when_exact_name_fails(
    writer, mock_entities, mock_embedder, engagement_id
):
    """When find_by_name returns None but find_similar returns a match above threshold,
    should add the new name as an alias, return the matched entity, record as reinforcement,
    and NOT increment entities_written."""
    matched = _make_entity(engagement_id, name="Authentication Service")
    similarity = 0.92

    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_similar = AsyncMock(return_value=[(matched, similarity)])

    result = await writer.execute(
        "add_entity",
        {"name": "Auth Service", "entity_type": "service", "aliases": ["auth-svc"]},
    )

    # Embedding should be generated for the fuzzy search (name only, no entity_type)
    mock_embedder.embed.assert_awaited_once_with("Auth Service")

    # Should call find_similar with the right threshold
    mock_entities.find_similar.assert_awaited_once()
    call_args = mock_entities.find_similar.call_args
    assert (
        call_args.kwargs.get("threshold") == 0.85
        or call_args[1].get("threshold") == 0.85
        or call_args[0][2] == 0.85
    )

    # Should add the new name as an alias on the matched entity
    mock_entities.update_on_rediscovery.assert_awaited_once()
    rediscovery_args = mock_entities.update_on_rediscovery.call_args
    assert rediscovery_args[0][0] == matched.entity_id
    # The aliases should include the new name "Auth Service" and original aliases
    new_aliases = rediscovery_args[0][1]
    assert "Auth Service" in new_aliases
    assert "auth-svc" in new_aliases

    # Should NOT create a new entity
    mock_entities.create.assert_not_awaited()

    # Should NOT increment entities_written (it's a reinforcement)
    assert writer.entities_written == 0

    # Result should mention the fuzzy match
    assert "Matched" in result
    assert "Authentication Service" in result
    assert f"{similarity:.2f}" in result

    # Name should be cached
    assert "Auth Service" in writer._entity_cache
    assert writer._entity_cache["Auth Service"] == matched.entity_id


@pytest.mark.asyncio
async def test_no_match_creates_new_entity(
    writer, mock_entities, mock_embedder, engagement_id
):
    """When both find_by_name and find_similar return empty, should create new entity."""
    new_id = uuid4()
    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_similar = AsyncMock(return_value=[])
    mock_entities.create = AsyncMock(return_value=new_id)

    result = await writer.execute(
        "add_entity",
        {
            "name": "BrandNewService",
            "entity_type": "service",
            "aliases": ["bns"],
            "properties": {"version": "2.0"},
        },
    )

    # Should create a new entity
    mock_entities.create.assert_awaited_once()
    create_kwargs = mock_entities.create.call_args.kwargs
    assert create_kwargs["engagement_id"] == engagement_id
    assert create_kwargs["name"] == "BrandNewService"
    assert create_kwargs["entity_type"] == "service"
    assert create_kwargs["aliases"] == ["bns"]
    assert create_kwargs["properties"] == {"version": "2.0"}
    # Embedding should be passed through from the embed call
    assert create_kwargs["embedding"] == [0.1] * 384

    # Should increment entities_written
    assert writer.entities_written == 1

    # Result should indicate creation
    assert "Created entity" in result
    assert str(new_id) in result

    # Name should be cached
    assert writer._entity_cache["BrandNewService"] == new_id


@pytest.mark.asyncio
async def test_cache_hit_skips_db_lookup(
    writer, mock_entities, engagement_id
):
    """When entity is in local cache, should skip DB lookups entirely."""
    cached_id = uuid4()
    writer._entity_cache["CachedEntity"] = cached_id

    result = await writer.execute(
        "add_entity",
        {"name": "CachedEntity", "entity_type": "service"},
    )

    # Should NOT call find_by_name or find_similar
    mock_entities.find_by_name.assert_not_awaited()
    mock_entities.find_similar.assert_not_awaited()

    # Should update on rediscovery
    mock_entities.update_on_rediscovery.assert_awaited_once_with(cached_id, [], {})

    # Should not create
    mock_entities.create.assert_not_awaited()
    assert writer.entities_written == 0
    assert "Updated existing entity" in result


# ---------------------------------------------------------------------------
# _resolve_entity tests (used by _add_relationship)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_entity_cache_hit(writer, mock_entities):
    """_resolve_entity should return cached ID without DB access."""
    cached_id = uuid4()
    writer._entity_cache["MyEntity"] = cached_id

    resolved = await writer._resolve_entity("MyEntity")

    assert resolved == cached_id
    mock_entities.find_by_name.assert_not_awaited()
    mock_entities.find_similar.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_entity_exact_match(
    writer, mock_entities, engagement_id
):
    """_resolve_entity should find by exact name when not cached."""
    existing = _make_entity(engagement_id, name="ExactMatch")
    mock_entities.find_by_name = AsyncMock(return_value=existing)

    resolved = await writer._resolve_entity("ExactMatch")

    assert resolved == existing.entity_id
    mock_entities.find_by_name.assert_awaited_once()
    mock_entities.find_similar.assert_not_awaited()
    # Should be cached for future lookups
    assert writer._entity_cache["ExactMatch"] == existing.entity_id


@pytest.mark.asyncio
async def test_resolve_entity_fuzzy_match(
    writer, mock_entities, mock_embedder, engagement_id
):
    """_resolve_entity should use fuzzy matching when exact match fails."""
    matched = _make_entity(engagement_id, name="PostgreSQL Database")
    similarity = 0.90

    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_similar = AsyncMock(return_value=[(matched, similarity)])

    resolved = await writer._resolve_entity("Postgres DB")

    assert resolved == matched.entity_id

    # Should embed just the name (no entity type since resolve doesn't have one)
    mock_embedder.embed.assert_awaited_once_with("Postgres DB")

    # Should add the new name as alias on the matched entity
    mock_entities.update_on_rediscovery.assert_awaited_once_with(
        matched.entity_id, ["Postgres DB"], {}
    )

    # Should NOT create a new entity
    mock_entities.create.assert_not_awaited()

    # Should cache the resolved name
    assert writer._entity_cache["Postgres DB"] == matched.entity_id


@pytest.mark.asyncio
async def test_resolve_entity_no_match_creates(
    writer, mock_entities, mock_embedder, engagement_id
):
    """_resolve_entity should auto-create when no match is found."""
    new_id = uuid4()
    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_similar = AsyncMock(return_value=[])
    mock_entities.create = AsyncMock(return_value=new_id)

    resolved = await writer._resolve_entity("TotallyNew")

    assert resolved == new_id

    # Should create with entity_type "unknown" and auto_created property
    mock_entities.create.assert_awaited_once()
    create_kwargs = mock_entities.create.call_args.kwargs
    assert create_kwargs["name"] == "TotallyNew"
    assert create_kwargs["entity_type"] == "unknown"
    assert create_kwargs["properties"] == {"auto_created": True}

    # Should increment entities_written
    assert writer.entities_written == 1

    # Should cache
    assert writer._entity_cache["TotallyNew"] == new_id


# ---------------------------------------------------------------------------
# String similarity match tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_string_similarity_match_in_add_entity(
    writer, mock_entities, mock_embedder, engagement_id
):
    """When exact match fails but string similarity is high, should match
    without needing embeddings."""
    existing = _make_entity(engagement_id, name="BCBS 239", entity_type="policy")

    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_by_normalized_prefix = AsyncMock(return_value=[existing])

    result = await writer.execute(
        "add_entity",
        {"name": "BCBS-239 Compliance", "entity_type": "policy"},
    )

    # String similarity between "BCBS-239 Compliance" and "BCBS 239" should
    # be >= 0.70 (containment of {bcbs,239} in {bcbs,239,compliance} = 1.0 * 0.9)
    assert "Matched" in result
    assert "BCBS 239" in result
    assert "string similarity" in result

    # Should NOT need embedding
    mock_embedder.embed.assert_not_awaited()

    # Should cache
    assert "BCBS-239 Compliance" in writer._entity_cache
    assert writer._entity_cache["BCBS-239 Compliance"] == existing.entity_id


@pytest.mark.asyncio
async def test_string_similarity_no_match_falls_through(
    writer, mock_entities, mock_embedder, engagement_id
):
    """When string similarity is below threshold, should fall through to embedding."""
    unrelated = _make_entity(engagement_id, name="Apple Inc.", entity_type="company")

    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_by_normalized_prefix = AsyncMock(return_value=[unrelated])
    mock_entities.find_similar = AsyncMock(return_value=[])
    new_id = uuid4()
    mock_entities.create = AsyncMock(return_value=new_id)

    result = await writer.execute(
        "add_entity",
        {"name": "Banana Corp.", "entity_type": "company"},
    )

    # String similarity should be too low, so it falls through to embedding
    mock_embedder.embed.assert_awaited_once_with("Banana Corp.")
    assert "Created entity" in result


@pytest.mark.asyncio
async def test_string_similarity_resolve_in_relationship(
    writer, mock_entities, mock_embedder, engagement_id
):
    """_resolve_entity should use string similarity before embedding."""
    existing = _make_entity(engagement_id, name="Data Lineage", entity_type="concept")

    mock_entities.find_by_name = AsyncMock(return_value=None)
    mock_entities.find_by_normalized_prefix = AsyncMock(return_value=[existing])

    resolved = await writer._resolve_entity("Data Lineage (Concept)")

    assert resolved == existing.entity_id
    # Should NOT need embedding
    mock_embedder.embed.assert_not_awaited()
    assert writer._entity_cache["Data Lineage (Concept)"] == existing.entity_id
