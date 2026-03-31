# Statistical Analysis Quick Reference

## One-Page Cheat Sheet

### Decision Tree: Which Test Should I Use?

```
Do you have the SAME tasks in both conditions?
│
├─ YES (paired data)
│  │
│  ├─ Binary outcomes (success/fail)?
│  │  └─ Use: mcnemar_exact_test()
│  │
│  └─ Continuous outcomes (iterations/tokens)?
│     │
│     ├─ Data looks normal?
│     │  └─ Use: paired_t_test()
│     │
│     └─ Data skewed or has outliers?
│        └─ Use: bootstrap_paired_difference_ci()
│
└─ NO (different tasks)
   │
   ├─ Binary outcomes (success/fail)?
   │  │
   │  ├─ Sample size < 30?
   │  │  └─ Use: fishers_exact_test()
   │  │
   │  └─ Sample size >= 30?
   │     └─ Use: bootstrap_success_rate_ci()
   │
   └─ Continuous outcomes?
      │
      ├─ Data looks normal?
      │  └─ Use: paired_t_test() (if paired) or compare with bootstrap
      │
      └─ Data skewed/outliers?
         └─ Use: mann_whitney_u_test() or bootstrap_median_difference_ci()
```

### Common Scenarios

| Scenario | Function | Example |
|----------|----------|---------|
| **Compare success rates** | `bootstrap_success_rate_ci(50, 100, 70, 100)` | Baseline 50%, treatment 70% |
| **Same tasks, different iterations** | `bootstrap_paired_difference_ci(baseline_iters, treatment_iters)` | How many fewer iterations? |
| **Token usage (outliers)** | `bootstrap_median_difference_ci(baseline_tokens, treatment_tokens)` | Median robust to outliers |
| **Small sample (n<30)** | `fishers_exact_test(8, 10, 5, 10)` | 8/10 vs 5/10 |
| **Multiple domains tested** | `fdr_correction(p_values)` | Test 5 domains, correct p-values |

### Quick Examples

#### Success Rate Comparison
```python
from evaluation.analysis import bootstrap_success_rate_ci, cohens_h

# Data
baseline_success, baseline_n = 50, 100
treatment_success, treatment_n = 70, 100

# Analysis
lower, upper, p = bootstrap_success_rate_ci(baseline_success, baseline_n, treatment_success, treatment_n)
h = cohens_h(baseline_success / baseline_n, treatment_success / treatment_n)

# Report
print(f"Success rate: {treatment_success/treatment_n - baseline_success/baseline_n:.1%} improvement")
print(f"95% CI: [{lower:.3f}, {upper:.3f}], p={p:.4f}")
print(f"Effect size: {h:.3f} ({interpret_effect_size('cohens_h', h)})")
```

#### Paired Task Comparison
```python
from evaluation.analysis import bootstrap_paired_difference_ci, cohens_d
import numpy as np

# Data (same tasks, different conditions)
baseline = np.array([5, 6, 4, 7, 5, 6])
treatment = np.array([3, 4, 2, 3, 3, 4])

# Analysis
lower, upper, p = bootstrap_paired_difference_ci(baseline, treatment)
d = cohens_d(baseline, treatment)

# Report
print(f"Mean reduction: {baseline.mean() - treatment.mean():.2f} iterations")
print(f"95% CI: [{lower:.2f}, {upper:.2f}], p={p:.4f}")
print(f"Cohen's d: {d:.3f} ({interpret_effect_size('cohens_d', d)})")
```

#### Multiple Domain Analysis
```python
from evaluation.analysis import fdr_correction

# Data: p-values from 5 domain-specific tests
domains = ["Python", "JavaScript", "SQL", "DevOps", "Math"]
p_values = [0.001, 0.015, 0.032, 0.089, 0.234]

# Correction
significant, adjusted = fdr_correction(p_values, alpha=0.05)

# Report
for domain, p, adj_p, sig in zip(domains, p_values, adjusted, significant):
    status = "✓" if sig else "✗"
    print(f"{status} {domain}: p={p:.4f}, adj_p={adj_p:.4f}")
```

### Effect Size Interpretation

| Cohen's d/h | Odds Ratio | Relative Risk | Interpretation |
|-------------|------------|---------------|----------------|
| < 0.2 | 0.67 - 1.5 | 0.83 - 1.2 | Negligible |
| 0.2 - 0.5 | 1.5 - 2.5 | 1.2 - 1.5 | Small |
| 0.5 - 0.8 | 2.5 - 4.0 | 1.5 - 2.0 | Medium |
| > 0.8 | > 4.0 | > 2.0 | Large |

### Statistical Significance Interpretation

| P-value | Interpretation | Symbol |
|---------|----------------|--------|
| p < 0.001 | Highly significant | *** |
| p < 0.01 | Very significant | ** |
| p < 0.05 | Significant | * |
| p >= 0.05 | Not significant | ns |

### Multiple Comparison Methods

| Method | Use When | Power | Conservative? |
|--------|----------|-------|---------------|
| Bonferroni | Small number of tests (< 5) | Low | Very |
| Holm-Bonferroni | Small number of tests | Medium | Moderate |
| FDR (BH) | Many tests, exploratory | High | Less |
| FDR (BY) | Many tests, dependent | Medium | Moderate |

**Rule of thumb:** Use FDR for exploratory analysis, Bonferroni for confirmatory.

### Common Mistakes to Avoid

❌ **Don't:** Use unpaired tests when you have paired data
✅ **Do:** Use paired tests for same tasks in different conditions

❌ **Don't:** Only report p-values
✅ **Do:** Report both p-values and effect sizes

❌ **Don't:** Use parametric tests on skewed data
✅ **Do:** Check normality first with `check_normality()`

❌ **Don't:** Forget to correct for multiple comparisons
✅ **Do:** Use `fdr_correction()` when testing multiple hypotheses

❌ **Don't:** Use mean for token usage with outliers
✅ **Do:** Use median with `bootstrap_median_difference_ci()`

### Minimum Sample Sizes

| Test | Minimum n | Recommended n | Notes |
|------|-----------|---------------|-------|
| Fisher's exact | 5 | 10+ | Exact for any n |
| McNemar's exact | 5 | 10+ | Exact for any n |
| Bootstrap | 10 | 30+ | Works but wide CI |
| Paired t-test | 10 | 30+ | Check normality |
| Mann-Whitney U | 10 | 30+ | Non-parametric |

### Reporting Template

```
Treatment showed a [DIRECTION] change in [METRIC]
([BASELINE_VALUE] → [TREATMENT_VALUE], difference = [DIFF]).
This difference was [INTERPRETATION] (95% CI [LOWER, UPPER],
p=[P_VALUE], [EFFECT_SIZE_NAME]=[EFFECT_VALUE], [INTERPRETATION]).
```

**Example:**
```
Treatment showed a positive change in success rate
(50.0% → 70.0%, difference = 20.0%). This difference was
statistically significant (95% CI [0.083, 0.317], p=0.0012,
Cohen's h=0.448, small to medium effect).
```

### Function Signatures (Quick Copy-Paste)

```python
# Bootstrap
bootstrap_success_rate_ci(successes_a, n_a, successes_b, n_b, alpha=0.05, n_iterations=10000, random_seed=None)
bootstrap_paired_difference_ci(values_a, values_b, alpha=0.05, n_iterations=10000, random_seed=None)
bootstrap_median_difference_ci(values_a, values_b, alpha=0.05, n_iterations=10000, random_seed=None)

# Effect Sizes
cohens_d(values_a, values_b, pooled=True)
cohens_h(p_a, p_b)
odds_ratio(successes_a, n_a, successes_b, n_b, alpha=0.05)
relative_risk(successes_a, n_a, successes_b, n_b, alpha=0.05)
interpret_effect_size(metric, value)  # metric: 'cohens_d', 'cohens_h', 'odds_ratio', 'relative_risk'

# Statistical Tests
mcnemar_exact_test(success_both, success_a_only, success_b_only, failure_both)
paired_t_test(values_a, values_b, alternative='two-sided')
mann_whitney_u_test(values_a, values_b, alternative='two-sided')
fishers_exact_test(success_a, n_a, success_b, n_b, alternative='two-sided')

# Multiple Comparisons
bonferroni_correction(p_values, alpha=0.05)
fdr_correction(p_values, alpha=0.05, method='bh')
sequential_bonferroni(p_values, alpha=0.05)

# Utilities
check_normality(values, alpha=0.05)
calculate_sample_size_for_effect(effect_size, alpha=0.05, power=0.80, effect_type='cohens_d')
```

### Getting Help

- **Full documentation:** See `README.md`
- **Examples:** Run `python evaluation/analysis/example_usage.py`
- **Tests:** See `tests/` for edge cases and validation

---

**Last Updated:** Phase 1 Implementation (2025-11-25)
