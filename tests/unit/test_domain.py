"""Tests for knowledge domain types."""

from __future__ import annotations

from uuid import uuid4

from alec.knowledge.domain import (
    AlignmentOpp,
    Contradiction,
    ConvergenceConfig,
    Entity,
    Gap,
    Relationship,
    WorkerResult,
)
from alec.knowledge.repositories.projections import rank_issues


def test_entity_defaults():
    e = Entity(
        entity_id=uuid4(),
        engagement_id=uuid4(),
        name="TestService",
        entity_type="service",
    )
    assert e.status == "active"
    assert e.observation_count == 0
    assert e.aliases == []
    assert e.properties == {}


def test_relationship_defaults():
    r = Relationship(
        relationship_id=uuid4(),
        engagement_id=uuid4(),
        from_entity=uuid4(),
        to_entity=uuid4(),
        relationship_type="calls",
    )
    assert r.confidence == 0.5
    assert r.evidence == []


def test_worker_result():
    wr = WorkerResult(
        task_id=uuid4(),
        worker_id="w1",
        entities_written=5,
        relationships_written=3,
        observations_written=2,
        followups_suggested=1,
        scope_overflow=False,
    )
    assert wr.error is None
    assert wr.tokens_used == 0


def test_convergence_config_defaults():
    c = ConvergenceConfig()
    assert c.convergence_threshold == 3.0
    assert c.consecutive_cycles_required == 3


def test_rank_issues_unsurveyed_source_highest():
    gaps = [
        Gap(
            entity_id=uuid4(),
            name="local_files:./docs",
            entity_type="source",
            model_id=None,
            model_name=None,
            observation_count=0,
            reference_count=0,
            gap_type="unsurveyed_source",
        ),
        Gap(
            entity_id=uuid4(),
            name="some-service",
            entity_type="service",
            model_id=None,
            model_name=None,
            observation_count=1,
            reference_count=10,
            gap_type="unexplored_entity",
        ),
    ]
    ranked = rank_issues(gaps, [], [])
    assert ranked[0].issue_type == "gap"
    assert ranked[0].score == 100.0


def test_rank_issues_capped_at_8():
    gaps = [
        Gap(
            entity_id=uuid4(),
            name=f"entity-{i}",
            entity_type="service",
            model_id=None,
            model_name=None,
            observation_count=0,
            reference_count=i,
            gap_type="unexplored_entity",
        )
        for i in range(20)
    ]
    ranked = rank_issues(gaps, [], [])
    assert len(ranked) <= 8


def test_rank_issues_mixed_types():
    gap = Gap(
        entity_id=uuid4(),
        name="svc",
        entity_type="service",
        model_id=None,
        model_name=None,
        observation_count=0,
        reference_count=5,
        gap_type="unexplored_entity",
    )
    contradiction = Contradiction(
        from_entity=uuid4(),
        from_name="A",
        to_entity=uuid4(),
        to_name="B",
        type_a="calls",
        type_b="reads_from",
        evidence_a=[],
        evidence_b=[],
        confidence_a=0.9,
        confidence_b=0.8,
        contradiction_type="conflicting_relationship",
    )
    opp = AlignmentOpp(
        entity_a_id=uuid4(),
        entity_a_name="X",
        entity_a_type="service",
        model_a_name="M1",
        model_a_purpose=None,
        entity_b_id=uuid4(),
        entity_b_name="Y",
        entity_b_type="service",
        model_b_name="M2",
        model_b_purpose=None,
        similarity=0.85,
    )
    ranked = rank_issues([gap], [contradiction], [opp])
    assert len(ranked) == 3
    # Contradiction (30 + 0.9*20 = 48) > AlignmentOpp (20 + 0.85*15 = 32.75) > Gap (5*2 = 10)
    assert ranked[0].issue_type == "contradiction"
    assert ranked[1].issue_type == "alignment_opportunity"
    assert ranked[2].issue_type == "gap"
