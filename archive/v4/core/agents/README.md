# Agents Service

**Strategic intelligence for ALEC's learning loop.**

This service provides macro-level analysis that GENERATOR cannot:
- GENERATOR extracts micro-patterns (turn-level)
- Agents extract macro-patterns (task-level, cross-session)

## Services

## Architectural Division of Labor

| Agent | Domain | Role |
|-------|--------|------|
| **LIBRARIAN** | Library Intelligence | **Passive/Analytical** - Identifies gaps, flags issues, archives |
| **STRATEGIST** | Performance Intelligence | **Active/Strategic** - Analyzes performance, fills gaps via synthesis |

**Metaphor:** Librarians organize and identify gaps; they don't write books. Strategists create strategies to fill those gaps.

### LIBRARIAN - Library Intelligence (Passive)

Analyzes the bullet library to identify knowledge gaps and maintain library hygiene.

**Consumes:**
- `attribution.resolved` - Analyze after GENERATOR processes session

**Emits:**
- `bullet.archived` - Harmful bullet auto-archived

**Diagnostic Types (6 total):**
1. `embedding_mismatch` - Bullet retrieved for wrong problem types
2. `content_divergence` - Embedding doesn't match content semantics
3. `counter_inconsistency` - High variance in outcomes across clusters
4. `competing_bullets` - Multiple bullets fighting for same problem
5. `content_quality_issue` - Uncertainty language ("unclear", "may", "cannot reliably")
6. `unvalidated_bullet` - Bullets stored as `status='unvalidated'` by CURATOR

**Capabilities:**
- Gap detection: Clusters with failures but no solutions
- Constraint fragmentation: Clusters with 5+ weak constraints
- Auto-archive: Bullets with high harm rate (uses counter-based detection, AppWorld-agnostic)

**Does NOT:** Create new bullets, call LLM, or take strategic action.

### STRATEGIST - Performance Intelligence (Active)

Analyzes agent performance across sessions and takes strategic action.

**Consumes:**
- `session.ended` - Session outcome signal (core signal)

**Emits:**
- `regression.detected` - Regression found in cluster performance
- `bullet.synthesized` - New workflow bullet created via LLM

**Capabilities:**
- Struggling clusters: Consistently poor success rates
- Regression detection: Clusters with declining success rates
- Bullet correlation: Bullets appearing in failures
- Learning curves: Improvement over time
- **LLM Synthesis:** Creates 'solutions' bullets to fill knowledge gaps

**Remediation (from LIBRARIAN diagnoses):**
- Types 1-2: Regenerate embeddings from cluster centroids or content
- Type 3: Create exclusion edges for inconsistent bullets
- Type 4: Archive losing bullet, link to winner via `similar_to`
- Types 5-6 (smart remediation):
  - If related solution exists → Archive (superseded)
  - If no solution → Rewrite via LLM with session transcript context

**Session Context:** Uses `user_message` and `assistant_response` from `session_turns` to inform evidence-based rewrites. Fetches turns where bullet was shown to compare successful vs failed approaches.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgresql://alec:...@localhost:5432/alec | PostgreSQL connection |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:9092 | Kafka bootstrap servers |
| `LIBRARIAN_ANALYSIS_THRESHOLD` | 10 | Sessions per cluster before analysis |
| `LIBRARIAN_AUTO_ARCHIVE_THRESHOLD` | 0.8 | Failure rate for auto-archive |
| `STRATEGIST_MIN_CLUSTER_TURNS` | 5 | Min turns before cluster analysis |
| `STRATEGIST_REGRESSION_WINDOW_DAYS` | 7 | Days for regression comparison |

## Running

### Docker Compose

```bash
docker-compose up -d agents
```

### Local Development

```bash
cd /home/matt/ALEC
python -m core.agents.main
```

## Testing

```bash
# Run all agents tests
pytest core/agents/tests -v

# Run SQL validation tests
pytest core/agents/tests -v -m sql_validation
```

## API Endpoints

Exposed via session service at port 8008:

- `GET /api/v1/system/intelligence` - Get combined LIBRARIAN + STRATEGIST analysis report (includes session_context availability)
- `POST /api/v1/system/intelligence/run` - Trigger batch analysis (archives harmful bullets, emits events)
- `POST /api/v1/system/intelligence/synthesize` - STRATEGIST LLM synthesis (`max_gaps` param)
- `POST /api/v1/system/intelligence/remediate` - Run remediation on LIBRARIAN diagnoses
- `POST /api/v1/system/diagnostic/librarian` - Test LIBRARIAN diagnostics (all 6 types)
- `POST /api/v1/system/diagnostic/strategist` - Test STRATEGIST remediation (includes session content check)

## Architecture

```
session.ended
     │
     ├──► GENERATOR (turn-level extraction)
     │         │
     │         ▼
     │    attribution.resolved
     │         │
     │         ├──► CLUSTERER (graph edges)
     │         │
     │         └──► LIBRARIAN (gap detection)
     │
     └──► STRATEGIST (performance analysis)
```

Both LIBRARIAN and STRATEGIST can also be triggered via API for batch analysis on historical data.
