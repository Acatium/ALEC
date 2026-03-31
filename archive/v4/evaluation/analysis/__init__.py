"""Statistical analysis tools for ALEC evaluation."""

from .bootstrap import bootstrap_success_rate_ci
from .effect_sizes import (
    cohens_d,
    cohens_h,
    interpret_effect_size,
    odds_ratio,
)
from .statistical_tests import (
    bonferroni_correction,
    fdr_correction,
    mann_whitney_u_test,
    mcnemar_exact_test,
    paired_t_test,
)

__all__ = [
    # Bootstrap
    "bootstrap_success_rate_ci",
    # Effect sizes
    "cohens_d",
    "cohens_h",
    "odds_ratio",
    "interpret_effect_size",
    # Statistical tests
    "mcnemar_exact_test",
    "paired_t_test",
    "mann_whitney_u_test",
    "bonferroni_correction",
    "fdr_correction",
]
