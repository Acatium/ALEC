"""Tests for consolidation domain types."""

from __future__ import annotations

from uuid import uuid4

from alec.errors import ConsolidationError
from alec.events.types import ConsolidationCompleted, ConsolidationStarted
from alec.knowledge.domain import (
    ConsolidationConfig,
    ConsolidationMaterial,
    ConsolidationResult,
    CrossLink,
    StaleEntity,
)


def test_consolidation_config_defaults():
    cfg = ConsolidationConfig()
    assert cfg.min_new_observations == 20
    assert cfg.min_interval_minutes == 15
    assert cfg.max_interval_minutes == 120
    assert cfg.max_entities_per_run == 30
    assert cfg.co_occurrence_threshold == 3
    assert cfg.embedding_similarity_threshold == 0.6


def test_consolidation_config_custom():
    cfg = ConsolidationConfig(min_new_observations=10, max_entities_per_run=50)
    assert cfg.min_new_observations == 10
    assert cfg.max_entities_per_run == 50


def test_stale_entity():
    eid = uuid4()
    se = StaleEntity(
        entity_id=eid,
        name="PaymentService",
        entity_type="service",
        observation_count=12,
        new_observations=5,
        has_existing_unit=True,
    )
    assert se.entity_id == eid
    assert se.name == "PaymentService"
    assert se.has_existing_unit is True


def test_consolidation_material():
    eid = uuid4()
    mat = ConsolidationMaterial(
        entity_id=eid,
        entity_name="OrderService",
        entity_type="service",
        aliases=["order-svc"],
        properties={"language": "python"},
        observations=[{"raw_text": "handles orders", "source_ref": "docs"}],
        relationships_outgoing=[{"to_name": "DB", "type": "writes_to"}],
        relationships_incoming=[{"from_name": "API", "type": "calls"}],
        alignments=[],
    )
    assert mat.entity_id == eid
    assert len(mat.observations) == 1
    assert len(mat.relationships_outgoing) == 1
    assert len(mat.relationships_incoming) == 1
    assert mat.aliases == ["order-svc"]


def test_cross_link():
    cl = CrossLink(
        entity_a_id=uuid4(),
        entity_a_name="UserService",
        entity_b_id=uuid4(),
        entity_b_name="AuthService",
        detection_method="co_occurrence",
        strength=5.0,
        detail="Co-appear in 5 observations",
    )
    assert cl.detection_method == "co_occurrence"
    assert cl.strength == 5.0


def test_cross_link_embedding():
    cl = CrossLink(
        entity_a_id=uuid4(),
        entity_a_name="UserService",
        entity_b_id=uuid4(),
        entity_b_name="ProfileService",
        detection_method="embedding_similarity",
        strength=0.85,
        detail="Consolidated summaries have 0.85 cosine similarity",
    )
    assert cl.detection_method == "embedding_similarity"
    assert cl.strength == 0.85


def test_consolidation_result():
    result = ConsolidationResult(
        entities_consolidated=10,
        units_created=7,
        units_updated=3,
        cross_links_detected=5,
        cross_links_recorded=4,
        errors=["Entity X synthesis failed"],
    )
    assert result.entities_consolidated == 10
    assert result.units_created == 7
    assert result.units_updated == 3
    assert len(result.errors) == 1


def test_consolidation_result_no_errors():
    result = ConsolidationResult(
        entities_consolidated=5,
        units_created=5,
        units_updated=0,
        cross_links_detected=0,
        cross_links_recorded=0,
        errors=[],
    )
    assert result.errors == []


def test_consolidation_error():
    err = ConsolidationError("synthesis failed")
    assert str(err) == "synthesis failed"
    assert isinstance(err, Exception)


def test_consolidation_started_event():
    eid = uuid4()
    event = ConsolidationStarted(engagement_id=eid, stale_entity_count=15)
    assert event.event_type == "consolidation.started"
    assert event.engagement_id == eid
    assert event.stale_entity_count == 15


def test_consolidation_completed_event():
    eid = uuid4()
    event = ConsolidationCompleted(
        engagement_id=eid,
        units_created=5,
        units_updated=3,
        cross_links_detected=2,
    )
    assert event.event_type == "consolidation.completed"
    assert event.units_created == 5
    assert event.units_updated == 3
    assert event.cross_links_detected == 2
