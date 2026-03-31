# AppWorld Evaluation Suite

Evaluation framework for measuring ALEC's learning capabilities using the AppWorld benchmark.

## Purpose

AppWorld provides a realistic benchmark of 750+ tasks across 9 apps (email, calendar, file management, etc.) for evaluating autonomous agents. This suite measures how ALEC's bullet-based learning improves task completion rates over time.

Key metrics tracked:
- **Task success rate** - Percentage of tasks completed correctly
- **Token efficiency** - Tokens used per successful task
- **Bullet effectiveness** - Which bullets contribute to success
- **Learning velocity** - How quickly performance improves with learning

## Prerequisites

- Docker and Docker Compose
- Running ALEC infrastructure (`docker-compose up -d` from project root)
- Anthropic API key configured in `.env`

## Running Experiments

### Quick Start

```bash
# Build the evaluation container
docker-compose -f docker-compose.yml -f evaluation/appworld/docker-compose.override.yml build appworld-eval

# Run baseline experiment (no learning)
docker-compose -f docker-compose.yml -f evaluation/appworld/docker-compose.override.yml run --rm appworld-eval \
    python -m runner --experiment baseline --tasks 50

# Run learning curve experiment
docker-compose -f docker-compose.yml -f evaluation/appworld/docker-compose.override.yml run --rm appworld-eval \
    python -m runner --experiment learning_curve --tasks 200
```

### Experiment Types

#### 1. Baseline (`baseline`)

Establishes performance without ALEC's learning system. Uses only default/static prompts.

```bash
docker-compose run --rm appworld-eval python -m runner --experiment baseline --tasks 100
```

**Output:**
- Raw success rate
- Token usage statistics
- Error distribution by task type

#### 2. Learning Curve (`learning_curve`)

Measures performance improvement as ALEC accumulates bullets over sequential tasks.

```bash
docker-compose run --rm appworld-eval python -m runner --experiment learning_curve --tasks 500 --batch-size 25
```

**Output:**
- Success rate over time (batched)
- Bullet accumulation rate
- Token efficiency trajectory

#### 3. Bullet Evolution (`bullet_evolution`)

Analyzes which bullets emerge and persist across many tasks.

```bash
docker-compose run --rm appworld-eval python -m runner --experiment bullet_evolution --tasks 300
```

**Output:**
- Top performing bullets by domain
- Bullet lifetime and effectiveness scores
- Semantic clusters of successful patterns

## Configuration

Experiment parameters are defined in `config/experiments.yaml`:

```yaml
experiments:
  baseline:
    tasks: 100
    seed: 42
    # Note: For baseline tests, disable learning services via /agents page

  learning_curve:
    tasks: 500
    batch_size: 25
    seed: 42
    checkpoint_interval: 50

  bullet_evolution:
    tasks: 300
    track_bullets: true
    effectiveness_threshold: 0.6
```

**Learning Control**: Learning is controlled via service toggles on the /agents page.
Disable bullet-reflector, effectiveness-reflector, and bullet-curator for baseline experiments.

### Custom Experiments

Create a custom experiment configuration:

```yaml
# config/experiments.yaml
experiments:
  my_experiment:
    tasks: 200
    task_filter:
      apps: ["email", "calendar"]
      difficulty: ["easy", "medium"]
```

Run with:
```bash
docker-compose run --rm appworld-eval python -m runner --experiment my_experiment
```

## Viewing Results

Results are stored in PostgreSQL and viewable in the ALEC frontend:

1. Navigate to `http://localhost:3001/evaluation`
2. Select experiment run from dropdown
3. View metrics:
   - Success rate charts
   - Token usage trends
   - Bullet effectiveness rankings
   - Task-by-task breakdown

### Raw Data Access

Query results directly:

```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -c "
SELECT
    experiment_type,
    COUNT(*) as tasks,
    AVG(CASE WHEN success THEN 1 ELSE 0 END) as success_rate,
    AVG(tokens_used) as avg_tokens
FROM evaluation_results
GROUP BY experiment_type
ORDER BY created_at DESC;
"
```

## Architecture

```
evaluation/appworld/
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── config/
│   └── experiments.yaml    # Experiment configurations
├── runner/
│   ├── __init__.py
│   ├── __main__.py         # CLI entry point
│   ├── alec_client.py      # ALEC session API client
│   ├── experiment.py       # Experiment orchestration
│   └── metrics.py          # Metric collection
└── experiments/
    ├── __init__.py
    ├── baseline.py         # Baseline experiment
    ├── learning_curve.py   # Learning curve experiment
    └── bullet_evolution.py # Bullet evolution experiment
```

## Troubleshooting

### Container can't connect to ALEC

Ensure ALEC services are running:
```bash
docker-compose ps
curl http://localhost:8008/health
```

### AppWorld download fails

The AppWorld dataset is large (~2GB). Ensure sufficient disk space and network connectivity:
```bash
docker-compose run --rm appworld-eval appworld download data --verbose
```

### Results not appearing in dashboard

Check that the evaluation results table exists:
```bash
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -c "\dt evaluation_*"
```

Run migrations if needed from the project root.

## Contributing

When adding new experiment types:

1. Create experiment class in `experiments/`
2. Add configuration schema in `config/experiments.yaml`
3. Register experiment in `runner/__main__.py`
4. Add dashboard visualizations in frontend

Follow ALEC coding standards: type hints, Google-style docstrings, async/await for I/O.
