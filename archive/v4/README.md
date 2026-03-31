# ALEC

**Adaptive Learning & Execution Core**

Event-driven learning system for conversational AI that improves through feedback loops.

---

## What is ALEC?

ALEC observes conversational AI sessions, extracts patterns, and injects contextual "bullets" to guide future responses. The system learns autonomously through:

- **Learning Loop** that evaluates turns and extracts generalizable insights
- **Thompson Sampling** for exploration-exploitation balanced bullet selection
- **Redis cache** for fast bullet retrieval during conversations
- **Event-driven architecture** for independent scaling and fault isolation

**Key Innovation:** Two-pool selection fixes bootstrap paradox; similarity gating prevents unfair attribution; LLM-based quality gate ensures only actionable insights become bullets.

---

## Quick Start

**In a hurry?** See [QUICKSTART.md](QUICKSTART.md) for a condensed 3-step setup guide.

---

### Prerequisites
- Docker 24+ & Docker Compose 2.0+
- Python 3.11+ (for local development)
- Anthropic API key ([Get one here](https://console.anthropic.com/))
- 10GB free disk space
- 4GB RAM minimum (8GB recommended)

### Verify Prerequisites

Before starting, verify you have the required software:

```bash
# Check Docker version (need 24+)
docker --version

# Check Docker Compose version (need 2.0+)
docker-compose --version

# Check Python version (need 3.11+)
python3 --version

# Check available disk space (need 10GB+)
df -h
```

### Setup

**Time Expectations:**
- First build: 5-10 minutes (downloads base images, installs dependencies)
- Subsequent builds: 1-3 minutes (uses cached layers)
- Service startup: 30-60 seconds (healthchecks must pass)

```bash
# 1. Clone repository
git clone <repository-url>
cd ALEC

# 2. Configure environment
cat > .env << EOF
ANTHROPIC_API_KEY=your-key-here
POSTGRES_USER=alec
POSTGRES_PASSWORD=alec-dev-password
POSTGRES_DB=alec
EOF

# Alternative: Copy from example (if available)
# cp .env.example .env
# Then edit .env and add your API key

# 3. Start all services (this will take several minutes on first run)
docker-compose up -d

# 4. Wait for services to start (~30-60 seconds)
echo "Waiting for services to initialize..."
sleep 30

# 5. Verify services are running
docker-compose ps

# Expected: All services should show "Up" or "healthy" status
# Note: memory-retrieval-reflector and performance-monitoring-reflector
# may show "Restarting" - this is a known issue with volume mounts

# 6. Test the API
curl http://localhost:8008/health
# Expected output: {"status":"healthy"}
```

### Access

- **Frontend:** http://localhost:3001
- **API:** http://localhost:8008
- **API Docs:** http://localhost:8008/docs

---

## What's Next?

After successful setup, explore ALEC:

1. **Try the Chat Interface**: Open http://localhost:3001 and start a conversation
2. **Explore the API**: Visit http://localhost:8008/docs for interactive API documentation
3. **Understand the Architecture**: Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design details
4. **View Service Logs**: `docker-compose logs -f session` to see real-time activity
5. **Inspect Kafka Events**: See debugging commands in [Development](#development) section
6. **Run Tests**: Follow [CONTRIBUTING.md](CONTRIBUTING.md) for local development setup
7. **Monitor Learning**: Check Redis and PostgreSQL to see bullets being created

---

## Troubleshooting

**For detailed known issues and workarounds, see [KNOWN_ISSUES.md](KNOWN_ISSUES.md)**

### Services stuck in "Restarting" state

**Symptoms**: `docker-compose ps` shows services constantly restarting

**Solution**:
```bash
# Check logs to identify the issue
docker-compose logs -f <service-name>

# If services are restarting, check specific logs for error details.
# See KNOWN_ISSUES.md for detailed workarounds.
```

### "Cannot connect to Docker daemon"

**Symptoms**: `docker-compose` commands fail with connection errors

**Solution**:
- **Mac/Windows**: Ensure Docker Desktop is running
- **Linux**: Start Docker service: `sudo systemctl start docker`

### Missing ANTHROPIC_API_KEY

**Symptoms**: session service fails to start or returns API errors

**Solution**:
1. Get your API key at https://console.anthropic.com/
2. Add it to your `.env` file:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE
   ```
3. Restart services: `docker-compose restart session`

### "No space left on device"

**Symptoms**: Build fails with disk space errors

**Solution**:
```bash
# Check Docker disk usage
docker system df

# Clean up unused images and containers
docker system prune -a

# Remove old volumes (WARNING: deletes all Docker volumes)
docker volume prune
```

### Port already in use

**Symptoms**: Service fails to start with "port already allocated"

**Solution**:
```bash
# Find process using the port (example for port 8008)
lsof -i :8008  # Mac/Linux
netstat -ano | findstr :8008  # Windows

# Stop conflicting service or change port in docker-compose.yml
```

### Services start but frontend shows "Cannot connect to API"

**Symptoms**: Frontend loads but can't communicate with backend

**Solution**:
1. Verify session service is healthy: `curl http://localhost:8008/health`
2. Check CORS settings in `.env` if accessing from different origin
3. Check browser console for specific errors

### Kafka healthcheck failing

**Symptoms**: Services wait indefinitely for Kafka to become healthy

**Solution**:
```bash
# Check Kafka logs
docker-compose logs kafka

# Kafka takes 30-45 seconds to initialize on first start
# If it fails after 2 minutes, try:
docker-compose restart kafka
```

### PostgreSQL connection refused

**Symptoms**: Services fail with "could not connect to server"

**Solution**:
```bash
# Verify PostgreSQL is running and healthy
docker-compose ps postgres

# Test connection manually
PGPASSWORD=alec-dev-password psql -h localhost -U alec -d alec -c "SELECT 1"

# If connection fails, restart PostgreSQL
docker-compose restart postgres
```

### Need to reset everything

**Solution**:
```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Rebuild and restart
docker-compose up -d --build
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│  Session Layer: session                 │
│  (Pure orchestration: bullets → LLM)    │
└────────────┬───────────▲────────────────┘
             │           │
     emits   │           │ writes
     events  │           │ bullets
             ▼           │
┌─────────────────────────────────────────┐
│  Event Bus: Kafka                       │
└────────────┬────────────────────────────┘
             │ consumes
             ▼
┌─────────────────────────────────────────┐
│  Learning Loop: 3 Services              │
│  • ADVISOR    → Task extraction +       │
│                 Thompson Sampling       │
│  • GENERATOR  → LLM turn evaluation +   │
│                 Counter updates         │
│  • CLUSTERER  → Knowledge graph         │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  Batch Processing: Librarian            │
│  (Deep consolidation - manual trigger)  │
└────────────┬────────────────────────────┘
             │ reads/writes
             ▼
┌─────────────────────────────────────────┐
│  Storage: PostgreSQL + pgvector         │
└─────────────────────────────────────────┘
```

**See [ARCHITECTURE.md](ARCHITECTURE.md) for details.**

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| session | 8008 | Session orchestration, bullet coordination |
| learning-loop | - | ADVISOR, GENERATOR, CLUSTERER |
| llm-gateway | - | LLM abstraction and cost tracking |
| librarian | - | Batch consolidation (manual trigger) |
| frontend | 3001 | React UI |
| kafka | 9092 | Event bus |
| postgres | 5432 | PostgreSQL + pgvector storage |
| redis | 6379 | Bullet cache |

---

## Development

### Run Tests

```bash
# All tests
pytest -v

# Specific service
pytest core/conversational_ai/tests -v

# With coverage
pytest --cov=core --cov-report=html
```

### Format Code

```bash
black .
isort .
mypy .
ruff check .
```

### View Logs

```bash
# Session service
docker-compose logs -f session

# Learning Loop
docker-compose logs -f learning-loop

# Last 100 lines
docker-compose logs --tail=100 session
```

### Debug Kafka Events

```bash
# List topics
docker exec -it alec-kafka kafka-topics --list --bootstrap-server localhost:9092

# Consume events
docker exec -it alec-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic session.created \
  --from-beginning
```

---

## Key Concepts

### Bullets
Contextual hints injected into LLM prompts, tagged for action:

- **`[+]` DO:** cheat_sheets, examples, meta_prompts, solutions (success/progress signals)
- **`[-]` AVOID:** constraints, failure insights (failure signals)

**Categories:**
- **cheat_sheets:** Quick reference facts
- **constraints:** Rules and guardrails
- **examples:** Concrete demonstrations
- **meta_prompts:** Reasoning guidance
- **solutions:** Proven problem→solution mappings

### Learning Loop
Event-driven learning with 3 internal services:

- **ADVISOR:** Thompson Sampling + task extraction for bullet selection
- **GENERATOR:** LLM-based turn evaluation, quality-gated insight extraction, counter updates with similarity gating
- **CLUSTERER:** DBSCAN clustering + knowledge graph edges

### Unified Thompson Sampling (Dec 2025)
All bullets compete in a single pool with scoring: `similarity × thompson_sample × age_decay`

- Thompson Sampling's variance naturally gives new bullets chances to be tested
- Relevant new constraints can beat less-relevant proven bullets
- Constraint consolidation prevents fragmentation (similar constraints → increment evidence)

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Services | Python 3.11+, FastAPI, LangGraph |
| Event Bus | Apache Kafka (KRaft mode) |
| Cache | Redis 7 |
| Database | PostgreSQL 17 + pgvector 0.8 |
| LLM | Anthropic Claude Haiku 4.5 (claude-haiku-4-5-20251001) |
| Frontend | React 18, TypeScript, Vite |
| Infrastructure | Docker Compose |

---

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and data flows
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development guide
- **[CLAUDE.md](CLAUDE.md)** - Context for Claude Code sessions
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment
- **[VISION.md](VISION.md)** - Project goals and philosophy

**Detailed specs:** `docs/architecture/`
- `conversational-ai-spec.md` - Session orchestrator
- `reflector-system-spec.md` - Reflector implementation
- `curator-spec.md` - Learning algorithms
- `data-flow-spec.md` - Event schemas
- `design-decisions.md` - Architectural rationale

---

## Performance

- **Session latency:** P95 < 500ms (Redis read + LLM call)
- **Reflector processing:** < 2s per event
- **Redis cache:** 24-hour TTL on session bullets
- **Vector search:** < 100ms with pgvector indexes

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development workflow
- Code standards
- Testing requirements
- Git workflow
- Pull request process

---

## License

(To be determined)

---

## Status

**Development:** Active
**Production:** Not ready (requires service mesh, auth, monitoring)

**Important**: This setup is for **local development only**. For production deployment, see [DEPLOYMENT.md](DEPLOYMENT.md).

This system is functional for local development and testing.

---

## System Requirements

### Minimum Requirements
- **OS**: Linux, macOS, or Windows with WSL2
- **RAM**: 4GB free memory
- **Disk**: 10GB free space
- **CPU**: 2+ cores
- **Network**: Stable internet connection for LLM API calls

### Recommended Requirements
- **RAM**: 8GB free memory
- **Disk**: 20GB free space (allows for logs and data growth)
- **CPU**: 4+ cores
- **Network**: High-speed connection (Claude API calls can be data-intensive)

### Platform-Specific Notes
- **Windows**: Docker Desktop with WSL2 backend recommended
- **macOS**: Docker Desktop with sufficient memory allocation (8GB+)
- **Linux**: Native Docker installation preferred for best performance

---

**Questions?** See [ARCHITECTURE.md](ARCHITECTURE.md) or open an issue.
