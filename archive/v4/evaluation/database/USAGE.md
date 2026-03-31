# Phase 0.4 Usage Guide: Evaluation Tracking

Quick reference for using the evaluation tracking infrastructure.

## Quick Start

### 1. Run an Experiment

The experiment runner automatically records outcomes:

```bash
# Run baseline experiment
docker-compose --profile evaluation run appworld-eval baseline \
  --dataset test_normal \
  --task-limit 10

# Run learning experiment
docker-compose --profile evaluation run appworld-eval learning_curve \
  --dataset train \
  --task-limit 50
```

### 2. Check Outcomes Were Recorded

```bash
# Count outcomes
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT COUNT(*) FROM evaluation_task_outcomes;"

# Show recent outcomes
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT task_id, success, turns_to_success, total_turns FROM evaluation_task_outcomes ORDER BY created_at DESC LIMIT 10;"
```

### 3. Analyze Results

```bash
# Get experiment ID
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT id, name, started_at FROM evaluation_experiments ORDER BY started_at DESC LIMIT 5;"

# View learning curve
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT task_sequence, ROUND(rolling_success_rate_10::numeric, 2) as rolling_avg FROM learning_curve_view WHERE experiment_id = '<ID>' ORDER BY task_sequence;"

# View cross-session learning
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT * FROM cross_session_learning_analysis WHERE experiment_id = '<ID>';"
```

## Common Workflows

### Workflow 1: Measure Cross-Session Learning

**Goal**: Determine if ALEC learns from earlier task variants to solve later variants faster.

```sql
-- Step 1: Run experiment with grouped tasks
-- Use grouping_strategy="base_id" to keep variants together

-- Step 2: Query cross-session learning view
SELECT
    problem_signature,
    total_variants,
    ROUND((first_variant_success_rate * 100)::numeric, 0) || '%' as first_variant,
    ROUND((later_variant_success_rate * 100)::numeric, 0) || '%' as later_variants,
    ROUND((later_variant_success_rate - first_variant_success_rate) * 100, 0) as improvement_pct,
    first_variant_avg_turns,
    later_variant_avg_turns
FROM cross_session_learning_analysis
WHERE experiment_id = '<ID>'
ORDER BY improvement_pct DESC;

-- Interpretation:
-- Positive improvement_pct = learning occurred
-- Negative improvement_pct = performance degraded (potential overfitting)
```

### Workflow 2: Identify Hard Problems

**Goal**: Find which task signatures are most difficult.

```sql
SELECT
    problem_signature,
    total_variants,
    ROUND(success_rate_pct, 1) as success_pct,
    ROUND(avg_total_turns, 1) as avg_turns
FROM problem_signature_performance
WHERE experiment_id = '<ID>'
ORDER BY success_rate_pct ASC, avg_total_turns DESC
LIMIT 20;

-- Then drill into failures:
SELECT
    o.task_id,
    o.total_turns,
    o.execution_log->'test_results'->>'num_tests' as total_tests,
    jsonb_array_length(COALESCE(o.execution_log->'test_results'->'passes', '[]'::jsonb)) as tests_passed
FROM evaluation_task_outcomes o
WHERE o.experiment_id = '<ID>'
  AND o.problem_signature = '<SIGNATURE>'
  AND o.success = false;
```

### Workflow 3: Compare Baseline vs. Learning

**Goal**: A/B test to measure learning system effectiveness.

**Setup**: Run two experiments with different service toggle states:
1. **Baseline**: Disable learning services via /agents page, then run experiment
2. **Learning**: Enable learning services via /agents page, then run experiment

```sql
-- Compare results by experiment name:
SELECT
    e.name,
    e.experiment_type,
    COUNT(o.outcome_id) as total_tasks,
    ROUND(AVG(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate_pct,
    ROUND(AVG(o.total_turns), 1) as avg_turns,
    ROUND(AVG(CASE WHEN o.success THEN o.turns_to_success ELSE NULL END), 1) as avg_turns_successful
FROM evaluation_experiments e
LEFT JOIN evaluation_task_outcomes o ON e.id = o.experiment_id
WHERE e.dataset_split = 'test_normal'
  AND e.status = 'completed'
GROUP BY e.id, e.name, e.experiment_type
ORDER BY success_rate_pct DESC;
```

### Workflow 4: Visualize Learning Curve

**Goal**: Plot success rate over time to show learning progression.

```sql
-- Export data for plotting
COPY (
    SELECT
        task_sequence,
        ROUND(rolling_success_rate_10::numeric, 3) as rolling_avg
    FROM learning_curve_view
    WHERE experiment_id = '<ID>'
    ORDER BY task_sequence
) TO '/tmp/learning_curve.csv' WITH CSV HEADER;

-- Then plot in Python, R, or Excel
-- X-axis: task_sequence
-- Y-axis: rolling_avg (0.0 to 1.0)
```

## Key Views Reference

### `problem_signature_performance`

**Purpose**: Aggregate metrics per problem signature

**Key Columns**:
- `success_rate_pct`: Percentage of variants that succeeded
- `avg_turns_when_successful`: Efficiency metric (lower is better)
- `avg_total_turns`: Includes failures (higher = problem is harder)

**Use Case**: Identify hardest problems, measure overall difficulty

### `cross_session_learning_analysis`

**Purpose**: Compare first vs. later variant performance

**Key Columns**:
- `first_variant_success_rate`: Success rate on first encounter
- `later_variant_success_rate`: Success rate on subsequent encounters
- Difference shows learning effect

**Use Case**: Measure cross-session learning, validate learning loop

### `learning_curve_view`

**Purpose**: Show performance evolution over time

**Key Columns**:
- `task_sequence`: Order tasks were executed
- `rolling_success_rate_10`: Smoothed success rate (10-task window)

**Use Case**: Visualize learning progression, detect performance degradation

## Troubleshooting

### No outcomes recorded

**Check experiment runner logs**:
```bash
docker-compose logs appworld-eval | grep "Recorded outcome"
```

**Verify database connection**:
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT COUNT(*) FROM evaluation_task_outcomes;"
```

### Views return no data

**Verify experiment ID**:
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT id, name FROM evaluation_experiments ORDER BY started_at DESC LIMIT 5;"
```

**Check outcome count per experiment**:
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT experiment_id, COUNT(*) FROM evaluation_task_outcomes GROUP BY experiment_id;"
```

## Best Practices

### 1. Use Consistent Grouping Strategy

For cross-session learning analysis, use `grouping_strategy="base_id"`:

```bash
docker-compose --profile evaluation run appworld-eval learning_curve \
  --dataset train \
  --grouping-strategy base_id
```

This ensures task variants run sequentially, allowing learning to occur.

### 2. Run Multiple Experiments for Comparison

Don't just run one experiment - compare:
- Baseline vs. Learning
- Different datasets (train, test_normal, test_challenge)
- Different grouping strategies
- Different checkpoint intervals

### 3. Archive Execution Logs

The `execution_log` JSONB field stores full execution history. Use it to debug failures:

```sql
SELECT
    task_id,
    execution_log->'error_message' as error,
    execution_log->'test_results' as test_results
FROM evaluation_task_outcomes
WHERE success = false
  AND experiment_id = '<ID>';
```

### 4. Monitor Database Size

Outcomes can accumulate quickly. Monitor disk usage:

```sql
SELECT
    pg_size_pretty(pg_total_relation_size('evaluation_task_outcomes')) as table_size;
```

Consider periodic cleanup of old experiments (after exporting results).

## Integration with Experiment Runner

The experiment runner automatically:
1. Records outcomes after each task (`_record_task_outcome()`)
2. Extracts problem signatures from task IDs
3. Builds execution logs with test results
4. Handles failures gracefully (logs warning, continues)

**No manual intervention required** - just run experiments and query results.

## Related Documentation

- **[README.md](README.md)**: Full architecture and design principles
- **[example_queries.sql](example_queries.sql)**: Pre-written analysis queries
- **[schema.sql](schema.sql)**: Database schema definition
