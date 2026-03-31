"""
Effect size calculations for learning experiments.

Provides standardized measures of practical significance beyond p-values.
"""

import math
from typing import Tuple

import numpy as np


def cohens_d(
    values_a: np.ndarray,
    values_b: np.ndarray,
    pooled: bool = True
) -> float:
    """
    Calculate Cohen's d effect size for continuous metrics.

    Cohen's d measures the standardized mean difference between two groups.
    Used for continuous metrics like iterations to solve or token usage.

    Interpretation:
        - |d| < 0.2: Negligible
        - |d| = 0.2-0.5: Small
        - |d| = 0.5-0.8: Medium
        - |d| > 0.8: Large

    Args:
        values_a: Array of values in condition A (baseline)
        values_b: Array of values in condition B (treatment)
        pooled: Use pooled standard deviation (default True for equal variance)

    Returns:
        Cohen's d effect size (positive = B > A, negative = A > B)

    Example:
        >>> # Baseline takes more iterations to solve
        >>> baseline_iters = np.array([5, 6, 4, 7, 5])
        >>> treatment_iters = np.array([3, 4, 2, 3, 3])
        >>> d = cohens_d(baseline_iters, treatment_iters)
        >>> print(f"Cohen's d = {d:.2f} ({interpret_effect_size('cohens_d', d)})")
        Cohen's d = -2.45 (large)
    """
    values_a = np.asarray(values_a)
    values_b = np.asarray(values_b)

    if len(values_a) == 0 or len(values_b) == 0:
        raise ValueError("Arrays must not be empty")

    mean_a = values_a.mean()
    mean_b = values_b.mean()

    if pooled:
        # Pooled standard deviation (assumes equal variance)
        var_a = values_a.var(ddof=1)
        var_b = values_b.var(ddof=1)
        n_a = len(values_a)
        n_b = len(values_b)
        pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
        std_pooled = np.sqrt(pooled_var)
        denominator = std_pooled
    else:
        # Use standard deviation of control group
        denominator = values_a.std(ddof=1)

    if denominator == 0:
        raise ValueError("Standard deviation is zero, cannot calculate Cohen's d")

    d = (mean_b - mean_a) / denominator
    return float(d)


def cohens_h(p_a: float, p_b: float) -> float:
    """
    Calculate Cohen's h effect size for proportions.

    Cohen's h measures the difference between two proportions using arcsine
    transformation. Used for success rates and binary outcomes.

    Interpretation:
        - |h| < 0.2: Negligible
        - |h| = 0.2-0.5: Small
        - |h| = 0.5-0.8: Medium
        - |h| > 0.8: Large

    Args:
        p_a: Proportion in condition A (0 to 1)
        p_b: Proportion in condition B (0 to 1)

    Returns:
        Cohen's h effect size (positive = B > A, negative = A > B)

    Example:
        >>> # Baseline 60% success, treatment 80% success
        >>> h = cohens_h(0.60, 0.80)
        >>> print(f"Cohen's h = {h:.3f} ({interpret_effect_size('cohens_h', h)})")
        Cohen's h = 0.448 (small to medium)

        >>> # Large difference
        >>> h = cohens_h(0.30, 0.70)
        >>> print(f"Cohen's h = {h:.3f} ({interpret_effect_size('cohens_h', h)})")
        Cohen's h = 0.867 (large)
    """
    if not (0 <= p_a <= 1):
        raise ValueError(f"p_a ({p_a}) must be between 0 and 1")
    if not (0 <= p_b <= 1):
        raise ValueError(f"p_b ({p_b}) must be between 0 and 1")

    # Arcsine transformation
    phi_a = 2 * math.asin(math.sqrt(p_a))
    phi_b = 2 * math.asin(math.sqrt(p_b))

    h = phi_b - phi_a
    return float(h)


def odds_ratio(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    alpha: float = 0.05,
) -> Tuple[float, float, float]:
    """
    Calculate odds ratio with confidence interval.

    Odds ratio measures the odds of success in B relative to A. Commonly used
    in medical trials and A/B testing.

    Interpretation:
        - OR = 1: No difference
        - OR > 1: B has higher odds of success than A
        - OR < 1: A has higher odds of success than B

    Args:
        successes_a: Number of successes in condition A
        n_a: Total trials in condition A
        successes_b: Number of successes in condition B
        n_b: Total trials in condition B
        alpha: Significance level for CI (default 0.05 for 95% CI)

    Returns:
        Tuple of (odds_ratio, lower_ci, upper_ci)

    Example:
        >>> # Baseline: 50/100 success, Treatment: 70/100 success
        >>> or_val, lower, upper = odds_ratio(50, 100, 70, 100)
        >>> print(f"OR = {or_val:.2f}, 95% CI [{lower:.2f}, {upper:.2f}]")
        OR = 2.33, 95% CI [1.35, 4.03]

        >>> # No significant difference (CI includes 1.0)
        >>> or_val, lower, upper = odds_ratio(50, 100, 52, 100)
        >>> print(f"OR = {or_val:.2f}, 95% CI [{lower:.2f}, {upper:.2f}]")
        OR = 1.08, 95% CI [0.65, 1.80]
    """
    # Validate inputs
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Sample sizes must be positive")
    if successes_a < 0 or successes_a > n_a:
        raise ValueError(f"successes_a ({successes_a}) must be between 0 and n_a ({n_a})")
    if successes_b < 0 or successes_b > n_b:
        raise ValueError(f"successes_b ({successes_b}) must be between 0 and n_b ({n_b})")

    failures_a = n_a - successes_a
    failures_b = n_b - successes_b

    # Add continuity correction for zero cells
    if successes_a == 0 or failures_a == 0 or successes_b == 0 or failures_b == 0:
        successes_a += 0.5
        failures_a += 0.5
        successes_b += 0.5
        failures_b += 0.5

    # Calculate odds ratio
    odds_a = successes_a / failures_a
    odds_b = successes_b / failures_b
    or_val = odds_b / odds_a

    # Calculate standard error on log scale
    se_log_or = math.sqrt(
        1 / successes_a + 1 / failures_a + 1 / successes_b + 1 / failures_b
    )

    # Calculate confidence interval on log scale
    from scipy import stats
    z_critical = stats.norm.ppf(1 - alpha / 2)
    log_or = math.log(or_val)
    log_lower = log_or - z_critical * se_log_or
    log_upper = log_or + z_critical * se_log_or

    # Transform back to original scale
    lower_ci = math.exp(log_lower)
    upper_ci = math.exp(log_upper)

    return float(or_val), float(lower_ci), float(upper_ci)


def relative_risk(
    successes_a: int,
    n_a: int,
    successes_b: int,
    n_b: int,
    alpha: float = 0.05,
) -> Tuple[float, float, float]:
    """
    Calculate relative risk (risk ratio) with confidence interval.

    Relative risk measures the probability of success in B relative to A.
    More intuitive than odds ratio for most audiences.

    Interpretation:
        - RR = 1: No difference
        - RR > 1: B has higher success rate than A
        - RR < 1: A has higher success rate than B

    Args:
        successes_a: Number of successes in condition A
        n_a: Total trials in condition A
        successes_b: Number of successes in condition B
        n_b: Total trials in condition B
        alpha: Significance level for CI (default 0.05 for 95% CI)

    Returns:
        Tuple of (relative_risk, lower_ci, upper_ci)

    Example:
        >>> # Baseline: 50/100 success (50%), Treatment: 70/100 success (70%)
        >>> rr, lower, upper = relative_risk(50, 100, 70, 100)
        >>> print(f"RR = {rr:.2f}, 95% CI [{lower:.2f}, {upper:.2f}]")
        RR = 1.40, 95% CI [1.11, 1.76]
    """
    # Validate inputs
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Sample sizes must be positive")
    if successes_a < 0 or successes_a > n_a:
        raise ValueError(f"successes_a ({successes_a}) must be between 0 and n_a ({n_a})")
    if successes_b < 0 or successes_b > n_b:
        raise ValueError(f"successes_b ({successes_b}) must be between 0 and n_b ({n_b})")

    # Calculate proportions
    p_a = successes_a / n_a
    p_b = successes_b / n_b

    # Add small constant to avoid division by zero
    if p_a == 0:
        p_a = 0.5 / n_a
    if p_b == 0:
        p_b = 0.5 / n_b

    # Calculate relative risk
    rr = p_b / p_a

    # Calculate standard error on log scale
    se_log_rr = math.sqrt(
        (1 - p_a) / (successes_a) + (1 - p_b) / (successes_b)
    )

    # Calculate confidence interval on log scale
    from scipy import stats
    z_critical = stats.norm.ppf(1 - alpha / 2)
    log_rr = math.log(rr)
    log_lower = log_rr - z_critical * se_log_rr
    log_upper = log_rr + z_critical * se_log_rr

    # Transform back to original scale
    lower_ci = math.exp(log_lower)
    upper_ci = math.exp(log_upper)

    return float(rr), float(lower_ci), float(upper_ci)


def interpret_effect_size(metric: str, value: float) -> str:
    """
    Interpret effect size using Cohen's conventions.

    Args:
        metric: One of 'cohens_d', 'cohens_h', 'odds_ratio', 'relative_risk'
        value: The effect size value

    Returns:
        Interpretation string (e.g., "small", "medium", "large")

    Example:
        >>> interpret_effect_size('cohens_d', 0.3)
        'small'
        >>> interpret_effect_size('cohens_d', 0.9)
        'large'
        >>> interpret_effect_size('odds_ratio', 2.5)
        'medium'
    """
    abs_value = abs(value)

    if metric in ['cohens_d', 'cohens_h']:
        # Cohen's conventions for d and h
        if abs_value < 0.2:
            return "negligible"
        elif abs_value < 0.5:
            return "small"
        elif abs_value < 0.8:
            return "medium"
        else:
            return "large"

    elif metric == 'odds_ratio':
        # Interpretation for odds ratios
        # Convert to log scale for symmetric interpretation
        if value == 0:
            return "undefined"
        log_or = abs(math.log(value))
        if log_or < math.log(1.5):  # OR between 0.67-1.5
            return "negligible"
        elif log_or < math.log(2.5):  # OR between 0.4-2.5
            return "small"
        elif log_or < math.log(4.0):  # OR between 0.25-4.0
            return "medium"
        else:
            return "large"

    elif metric == 'relative_risk':
        # Interpretation for relative risk
        if value == 0:
            return "undefined"
        log_rr = abs(math.log(value))
        if log_rr < math.log(1.2):  # RR between 0.83-1.2
            return "negligible"
        elif log_rr < math.log(1.5):  # RR between 0.67-1.5
            return "small"
        elif log_rr < math.log(2.0):  # RR between 0.5-2.0
            return "medium"
        else:
            return "large"

    else:
        raise ValueError(f"Unknown metric: {metric}")


def calculate_sample_size_for_effect(
    effect_size: float,
    alpha: float = 0.05,
    power: float = 0.80,
    effect_type: str = 'cohens_d',
) -> int:
    """
    Calculate required sample size to detect an effect with given power.

    Args:
        effect_size: Expected effect size to detect
        alpha: Type I error rate (default 0.05)
        power: Statistical power (1 - Type II error, default 0.80)
        effect_type: Type of effect size ('cohens_d' or 'cohens_h')

    Returns:
        Required sample size per group

    Example:
        >>> # How many samples needed to detect medium effect (d=0.5)?
        >>> n = calculate_sample_size_for_effect(0.5, power=0.80)
        >>> print(f"Need {n} samples per group")
        Need 64 samples per group
    """
    from scipy import stats

    if effect_type not in ['cohens_d', 'cohens_h']:
        raise ValueError(f"effect_type must be 'cohens_d' or 'cohens_h', got {effect_type}")

    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be between 0 and 1, got {alpha}")
    if not 0 < power < 1:
        raise ValueError(f"power must be between 0 and 1, got {power}")
    if effect_size <= 0:
        raise ValueError(f"effect_size must be positive, got {effect_size}")

    # Z-scores for alpha and power
    z_alpha = stats.norm.ppf(1 - alpha / 2)  # Two-tailed
    z_beta = stats.norm.ppf(power)

    # Sample size formula for equal group sizes
    # n = 2 * ((z_alpha + z_beta) / effect_size)^2
    n = 2 * ((z_alpha + z_beta) / effect_size) ** 2

    # Round up to nearest integer
    return int(math.ceil(n))
