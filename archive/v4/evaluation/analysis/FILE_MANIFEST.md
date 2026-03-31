# File Manifest - Phase 1: Statistical Core

## Directory Structure

```
evaluation/analysis/
├── Core Implementation (3 modules)
│   ├── bootstrap.py                     # Bootstrap confidence intervals
│   ├── effect_sizes.py                  # Effect size calculations
│   └── statistical_tests.py             # Hypothesis testing
│
├── Tests (3 modules, 89 tests)
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_bootstrap.py            # 16 test methods
│   │   ├── test_effect_sizes.py         # 36 test methods
│   │   └── test_statistical_tests.py    # 37 test methods
│
├── Documentation (3 files)
│   ├── README.md                        # Comprehensive user guide
│   ├── IMPLEMENTATION_SUMMARY.md        # Technical details
│   └── QUICK_REFERENCE.md              # One-page cheat sheet
│
├── Utilities (2 scripts)
│   ├── example_usage.py                 # 5 working examples
│   └── verify_implementation.py         # Syntax validation
│
└── Support Files (3 files)
    ├── __init__.py                      # Package exports
    ├── requirements.txt                 # scipy dependency
    └── FILE_MANIFEST.md                 # This file
```

## File Details

### Core Implementation

#### `bootstrap.py` (210 lines)
- `bootstrap_success_rate_ci()` - Compare success rates with bootstrap
- `bootstrap_paired_difference_ci()` - Paired continuous outcomes
- `bootstrap_median_difference_ci()` - Robust to outliers
- **Purpose:** Non-parametric confidence intervals
- **Dependencies:** numpy
- **Tests:** 16 methods in test_bootstrap.py

#### `effect_sizes.py` (311 lines)
- `cohens_d()` - Standardized mean difference
- `cohens_h()` - Proportion difference
- `odds_ratio()` - Odds ratio with CI
- `relative_risk()` - Relative risk with CI
- `interpret_effect_size()` - Cohen's interpretations
- `calculate_sample_size_for_effect()` - Power analysis
- **Purpose:** Measure practical significance
- **Dependencies:** numpy, scipy.stats
- **Tests:** 36 methods in test_effect_sizes.py

#### `statistical_tests.py` (364 lines)
- `mcnemar_exact_test()` - Paired binary outcomes
- `paired_t_test()` - Paired continuous (parametric)
- `mann_whitney_u_test()` - Independent groups (non-parametric)
- `fishers_exact_test()` - Small sample binary
- `bonferroni_correction()` - Family-wise error control
- `fdr_correction()` - False discovery rate control
- `sequential_bonferroni()` - Holm-Bonferroni
- `check_normality()` - Shapiro-Wilk test
- **Purpose:** Hypothesis testing and multiple comparisons
- **Dependencies:** numpy, scipy.stats
- **Tests:** 37 methods in test_statistical_tests.py

### Tests

#### `tests/test_bootstrap.py`
- 5 test classes
- 16 test methods
- Covers: significance detection, CI width, edge cases, reproducibility

#### `tests/test_effect_sizes.py`
- 7 test classes
- 36 test methods
- Covers: effect size ranges, interpretations, ratios, sample size calculations

#### `tests/test_statistical_tests.py`
- 10 test classes
- 37 test methods
- Covers: parametric/non-parametric tests, multiple comparisons, normality checks

### Documentation

#### `README.md`
- **Purpose:** Primary user documentation
- **Sections:**
  - Overview and installation
  - Module reference with examples
  - Usage guidelines and best practices
  - Testing instructions
  - References to statistical literature
- **Audience:** Users implementing statistical analysis

#### `IMPLEMENTATION_SUMMARY.md`
- **Purpose:** Technical implementation details
- **Sections:**
  - Deliverables overview
  - Function implementations
  - Test coverage breakdown
  - Design decisions
  - Performance characteristics
  - Integration points
- **Audience:** Developers and maintainers

#### `QUICK_REFERENCE.md`
- **Purpose:** Quick lookup guide
- **Sections:**
  - Decision tree for test selection
  - Common scenarios table
  - Quick examples (copy-paste ready)
  - Effect size interpretation
  - Function signatures
- **Audience:** Users needing fast answers

#### `FILE_MANIFEST.md` (this file)
- **Purpose:** File organization reference
- **Sections:**
  - Directory structure
  - File details and purposes
  - Line counts and dependencies

### Utilities

#### `example_usage.py`
- **Purpose:** Working examples for all major use cases
- **Examples:**
  1. Success rate comparison (bootstrap + effect sizes)
  2. Paired task comparison (iterations)
  3. Token usage comparison (skewed data)
  4. McNemar's test for paired tasks
  5. Multiple comparison correction
- **Usage:** `python evaluation/analysis/example_usage.py`

#### `verify_implementation.py`
- **Purpose:** Validate syntax and documentation
- **Checks:**
  - Python syntax validation
  - Docstring coverage
  - Test method counting
- **Usage:** `python evaluation/analysis/verify_implementation.py`

### Support Files

#### `__init__.py`
- **Purpose:** Package initialization and exports
- **Exports:** All 21 statistical functions
- **Usage:** `from evaluation.analysis import bootstrap_success_rate_ci`

#### `requirements.txt`
- **Purpose:** Dependency specification
- **Contents:** scipy>=1.10.0
- **Note:** numpy and pytest already in main requirements

## Usage Patterns

### Import Everything
```python
from evaluation.analysis import *
```

### Import Specific Functions
```python
from evaluation.analysis import (
    bootstrap_success_rate_ci,
    cohens_d,
    mcnemar_exact_test,
)
```

### Import Module
```python
import evaluation.analysis as stats
stats.bootstrap_success_rate_ci(...)
```

## File Statistics

| Category | Files | Lines | Tests |
|----------|-------|-------|-------|
| Core Implementation | 3 | 885 | - |
| Tests | 3 | ~2,000 | 89 |
| Documentation | 4 | ~1,500 | - |
| Utilities | 2 | ~400 | - |
| Support | 2 | ~50 | - |
| **Total** | **14** | **~4,835** | **89** |

## Dependencies

- **numpy:** Array operations (already in ALEC)
- **scipy:** Statistical distributions and tests (added to requirements.txt)
- **pytest:** Testing framework (already in ALEC)

## Testing Coverage

Run all tests:
```bash
pytest evaluation/analysis/tests/ -v
```

Expected output: 89 passed

## Next Phase Integration

Phase 2 will use these files to implement:
- **Experiment Runner:** Uses bootstrap and statistical tests
- **Metrics Calculator:** Uses effect sizes
- **Comparison Engine:** Uses all statistical functions
- **Report Generator:** Formats results from all modules

## Maintenance

When updating this module:
1. Add new functions to appropriate core module
2. Add tests to corresponding test file
3. Update `__init__.py` exports
4. Add example to `example_usage.py`
5. Update README.md reference section
6. Update QUICK_REFERENCE.md if applicable

## Version History

- **v1.0 (2025-11-25):** Initial implementation
  - 21 statistical functions
  - 89 comprehensive tests
  - Complete documentation

---

**Last Updated:** 2025-11-25
