"""Unit tests for trust tier + annotation ranking."""

from __future__ import annotations

from uuid import uuid4

import pytest

from alec.knowledge.domain import AlignmentOpp, Contradiction, Gap
from alec.knowledge.repositories.projections import rank_issues


def _make_gap(entity_id=None, reference_count=5, gap_type="unexplored_entity"):
    return Gap(
        entity_id=entity_id or uuid4(),
        name="TestEntity",
        entity_type="service",
        model_id=None,
        model_name=None,
        observation_count=1,
        reference_count=reference_count,
        gap_type=gap_type,
    )


def _make_contradiction(from_entity=None):
    return Contradiction(
        from_entity=from_entity or uuid4(),
        from_name="A",
        to_entity=uuid4(),
        to_name="B",
        type_a="calls",
        type_b="reads_from",
        evidence_a=[],
        evidence_b=[],
        confidence_a=0.8,
        confidence_b=0.7,
        contradiction_type="conflicting_relationship",
    )


def _make_alignment_opp(entity_a_id=None):
    return AlignmentOpp(
        entity_a_id=entity_a_id or uuid4(),
        entity_a_name="X",
        entity_a_type="service",
        model_a_name="M1",
        model_a_purpose=None,
        entity_b_id=uuid4(),
        entity_b_name="Y",
        entity_b_type="service",
        model_b_name="M2",
        model_b_purpose=None,
        similarity=0.8,
    )


# ── Baseline behavior preserved ──────────────────────────────


def test_rank_issues_baseline():
    """Without annotations/trust, scoring works as before."""
    gaps = [_make_gap(reference_count=5)]
    contradictions = [_make_contradiction()]
    alignment_opps = [_make_alignment_opp()]

    result = rank_issues(gaps, contradictions, alignment_opps)

    assert len(result) == 3
    # Contradiction: 30 + 0.8*20 = 46.0
    # Gap: 5*2 = 10.0
    # Alignment: 20 + 0.8*15 = 32.0
    assert result[0].issue_type == "contradiction"
    assert result[1].issue_type == "alignment_opportunity"
    assert result[2].issue_type == "gap"


def test_rank_issues_no_annotations_no_tiers():
    """Explicit None for annotations and tiers works like baseline."""
    gaps = [_make_gap()]
    result_a = rank_issues(gaps, [], [])
    result_b = rank_issues(gaps, [], [], entity_annotations=None, entity_trust_tiers=None)
    assert result_a[0].score == result_b[0].score


# ── Annotation modifiers (parametrized) ──────────────────────


@pytest.mark.parametrize(
    "annotation_type, expected_delta",
    [
        ("important", 25.0),
        ("explore_more", 15.0),
        ("dismiss", -50.0),
        ("correction", 10.0),
        ("note", 5.0),
    ],
)
def test_annotation_modifier(annotation_type, expected_delta):
    """Each annotation type applies its expected score delta."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=5)]

    base = rank_issues(gaps, [], [])
    modified = rank_issues(gaps, [], [], entity_annotations={eid: [annotation_type]})

    assert modified[0].score == base[0].score + expected_delta


def test_multiple_annotations_stack():
    """Multiple annotations stack additively."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=5)]

    base = rank_issues(gaps, [], [])
    stacked = rank_issues(
        gaps, [], [],
        entity_annotations={eid: ["important", "explore_more"]},
    )

    assert stacked[0].score == base[0].score + 25.0 + 15.0


# ── Trust tier multipliers (parametrized) ────────────────────


@pytest.mark.parametrize(
    "tier, multiplier",
    [
        ("authoritative", 1.3),
        ("analytical", 1.1),
        ("reference", 1.0),
    ],
)
def test_trust_tier_multiplier(tier, multiplier):
    """Each trust tier applies its expected multiplier."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=5)]

    base = rank_issues(gaps, [], [])
    result = rank_issues(gaps, [], [], entity_trust_tiers={eid: tier})

    assert abs(result[0].score - base[0].score * multiplier) < 0.01


# ── Combined stacking (parametrized) ────────────────────────


@pytest.mark.parametrize(
    "annotations, tier, expected_score",
    [
        # Base: 5*2=10, +25 (important) = 35, *1.3 (authoritative) = 45.5
        (["important"], "authoritative", 45.5),
        # Base: 10, +15 (explore_more) = 25, *1.1 (analytical) = 27.5
        (["explore_more"], "analytical", 27.5),
        # Base: 10, +25+15 (important+explore_more) = 50, *1.3 (authoritative) = 65.0
        (["important", "explore_more"], "authoritative", 65.0),
    ],
)
def test_annotation_plus_trust_tier_combined(annotations, tier, expected_score):
    """Annotations are additive, then trust tier multiplies."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=5)]

    result = rank_issues(
        gaps, [], [],
        entity_annotations={eid: annotations},
        entity_trust_tiers={eid: tier},
    )

    assert abs(result[0].score - expected_score) < 0.01


# ── Edge cases ────────────────────────────────────────────────


def test_unknown_entity_id_no_crash():
    """Annotations for entity IDs not in the issues are ignored."""
    unknown_eid = uuid4()
    gaps = [_make_gap()]

    # Should not crash even if annotation references an unknown entity
    result = rank_issues(
        gaps, [], [],
        entity_annotations={unknown_eid: ["important"]},
    )
    assert len(result) == 1


def test_contradiction_uses_from_entity():
    """Contradiction scoring uses from_entity for annotation lookup."""
    eid = uuid4()
    contradiction = _make_contradiction(from_entity=eid)

    base = rank_issues([], [contradiction], [])
    boosted = rank_issues(
        [], [contradiction], [],
        entity_annotations={eid: ["important"]},
    )

    assert boosted[0].score == base[0].score + 25.0


def test_alignment_opp_uses_entity_a_id():
    """AlignmentOpp scoring uses entity_a_id for annotation lookup."""
    eid = uuid4()
    opp = _make_alignment_opp(entity_a_id=eid)

    base = rank_issues([], [], [opp])
    boosted = rank_issues(
        [], [], [opp],
        entity_annotations={eid: ["important"]},
    )

    assert boosted[0].score == base[0].score + 25.0


def test_rank_issues_still_returns_top_8():
    """Result is capped at 8 even with many issues."""
    gaps = [_make_gap(reference_count=i) for i in range(15)]
    result = rank_issues(gaps, [], [])
    assert len(result) == 8
