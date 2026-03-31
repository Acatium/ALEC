# Quick Reference: Evaluation Tracking Queries

## Most Common Queries

### 1. Check if outcomes are being recorded
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT COUNT(*) as total_outcomes FROM evaluation_task_outcomes;"
```

### 2. Show recent outcomes
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT task_id, success, turns_to_success, total_turns, created_at FROM evaluation_task_outcomes ORDER BY created_at DESC LIMIT 10;"
```

### 3. Get latest experiment ID
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT id, name, started_at FROM evaluation_experiments ORDER BY started_at DESC LIMIT 1;"
```

### 4. View cross-session learning (replace <ID>)
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT * FROM cross_session_learning_analysis WHERE experiment_id = '<ID>';"
```

### 5. View learning curve (replace <ID>)
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT task_sequence, ROUND(rolling_success_rate_10::numeric, 2) FROM learning_curve_view WHERE experiment_id = '<ID>' ORDER BY task_sequence;"
```

### 6. Find hardest problems (replace <ID>)
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT problem_signature, success_rate_pct, avg_total_turns FROM problem_signature_performance WHERE experiment_id = '<ID>' ORDER BY success_rate_pct ASC LIMIT 10;"
```

## One-Liner Analysis

### Success rate for latest experiment
```bash
LATEST_ID=$(PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -t -c "SELECT id FROM evaluation_experiments ORDER BY started_at DESC LIMIT 1;" | xargs) && \
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT ROUND(AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate FROM evaluation_task_outcomes WHERE experiment_id = '$LATEST_ID';"
```

### Cross-session learning for latest experiment
```bash
LATEST_ID=$(PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -t -c "SELECT id FROM evaluation_experiments ORDER BY started_at DESC LIMIT 1;" | xargs) && \
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT problem_signature, ROUND((first_variant_success_rate * 100)::numeric, 0) || '% → ' || ROUND((later_variant_success_rate * 100)::numeric, 0) || '%' as learning FROM cross_session_learning_analysis WHERE experiment_id = '$LATEST_ID';"
```

## Export Data

### Export learning curve to CSV
```bash
LATEST_ID=$(PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -t -c "SELECT id FROM evaluation_experiments ORDER BY started_at DESC LIMIT 1;" | xargs) && \
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "COPY (SELECT task_sequence, rolling_success_rate_10 FROM learning_curve_view WHERE experiment_id = '$LATEST_ID') TO STDOUT WITH CSV HEADER;" > /tmp/learning_curve.csv
```

### Export all outcomes to JSON
```bash
LATEST_ID=$(PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -t -c "SELECT id FROM evaluation_experiments ORDER BY started_at DESC LIMIT 1;" | xargs) && \
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT row_to_json(t) FROM (SELECT * FROM evaluation_task_outcomes WHERE experiment_id = '$LATEST_ID') t;" > /tmp/outcomes.json
```

## Verification Shortcuts

### Verify schema exists
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "\d evaluation_task_outcomes"
```

### Verify views exist
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT table_name FROM information_schema.views WHERE table_schema = 'public' AND table_name LIKE '%learning%' OR table_name LIKE '%problem%';"
```

### Count records per experiment
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT e.name, COUNT(o.outcome_id) as outcomes FROM evaluation_experiments e LEFT JOIN evaluation_task_outcomes o ON e.id = o.experiment_id GROUP BY e.id, e.name ORDER BY e.started_at DESC;"
```

## Troubleshooting

### No outcomes recorded?
```bash
# Check experiment runner logs
docker-compose logs appworld-eval | grep "Recorded outcome"

# Check database connection
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT COUNT(*) FROM evaluation_task_outcomes;"
```

### Views return empty?
```bash
# List all experiments
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT id, name, started_at FROM evaluation_experiments ORDER BY started_at DESC;"

# Check outcome count per experiment
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec \
  -c "SELECT experiment_id, COUNT(*) FROM evaluation_task_outcomes GROUP BY experiment_id;"
```

## Interactive Analysis

### Connect to psql
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec
```

Then run queries interactively:
```sql
-- Set experiment ID
\set exp_id '00000000-0000-0000-0000-000000000000'

-- View learning curve
SELECT task_sequence, rolling_success_rate_10
FROM learning_curve_view
WHERE experiment_id = :'exp_id'
ORDER BY task_sequence;

-- View cross-session learning
SELECT * FROM cross_session_learning_analysis
WHERE experiment_id = :'exp_id';

-- Find failures
SELECT task_id, total_turns, execution_log->'error_message'
FROM evaluation_task_outcomes
WHERE experiment_id = :'exp_id' AND success = false;
```

## File Locations

- **Schema**: `/home/matt/ALEC/evaluation/database/schema.sql`
- **Connection**: `/home/matt/ALEC/evaluation/database/connection.py`
- **Examples**: `/home/matt/ALEC/evaluation/database/example_queries.sql`
- **Full docs**: `/home/matt/ALEC/evaluation/database/README.md`
- **Usage guide**: `/home/matt/ALEC/evaluation/database/USAGE.md`
