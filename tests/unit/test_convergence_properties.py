"""Property-based tests for convergence metrics using Hypothesis."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st


def _novelty_decay(obs: int) -> float:
    """Reproduce the novelty decay formula from the convergence logic."""
    return 1.0 / (math.log(obs + 2) * 1.4427)


@given(obs=st.integers(min_value=0, max_value=100000))
@settings(max_examples=100)
def test_novelty_decay_always_positive(obs):
    """Property: novelty decay weight is always positive for any non-negative obs count."""
    weight = _novelty_decay(obs)
    assert weight > 0


@given(obs=st.integers(min_value=0, max_value=99999))
@settings(max_examples=100)
def test_novelty_decay_strictly_decreasing(obs):
    """Property: adding one more observation always decreases the weight."""
    w_current = _novelty_decay(obs)
    w_next = _novelty_decay(obs + 1)
    assert w_next < w_current


@given(obs=st.integers(min_value=0, max_value=100000))
@settings(max_examples=100)
def test_novelty_decay_bounded_below_one(obs):
    """Property: novelty decay weight is always below 1.0."""
    weight = _novelty_decay(obs)
    assert weight < 1.0
