# Statistical Analysis for ALEC Evaluation

This module provides robust statistical tools for analyzing learning experiments and proving that ALEC's learning mechanisms work.

## Overview

The analysis module implements three core components:

1. **Bootstrap Methods** (`bootstrap.py`) - Non-parametric confidence intervals
2. **Effect Sizes** (`effect_sizes.py`) - Standardized measures of practical significance
3. **Statistical Tests** (`statistical_tests.py`) - Hypothesis testing with multiple comparison correction

## Installation

```bash
# Install scipy (numpy and pytest already in main requirements)
pip install scipy>=1.10.0
```

## Quick Start

```python
from evaluation.analysis import (
    bootstrap_success_rate_ci,
    cohens_d,
    mcnemar_exact_test,
)

# Compare success rates between baseline and treatment
baseline_success, baseline_total = 50, 100
treatment_success, treatment_total = 70, 100

# Bootstrap confidence interval
lower, upper, p_value = bootstrap_success_rate_ci(
    baseline_success, baseline_total,
    treatment_success, treatment_total
)

print(f"Success rate difference 95% CI: [{lower:.3f}, {upper:.3f}]")
print(f"P-value: {p_value:.4f}")

# Effect size
from evaluation.analysis import cohens_h, interpret_effect_size
h = cohens_h(baseline_success / baseline_total, treatment_success / treatment_total)
print(f"Cohen's h: {h:.3f} ({interpret_effect_size('cohens_h', h)})")
```

See `example_usage.py` for comprehensive examples.

## Module Reference

### Bootstrap Methods (`bootstrap.py`)

Non-parametric confidence intervals that don't assume normal distributions.

#### `bootstrap_success_rate_ci(successes_a, n_a, successes_b, n_b, alpha=0.05, n_iterations=10000)`

Calculate bootstrap CI for difference in success rates.

**Returns:** `(lower_bound, upper_bound, p_value)`

**Example:**
```python
# Baseline: 50/100, Treatment: 70/100
lower, upper, p = bootstrap_success_rate_ci(50, 100, 70, 100)
# Returns: (0.083, 0.317, 0.0012)
```

#### `bootstrap_paired_difference_ci(values_a, values_b, alpha=0.05, n_iterations=10000)`

Calculate bootstrap CI for paired differences (e.g., iterations to solve same tasks).

**Returns:** `(lower_bound, upper_bound, p_value)`

**Example:**
```python
import numpy as np
baseline = np.array([5, 6, 4, 7, 5])
treatment = np.array([3, 4, 2, 3, 3])
lower, upper, p = bootstrap_paired_difference_ci(baseline, treatment)
# Returns negative difference (treatment better)
```

#### `bootstrap_median_difference_ci(values_a, values_b, alpha=0.05, n_iterations=10000)`

Calculate bootstrap CI for difference in medians (robust to outliers).

**Returns:** `(lower_bound, upper_bound, p_value)`

**Use when:** Distributions are skewed (e.g., token usage with outliers)

---

### Effect Sizes (`effect_sizes.py`)

Standardized measures of practical significance beyond p-values.

#### `cohens_d(values_a, values_b, pooled=True)`

Cohen's d for continuous metrics (iterations, tokens, latency).

**Interpretation:**
- |d| < 0.2: Negligible
- |d| = 0.2-0.5: Small
- |d| = 0.5-0.8: Medium
- |d| > 0.8: Large

**Example:**
```python
baseline = np.array([5, 6, 4, 7, 5])
treatment = np.array([3, 4, 2, 3, 3])
d = cohens_d(baseline, treatment)
# Returns: -2.45 (large effect, treatment reduces iterations)
```

#### `cohens_h(p_a, p_b)`

Cohen's h for proportions (success rates).

**Parameters:** Proportions from 0 to 1

**Interpretation:** Same thresholds as Cohen's d

**Example:**
```python
h = cohens_h(0.60, 0.80)
# Returns: 0.448 (small to medium effect)
```

#### `odds_ratio(successes_a, n_a, successes_b, n_b, alpha=0.05)`

Odds ratio with confidence interval.

**Returns:** `(odds_ratio, lower_ci, upper_ci)`

**Interpretation:**
- OR = 1: No difference
- OR > 1: B has higher odds of success
- OR < 1: A has higher odds of success

**Example:**
```python
or_val, lower, upper = odds_ratio(50, 100, 70, 100)
# Returns: (2.33, 1.35, 4.03)
```

#### `relative_risk(successes_a, n_a, successes_b, n_b, alpha=0.05)`

Relative risk with confidence interval (more intuitive than odds ratio).

**Returns:** `(relative_risk, lower_ci, upper_ci)`

**Example:**
```python
rr, lower, upper = relative_risk(50, 100, 70, 100)
# Returns: (1.40, 1.11, 1.76)
```

#### `interpret_effect_size(metric, value)`

Interpret effect size using Cohen's conventions.

**Parameters:**
- `metric`: 'cohens_d', 'cohens_h', 'odds_ratio', 'relative_risk'
- `value`: The effect size value

**Returns:** String like "small", "medium", "large"

#### `calculate_sample_size_for_effect(effect_size, alpha=0.05, power=0.80)`

Calculate required sample size to detect an effect with given power.

**Example:**
```python
n = calculate_sample_size_for_effect(0.5, power=0.80)
# Returns: 64 (need 64 samples per group to detect medium effect)
```

---

### Statistical Tests (`statistical_tests.py`)

Hypothesis tests for comparing baseline vs treatment.

#### `mcnemar_exact_test(success_both, success_a_only, success_b_only, failure_both)`

McNemar's test for paired binary outcomes (same tasks, different systems).

**Returns:** `(p_value, interpretation)`

**Example:**
```python
# 100 tasks: both succeed 40, only baseline 10, only treatment 30, both fail 20
p, interp = mcnemar_exact_test(40, 10, 30, 20)
# Returns: (0.0027, "significant")
```

#### `paired_t_test(values_a, values_b, alternative='two-sided')`

Paired t-test for continuous outcomes (assumes normality).

**Returns:** `(t_statistic, p_value, interpretation)`

**Example:**
```python
baseline = np.array([5, 6, 4, 7, 5])
treatment = np.array([3, 4, 2, 3, 3])
t, p, interp = paired_t_test(baseline, treatment)
# Returns: (-6.71, 0.0011, "highly significant")
```

#### `mann_whitney_u_test(values_a, values_b, alternative='two-sided')`

Mann-Whitney U test for non-normal distributions (robust to outliers).

**Returns:** `(u_statistic, p_value, interpretation)`

**Use when:** Distributions are skewed or normality is violated

**Example:**
```python
# Token usage with outliers
baseline = np.array([1000, 1200, 5000, 1100, 900])
treatment = np.array([800, 900, 950, 850, 920])
u, p, interp = mann_whitney_u_test(baseline, treatment)
```

#### `fishers_exact_test(success_a, n_a, success_b, n_b, alternative='two-sided')`

Fisher's exact test for small sample binary outcomes.

**Returns:** `(odds_ratio, p_value, interpretation)`

**Example:**
```python
# Small sample: 8/10 vs 5/10
or_val, p, interp = fishers_exact_test(8, 10, 5, 10)
```

#### `bonferroni_correction(p_values, alpha=0.05)`

Conservative correction for multiple comparisons (controls family-wise error rate).

**Returns:** List of booleans indicating significance

**Example:**
```python
p_values = [0.01, 0.03, 0.04, 0.10]
significant = bonferroni_correction(p_values, alpha=0.05)
# Returns: [True, False, False, False] (adjusted alpha = 0.0125)
```

#### `fdr_correction(p_values, alpha=0.05, method='bh')`

False Discovery Rate correction (less conservative than Bonferroni).

**Returns:** `(significant_list, adjusted_p_values)`

**Methods:**
- `'bh'`: Benjamini-Hochberg (default, for independent tests)
- `'by'`: Benjamini-Yekutieli (more conservative, for dependent tests)

**Example:**
```python
p_values = [0.01, 0.03, 0.04, 0.10]
significant, adjusted = fdr_correction(p_values, alpha=0.05)
# More liberal than Bonferroni
```

#### `sequential_bonferroni(p_values, alpha=0.05)`

Holm-Bonferroni correction (more powerful than standard Bonferroni).

**Returns:** List of booleans indicating significance

#### `check_normality(values, alpha=0.05)`

Check if data follows normal distribution using Shapiro-Wilk test.

**Returns:** `(is_normal, p_value, recommendation)`

**Example:**
```python
is_normal, p, rec = check_normality(data)
if is_normal:
    # Use paired t-test
else:
    # Use Mann-Whitney U test
```

---

## Usage Guidelines

### When to Use Each Test

| Scenario | Test | Why |
|----------|------|-----|
| Same tasks, binary outcomes | `mcnemar_exact_test` | Paired data, exact test |
| Same tasks, continuous outcomes | `paired_t_test` | More power than unpaired |
| Same tasks, skewed data | `bootstrap_paired_difference_ci` | Non-parametric, robust |
| Different tasks, binary outcomes | `fishers_exact_test` (small n) or bootstrap | Small samples need exact test |
| Different tasks, continuous outcomes | `mann_whitney_u_test` | Non-parametric, robust |
| Token usage (outliers) | `bootstrap_median_difference_ci` | Median robust to outliers |
| Multiple domains tested | `fdr_correction` | Controls false discovery rate |

### Choosing Effect Sizes

| Metric Type | Effect Size | Notes |
|-------------|-------------|-------|
| Success rate | `cohens_h` | Arcsine transformation |
| Success rate | `odds_ratio` | Interpretable as odds |
| Success rate | `relative_risk` | Most intuitive for audiences |
| Iterations | `cohens_d` | Standardized mean difference |
| Tokens | `cohens_d` | Log-transform first if very skewed |
| Latency | `cohens_d` | Check normality first |

### Best Practices

1. **Always report both p-values and effect sizes**
   - P-values tell you if difference is real
   - Effect sizes tell you if difference matters

2. **Use paired tests when possible**
   - Same tasks in baseline and treatment
   - More statistical power

3. **Check normality before choosing test**
   ```python
   is_normal, _, rec = check_normality(data)
   print(rec)  # "Use parametric tests" or "Use non-parametric tests"
   ```

4. **Correct for multiple comparisons**
   - Testing multiple domains? Use `fdr_correction`
   - Family of related tests? Use `sequential_bonferroni`

5. **Use bootstrap for small samples or non-normal data**
   - No assumptions about distribution
   - Works with n as small as 10

6. **Report confidence intervals, not just point estimates**
   ```python
   lower, upper, p = bootstrap_success_rate_ci(...)
   print(f"Difference: {(upper+lower)/2:.3f}, 95% CI [{lower:.3f}, {upper:.3f}]")
   ```

## Testing

```bash
# Run all tests
pytest evaluation/analysis/tests/ -v

# Run specific test module
pytest evaluation/analysis/tests/test_bootstrap.py -v

# Run with coverage
pytest evaluation/analysis/tests/ --cov=evaluation.analysis --cov-report=html
```

## Example Output

Run the example usage script to see statistical analysis in action:

```bash
python evaluation/analysis/example_usage.py
```

This will output comprehensive analyses for:
- Success rate comparison
- Paired task comparison (iterations)
- Token usage comparison (skewed data)
- McNemar's test for paired tasks
- Multiple comparison correction

## References

### Bootstrap Methods
- Efron, B., & Tibshirani, R. J. (1994). *An Introduction to the Bootstrap*. Chapman and Hall/CRC.

### Effect Sizes
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.). Routledge.
- Ellis, P. D. (2010). *The Essential Guide to Effect Sizes*. Cambridge University Press.

### Statistical Tests
- McNemar, Q. (1947). "Note on the sampling error of the difference between correlated proportions." *Psychometrika*, 12(2), 153-157.
- Benjamini, Y., & Hochberg, Y. (1995). "Controlling the false discovery rate." *Journal of the Royal Statistical Society B*, 57(1), 289-300.

## Implementation Details

- **Bootstrap iterations:** 10,000 (provides stable estimates)
- **Confidence level:** 95% (alpha=0.05) by default
- **P-value method:** Two-tailed tests by default
- **Effect size conventions:** Cohen's standardized thresholds
- **Zero-cell handling:** Continuity correction for odds ratio
- **Small sample tests:** Exact methods when n < 25

## Contributing

When adding new statistical methods:

1. Add function to appropriate module
2. Include comprehensive docstring with examples
3. Add type hints
4. Write unit tests (aim for >90% coverage)
5. Add usage example to `example_usage.py`
6. Update this README

## License

Part of the ALEC project. See main repository for license details.
