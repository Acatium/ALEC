"""Property-based tests for ranking logic using Hypothesis."""

from __future__ import annotations

from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from alec.knowledge.domain import Gap
from alec.knowledge.repositories.projections import rank_issues


def _make_gap(entity_id=None, reference_count=5):
    return Gap(
        entity_id=entity_id or uuid4(),
        name="TestEntity",
        entity_type="service",
        model_id=None,
        model_name=None,
        observation_count=1,
        reference_count=reference_count,
        gap_type="unexplored_entity",
    )


@given(ref_count=st.integers(min_value=0, max_value=10000))
@settings(max_examples=50)
def test_important_always_increases_score(ref_count):
    """Property: 'important' annotation always increases score, for any ref_count."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=ref_count)]

    base = rank_issues(gaps, [], [])
    boosted = rank_issues(gaps, [], [], entity_annotations={eid: ["important"]})

    assert boosted[0].score > base[0].score


@given(ref_count=st.integers(min_value=0, max_value=10000))
@settings(max_examples=50)
def test_dismiss_always_decreases_score(ref_count):
    """Property: 'dismiss' annotation always decreases score, for any ref_count."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=ref_count)]

    base = rank_issues(gaps, [], [])
    dismissed = rank_issues(gaps, [], [], entity_annotations={eid: ["dismiss"]})

    assert dismissed[0].score < base[0].score


@given(ref_count=st.integers(min_value=0, max_value=10000))
@settings(max_examples=50)
def test_authoritative_always_gte_reference(ref_count):
    """Property: authoritative tier score always >= reference tier score."""
    eid = uuid4()
    gaps = [_make_gap(entity_id=eid, reference_count=ref_count)]

    reference = rank_issues(gaps, [], [], entity_trust_tiers={eid: "reference"})
    authoritative = rank_issues(gaps, [], [], entity_trust_tiers={eid: "authoritative"})

    assert authoritative[0].score >= reference[0].score
