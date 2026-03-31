# SESSION Service v3

Pure orchestration service for ALEC conversations. Reads bullets from Redis, calls Claude via gateway, emits events to Kafka.

## Architecture

**No LangGraph** - simple async orchestration replaces graph-based flow.

```
User Request
    ↓
POST /api/v1/chat/message
    ↓
1. emit bullets.requested → ADVISOR
    ↓
2. Poll Redis (1.5s timeout)
    ↓
3. Build prompt (system + windowed history + bullets + current)
    ↓
4. Call LLM via gateway
    ↓
5. emit llm.response.received → REFLECTOR
    ↓
Response
```

## Structure

```
core/session/
├── main.py                     # FastAPI entry point
├── service.py                  # Lifecycle management
├── metrics.py                  # Prometheus metrics
├── api/
│   ├── routes.py              # Chat endpoints
│   ├── library_routes.py      # Bullet management
│   ├── evaluation_routes.py   # Evaluation endpoints
│   ├── system_routes.py       # Admin endpoints
│   └── models.py              # Pydantic models
├── domain/
│   ├── conversation.py        # Orchestration logic
│   ├── bullet_formatter.py    # v3 format → prompt
│   └── llm_client.py          # Gateway client
├── infrastructure/
│   ├── bullet_cache.py        # Redis polling + fallback
│   ├── kafka_producer.py      # Event emission
│   └── session_store.py       # PostgreSQL CRUD
└── tests/
    ├── unit/                  # Unit tests (mocked deps)
    └── integration/           # DB integration tests
```

## Key Components

### ConversationOrchestrator
- Coordinates bullet retrieval, LLM calls, and events
- Message windowing: first turn + last 4 turns
- Bullet injection after first user message (prompt cache efficiency)

### BulletCache
- Polls Redis for `session:{id}:turn:{n}:bullets_ready`
- 1.5s timeout with in-memory fallback
- Tracks bullets shown per session

### Bullet Format (v3)
ADVISOR writes flat bullet list with polarity:
```json
{
  "bullets": [
    {"id": "...", "situation": "...", "assertion": "...", "polarity": "do|dont|know", "score": 0.85}
  ],
  "cluster_id": "..."
}
```

SESSION converts polarity → categories:
- `do` → Solutions (#S)
- `dont` → Constraints (#C)
- `know` → Reference (#R)

## API Endpoints

### Chat (`/api/v1/chat`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/message` | POST | Send message, get response |
| `/stream` | POST | SSE streaming response |
| `/sessions` | GET/POST | List/create sessions |
| `/sessions/{id}` | GET | Get session |
| `/sessions/{id}/complete` | POST | Complete session |
| `/sessions/{id}/history` | GET | Get history |
| `/sessions/{id}/bullets` | GET | Get bullets used |

### Library (`/api/v1/library`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | List bullets |
| `/{id}` | GET/PATCH | Get/update bullet |
| `/{id}` | DELETE | Archive bullet |

### Evaluation (`/api/v1/evaluation`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/experiments` | GET/POST | List/create experiments |
| `/experiments/{id}` | GET/DELETE | Get/delete experiment |
| `/experiments/{id}/start` | POST | Start experiment |
| `/experiments/{id}/stop` | POST | Stop experiment |
| `/experiments/{id}/results` | GET | Get results |
| `/epochs` | GET | Compare experiments |

### System (`/api/v1/system`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/reset` | POST | Reset all data |
| `/reset/counters` | POST | Reset bullet counters |
| `/reset/sessions` | POST | Clear sessions |
| `/learning-stats` | GET | Dashboard data |
| `/intelligence` | GET | Analysis report |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | PostgreSQL URL |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL |
| `LLM_GATEWAY_URL` | `http://llm-gateway:8011` | Gateway URL |
| `LLM_TIMEOUT` | `120` | LLM timeout seconds |
| `METRICS_PORT` | `9090` | Prometheus port |

## Running

### Development
```bash
docker-compose up -d session
```

### Testing
```bash
# Unit tests
pytest core/session/tests/unit/ -v

# Integration tests (requires PostgreSQL)
pytest core/session/tests/integration/ -v -m db_integration
```

## Observability

### Structured Logging
All components use structlog:
```python
self.logger.info("turn_completed", session_id=session_id, duration_ms=123)
```

### Prometheus Metrics
- `session_requests_total` - Request counts by endpoint/status
- `session_request_duration_seconds` - Request latency
- `session_turns_total` - Turn counts by status
- `session_turn_duration_seconds` - Turn latency
- `session_bullets_used_total` - Bullets injected
- `session_llm_calls_total` - LLM call counts

### Health Check
`GET /health` returns dependency status:
```json
{
  "status": "healthy",
  "postgres": "ok",
  "redis": "ok",
  "kafka": "ok"
}
```

## Event Flow

### Produced Events
| Topic | Event Type | Trigger |
|-------|------------|---------|
| `session.created` | Session creation | New session |
| `bullets.requested` | Each turn | Before LLM call |
| `llm.response.received` | Each turn | After LLM call |
| `session.ended` | Session complete | Complete endpoint |

### Consumed Events
None - SESSION is a producer only.
