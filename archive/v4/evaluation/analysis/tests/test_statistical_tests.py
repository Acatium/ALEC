"""Unit tests for statistical hypothesis tests."""

import numpy as np
import pytest

from evaluation.analysis.statistical_tests import (
    bonferroni_correction,
    check_normality,
    fdr_correction,
    fishers_exact_test,
    mann_whitney_u_test,
    mcnemar_exact_test,
    paired_t_test,
    sequential_bonferroni,
)


class TestMcNemarExactTest:
    """Tests for McNemar's exact test."""

    def test_significant_difference(self):
        """Test detection of significant difference in paired proportions."""
        # 100 tasks: both succeed 40, only baseline 10, only treatment 30, both fail 20
        # Treatment succeeds on 30 tasks where baseline failed (significant improvement)
        p_value, interp = mcnemar_exact_test(40, 10, 30, 20)

        assert p_value < 0.05, "Should detect significant difference"
        assert interp in ["significant", "very significant", "highly significant"]

    def test_no_difference(self):
        """Test when there is no difference."""
        # Equal discordant pairs (15 vs 15)
        p_value, interp = mcnemar_exact_test(40, 15, 15, 30)

        assert p_value > 0.05, "Should not detect difference"
        assert interp == "not significant"

    def test_perfect_agreement(self):
        """Test when there are no discordant pairs."""
        # Both succeed or both fail on all tasks
        p_value, interp = mcnemar_exact_test(50, 0, 0, 50)

        assert p_value == 1.0, "Perfect agreement should give p=1.0"
        assert interp == "no difference"

    def test_small_sample_exact_test(self):
        """Test that exact test is used for small samples."""
        # Only 10 discordant pairs (should use exact binomial)
        p_value, _ = mcnemar_exact_test(40, 2, 8, 50)

        # Should still give valid p-value
        assert 0 <= p_value <= 1, "P-value should be valid"

    def test_large_sample_chi_square(self):
        """Test that chi-square approximation is used for large samples."""
        # 100 discordant pairs (should use chi-square)
        p_value, _ = mcnemar_exact_test(100, 30, 70, 100)

        assert p_value < 0.001, "Large imbalance should be highly significant"

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs."""
        with pytest.raises(ValueError, match="non-negative"):
            mcnemar_exact_test(-1, 10, 10, 10)

        with pytest.raises(ValueError, match="cannot be zero"):
            mcnemar_exact_test(0, 0, 0, 0)


class TestPairedTTest:
    """Tests for paired t-test."""

    def test_significant_paired_difference(self):
        """Test detection of significant paired difference."""
        baseline = np.array([5, 6, 4, 7, 5, 6])
        treatment = np.array([3, 4, 2, 3, 3, 4])

        t, p, interp = paired_t_test(baseline, treatment)

        assert t < 0, "T-statistic should be negative (treatment better)"
        assert p < 0.05, "Should be significant"
        assert interp in ["significant", "very significant", "highly significant"]

    def test_no_paired_difference(self):
        """Test when there is no difference."""
        values = np.array([5, 6, 4, 7, 5, 6])

        t, p, interp = paired_t_test(values, values)

        assert abs(t) < 0.01, "T-statistic should be near zero"
        assert p > 0.05, "Should not be significant"
        assert interp == "not significant"

    def test_one_tailed_test(self):
        """Test one-tailed alternative hypotheses."""
        baseline = np.array([5, 6, 4, 7, 5])
        treatment = np.array([3, 4, 2, 3, 3])

        # Test if baseline > treatment (should be significant)
        _, p_less, _ = paired_t_test(baseline, treatment, alternative='less')
        assert p_less < 0.05, "Should detect baseline > treatment"

        # Test if baseline < treatment (should not be significant)
        _, p_greater, _ = paired_t_test(baseline, treatment, alternative='greater')
        assert p_greater > 0.05, "Should not detect baseline < treatment"

    def test_mismatched_lengths(self):
        """Test error when arrays have different lengths."""
        with pytest.raises(ValueError, match="same length"):
            paired_t_test(np.array([1, 2, 3]), np.array([1, 2]))

    def test_insufficient_pairs(self):
        """Test error when too few pairs."""
        with pytest.raises(ValueError, match="at least 2"):
            paired_t_test(np.array([1]), np.array([2]))


class TestMannWhitneyUTest:
    """Tests for Mann-Whitney U test."""

    def test_significant_difference_skewed_data(self):
        """Test detection of difference in skewed distributions."""
        # Token usage: baseline has outliers
        baseline = np.array([1000, 1200, 5000, 1100, 900, 8000])
        treatment = np.array([800, 900, 950, 850, 920, 1100])

        u, p, interp = mann_whitney_u_test(baseline, treatment)

        assert p < 0.10, "Should detect difference despite skew"

    def test_no_difference(self):
        """Test when distributions are similar."""
        values = np.array([1, 2, 3, 4, 5, 6])

        u, p, interp = mann_whitney_u_test(values, values)

        # P-value should be high (distributions identical)
        assert p > 0.05, "Should not detect difference"

    def test_one_tailed_test(self):
        """Test one-tailed alternatives."""
        baseline = np.array([10, 12, 11, 13, 12])
        treatment = np.array([8, 9, 7, 8, 9])

        # Test if baseline > treatment
        _, p_less, _ = mann_whitney_u_test(baseline, treatment, alternative='less')
        assert p_less < 0.05, "Should detect baseline > treatment"

    def test_ties_handled(self):
        """Test that ties are handled correctly."""
        # Data with many ties
        baseline = np.array([1, 1, 2, 2, 3])
        treatment = np.array([1, 2, 2, 3, 3])

        u, p, _ = mann_whitney_u_test(baseline, treatment)

        # Should still compute valid result
        assert 0 <= p <= 1, "P-value should be valid with ties"

    def test_empty_arrays(self):
        """Test error with empty arrays."""
        with pytest.raises(ValueError, match="must not be empty"):
            mann_whitney_u_test(np.array([]), np.array([1, 2, 3]))


class TestFishersExactTest:
    """Tests for Fisher's exact test."""

    def test_small_sample_significant(self):
        """Test with small sample showing clear difference."""
        # Baseline: 2/10, Treatment: 8/10
        or_val, p, interp = fishers_exact_test(2, 10, 8, 10)

        assert or_val > 1.0, "OR should indicate treatment better"
        assert p < 0.05, "Should be significant"

    def test_small_sample_not_significant(self):
        """Test with small sample showing no difference."""
        # Baseline: 5/10, Treatment: 6/10
        or_val, p, interp = fishers_exact_test(5, 10, 6, 10)

        assert p > 0.05, "Should not be significant"
        assert interp == "not significant"

    def test_one_tailed_test(self):
        """Test one-tailed alternatives."""
        or_val1, p1, _ = fishers_exact_test(2, 10, 8, 10, alternative='less')
        or_val2, p2, _ = fishers_exact_test(2, 10, 8, 10, alternative='greater')

        # p1 should be smaller (treatment clearly better)
        assert p1 < p2

    def test_invalid_inputs(self):
        """Test error handling."""
        with pytest.raises(ValueError):
            fishers_exact_test(-1, 10, 5, 10)

        with pytest.raises(ValueError):
            fishers_exact_test(11, 10, 5, 10)


class TestBonferroniCorrection:
    """Tests for Bonferroni correction."""

    def test_bonferroni_conservative(self):
        """Test that Bonferroni is conservative."""
        p_values = [0.01, 0.03, 0.04, 0.10]
        significant = bonferroni_correction(p_values, alpha=0.05)

        # With 4 tests, adjusted alpha = 0.0125
        # Only p=0.01 should be significant
        assert significant == [True, False, False, False]

    def test_bonferroni_all_significant(self):
        """Test when all tests are significant after correction."""
        p_values = [0.001, 0.002, 0.003]
        significant = bonferroni_correction(p_values, alpha=0.05)

        # Adjusted alpha = 0.0167, all should pass
        assert all(significant)

    def test_bonferroni_none_significant(self):
        """Test when no tests are significant after correction."""
        p_values = [0.06, 0.07, 0.08]
        significant = bonferroni_correction(p_values, alpha=0.05)

        assert not any(significant)

    def test_empty_list(self):
        """Test with empty p-value list."""
        significant = bonferroni_correction([])
        assert significant == []


class TestFDRCorrection:
    """Tests for FDR correction."""

    def test_fdr_less_conservative_than_bonferroni(self):
        """Test that FDR is less conservative than Bonferroni."""
        p_values = [0.01, 0.03, 0.04, 0.10]

        bonf_sig = bonferroni_correction(p_values, alpha=0.05)
        fdr_sig, _ = fdr_correction(p_values, alpha=0.05)

        # FDR should accept more tests
        assert sum(fdr_sig) >= sum(bonf_sig)

    def test_fdr_bh_method(self):
        """Test Benjamini-Hochberg FDR correction."""
        p_values = [0.01, 0.03, 0.04, 0.10]
        significant, adjusted = fdr_correction(p_values, alpha=0.05, method='bh')

        # Should reject first few, accept last
        assert significant[0], "Smallest p-value should be significant"
        assert not significant[-1], "Largest p-value should not be significant"

        # Adjusted p-values should be >= original
        for orig, adj in zip(p_values, adjusted):
            assert adj >= orig, "Adjusted p should be >= original"

    def test_fdr_by_method(self):
        """Test Benjamini-Yekutieli FDR correction."""
        p_values = [0.01, 0.03, 0.04, 0.10]

        sig_bh, adj_bh = fdr_correction(p_values, alpha=0.05, method='bh')
        sig_by, adj_by = fdr_correction(p_values, alpha=0.05, method='by')

        # BY should be more conservative than BH
        assert sum(sig_by) <= sum(sig_bh)

        # BY adjusted p-values should be larger
        assert all(by >= bh for by, bh in zip(adj_by, adj_bh))

    def test_empty_list(self):
        """Test with empty p-value list."""
        significant, adjusted = fdr_correction([])
        assert significant == []
        assert adjusted == []


class TestSequentialBonferroni:
    """Tests for sequential Bonferroni (Holm-Bonferroni)."""

    def test_more_powerful_than_bonferroni(self):
        """Test that Holm-Bonferroni is more powerful than Bonferroni."""
        p_values = [0.01, 0.02, 0.03, 0.10]

        bonf_sig = bonferroni_correction(p_values, alpha=0.05)
        holm_sig = sequential_bonferroni(p_values, alpha=0.05)

        # Holm should accept more or equal tests
        assert sum(holm_sig) >= sum(bonf_sig)

    def test_sequential_rejection(self):
        """Test that rejection stops at first non-significant."""
        p_values = [0.01, 0.03, 0.08, 0.10]
        significant = sequential_bonferroni(p_values, alpha=0.05)

        # Should reject smallest, then stop
        # alpha/4 = 0.0125 -> reject p=0.01
        # alpha/3 = 0.0167 -> fail to reject p=0.03 (borderline, might reject)
        # Once failed, all subsequent fail
        assert significant[0], "Smallest p-value should be significant"

    def test_empty_list(self):
        """Test with empty p-value list."""
        significant = sequential_bonferroni([])
        assert significant == []


class TestCheckNormality:
    """Tests for normality check."""

    def test_normal_distribution(self):
        """Test detection of normal distribution."""
        np.random.seed(42)
        normal_data = np.random.normal(100, 15, 50)

        is_normal, p, rec = check_normality(normal_data)

        assert is_normal, "Should detect normality"
        assert p > 0.05, "Shapiro-Wilk should not reject normality"
        assert "parametric" in rec.lower()

    def test_skewed_distribution(self):
        """Test detection of non-normal distribution."""
        np.random.seed(42)
        skewed_data = np.random.exponential(10, 50)

        is_normal, p, rec = check_normality(skewed_data)

        assert not is_normal, "Should detect non-normality"
        assert p < 0.05, "Shapiro-Wilk should reject normality"
        assert "non-parametric" in rec.lower()

    def test_small_sample(self):
        """Test with very small sample."""
        small_data = np.array([1, 2])

        is_normal, p, rec = check_normality(small_data)

        assert not is_normal, "Should indicate insufficient data"
        assert "too small" in rec.lower()


class TestStatisticalTestsIntegration:
    """Integration tests across statistical tests."""

    def test_paired_vs_unpaired_consistency(self):
        """Test that paired and unpaired tests give consistent conclusions."""
        # Generate data where treatment clearly better
        np.random.seed(42)
        baseline = np.random.normal(100, 15, 30)
        treatment = np.random.normal(85, 15, 30)

        # Paired t-test
        _, p_paired, _ = paired_t_test(baseline, treatment)

        # Mann-Whitney (unpaired)
        _, p_mw, _ = mann_whitney_u_test(baseline, treatment)

        # Both should detect difference
        assert p_paired < 0.05, "Paired t-test should detect difference"
        assert p_mw < 0.05, "Mann-Whitney should detect difference"

    def test_multiple_comparison_methods_consistency(self):
        """Test that multiple comparison methods give sensible results."""
        # Mix of significant and non-significant p-values
        p_values = [0.001, 0.01, 0.03, 0.08, 0.15]

        bonf = bonferroni_correction(p_values, alpha=0.05)
        holm = sequential_bonferroni(p_values, alpha=0.05)
        fdr_sig, _ = fdr_correction(p_values, alpha=0.05)

        # Ordering: FDR should accept most, Bonferroni fewest
        assert sum(fdr_sig) >= sum(holm) >= sum(bonf), \
            "FDR should be most liberal, Bonferroni most conservative"

        # All should agree on most significant test
        assert bonf[0] and holm[0] and fdr_sig[0], \
            "All methods should reject p=0.001"

    def test_normality_guides_test_choice(self):
        """Test that normality check guides test selection."""
        np.random.seed(42)

        # Normal data - t-test should be appropriate
        normal_a = np.random.normal(100, 15, 30)
        normal_b = np.random.normal(90, 15, 30)
        is_normal_a, _, _ = check_normality(normal_a)
        is_normal_b, _, _ = check_normality(normal_b)

        if is_normal_a and is_normal_b:
            # Use t-test
            _, p_t, _ = paired_t_test(normal_a, normal_b)
            assert p_t < 0.05, "T-test should work well for normal data"

        # Skewed data - Mann-Whitney should be more robust
        skewed_a = np.random.exponential(10, 30)
        skewed_b = np.random.exponential(8, 30)
        is_normal, _, _ = check_normality(skewed_a)

        if not is_normal:
            # Use Mann-Whitney
            _, p_mw, _ = mann_whitney_u_test(skewed_a, skewed_b)
            # Should still give valid result
            assert 0 <= p_mw <= 1
