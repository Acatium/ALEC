# Evaluation Database Infrastructure (Phase 0.4)

This directory contains the evaluation harness's own tracking infrastructure, maintaining architectural separation from ALEC core services.

## Overview

The evaluation tracking system records ground truth outcomes from AppWorld task execution, enabling:
- Cross-session learning analysis (do later task variants succeed faster?)
- Learning curve visualization (does success rate improve over time?)
- Problem difficulty assessment (which task signatures are hardest?)
- Experiment reproducibility (can we recreate results?)

## Key Design Principles

### Architectural Separation
- **Evaluation tables**: Separate from ALEC core tables
- **No foreign keys**: `evaluation_task_outcomes.session_id` is reference-only
- **Read-only for ALEC**: Core services never read evaluation tracking tables
- **Consumer pattern**: Evaluation harness observes, doesn't control ALEC

### Data Flow
1. Experiment runner executes tasks via ALEC session service
2. After each task completes, writes outcome to `evaluation_task_outcomes`
3. Outcome includes: success/failure, turns taken, problem signature, execution log
4. Views provide pre-computed analytics (learning curves, cross-session analysis)

## Files

### Schema
- **`schema.sql`**: Creates `evaluation_task_outcomes` table and analytical views
- **`14_evaluation_tracking.sql`**: Docker init script (auto-applied on startup)

### Connection
- **`connection.py`**: Database connection helper with `record_task_outcome()` method
- **`__init__.py`**: Package marker

### Verification
- **`verify_tracking.sql`**: SQL-based verification (runnable without Python dependencies)
- **`verify_tracking.py`**: Python-based verification (requires asyncpg)

### Documentation
- **`example_queries.sql`**: Common analysis queries with explanations
- **`README.md`**: This file

## Database Schema

### Table: `evaluation_task_outcomes`

Tracks individual task outcomes from evaluation harness perspective.

| Column | Type | Description |
|--------|------|-------------|
| `outcome_id` | UUID | Primary key |
| `experiment_id` | UUID | Links to `evaluation_experiments` table |
| `task_id` | VARCHAR(100) | Task identifier (e.g., "024c982_2") |
| `session_id` | UUID | Session reference (not FK - read-only) |
| `success` | BOOLEAN | Ground truth: did task pass all tests? |
| `turns_to_success` | INTEGER | Turns taken to succeed (NULL if failed) |
| `total_turns` | INTEGER | Total conversation turns |
| `problem_signature` | VARCHAR(100) | Base problem ID (e.g., "024c982") |
| `execution_log` | JSONB | Full execution history for debugging |
| `created_at` | TIMESTAMP | Record creation time |

**Indexes**: `experiment_id`, `task_id`, `problem_signature`, `session_id`, `success`

### Views

#### `problem_signature_performance`
Shows aggregate performance across task variants.

```sql
SELECT * FROM problem_signature_performance WHERE experiment_id = '<ID>';
```

**Columns**:
- `problem_signature`: Base problem ID
- `total_variants`: Number of task variants
- `successful_variants`: Count of successful attempts
- `success_rate_pct`: Success percentage
- `avg_turns_when_successful`: Average turns for successful tasks

#### `learning_curve_view`
Shows success rate progression over time.

```sql
SELECT * FROM learning_curve_view WHERE experiment_id = '<ID>';
```

**Columns**:
- `task_sequence`: Order in which tasks were run
- `task_id`, `problem_signature`, `success`, `turns_to_success`
- `rolling_success_rate_10`: 10-task rolling average

#### `cross_session_learning_analysis`
Measures learning across task variants.

```sql
SELECT * FROM cross_session_learning_analysis WHERE experiment_id = '<ID>';
```

**Columns**:
- `first_variant_success_rate`: Success rate on first variant
- `later_variant_success_rate`: Success rate on subsequent variants
- `first_variant_avg_turns`: Average turns on first variant
- `later_variant_avg_turns`: Average turns on later variants

**Interpretation**: If `later_variant_success_rate > first_variant_success_rate`, system learned from earlier attempts.

## Usage

### Recording Outcomes (Experiment Runner)

```python
from evaluation.database.connection import EvaluationDatabase

# Initialize database connection
eval_db = EvaluationDatabase()
await eval_db.get_pool()

# Record task outcome after execution
await eval_db.record_task_outcome(
    experiment_id=experiment_id,
    task_id="024c982_2",
    session_id=session_id,
    success=True,
    turns_to_success=5,
    total_turns=5,
    execution_log={
        "iterations": 5,
        "tokens_used": 12500,
        "test_results": {"num_tests": 5, "passes": [0, 1, 2, 3, 4]},
    },
)

# Clean up when done
await eval_db.close()
```

### Querying Outcomes (Analysis)

See `example_queries.sql` for common analysis patterns:
- Overall success rates
- Cross-session learning evidence
- Learning curves
- Problem difficulty analysis
- Failure analysis
- Experiment comparisons (A/B testing)

### Verification

```bash
# SQL verification (no dependencies required)
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -f evaluation/database/verify_tracking.sql

# Python verification (requires asyncpg)
cd evaluation/database
python3 verify_tracking.py
```

## Integration with Experiment Runner

The experiment runner (`evaluation/appworld/runner/experiment_runner.py`) automatically records outcomes:

1. After each task completes:
   ```python
   await self._record_task_outcome(experiment_id, result)
   ```

2. Extracts problem signature from task ID:
   ```python
   # "024c982_2" → "024c982"
   problem_signature = task_id.rsplit('_', 1)[0]
   ```

3. Builds execution log:
   ```python
   execution_log = {
       "success": result.success,
       "iterations": result.iterations,
       "tokens_used": result.tokens_used,
       "duration_ms": result.duration_ms,
       "error_message": result.error_message,
       "test_results": result.test_results,
   }
   ```

## Analysis Examples

### Example 1: Did learning improve later variants?

```sql
SELECT
    problem_signature,
    ROUND((first_variant_success_rate * 100)::numeric, 0) || '%' as first,
    ROUND((later_variant_success_rate * 100)::numeric, 0) || '%' as later,
    ROUND((later_variant_success_rate - first_variant_success_rate) * 100, 0) as improvement
FROM cross_session_learning_analysis
WHERE experiment_id = '<ID>'
  AND later_variant_success_rate > first_variant_success_rate
ORDER BY improvement DESC;
```

### Example 2: Which problems are hardest?

```sql
SELECT
    problem_signature,
    total_variants,
    ROUND(success_rate_pct, 1) as success_pct,
    ROUND(avg_total_turns, 1) as avg_turns
FROM problem_signature_performance
WHERE experiment_id = '<ID>'
ORDER BY success_rate_pct ASC, avg_total_turns DESC
LIMIT 10;
```

### Example 3: Is success rate improving over time?

```sql
SELECT
    task_sequence,
    ROUND(rolling_success_rate_10::numeric, 2) as rolling_avg
FROM learning_curve_view
WHERE experiment_id = '<ID>'
ORDER BY task_sequence;
```

## Future Enhancements

Potential additions (not yet implemented):
- **Bullet correlation analysis**: Which bullets correlate with success?
- **Domain-specific metrics**: Success rates by detected domain
- **Temporal patterns**: Are certain problems harder early vs. late?
- **Multi-experiment aggregation**: Cross-experiment learning trends

## Troubleshooting

### Issue: Outcomes not being recorded

**Check**:
1. Database connection: `await eval_db.get_pool()`
2. Experiment runner logs: Look for "Recorded outcome" debug messages
3. Database errors: Check PostgreSQL logs

```bash
# Check if table exists
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "\d evaluation_task_outcomes"

# Check recent outcomes
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT COUNT(*) FROM evaluation_task_outcomes"
```

### Issue: Views returning no data

**Cause**: Views filter by `experiment_id` - ensure you're querying the correct experiment.

```sql
-- List all experiments
SELECT id, name, experiment_type, started_at
FROM evaluation_experiments
ORDER BY started_at DESC;

-- Check outcome count per experiment
SELECT experiment_id, COUNT(*) as outcome_count
FROM evaluation_task_outcomes
GROUP BY experiment_id;
```

## Related Documentation

- **[ARCHITECTURE.md](../../ARCHITECTURE.md)**: Overall system design
- **[CLAUDE.md](../../CLAUDE.md)**: Development guidelines
- **[evaluation/appworld/runner/](../appworld/runner/)**: Experiment runner implementation
