"""Unit tests for enhanced convergence metric types."""

from __future__ import annotations

import math

from alec.knowledge.domain import ConvergenceConfig, ConvergenceMetrics

# ── ConvergenceConfig defaults ────────────────────────────────


def test_convergence_config_defaults():
    """ConvergenceConfig has sensible defaults."""
    cfg = ConvergenceConfig()
    assert cfg.convergence_threshold == 3.0
    assert cfg.consecutive_cycles_required == 3
    assert cfg.novelty_decay is True
    assert cfg.max_reinforcement_per_entity_per_cycle == 3
    assert cfg.expansion_deceleration_cycles == 4
    assert cfg.source_dominance_threshold == 0.6


def test_convergence_config_custom():
    """ConvergenceConfig accepts custom values."""
    cfg = ConvergenceConfig(
        convergence_threshold=5.0,
        consecutive_cycles_required=5,
        novelty_decay=False,
        max_reinforcement_per_entity_per_cycle=10,
        expansion_deceleration_cycles=6,
        source_dominance_threshold=0.8,
    )
    assert cfg.convergence_threshold == 5.0
    assert cfg.novelty_decay is False
    assert cfg.max_reinforcement_per_entity_per_cycle == 10


# ── ConvergenceMetrics defaults ───────────────────────────────


def test_convergence_metrics_fields():
    """ConvergenceMetrics stores all required fields."""
    m = ConvergenceMetrics(
        raw_ratio=5.0,
        weighted_ratio=3.2,
        expansion_rate=10,
        expansion_acceleration=-2.0,
        per_source_ratios={"src1": 4.0, "src2": 2.5},
        primary_converged=True,
        secondary_converged=False,
    )
    assert m.raw_ratio == 5.0
    assert m.weighted_ratio == 3.2
    assert m.expansion_rate == 10
    assert m.expansion_acceleration == -2.0
    assert len(m.per_source_ratios) == 2
    assert m.primary_converged is True
    assert m.secondary_converged is False


def test_convergence_metrics_empty_sources():
    """ConvergenceMetrics works with empty per_source_ratios."""
    m = ConvergenceMetrics(
        raw_ratio=0.0,
        weighted_ratio=0.0,
        expansion_rate=0,
        expansion_acceleration=0.0,
        per_source_ratios={},
        primary_converged=False,
        secondary_converged=False,
    )
    assert m.per_source_ratios == {}
    assert m.primary_converged is False


# ── Novelty decay math ────────────────────────────────────────


def test_novelty_decay_formula():
    """Novelty decay: 1 / (ln(obs+2) * 1.4427) decreases with more observations."""
    def decay(obs: int) -> float:
        return 1.0 / (math.log(obs + 2) * 1.4427)

    # Entity with 1 observation should have higher weight than one with 100
    w1 = decay(1)
    w10 = decay(10)
    w100 = decay(100)

    assert w1 > w10 > w100
    # At obs=1: ln(3)*1.4427 ≈ 1.585, so weight ≈ 0.631
    assert abs(w1 - 1.0 / (math.log(3) * 1.4427)) < 0.001


def test_novelty_decay_never_negative():
    """Novelty decay is always positive for any non-negative observation count."""
    for obs in [0, 1, 5, 50, 500, 5000]:
        weight = 1.0 / (math.log(obs + 2) * 1.4427)
        assert weight > 0
