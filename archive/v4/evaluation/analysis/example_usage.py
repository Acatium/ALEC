"""
Example usage of statistical analysis tools for ALEC evaluation.

This script demonstrates how to analyze experiment results using the
statistical functions in the analysis module.
"""

import numpy as np

from evaluation.analysis import (
    bootstrap_median_difference_ci,
    bootstrap_paired_difference_ci,
    bootstrap_success_rate_ci,
    check_normality,
    cohens_d,
    cohens_h,
    fdr_correction,
    fishers_exact_test,
    interpret_effect_size,
    mann_whitney_u_test,
    mcnemar_exact_test,
    odds_ratio,
    paired_t_test,
    relative_risk,
)


def example_success_rate_comparison():
    """Example: Compare success rates between baseline and treatment."""
    print("=" * 70)
    print("EXAMPLE 1: Success Rate Comparison")
    print("=" * 70)

    # Scenario: Baseline vs treatment on 100 tasks each
    baseline_success = 50
    baseline_total = 100
    treatment_success = 70
    treatment_total = 100

    print(f"\nBaseline: {baseline_success}/{baseline_total} ({baseline_success/baseline_total:.1%}) success")
    print(f"Treatment: {treatment_success}/{treatment_total} ({treatment_success/treatment_total:.1%}) success")

    # Bootstrap confidence interval
    lower, upper, p_value = bootstrap_success_rate_ci(
        baseline_success, baseline_total,
        treatment_success, treatment_total,
        random_seed=42
    )

    print("\nBootstrap Analysis (10,000 iterations):")
    print(f"  Difference (Treatment - Baseline): {(treatment_success/treatment_total - baseline_success/baseline_total):.3f}")
    print(f"  95% CI: [{lower:.3f}, {upper:.3f}]")
    print(f"  P-value: {p_value:.4f}")

    if p_value < 0.001:
        conclusion = "highly significant (p < 0.001)"
    elif p_value < 0.01:
        conclusion = "very significant (p < 0.01)"
    elif p_value < 0.05:
        conclusion = "significant (p < 0.05)"
    else:
        conclusion = "not significant (p >= 0.05)"

    print(f"  Conclusion: {conclusion}")

    # Effect sizes
    h = cohens_h(baseline_success / baseline_total, treatment_success / treatment_total)
    or_val, or_lower, or_upper = odds_ratio(baseline_success, baseline_total, treatment_success, treatment_total)
    rr, rr_lower, rr_upper = relative_risk(baseline_success, baseline_total, treatment_success, treatment_total)

    print("\nEffect Sizes:")
    print(f"  Cohen's h: {h:.3f} ({interpret_effect_size('cohens_h', h)})")
    print(f"  Odds Ratio: {or_val:.2f}, 95% CI [{or_lower:.2f}, {or_upper:.2f}]")
    print(f"  Relative Risk: {rr:.2f}, 95% CI [{rr_lower:.2f}, {rr_upper:.2f}]")

    # Statistical test
    fisher_or, fisher_p, fisher_interp = fishers_exact_test(
        baseline_success, baseline_total,
        treatment_success, treatment_total
    )

    print("\nFisher's Exact Test:")
    print(f"  P-value: {fisher_p:.4f} ({fisher_interp})")

    print("\n" + "=" * 70 + "\n")


def example_paired_comparison():
    """Example: Compare iterations to solve same tasks."""
    print("=" * 70)
    print("EXAMPLE 2: Paired Task Comparison (Iterations to Solve)")
    print("=" * 70)

    # Scenario: Same 10 tasks, baseline vs treatment
    baseline_iterations = np.array([5, 6, 4, 7, 5, 6, 8, 5, 6, 7])
    treatment_iterations = np.array([3, 4, 2, 3, 4, 4, 5, 3, 4, 5])

    print(f"\nBaseline iterations (mean ± std): {baseline_iterations.mean():.2f} ± {baseline_iterations.std():.2f}")
    print(f"Treatment iterations (mean ± std): {treatment_iterations.mean():.2f} ± {treatment_iterations.std():.2f}")

    # Check normality
    is_normal_baseline, p_baseline, rec_baseline = check_normality(baseline_iterations)
    is_normal_treatment, p_treatment, rec_treatment = check_normality(treatment_iterations)

    print("\nNormality Check:")
    print(f"  Baseline: p={p_baseline:.4f} ({rec_baseline})")
    print(f"  Treatment: p={p_treatment:.4f} ({rec_treatment})")

    # Bootstrap confidence interval
    lower, upper, p_value = bootstrap_paired_difference_ci(
        baseline_iterations, treatment_iterations, random_seed=42
    )

    print("\nBootstrap Paired Difference (10,000 iterations):")
    print(f"  Mean difference (Treatment - Baseline): {(treatment_iterations - baseline_iterations).mean():.2f}")
    print(f"  95% CI: [{lower:.2f}, {upper:.2f}]")
    print(f"  P-value: {p_value:.4f}")

    # Effect size
    d = cohens_d(baseline_iterations, treatment_iterations)
    print("\nEffect Size:")
    print(f"  Cohen's d: {d:.3f} ({interpret_effect_size('cohens_d', d)})")

    # Paired t-test
    t_stat, t_p, t_interp = paired_t_test(baseline_iterations, treatment_iterations)
    print("\nPaired t-test:")
    print(f"  t-statistic: {t_stat:.3f}")
    print(f"  P-value: {t_p:.4f} ({t_interp})")

    print("\n" + "=" * 70 + "\n")


def example_token_usage_comparison():
    """Example: Compare token usage (skewed distribution)."""
    print("=" * 70)
    print("EXAMPLE 3: Token Usage Comparison (Skewed Data)")
    print("=" * 70)

    # Scenario: Token usage has outliers
    baseline_tokens = np.array([1000, 1200, 5000, 1100, 900, 8000, 1150, 950, 1300, 1050])
    treatment_tokens = np.array([800, 900, 950, 850, 920, 1100, 880, 810, 950, 870])

    print("\nBaseline tokens:")
    print(f"  Mean: {baseline_tokens.mean():.0f}")
    print(f"  Median: {np.median(baseline_tokens):.0f}")
    print(f"  Std: {baseline_tokens.std():.0f}")

    print("\nTreatment tokens:")
    print(f"  Mean: {treatment_tokens.mean():.0f}")
    print(f"  Median: {np.median(treatment_tokens):.0f}")
    print(f"  Std: {treatment_tokens.std():.0f}")

    # Check normality (expect non-normal due to outliers)
    is_normal, p_norm, rec = check_normality(baseline_tokens)
    print("\nNormality Check (Baseline):")
    print(f"  P-value: {p_norm:.4f}")
    print(f"  Recommendation: {rec}")

    # Bootstrap median difference (robust to outliers)
    lower, upper, p_value = bootstrap_median_difference_ci(
        baseline_tokens, treatment_tokens, random_seed=42
    )

    print("\nBootstrap Median Difference (10,000 iterations):")
    print(f"  Median difference: {np.median(treatment_tokens) - np.median(baseline_tokens):.0f}")
    print(f"  95% CI: [{lower:.0f}, {upper:.0f}]")
    print(f"  P-value: {p_value:.4f}")

    # Mann-Whitney U test (non-parametric, robust to outliers)
    u_stat, u_p, u_interp = mann_whitney_u_test(baseline_tokens, treatment_tokens)
    print("\nMann-Whitney U Test (non-parametric):")
    print(f"  U-statistic: {u_stat:.0f}")
    print(f"  P-value: {u_p:.4f} ({u_interp})")

    # Cohen's d (for comparison, less robust to outliers)
    d = cohens_d(baseline_tokens, treatment_tokens)
    print("\nEffect Size:")
    print(f"  Cohen's d: {d:.3f} ({interpret_effect_size('cohens_d', d)})")

    print("\n" + "=" * 70 + "\n")


def example_mcnemar_test():
    """Example: McNemar's test for paired binary outcomes."""
    print("=" * 70)
    print("EXAMPLE 4: McNemar's Test (Paired Tasks)")
    print("=" * 70)

    # Scenario: 100 tasks tested with both baseline and treatment
    both_succeed = 40  # Both baseline and treatment succeed
    only_baseline = 10  # Only baseline succeeds
    only_treatment = 30  # Only treatment succeeds
    both_fail = 20      # Both fail

    print("\nPaired Task Outcomes (n=100 tasks):")
    print(f"  Both succeed: {both_succeed}")
    print(f"  Only baseline succeeds: {only_baseline}")
    print(f"  Only treatment succeeds: {only_treatment}")
    print(f"  Both fail: {both_fail}")

    baseline_success_rate = (both_succeed + only_baseline) / 100
    treatment_success_rate = (both_succeed + only_treatment) / 100

    print("\nSuccess Rates:")
    print(f"  Baseline: {baseline_success_rate:.1%}")
    print(f"  Treatment: {treatment_success_rate:.1%}")

    # McNemar's test
    p_value, interp = mcnemar_exact_test(both_succeed, only_baseline, only_treatment, both_fail)

    print("\nMcNemar's Exact Test:")
    print(f"  P-value: {p_value:.4f} ({interp})")
    print(f"  Discordant pairs: {only_baseline + only_treatment}")
    print(f"  Treatment advantage: {only_treatment - only_baseline} more successes")

    print("\n" + "=" * 70 + "\n")


def example_multiple_comparisons():
    """Example: Multiple comparison correction."""
    print("=" * 70)
    print("EXAMPLE 5: Multiple Comparison Correction")
    print("=" * 70)

    # Scenario: Testing treatment on 5 different domains
    domains = ["Python", "JavaScript", "SQL", "DevOps", "Math"]
    p_values = [0.001, 0.015, 0.032, 0.089, 0.234]

    print("\nP-values from 5 domain-specific tests:")
    for domain, p in zip(domains, p_values):
        print(f"  {domain:12s}: p={p:.4f}")

    # Uncorrected
    uncorrected_sig = [p < 0.05 for p in p_values]
    print(f"\nUncorrected (alpha=0.05): {sum(uncorrected_sig)}/5 significant")

    # FDR correction (Benjamini-Hochberg)
    fdr_sig, fdr_adjusted = fdr_correction(p_values, alpha=0.05)
    print(f"\nFDR Correction (Benjamini-Hochberg): {sum(fdr_sig)}/5 significant")
    for domain, p, adj_p, sig in zip(domains, p_values, fdr_adjusted, fdr_sig):
        status = "SIGNIFICANT" if sig else "not significant"
        print(f"  {domain:12s}: p={p:.4f}, adjusted p={adj_p:.4f} ({status})")

    print("\n" + "=" * 70 + "\n")


def main():
    """Run all examples."""
    print("\n")
    print("*" * 70)
    print("STATISTICAL ANALYSIS EXAMPLES FOR ALEC EVALUATION")
    print("*" * 70)
    print("\n")

    example_success_rate_comparison()
    example_paired_comparison()
    example_token_usage_comparison()
    example_mcnemar_test()
    example_multiple_comparisons()

    print("*" * 70)
    print("SUMMARY")
    print("*" * 70)
    print("""
Key Takeaways:

1. Bootstrap Methods:
   - Non-parametric, no normality assumptions
   - Provides confidence intervals and p-values
   - Use 10,000 iterations for stable estimates

2. Effect Sizes:
   - Cohen's d: Standardized mean difference (continuous metrics)
   - Cohen's h: Arcsine-transformed proportion difference (binary outcomes)
   - Odds Ratio / Relative Risk: Interpretable ratios for success rates
   - Interpretation: <0.2 negligible, 0.2-0.5 small, 0.5-0.8 medium, >0.8 large

3. Statistical Tests:
   - McNemar: Paired binary outcomes (same tasks, different systems)
   - Paired t-test: Paired continuous outcomes (assumes normality)
   - Mann-Whitney U: Independent groups (non-parametric, robust to outliers)
   - Fisher's exact: Small sample binary outcomes

4. Multiple Comparisons:
   - Always correct when testing multiple hypotheses
   - FDR (Benjamini-Hochberg): Good balance of power and control
   - Use for domain-specific or subgroup analyses

5. Best Practices:
   - Check normality before choosing parametric vs non-parametric tests
   - Use median for skewed distributions (e.g., token usage)
   - Report both effect sizes and p-values
   - Always use paired tests when comparing same tasks
""")
    print("*" * 70)


if __name__ == "__main__":
    main()
