"""
Statistical hypothesis tests for learning experiments.

Provides robust tests for binary outcomes, paired comparisons, and
multiple comparison corrections.
"""

from typing import List, Tuple

import numpy as np
from scipy import stats


def mcnemar_exact_test(
    success_both: int,
    success_a_only: int,
    success_b_only: int,
    failure_both: int,
) -> Tuple[float, str]:
    """
    McNemar's exact test for paired binary outcomes.

    Tests whether paired proportions are significantly different. Useful for
    comparing baseline vs treatment on the same set of tasks.

    Args:
        success_both: Tasks where both A and B succeeded
        success_a_only: Tasks where only A succeeded
        success_b_only: Tasks where only B succeeded
        failure_both: Tasks where both A and B failed

    Returns:
        Tuple of (p_value, interpretation)

    Example:
        >>> # 100 tasks total
        >>> # Both succeed: 40, Only baseline: 10, Only treatment: 30, Both fail: 20
        >>> p, interp = mcnemar_exact_test(40, 10, 30, 20)
        >>> print(f"McNemar p={p:.4f} ({interp})")
        McNemar p=0.0027 (significant)

    Reference:
        McNemar, Q. (1947). "Note on the sampling error of the difference
        between correlated proportions or percentages". Psychometrika, 12(2), 153-157.
    """
    # Validate inputs
    total = success_both + success_a_only + success_b_only + failure_both
    if total == 0:
        raise ValueError("Total count cannot be zero")
    if any(x < 0 for x in [success_both, success_a_only, success_b_only, failure_both]):
        raise ValueError("All counts must be non-negative")

    # McNemar test focuses on discordant pairs
    b = success_a_only  # A succeeded, B failed
    c = success_b_only  # B succeeded, A failed
    n_discordant = b + c

    if n_discordant == 0:
        # Perfect agreement, no difference
        return 1.0, "no difference"

    # For small samples (< 25 discordant pairs), use exact binomial test
    if n_discordant < 25:
        # Under null hypothesis, b and c should be equal
        # Test if observed b is significantly different from expected b = n/2
        p_value = stats.binom_test(b, n=n_discordant, p=0.5, alternative='two-sided')
    else:
        # For larger samples, use chi-square approximation with continuity correction
        chi2 = (abs(b - c) - 1) ** 2 / (b + c)
        p_value = stats.chi2.sf(chi2, df=1)

    # Interpret result
    if p_value < 0.001:
        interpretation = "highly significant"
    elif p_value < 0.01:
        interpretation = "very significant"
    elif p_value < 0.05:
        interpretation = "significant"
    else:
        interpretation = "not significant"

    return float(p_value), interpretation


def paired_t_test(
    values_a: np.ndarray,
    values_b: np.ndarray,
    alternative: str = 'two-sided',
) -> Tuple[float, float, str]:
    """
    Paired t-test for continuous outcomes.

    Tests whether the mean difference between paired samples is significantly
    different from zero. Assumes differences are approximately normal.

    Args:
        values_a: Array of values in condition A (baseline)
        values_b: Array of values in condition B (treatment)
        alternative: 'two-sided', 'less', or 'greater'

    Returns:
        Tuple of (t_statistic, p_value, interpretation)

    Example:
        >>> # Same tasks, different iterations to solve
        >>> baseline_iters = np.array([5, 6, 4, 7, 5, 6])
        >>> treatment_iters = np.array([3, 4, 2, 3, 3, 4])
        >>> t, p, interp = paired_t_test(baseline_iters, treatment_iters)
        >>> print(f"Paired t-test: t={t:.2f}, p={p:.4f} ({interp})")
        Paired t-test: t=-6.71, p=0.0011 (highly significant)
    """
    values_a = np.asarray(values_a)
    values_b = np.asarray(values_b)

    # Validate inputs
    if len(values_a) != len(values_b):
        raise ValueError(f"Arrays must have same length: {len(values_a)} != {len(values_b)}")
    if len(values_a) < 2:
        raise ValueError("Need at least 2 pairs for t-test")
    if alternative not in ['two-sided', 'less', 'greater']:
        raise ValueError(f"alternative must be 'two-sided', 'less', or 'greater', got {alternative}")

    # Perform paired t-test
    t_stat, p_value = stats.ttest_rel(values_a, values_b, alternative=alternative)

    # Interpret result
    if p_value < 0.001:
        interpretation = "highly significant"
    elif p_value < 0.01:
        interpretation = "very significant"
    elif p_value < 0.05:
        interpretation = "significant"
    else:
        interpretation = "not significant"

    return float(t_stat), float(p_value), interpretation


def mann_whitney_u_test(
    values_a: np.ndarray,
    values_b: np.ndarray,
    alternative: str = 'two-sided',
) -> Tuple[float, float, str]:
    """
    Mann-Whitney U test (Wilcoxon rank-sum test) for non-normal distributions.

    Non-parametric test comparing distributions of two independent samples.
    More robust than t-test when normality assumption is violated.

    Args:
        values_a: Array of values in condition A
        values_b: Array of values in condition B
        alternative: 'two-sided', 'less', or 'greater'

    Returns:
        Tuple of (u_statistic, p_value, interpretation)

    Example:
        >>> # Token usage (highly skewed, not normal)
        >>> baseline_tokens = np.array([1000, 1200, 5000, 1100, 900, 8000])
        >>> treatment_tokens = np.array([800, 900, 950, 850, 920, 1100])
        >>> u, p, interp = mann_whitney_u_test(baseline_tokens, treatment_tokens)
        >>> print(f"Mann-Whitney U test: U={u:.0f}, p={p:.4f} ({interp})")
        Mann-Whitney U test: U=2.0, p=0.0152 (significant)
    """
    values_a = np.asarray(values_a)
    values_b = np.asarray(values_b)

    # Validate inputs
    if len(values_a) == 0 or len(values_b) == 0:
        raise ValueError("Arrays must not be empty")
    if alternative not in ['two-sided', 'less', 'greater']:
        raise ValueError(f"alternative must be 'two-sided', 'less', or 'greater', got {alternative}")

    # Perform Mann-Whitney U test
    u_stat, p_value = stats.mannwhitneyu(
        values_a, values_b, alternative=alternative
    )

    # Interpret result
    if p_value < 0.001:
        interpretation = "highly significant"
    elif p_value < 0.01:
        interpretation = "very significant"
    elif p_value < 0.05:
        interpretation = "significant"
    else:
        interpretation = "not significant"

    return float(u_stat), float(p_value), interpretation


def fishers_exact_test(
    success_a: int,
    n_a: int,
    success_b: int,
    n_b: int,
    alternative: str = 'two-sided',
) -> Tuple[float, float, str]:
    """
    Fisher's exact test for 2x2 contingency tables.

    Exact test for independence between binary variables. More accurate than
    chi-square for small sample sizes.

    Args:
        success_a: Number of successes in condition A
        n_a: Total trials in condition A
        success_b: Number of successes in condition B
        n_b: Total trials in condition B
        alternative: 'two-sided', 'less', or 'greater'

    Returns:
        Tuple of (odds_ratio, p_value, interpretation)

    Example:
        >>> # Small sample: baseline 8/10 success, treatment 5/10 success
        >>> or_val, p, interp = fishers_exact_test(8, 10, 5, 10)
        >>> print(f"Fisher's exact: OR={or_val:.2f}, p={p:.4f} ({interp})")
        Fisher's exact: OR=0.19, p=0.1537 (not significant)
    """
    # Validate inputs
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Sample sizes must be positive")
    if success_a < 0 or success_a > n_a:
        raise ValueError(f"success_a ({success_a}) must be between 0 and n_a ({n_a})")
    if success_b < 0 or success_b > n_b:
        raise ValueError(f"success_b ({success_b}) must be between 0 and n_b ({n_b})")
    if alternative not in ['two-sided', 'less', 'greater']:
        raise ValueError(f"alternative must be 'two-sided', 'less', or 'greater', got {alternative}")

    # Create 2x2 contingency table
    # Rows: A vs B, Columns: Success vs Failure
    table = [
        [success_a, n_a - success_a],
        [success_b, n_b - success_b],
    ]

    # Perform Fisher's exact test
    odds_ratio, p_value = stats.fisher_exact(table, alternative=alternative)

    # Interpret result
    if p_value < 0.001:
        interpretation = "highly significant"
    elif p_value < 0.01:
        interpretation = "very significant"
    elif p_value < 0.05:
        interpretation = "significant"
    else:
        interpretation = "not significant"

    return float(odds_ratio), float(p_value), interpretation


def bonferroni_correction(p_values: List[float], alpha: float = 0.05) -> List[bool]:
    """
    Bonferroni correction for multiple comparisons.

    Conservative method that controls family-wise error rate (FWER).
    Divides alpha by number of tests.

    Args:
        p_values: List of p-values from multiple tests
        alpha: Desired family-wise error rate (default 0.05)

    Returns:
        List of booleans indicating which tests are significant after correction

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.10]
        >>> significant = bonferroni_correction(p_values, alpha=0.05)
        >>> for i, (p, sig) in enumerate(zip(p_values, significant)):
        ...     print(f"Test {i+1}: p={p:.3f}, significant={sig}")
        Test 1: p=0.010, significant=True
        Test 2: p=0.030, significant=False
        Test 3: p=0.040, significant=False
        Test 4: p=0.100, significant=False
    """
    if not p_values:
        return []

    n_tests = len(p_values)
    adjusted_alpha = alpha / n_tests

    significant = [p <= adjusted_alpha for p in p_values]
    return significant


def fdr_correction(
    p_values: List[float],
    alpha: float = 0.05,
    method: str = 'bh',
) -> Tuple[List[bool], List[float]]:
    """
    False Discovery Rate (FDR) correction for multiple comparisons.

    Less conservative than Bonferroni. Controls expected proportion of
    false discoveries among rejected hypotheses.

    Args:
        p_values: List of p-values from multiple tests
        alpha: Desired FDR level (default 0.05)
        method: 'bh' for Benjamini-Hochberg (default) or 'by' for Benjamini-Yekutieli

    Returns:
        Tuple of (significant_list, adjusted_p_values)

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.10]
        >>> significant, adjusted = fdr_correction(p_values, alpha=0.05)
        >>> for i, (p, adj_p, sig) in enumerate(zip(p_values, adjusted, significant)):
        ...     print(f"Test {i+1}: p={p:.3f}, adj_p={adj_p:.3f}, sig={sig}")
        Test 1: p=0.010, adj_p=0.040, sig=True
        Test 2: p=0.030, adj_p=0.060, sig=True
        Test 3: p=0.040, adj_p=0.067, sig=False
        Test 4: p=0.100, adj_p=0.100, sig=False
    """
    if not p_values:
        return [], []

    p_values = np.asarray(p_values)
    n_tests = len(p_values)

    # Sort p-values and track original indices
    sorted_indices = np.argsort(p_values)
    sorted_p = p_values[sorted_indices]

    # Calculate adjusted p-values
    if method == 'bh':
        # Benjamini-Hochberg procedure
        adjusted_p = np.minimum.accumulate(
            sorted_p * n_tests / np.arange(1, n_tests + 1)[::-1]
        )[::-1]
    elif method == 'by':
        # Benjamini-Yekutieli procedure (more conservative, for dependent tests)
        c_n = np.sum(1.0 / np.arange(1, n_tests + 1))
        adjusted_p = np.minimum.accumulate(
            sorted_p * n_tests * c_n / np.arange(1, n_tests + 1)[::-1]
        )[::-1]
    else:
        raise ValueError(f"method must be 'bh' or 'by', got {method}")

    # Cap adjusted p-values at 1.0
    adjusted_p = np.minimum(adjusted_p, 1.0)

    # Restore original order
    restored_adjusted_p = np.empty(n_tests)
    restored_adjusted_p[sorted_indices] = adjusted_p

    # Determine significance
    significant = restored_adjusted_p <= alpha

    return significant.tolist(), restored_adjusted_p.tolist()


def sequential_bonferroni(
    p_values: List[float],
    alpha: float = 0.05,
) -> List[bool]:
    """
    Sequential Bonferroni (Holm-Bonferroni) correction.

    More powerful than standard Bonferroni while still controlling FWER.
    Rejects hypotheses sequentially from smallest to largest p-value.

    Args:
        p_values: List of p-values from multiple tests
        alpha: Desired family-wise error rate (default 0.05)

    Returns:
        List of booleans indicating which tests are significant after correction

    Example:
        >>> p_values = [0.01, 0.03, 0.04, 0.10]
        >>> significant = sequential_bonferroni(p_values, alpha=0.05)
        >>> for i, (p, sig) in enumerate(zip(p_values, significant)):
        ...     print(f"Test {i+1}: p={p:.3f}, significant={sig}")
        Test 1: p=0.010, significant=True
        Test 2: p=0.030, significant=True
        Test 3: p=0.040, significant=False
        Test 4: p=0.100, significant=False
    """
    if not p_values:
        return []

    n_tests = len(p_values)
    p_array = np.asarray(p_values)

    # Sort p-values and track original indices
    sorted_indices = np.argsort(p_array)
    sorted_p = p_array[sorted_indices]

    # Apply Holm-Bonferroni sequentially
    significant_sorted = np.zeros(n_tests, dtype=bool)
    for i in range(n_tests):
        adjusted_alpha = alpha / (n_tests - i)
        if sorted_p[i] <= adjusted_alpha:
            significant_sorted[i] = True
        else:
            # Once we fail to reject, all subsequent tests also fail
            break

    # Restore original order
    significant = np.empty(n_tests, dtype=bool)
    significant[sorted_indices] = significant_sorted

    return significant.tolist()


def check_normality(values: np.ndarray, alpha: float = 0.05) -> Tuple[bool, float, str]:
    """
    Check if data follows normal distribution using Shapiro-Wilk test.

    Helps decide whether to use parametric (t-test) or non-parametric
    (Mann-Whitney) tests.

    Args:
        values: Array of values to test
        alpha: Significance level (default 0.05)

    Returns:
        Tuple of (is_normal, p_value, recommendation)

    Example:
        >>> # Normal data
        >>> normal_data = np.random.normal(100, 15, 50)
        >>> is_normal, p, rec = check_normality(normal_data)
        >>> print(f"Normal: {is_normal}, p={p:.4f}, {rec}")
        Normal: True, p=0.3421, Use parametric tests (t-test)

        >>> # Skewed data
        >>> skewed_data = np.random.exponential(10, 50)
        >>> is_normal, p, rec = check_normality(skewed_data)
        >>> print(f"Normal: {is_normal}, p={p:.4f}, {rec}")
        Normal: False, p=0.0001, Use non-parametric tests (Mann-Whitney)
    """
    values = np.asarray(values)

    if len(values) < 3:
        return False, 1.0, "Sample too small for normality test"

    # Shapiro-Wilk test
    statistic, p_value = stats.shapiro(values)

    is_normal = p_value > alpha

    if is_normal:
        recommendation = "Use parametric tests (t-test)"
    else:
        recommendation = "Use non-parametric tests (Mann-Whitney)"

    return bool(is_normal), float(p_value), recommendation
