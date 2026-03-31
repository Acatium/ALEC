"""Unit tests for bootstrap confidence intervals."""

import numpy as np
import pytest

from evaluation.analysis.bootstrap import (
    bootstrap_median_difference_ci,
    bootstrap_paired_difference_ci,
    bootstrap_success_rate_ci,
)


class TestBootstrapSuccessRateCI:
    """Tests for bootstrap_success_rate_ci function."""

    def test_significant_difference(self):
        """Test detection of significant difference in success rates."""
        # Baseline: 50/100, Treatment: 70/100 (20% improvement)
        lower, upper, p_value = bootstrap_success_rate_ci(
            50, 100, 70, 100, random_seed=42
        )

        # Should detect significant positive difference
        assert lower > 0, "Lower CI should be positive"
        assert upper > lower, "Upper CI should be greater than lower"
        assert p_value < 0.05, "Should be statistically significant"
        assert 0.10 < (upper - lower) < 0.30, "CI width should be reasonable"

    def test_no_difference(self):
        """Test when there is no real difference."""
        # Both groups: 50/100 success
        lower, upper, p_value = bootstrap_success_rate_ci(
            50, 100, 50, 100, random_seed=42
        )

        # CI should include zero
        assert lower < 0 < upper, "CI should include zero"
        assert p_value > 0.05, "Should not be significant"

    def test_small_sample_size(self):
        """Test with small sample sizes."""
        # Baseline: 5/10, Treatment: 8/10
        lower, upper, p_value = bootstrap_success_rate_ci(
            5, 10, 8, 10, random_seed=42
        )

        # Should still work but with wider CI
        assert upper - lower > 0.2, "CI should be wide with small n"
        assert -1 <= lower <= 1, "CI bounds should be in valid range"
        assert -1 <= upper <= 1, "CI bounds should be in valid range"

    def test_perfect_vs_zero(self):
        """Test extreme case: perfect success vs total failure."""
        lower, upper, p_value = bootstrap_success_rate_ci(
            0, 10, 10, 10, random_seed=42
        )

        # Should show large positive difference
        assert lower > 0.7, "Lower CI should indicate large effect"
        assert upper > 0.9, "Upper CI should be close to 1.0"
        assert p_value < 0.001, "Should be highly significant"

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs."""
        with pytest.raises(ValueError):
            bootstrap_success_rate_ci(-1, 10, 5, 10)  # Negative successes

        with pytest.raises(ValueError):
            bootstrap_success_rate_ci(11, 10, 5, 10)  # More successes than trials

        with pytest.raises(ValueError):
            bootstrap_success_rate_ci(5, 0, 5, 10)  # Zero sample size

        with pytest.raises(ValueError):
            bootstrap_success_rate_ci(5, 10, 5, 10, alpha=1.5)  # Invalid alpha

    def test_different_alpha_levels(self):
        """Test different confidence levels."""
        # 90% CI should be narrower than 95% CI
        lower_95, upper_95, _ = bootstrap_success_rate_ci(
            50, 100, 70, 100, alpha=0.05, random_seed=42
        )
        lower_90, upper_90, _ = bootstrap_success_rate_ci(
            50, 100, 70, 100, alpha=0.10, random_seed=42
        )

        width_95 = upper_95 - lower_95
        width_90 = upper_90 - lower_90

        assert width_90 < width_95, "90% CI should be narrower than 95% CI"

    def test_reproducibility(self):
        """Test that random seed ensures reproducibility."""
        result1 = bootstrap_success_rate_ci(50, 100, 70, 100, random_seed=42)
        result2 = bootstrap_success_rate_ci(50, 100, 70, 100, random_seed=42)

        assert result1 == result2, "Same seed should give same results"


class TestBootstrapPairedDifferenceCI:
    """Tests for bootstrap_paired_difference_ci function."""

    def test_paired_reduction(self):
        """Test detection of reduction in paired samples."""
        # Treatment reduces iterations to solve
        baseline = np.array([5, 6, 4, 7, 5, 6])
        treatment = np.array([3, 4, 2, 3, 3, 4])

        lower, upper, p_value = bootstrap_paired_difference_ci(
            baseline, treatment, random_seed=42
        )

        # Should detect significant negative difference (reduction)
        assert upper < 0, "Upper CI should be negative (treatment better)"
        assert lower < upper, "Lower CI should be less than upper"
        assert p_value < 0.05, "Should be statistically significant"

    def test_no_paired_difference(self):
        """Test when paired samples have no difference."""
        values = np.array([5, 6, 4, 7, 5, 6])

        lower, upper, p_value = bootstrap_paired_difference_ci(
            values, values, random_seed=42
        )

        # CI should be tight around zero
        assert abs(lower) < 0.1, "Lower CI should be near zero"
        assert abs(upper) < 0.1, "Upper CI should be near zero"
        assert p_value > 0.05, "Should not be significant"

    def test_mismatched_lengths(self):
        """Test error when arrays have different lengths."""
        values_a = np.array([1, 2, 3])
        values_b = np.array([1, 2])

        with pytest.raises(ValueError, match="same length"):
            bootstrap_paired_difference_ci(values_a, values_b)

    def test_empty_arrays(self):
        """Test error when arrays are empty."""
        with pytest.raises(ValueError, match="must not be empty"):
            bootstrap_paired_difference_ci(np.array([]), np.array([]))


class TestBootstrapMedianDifferenceCI:
    """Tests for bootstrap_median_difference_ci function."""

    def test_median_with_skewed_data(self):
        """Test median difference with skewed distributions."""
        # Token usage: baseline has outliers, treatment is consistent
        baseline = np.array([1000, 1200, 5000, 1100, 900, 8000])
        treatment = np.array([800, 900, 950, 850, 920, 1100])

        lower, upper, p_value = bootstrap_median_difference_ci(
            baseline, treatment, random_seed=42
        )

        # Should detect reduction despite outliers
        assert upper < 0, "Median should be lower in treatment"
        assert p_value < 0.10, "Should be significant or near-significant"

    def test_median_more_robust_than_mean(self):
        """Test that median is robust to outliers."""
        # Same data except one extreme outlier
        baseline_no_outlier = np.array([100, 110, 120, 105, 115])
        baseline_with_outlier = np.array([100, 110, 120, 105, 10000])
        treatment = np.array([90, 95, 100, 92, 98])

        lower1, upper1, _ = bootstrap_median_difference_ci(
            baseline_no_outlier, treatment, random_seed=42
        )
        lower2, upper2, _ = bootstrap_median_difference_ci(
            baseline_with_outlier, treatment, random_seed=42
        )

        # Median-based CI should be similar despite outlier
        assert abs((lower2 - lower1) / lower1) < 0.2, "Median robust to outliers"

    def test_empty_arrays(self):
        """Test error when arrays are empty."""
        with pytest.raises(ValueError, match="must not be empty"):
            bootstrap_median_difference_ci(np.array([]), np.array([1, 2, 3]))


class TestBootstrapIntegration:
    """Integration tests across bootstrap functions."""

    def test_consistent_conclusions(self):
        """Test that different bootstrap methods give consistent conclusions."""
        # Generate data where treatment clearly better
        np.random.seed(42)
        baseline = np.random.normal(100, 15, 50)
        treatment = np.random.normal(80, 15, 50)

        # Convert to binary outcomes (lower is better, threshold at 90)
        baseline_success = np.sum(baseline < 90)
        treatment_success = np.sum(treatment < 90)

        # All methods should agree treatment is better
        _, _, p_success = bootstrap_success_rate_ci(
            baseline_success, 50, treatment_success, 50, random_seed=42
        )
        _, _, p_paired = bootstrap_paired_difference_ci(
            baseline, treatment, random_seed=42
        )
        _, _, p_median = bootstrap_median_difference_ci(
            baseline, treatment, random_seed=42
        )

        # All should be significant (though exact p-values differ)
        assert p_success < 0.05, "Success rate should detect difference"
        assert p_paired < 0.05, "Paired difference should detect difference"
        assert p_median < 0.05, "Median difference should detect difference"

    def test_power_comparison(self):
        """Test that paired tests have more power than unpaired for paired data."""
        # Same tasks, treatment slightly better
        np.random.seed(42)
        baseline = np.array([5, 6, 4, 7, 5, 6, 8, 5, 6, 7])
        treatment = baseline - 1  # Treatment saves 1 iteration per task

        # Paired test should detect this small but consistent difference
        _, _, p_paired = bootstrap_paired_difference_ci(
            baseline, treatment, random_seed=42
        )

        # Convert to success rates (threshold: complete in ≤5 iterations)
        baseline_success = np.sum(baseline <= 5)
        treatment_success = np.sum(treatment <= 5)

        _, _, p_unpaired = bootstrap_success_rate_ci(
            baseline_success, len(baseline),
            treatment_success, len(treatment),
            random_seed=42
        )

        # Paired test should have smaller p-value (more power)
        assert p_paired < p_unpaired, "Paired test should have more power"
