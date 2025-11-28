# Observability Dashboard Backend

FastAPI backend for the Agent Observability Dashboard.

## Setup

```bash
uv sync
uv run python main.py
```

## API

- `GET /health` - Health check
- `GET /events` - List events
- `GET /sessions` - List sessions
- `GET /sessions/{id}` - Session detail
- `GET /metrics` - Aggregated metrics
- `POST /import` - Trigger event import

