# Example 002: Agent Observability Dashboard

Real-time observability dashboard for Claude Agent SDK applications, demonstrating how to consume and visualize hook events.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Claude Agent SDK Application                              │
│  (uses hooks from primitives/v1/hooks/)                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          │ Writes to
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  .agentic/analytics/events.jsonl                                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          │ Watched by
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                              │
│  • Imports events from JSONL → SQLite                          │
│  • REST API for sessions, events, metrics                      │
│  • Token/cost calculation                                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          │ API calls
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite)                                        │
│  • Real-time event feed                                        │
│  • Token/cost charts                                           │
│  • Session explorer                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Backend

```bash
cd backend

# Install dependencies
uv sync

# Run server (starts on http://localhost:8000)
uv run python main.py
```

### Frontend

```bash
cd frontend

# Install dependencies
bun install

# Run dev server (starts on http://localhost:5173)
bun run dev
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/events` | List events (with filters) |
| GET | `/sessions` | List session summaries |
| GET | `/sessions/{id}` | Session detail with events |
| GET | `/metrics` | Aggregated metrics |
| POST | `/import` | Manually trigger event import |

## Configuration

Environment variables (or `.env` file in backend/):

```env
OBSERVABILITY_DATABASE_URL=sqlite+aiosqlite:///./data/events.db
OBSERVABILITY_EVENTS_JSONL_PATH=.agentic/analytics/events.jsonl
OBSERVABILITY_API_PORT=8000
OBSERVABILITY_POLL_INTERVAL=1.0
```

## Tech Stack

**Backend:**
- Python 3.11+
- FastAPI
- SQLAlchemy (async)
- SQLite (aiosqlite)
- Pydantic

**Frontend:**
- Bun
- Vite
- React + TypeScript
- Tailwind CSS
- Recharts

## Integration with Agentic Primitives

This example demonstrates:

1. **Hook Integration**: The hooks in `primitives/v1/hooks/handlers/` write events to `.agentic/analytics/events.jsonl`

2. **Event Schema**: Events match the format from hook handlers (see `src/models/events.py`)

3. **Model Pricing**: Can load pricing from `providers/models/anthropic/` for cost calculation

4. **Repository Pattern**: Database layer abstracted for future Postgres/Supabase support

