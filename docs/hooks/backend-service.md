# Hook Backend Service

The `agentic-hooks-backend` service receives events from the `agentic-hooks` client library and stores them for observability and analytics.

## Features

- **High Throughput**: 50,000+ events/second with bulk inserts
- **Async PostgreSQL**: Non-blocking database operations with asyncpg
- **Local Dev Fallback**: JSONL storage when PostgreSQL isn't available
- **Health Checks**: Kubernetes-ready health endpoints
- **Prometheus Metrics**: Built-in observability

## Quick Start

### Local Development (JSONL)

```bash
cd lib/agentic-primitives/services/hooks

# Install dependencies
uv sync

# Run with JSONL storage
uv run uvicorn hooks_backend.main:app --reload --port 8080

# Test it
curl -X POST http://localhost:8080/events \
  -H "Content-Type: application/json" \
  -d '{"event_type": "session_started", "session_id": "test-123"}'
```

### Docker Compose (PostgreSQL)

```bash
cd lib/agentic-primitives/services/hooks

# Start services
docker compose up -d

# Check health
curl http://localhost:8080/health

# View logs
docker compose logs -f hooks-backend
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | None | PostgreSQL connection string |
| `STORAGE_TYPE` | `auto` | Storage type: `postgres`, `jsonl`, or `auto` |
| `JSONL_PATH` | `.agentic/analytics/events.jsonl` | Path for JSONL storage |
| `LOG_LEVEL` | `INFO` | Logging level |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8080` | Server port |

### Storage Type Selection

- `auto`: Uses PostgreSQL if `DATABASE_URL` is set, otherwise JSONL
- `postgres`: Forces PostgreSQL (requires `DATABASE_URL`)
- `jsonl`: Forces JSONL file storage

## API Reference

### POST /events

Receive a single event.

**Request:**
```json
{
  "event_type": "session_started",
  "session_id": "session-123",
  "workflow_id": "workflow-456",
  "data": {
    "model": "claude-sonnet-4-5-20250929"
  }
}
```

**Response (202 Accepted):**
```json
{
  "accepted": 1,
  "message": "Events accepted"
}
```

### POST /events/batch

Receive multiple events.

**Request:**
```json
[
  {"event_type": "session_started", "session_id": "s1"},
  {"event_type": "tool_execution_started", "session_id": "s1"},
  {"event_type": "tool_execution_completed", "session_id": "s1"}
]
```

**Response (202 Accepted):**
```json
{
  "accepted": 3,
  "message": "Events accepted"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "storage": "postgres",
  "version": "0.1.0"
}
```

### GET /metrics

JSON metrics.

**Response:**
```json
{
  "events_received_total": 15000,
  "events_stored_total": 14998,
  "storage_errors_total": 2,
  "uptime_seconds": 3600.5
}
```

### GET /metrics/prometheus

Prometheus-format metrics.

**Response:**
```
# HELP hooks_events_received_total Total number of events received
# TYPE hooks_events_received_total counter
hooks_events_received_total 15000

# HELP hooks_events_stored_total Total number of events stored
# TYPE hooks_events_stored_total counter
hooks_events_stored_total 14998
...
```

## Deployment

### Docker Compose (Development)

```bash
docker compose up -d
```

### Docker Compose (Production)

```bash
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hooks-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hooks-backend
  template:
    metadata:
      labels:
        app: hooks-backend
    spec:
      containers:
      - name: hooks-backend
        image: agentic-hooks-backend:latest
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: url
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          limits:
            cpu: "1"
            memory: 512Mi
          requests:
            cpu: "0.25"
            memory: 128Mi
---
apiVersion: v1
kind: Service
metadata:
  name: hooks-backend
spec:
  selector:
    app: hooks-backend
  ports:
  - port: 8080
    targetPort: 8080
```

## Database Setup

### PostgreSQL Schema

The schema is automatically applied when using Docker Compose. For manual setup:

```bash
psql -U hooks -d hooks -f migrations/001_initial_schema.sql
```

### Time-Based Partitioning

The schema uses monthly partitions for efficient data management:

```sql
-- Create partition for a specific month
SELECT create_monthly_partition(2025, 12);

-- View partition statistics
SELECT * FROM get_partition_stats();

-- Archive old partitions
SELECT archive_old_partitions(3);  -- Keep last 3 months
```

## Performance

### Throughput

| Mode | Events/Second |
|------|---------------|
| JSONL | ~5,000 |
| PostgreSQL (executemany) | ~10,000 |
| PostgreSQL (COPY) | ~50,000 |

### Latency (p99)

| Mode | Latency |
|------|---------|
| Single event | ~2ms |
| Batch (50 events) | ~5ms |
| Batch (100 events) | ~8ms |

### Connection Pool

Default pool settings:
- Min connections: 5
- Max connections: 20

For high throughput, increase in production:
```python
PostgresStorage(
    database_url="...",
    pool_min_size=10,
    pool_max_size=50,
)
```

## Monitoring

### Prometheus Integration

Add to your Prometheus config:

```yaml
scrape_configs:
  - job_name: 'hooks-backend'
    static_configs:
      - targets: ['hooks-backend:8080']
    metrics_path: /metrics/prometheus
```

### Grafana Dashboard

Key metrics to monitor:
- `hooks_events_received_total` - Event ingestion rate
- `hooks_events_stored_total` - Successful storage rate
- `hooks_storage_errors_total` - Storage failures
- `hooks_uptime_seconds` - Service uptime

### Alerts

```yaml
groups:
- name: hooks-backend
  rules:
  - alert: HooksBackendDown
    expr: up{job="hooks-backend"} == 0
    for: 5m

  - alert: HooksStorageErrors
    expr: rate(hooks_storage_errors_total[5m]) > 0.1
    for: 5m
```

## Troubleshooting

### Connection Refused

```
Connection refused: http://localhost:8080
```

Ensure the service is running:
```bash
docker compose ps
docker compose logs hooks-backend
```

### Database Connection Failed

```
asyncpg.exceptions.ConnectionRefusedError
```

Check PostgreSQL is healthy:
```bash
docker compose exec postgres pg_isready -U hooks
```

### Out of Memory

Reduce batch sizes or increase container memory:
```yaml
services:
  hooks-backend:
    deploy:
      resources:
        limits:
          memory: 1G
```

### Slow Performance

1. Check PostgreSQL indexes exist
2. Verify connection pool isn't exhausted
3. Review partition strategy
4. Consider horizontal scaling
