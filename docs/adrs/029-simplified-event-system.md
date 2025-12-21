# ADR-029: Simplified Event System

## Status

Accepted

## Context

The previous OTel-first observability approach (ADR-026) introduced significant complexity:

1. **OTel SDK dependency** - `agentic_otel` required `opentelemetry-sdk` and related packages
2. **Collector infrastructure** - Required running an OTel Collector for aggregation
3. **Protocol complexity** - gRPC/HTTP protocols, span hierarchies, semantic conventions
4. **Visualization stack** - Jaeger, Grafana for viewing telemetry

For our use case (building custom React dashboards for agent observability), this was overengineered:

- Claude CLI emits metrics and logs natively via OTel (not traces)
- Custom hooks need to emit structured events, not OTel spans
- AEF needs to store events in TimescaleDB for querying, not Jaeger
- We want zero-dependency hooks that work in any environment

## Decision

Replace the OTel-based observability with a simplified JSONL event system:

### 1. New `agentic_events` Package (replaces `agentic_otel`)

```python
from agentic_events import EventEmitter, EventType

emitter = EventEmitter(session_id="session-123", provider="claude")
emitter.tool_started("Bash", "toolu_abc", "git status")
emitter.tool_completed("Bash", "toolu_abc", success=True, duration_ms=150)
```

**Zero external dependencies** - uses only Python stdlib.

### 2. JSONL Output to stdout

Events are emitted as JSON lines to stdout:

```json
{"event_type": "tool_execution_started", "timestamp": "2025-12-17T10:00:00Z", "session_id": "session-123", "provider": "claude", "context": {"tool_name": "Bash", "tool_use_id": "toolu_abc"}}
```

### 3. AEF Captures and Stores

The agent runner captures stdout, parses JSONL events, and stores them in TimescaleDB:

```sql
CREATE TABLE agent_events (
    time TIMESTAMPTZ NOT NULL,
    session_id TEXT NOT NULL,
    execution_id TEXT,
    event_type TEXT NOT NULL,
    data JSONB NOT NULL
);
```

### 4. Batch Inserts for Scale

Events are buffered and inserted in batches using PostgreSQL's COPY command for high throughput (target: 10K concurrent agents).

## Consequences

### Positive

1. **Zero dependencies** - Hooks work anywhere Python runs
2. **Simpler architecture** - No OTel Collector, Jaeger, Grafana
3. **Native TimescaleDB** - Events stored directly for SQL queries
4. **Better for custom dashboards** - Query raw events via API
5. **Scalable** - Batch inserts handle high event volumes

### Negative

1. **No distributed tracing** - Can't trace across services (but we don't need this)
2. **No automatic span hierarchy** - Must correlate events manually
3. **Custom query layer** - Must build our own event API (which we wanted anyway)

## Removed Components

- `agentic_otel` package (deleted)
- `agentic_hooks` package (deleted)
- OTel Collector configuration
- Jaeger integration
- Grafana dashboards

## Migration

1. Replace `agentic_otel` imports with `agentic_events`
2. Replace `HookOTelEmitter` with `EventEmitter`
3. Remove OTel environment variables
4. Update Dockerfile to include `agentic_events` wheel
