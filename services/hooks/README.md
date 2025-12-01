# agentic-hooks-backend

High-performance backend service for agentic hook events. Receives events from the `agentic-hooks` client library and stores them in PostgreSQL or JSONL files.

## Features

- **High Throughput**: Handles 10k+ events/sec with batched inserts
- **Async PostgreSQL**: Uses asyncpg for non-blocking database access
- **Local Dev Fallback**: JSONL storage when PostgreSQL isn't available
- **Health Checks**: Kubernetes-ready health endpoints
- **Prometheus Metrics**: Expose metrics for observability

## Quick Start

### Local Development (JSONL)

```bash
# Install dependencies
uv sync

# Run with JSONL storage (no database needed)
uv run uvicorn hooks_backend.main:app --reload --port 8080

# Test it
curl -X POST http://localhost:8080/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "session_started", "session_id": "test-123"}'
```

### Production (PostgreSQL)

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/hooks"

# Run server
uv run uvicorn hooks_backend.main:app --host 0.0.0.0 --port 8080
```

## API Endpoints

### POST /events
Receive a single event.

```json
{
  "event_type": "session_started",
  "session_id": "session-123",
  "workflow_id": "workflow-456",
  "data": {"model": "claude-sonnet-4-5-20250929"}
}
```

### POST /events/batch
Receive multiple events in a batch.

```json
[
  {"event_type": "session_started", "session_id": "session-123"},
  {"event_type": "tool_execution_started", "session_id": "session-123"}
]
```

### GET /health
Health check endpoint.

### GET /metrics
Prometheus metrics endpoint.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | None | PostgreSQL connection string |
| `STORAGE_TYPE` | `auto` | Storage type: `postgres`, `jsonl`, or `auto` |
| `JSONL_PATH` | `.agentic/analytics/events.jsonl` | Path for JSONL storage |
| `LOG_LEVEL` | `INFO` | Logging level |

## Docker

```bash
# Build
docker build -t agentic-hooks-backend .

# Run
docker run -p 8080:8080 -e DATABASE_URL=... agentic-hooks-backend
```

## License

MIT
