"""Unit tests for effect size calculations."""


import numpy as np
import pytest

from evaluation.analysis.effect_sizes import (
    calculate_sample_size_for_effect,
    cohens_d,
    cohens_h,
    interpret_effect_size,
    odds_ratio,
    relative_risk,
)


class TestCohensD:
    """Tests for Cohen's d effect size."""

    def test_large_effect(self):
        """Test detection of large effect size."""
        # Two groups with large difference
        baseline = np.array([5, 6, 4, 7, 5, 6])
        treatment = np.array([2, 3, 1, 2, 2, 3])

        d = cohens_d(baseline, treatment)

        assert abs(d) > 0.8, "Should detect large effect"
        assert d < 0, "Treatment reduces iterations (negative d)"
        assert interpret_effect_size('cohens_d', d) == "large"

    def test_medium_effect(self):
        """Test detection of medium effect size."""
        baseline = np.array([100, 110, 95, 105, 100])
        treatment = np.array([90, 95, 85, 92, 88])

        d = cohens_d(baseline, treatment)

        assert 0.5 <= abs(d) < 0.8, "Should detect medium effect"
        assert interpret_effect_size('cohens_d', d) == "medium"

    def test_small_effect(self):
        """Test detection of small effect size."""
        baseline = np.array([100, 102, 98, 101, 99])
        treatment = np.array([97, 99, 95, 98, 96])

        d = cohens_d(baseline, treatment)

        assert 0.2 <= abs(d) < 0.5, "Should detect small effect"
        assert interpret_effect_size('cohens_d', d) == "small"

    def test_negligible_effect(self):
        """Test when effect is negligible."""
        baseline = np.array([100, 102, 98, 101, 99])
        treatment = np.array([100, 101, 99, 100, 100])

        d = cohens_d(baseline, treatment)

        assert abs(d) < 0.2, "Should detect negligible effect"
        assert interpret_effect_size('cohens_d', d) == "negligible"

    def test_pooled_vs_control_std(self):
        """Test difference between pooled and control-group std."""
        baseline = np.array([100, 120, 80, 110, 90])  # High variance
        treatment = np.array([95, 96, 94, 95, 95])    # Low variance

        d_pooled = cohens_d(baseline, treatment, pooled=True)
        d_control = cohens_d(baseline, treatment, pooled=False)

        # Should give different results due to variance difference
        assert d_pooled != d_control

    def test_zero_std_raises_error(self):
        """Test error when standard deviation is zero."""
        baseline = np.array([100, 100, 100])
        treatment = np.array([90, 90, 90])

        with pytest.raises(ValueError, match="Standard deviation is zero"):
            cohens_d(baseline, treatment, pooled=False)

    def test_empty_arrays(self):
        """Test error when arrays are empty."""
        with pytest.raises(ValueError, match="must not be empty"):
            cohens_d(np.array([]), np.array([1, 2, 3]))


class TestCohensH:
    """Tests for Cohen's h effect size."""

    def test_large_proportion_difference(self):
        """Test large difference in proportions."""
        h = cohens_h(0.30, 0.70)

        assert abs(h) > 0.8, "Should detect large effect"
        assert interpret_effect_size('cohens_h', h) == "large"

    def test_medium_proportion_difference(self):
        """Test medium difference in proportions."""
        h = cohens_h(0.50, 0.70)

        assert 0.5 <= abs(h) < 0.8, "Should detect medium effect"
        assert interpret_effect_size('cohens_h', h) in ["medium", "small"]

    def test_small_proportion_difference(self):
        """Test small difference in proportions."""
        h = cohens_h(0.50, 0.60)

        assert 0.2 <= abs(h) < 0.5, "Should detect small effect"
        assert interpret_effect_size('cohens_h', h) == "small"

    def test_no_difference(self):
        """Test when proportions are equal."""
        h = cohens_h(0.50, 0.50)

        assert abs(h) < 0.01, "Should be near zero"
        assert interpret_effect_size('cohens_h', h) == "negligible"

    def test_extreme_proportions(self):
        """Test with extreme proportions (0 and 1)."""
        h = cohens_h(0.0, 1.0)

        assert abs(h) > 3.0, "Maximum difference should be large"

    def test_invalid_proportions(self):
        """Test error with invalid proportions."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            cohens_h(-0.1, 0.5)

        with pytest.raises(ValueError, match="must be between 0 and 1"):
            cohens_h(0.5, 1.5)

    def test_symmetry(self):
        """Test that h is symmetric (opposite sign)."""
        h1 = cohens_h(0.3, 0.7)
        h2 = cohens_h(0.7, 0.3)

        assert abs(h1 + h2) < 0.01, "Should be symmetric"


class TestOddsRatio:
    """Tests for odds ratio calculation."""

    def test_strong_positive_effect(self):
        """Test strong positive treatment effect."""
        # Baseline: 50/100, Treatment: 70/100
        or_val, lower, upper = odds_ratio(50, 100, 70, 100)

        assert or_val > 1.5, "Should show strong positive effect"
        assert lower > 1.0, "CI should not include 1.0"
        assert upper > or_val, "Upper CI should be greater than OR"
        assert interpret_effect_size('odds_ratio', or_val) in ["small", "medium"]

    def test_no_effect(self):
        """Test when there is no effect."""
        # Both: 50/100
        or_val, lower, upper = odds_ratio(50, 100, 50, 100)

        assert 0.9 < or_val < 1.1, "OR should be close to 1.0"
        assert lower < 1.0 < upper, "CI should include 1.0"

    def test_negative_effect(self):
        """Test negative treatment effect."""
        # Baseline: 70/100, Treatment: 50/100
        or_val, lower, upper = odds_ratio(70, 100, 50, 100)

        assert or_val < 1.0, "OR should be less than 1.0"
        assert upper < 1.0, "CI should not include 1.0"

    def test_zero_cell_continuity_correction(self):
        """Test continuity correction for zero cells."""
        # One group has zero successes
        or_val, lower, upper = odds_ratio(0, 10, 5, 10)

        assert or_val > 0, "OR should be positive with continuity correction"
        assert lower > 0, "CI bounds should be positive"

    def test_perfect_separation(self):
        """Test with perfect separation (all success vs all failure)."""
        or_val, lower, upper = odds_ratio(0, 10, 10, 10)

        assert or_val > 10, "OR should be very large"
        assert lower > 1.0, "Should be clearly significant"

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs."""
        with pytest.raises(ValueError):
            odds_ratio(-1, 10, 5, 10)

        with pytest.raises(ValueError):
            odds_ratio(11, 10, 5, 10)

        with pytest.raises(ValueError):
            odds_ratio(5, 0, 5, 10)


class TestRelativeRisk:
    """Tests for relative risk calculation."""

    def test_increased_risk(self):
        """Test when treatment increases success rate."""
        # Baseline: 50/100 (50%), Treatment: 70/100 (70%)
        rr, lower, upper = relative_risk(50, 100, 70, 100)

        assert rr > 1.0, "RR should be greater than 1.0"
        assert 1.3 < rr < 1.5, "RR should be ~1.4 (70%/50%)"
        assert lower > 1.0, "CI should not include 1.0"

    def test_decreased_risk(self):
        """Test when treatment decreases success rate."""
        # Baseline: 70/100, Treatment: 50/100
        rr, lower, upper = relative_risk(70, 100, 50, 100)

        assert rr < 1.0, "RR should be less than 1.0"
        assert upper < 1.0, "CI should not include 1.0"

    def test_no_difference(self):
        """Test when rates are equal."""
        rr, lower, upper = relative_risk(50, 100, 50, 100)

        assert 0.95 < rr < 1.05, "RR should be close to 1.0"
        assert lower < 1.0 < upper, "CI should include 1.0"

    def test_rr_vs_or_comparison(self):
        """Test that RR is closer to 1.0 than OR for same data."""
        # For non-rare events, RR is more conservative than OR
        or_val, _, _ = odds_ratio(50, 100, 70, 100)
        rr_val, _, _ = relative_risk(50, 100, 70, 100)

        # Both should be > 1.0 (treatment better)
        assert or_val > rr_val, "OR should be more extreme than RR"
        assert abs(rr_val - 1.0) < abs(or_val - 1.0), "RR closer to null"


class TestInterpretEffectSize:
    """Tests for effect size interpretation."""

    def test_cohens_d_interpretation(self):
        """Test interpretation of Cohen's d."""
        assert interpret_effect_size('cohens_d', 0.1) == "negligible"
        assert interpret_effect_size('cohens_d', 0.3) == "small"
        assert interpret_effect_size('cohens_d', 0.6) == "medium"
        assert interpret_effect_size('cohens_d', 1.0) == "large"
        assert interpret_effect_size('cohens_d', -0.9) == "large"

    def test_cohens_h_interpretation(self):
        """Test interpretation of Cohen's h."""
        assert interpret_effect_size('cohens_h', 0.1) == "negligible"
        assert interpret_effect_size('cohens_h', 0.3) == "small"
        assert interpret_effect_size('cohens_h', 0.6) == "medium"
        assert interpret_effect_size('cohens_h', 0.9) == "large"

    def test_odds_ratio_interpretation(self):
        """Test interpretation of odds ratio."""
        assert interpret_effect_size('odds_ratio', 1.0) == "negligible"
        assert interpret_effect_size('odds_ratio', 1.8) == "small"
        assert interpret_effect_size('odds_ratio', 3.0) == "medium"
        assert interpret_effect_size('odds_ratio', 5.0) == "large"
        # Symmetric for OR < 1
        assert interpret_effect_size('odds_ratio', 0.5) == "small"

    def test_relative_risk_interpretation(self):
        """Test interpretation of relative risk."""
        assert interpret_effect_size('relative_risk', 1.0) == "negligible"
        assert interpret_effect_size('relative_risk', 1.3) == "small"
        assert interpret_effect_size('relative_risk', 1.7) == "medium"
        assert interpret_effect_size('relative_risk', 2.5) == "large"

    def test_unknown_metric_raises_error(self):
        """Test error for unknown metric."""
        with pytest.raises(ValueError, match="Unknown metric"):
            interpret_effect_size('unknown_metric', 0.5)


class TestCalculateSampleSize:
    """Tests for sample size calculation."""

    def test_medium_effect_sample_size(self):
        """Test sample size for detecting medium effect."""
        n = calculate_sample_size_for_effect(0.5, power=0.80)

        # For d=0.5, 80% power, alpha=0.05, need ~64 per group
        assert 60 < n < 70, f"Expected ~64, got {n}"

    def test_large_effect_needs_fewer_samples(self):
        """Test that large effects need fewer samples."""
        n_medium = calculate_sample_size_for_effect(0.5, power=0.80)
        n_large = calculate_sample_size_for_effect(0.8, power=0.80)

        assert n_large < n_medium, "Large effect needs fewer samples"

    def test_higher_power_needs_more_samples(self):
        """Test that higher power requires more samples."""
        n_80 = calculate_sample_size_for_effect(0.5, power=0.80)
        n_90 = calculate_sample_size_for_effect(0.5, power=0.90)

        assert n_90 > n_80, "90% power needs more samples than 80%"

    def test_small_effect_needs_many_samples(self):
        """Test that small effects need large samples."""
        n = calculate_sample_size_for_effect(0.2, power=0.80)

        assert n > 300, "Small effect needs large sample"

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs."""
        with pytest.raises(ValueError):
            calculate_sample_size_for_effect(-0.5)  # Negative effect

        with pytest.raises(ValueError):
            calculate_sample_size_for_effect(0.5, alpha=1.5)  # Invalid alpha

        with pytest.raises(ValueError):
            calculate_sample_size_for_effect(0.5, power=1.5)  # Invalid power


class TestEffectSizesIntegration:
    """Integration tests for effect size calculations."""

    def test_consistent_conclusions_across_metrics(self):
        """Test that different metrics agree on effect direction."""
        # Generate data with clear treatment benefit
        np.random.seed(42)
        baseline = np.random.normal(100, 15, 100)
        treatment = np.random.normal(85, 15, 100)

        # Convert to binary (success if < 90)
        baseline_success = np.sum(baseline < 90)
        treatment_success = np.sum(treatment < 90)

        # Calculate different metrics
        d = cohens_d(baseline, treatment)
        h = cohens_h(baseline_success / 100, treatment_success / 100)
        or_val, _, _ = odds_ratio(baseline_success, 100, treatment_success, 100)
        rr, _, _ = relative_risk(baseline_success, 100, treatment_success, 100)

        # All should indicate treatment is better
        assert d < 0, "Cohen's d: treatment better (lower)"
        assert h > 0, "Cohen's h: treatment better (higher success rate)"
        assert or_val > 1.0, "OR: treatment better"
        assert rr > 1.0, "RR: treatment better"

    def test_effect_size_interpretation_consistency(self):
        """Test that effect size interpretations are consistent."""
        # Large Cohen's d should correspond to large Cohen's h
        # for equivalent proportion differences

        # d = 0.8 roughly equivalent to proportion change from 50% to 71%
        d = 0.8
        h = cohens_h(0.50, 0.71)

        assert interpret_effect_size('cohens_d', d) == "large"
        assert interpret_effect_size('cohens_h', h) in ["medium", "large"]
