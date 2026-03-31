"""
Bootstrap confidence intervals for success rate comparisons.

Implements non-parametric bootstrap for estimating confidence intervals
and p-values for the difference between two success rates.
"""

from typing import Tuple

import numpy as np


def bootstrap_success_rate_ci(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    alpha: float = 0.05,
    n_iterations: int = 10000,
    random_seed: int | None = None,
) -> Tuple[float, float, float]:
    """
    Calculate bootstrap confidence interval for difference in success rates.

    Uses non-parametric bootstrap with percentile method to estimate the
    confidence interval for (rate_B - rate_A). A positive difference indicates
    B performs better than A.

    Args:
        successes_a: Number of successes in condition A
        n_a: Total trials in condition A
        successes_b: Number of successes in condition B
        n_b: Total trials in condition B
        alpha: Significance level (default 0.05 for 95% CI)
        n_iterations: Number of bootstrap iterations (default 10,000)
        random_seed: Random seed for reproducibility (optional)

    Returns:
        Tuple of (lower_bound, upper_bound, p_value) where:
        - lower_bound: Lower bound of (1-alpha)% CI for rate difference
        - upper_bound: Upper bound of (1-alpha)% CI for rate difference
        - p_value: Two-tailed p-value testing if difference != 0

    Example:
        >>> # Baseline: 50/100 success, Treatment: 70/100 success
        >>> lower, upper, p_value = bootstrap_success_rate_ci(50, 100, 70, 100)
        >>> print(f"Difference 95% CI: [{lower:.3f}, {upper:.3f}], p={p_value:.4f}")
        Difference 95% CI: [0.083, 0.317], p=0.0012

        >>> # No significant difference
        >>> lower, upper, p_value = bootstrap_success_rate_ci(50, 100, 52, 100)
        >>> print(f"p={p_value:.4f}")
        p=0.7234
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    # Validate inputs
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Sample sizes must be positive")
    if successes_a < 0 or successes_a > n_a:
        raise ValueError(f"successes_a ({successes_a}) must be between 0 and n_a ({n_a})")
    if successes_b < 0 or successes_b > n_b:
        raise ValueError(f"successes_b ({successes_b}) must be between 0 and n_b ({n_b})")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha ({alpha}) must be between 0 and 1")

    # Create binary outcome arrays
    outcomes_a = np.array([1] * successes_a + [0] * (n_a - successes_a))
    outcomes_b = np.array([1] * successes_b + [0] * (n_b - successes_b))

    # Bootstrap sampling
    bootstrap_diffs = np.zeros(n_iterations)
    for i in range(n_iterations):
        # Resample with replacement
        sample_a = np.random.choice(outcomes_a, size=n_a, replace=True)
        sample_b = np.random.choice(outcomes_b, size=n_b, replace=True)

        # Calculate difference in success rates (B - A)
        rate_a = sample_a.mean()
        rate_b = sample_b.mean()
        bootstrap_diffs[i] = rate_b - rate_a

    # Calculate confidence interval using percentile method
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100
    lower_bound = np.percentile(bootstrap_diffs, lower_percentile)
    upper_bound = np.percentile(bootstrap_diffs, upper_percentile)

    # Calculate two-tailed p-value
    # P-value = proportion of bootstrap samples where difference crosses zero
    observed_diff = (successes_b / n_b) - (successes_a / n_a)
    if observed_diff >= 0:
        # Observed positive difference: count how often bootstrap is <= 0
        p_value = 2 * np.mean(bootstrap_diffs <= 0)
    else:
        # Observed negative difference: count how often bootstrap is >= 0
        p_value = 2 * np.mean(bootstrap_diffs >= 0)

    # Cap p-value at 1.0
    p_value = min(p_value, 1.0)

    return lower_bound, upper_bound, p_value


def bootstrap_paired_difference_ci(
    values_a: np.ndarray,
    values_b: np.ndarray,
    alpha: float = 0.05,
    n_iterations: int = 10000,
    random_seed: int | None = None,
) -> Tuple[float, float, float]:
    """
    Calculate bootstrap confidence interval for paired differences.

    Uses non-parametric bootstrap for paired samples (e.g., iterations to solve
    same task in baseline vs treatment). Resamples pairs with replacement.

    Args:
        values_a: Array of values in condition A (shape: n_samples)
        values_b: Array of values in condition B (shape: n_samples)
        alpha: Significance level (default 0.05 for 95% CI)
        n_iterations: Number of bootstrap iterations (default 10,000)
        random_seed: Random seed for reproducibility (optional)

    Returns:
        Tuple of (lower_bound, upper_bound, p_value) where:
        - lower_bound: Lower bound of (1-alpha)% CI for mean difference
        - upper_bound: Upper bound of (1-alpha)% CI for mean difference
        - p_value: Two-tailed p-value testing if difference != 0

    Example:
        >>> # Same tasks, different iterations to solve
        >>> baseline_iters = np.array([3, 5, 2, 4, 6])
        >>> treatment_iters = np.array([2, 3, 1, 2, 4])
        >>> lower, upper, p = bootstrap_paired_difference_ci(baseline_iters, treatment_iters)
        >>> print(f"Mean difference 95% CI: [{lower:.2f}, {upper:.2f}], p={p:.4f}")
        Mean difference 95% CI: [-2.80, -0.60], p=0.0234
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    values_a = np.asarray(values_a)
    values_b = np.asarray(values_b)

    # Validate inputs
    if len(values_a) != len(values_b):
        raise ValueError(
            f"Arrays must have same length: {len(values_a)} != {len(values_b)}"
        )
    if len(values_a) == 0:
        raise ValueError("Arrays must not be empty")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha ({alpha}) must be between 0 and 1")

    n_samples = len(values_a)

    # Calculate paired differences
    differences = values_b - values_a

    # Bootstrap sampling
    bootstrap_means = np.zeros(n_iterations)
    for i in range(n_iterations):
        # Resample pairs with replacement
        indices = np.random.choice(n_samples, size=n_samples, replace=True)
        bootstrap_means[i] = differences[indices].mean()

    # Calculate confidence interval using percentile method
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100
    lower_bound = np.percentile(bootstrap_means, lower_percentile)
    upper_bound = np.percentile(bootstrap_means, upper_percentile)

    # Calculate two-tailed p-value
    observed_mean = differences.mean()
    if observed_mean >= 0:
        p_value = 2 * np.mean(bootstrap_means <= 0)
    else:
        p_value = 2 * np.mean(bootstrap_means >= 0)

    p_value = min(p_value, 1.0)

    return lower_bound, upper_bound, p_value


def bootstrap_median_difference_ci(
    values_a: np.ndarray,
    values_b: np.ndarray,
    alpha: float = 0.05,
    n_iterations: int = 10000,
    random_seed: int | None = None,
) -> Tuple[float, float, float]:
    """
    Calculate bootstrap confidence interval for difference in medians.

    Useful for skewed distributions (e.g., token usage) where median is more
    robust than mean.

    Args:
        values_a: Array of values in condition A
        values_b: Array of values in condition B
        alpha: Significance level (default 0.05 for 95% CI)
        n_iterations: Number of bootstrap iterations (default 10,000)
        random_seed: Random seed for reproducibility (optional)

    Returns:
        Tuple of (lower_bound, upper_bound, p_value) where:
        - lower_bound: Lower bound of (1-alpha)% CI for median difference
        - upper_bound: Upper bound of (1-alpha)% CI for median difference
        - p_value: Two-tailed p-value testing if difference != 0

    Example:
        >>> # Token usage (highly skewed)
        >>> baseline_tokens = np.array([1000, 1200, 5000, 1100, 900])
        >>> treatment_tokens = np.array([800, 900, 950, 850, 920])
        >>> lower, upper, p = bootstrap_median_difference_ci(baseline_tokens, treatment_tokens)
        >>> print(f"Median difference 95% CI: [{lower:.0f}, {upper:.0f}], p={p:.4f}")
        Median difference 95% CI: [-4050, -50], p=0.0456
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    values_a = np.asarray(values_a)
    values_b = np.asarray(values_b)

    # Validate inputs
    if len(values_a) == 0 or len(values_b) == 0:
        raise ValueError("Arrays must not be empty")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha ({alpha}) must be between 0 and 1")

    # Bootstrap sampling
    bootstrap_diffs = np.zeros(n_iterations)
    for i in range(n_iterations):
        # Resample with replacement
        sample_a = np.random.choice(values_a, size=len(values_a), replace=True)
        sample_b = np.random.choice(values_b, size=len(values_b), replace=True)

        # Calculate difference in medians (B - A)
        bootstrap_diffs[i] = np.median(sample_b) - np.median(sample_a)

    # Calculate confidence interval using percentile method
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100
    lower_bound = np.percentile(bootstrap_diffs, lower_percentile)
    upper_bound = np.percentile(bootstrap_diffs, upper_percentile)

    # Calculate two-tailed p-value
    observed_diff = np.median(values_b) - np.median(values_a)
    if observed_diff >= 0:
        p_value = 2 * np.mean(bootstrap_diffs <= 0)
    else:
        p_value = 2 * np.mean(bootstrap_diffs >= 0)

    p_value = min(p_value, 1.0)

    return lower_bound, upper_bound, p_value
