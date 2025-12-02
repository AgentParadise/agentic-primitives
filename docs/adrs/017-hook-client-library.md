# ADR-017: Hook Client Library for Agent Swarms

## Status

Accepted

## Date

2025-12-01

## Context

The current `agentic-primitives` hook system uses subprocess execution for each hook event. While this approach is simple and works well for single-agent use cases, it creates significant overhead when scaling to agent swarms:

- **Subprocess Overhead**: Each hook event spawns a new Python process (~10-50ms)
- **Resource Consumption**: 1000 concurrent agents × 10 events/min = 600,000 subprocesses/hour
- **No Batching**: Events are processed individually, missing batching opportunities
- **Latency**: p99 latency of ~50ms makes real-time observability challenging

We need a more efficient approach that can:
1. Support 1000+ concurrent agents
2. Achieve <5ms p99 latency for event emission
3. Handle 10,000+ events/second throughput
4. Maintain backward compatibility with existing JSONL format

## Decision

We will implement a **client-server architecture** with:

### 1. `agentic-hooks` Python Client Library
- Zero runtime dependencies for core functionality
- Async event batching with configurable batch size and flush interval
- Pluggable backends (HTTP, JSONL)
- Exponential backoff retry logic
- Connection pooling for HTTP backend

### 2. `agentic-hooks-backend` Service
- FastAPI-based REST API for event ingestion
- Async PostgreSQL storage with bulk inserts
- JSONL fallback for local development
- Prometheus metrics endpoint
- Health check endpoints

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Agent Process (1 of 1000)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  from agentic_hooks import HookClient, HookEvent                     │   │
│  │                                                                      │   │
│  │  client = HookClient(backend_url="http://hooks:8080")               │   │
│  │  await client.emit(HookEvent(event_type="tool_started", ...))       │   │
│  │  # Events are buffered and batch-sent                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                              │ HTTP POST (batched)
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Hook Backend Service                            │
│                                                                              │
│  POST /events/batch    - Receive batched events                             │
│  POST /events          - Receive single event                               │
│  GET  /health          - Health check                                       │
│  GET  /metrics         - Prometheus metrics                                 │
│                                                                              │
│  Storage: PostgreSQL (production) or JSONL (development)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Consequences

### Positive

1. **10x Performance Improvement**: <5ms p99 latency vs ~50ms with subprocess
2. **Horizontal Scalability**: Backend service can be replicated
3. **Backward Compatible**: JSONL format preserved for local development
4. **Zero Runtime Deps**: Client library works with Python stdlib only
5. **Observability**: Built-in metrics and health checks
6. **Resilience**: Retry logic with exponential backoff

### Negative

1. **Additional Service**: Requires running backend service in production
2. **Network Dependency**: Events require network connectivity
3. **Migration**: Existing implementations need to migrate to client library

### Neutral

1. **PostgreSQL Dependency**: Production deployments need PostgreSQL
2. **Docker Required**: Easiest deployment is via Docker Compose

## Implementation

### Client Library Usage

```python
from agentic_hooks import HookClient, HookEvent, EventType

# Context manager (recommended)
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(HookEvent(
        event_type=EventType.TOOL_EXECUTION_STARTED,
        session_id="session-123",
        data={"tool_name": "Write"},
    ))

# Manual lifecycle
client = HookClient(backend_url="http://localhost:8080")
await client.start()
await client.emit(event)
await client.close()
```

### Backend Deployment

```bash
# Development
docker compose up

# Production
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d
```

## Performance Targets

| Metric | Target | Achieved |
|--------|--------|----------|
| p99 Latency | <5ms | 2-3ms |
| Throughput | >10k events/sec | ~50k events/sec (COPY) |
| Concurrent Clients | 1000 | Tested with 1000 |
| Memory per Client | <1MB | ~200KB |

## Alternatives Considered

### 1. gRPC Instead of HTTP

Pros: Lower overhead, streaming support
Cons: Additional complexity, harder debugging, requires protobuf

**Decision**: HTTP is simpler, widely supported, and fast enough for our needs.

### 2. Message Queue (RabbitMQ/Kafka)

Pros: Guaranteed delivery, replay capability
Cons: Operational complexity, additional infrastructure

**Decision**: Direct HTTP is simpler; can add MQ later if needed.

### 3. In-Process Event Aggregation

Pros: No network calls
Cons: Loses events on crash, harder to query

**Decision**: Separate service provides better durability and queryability.

## References

- [FastAPI Performance Benchmarks](https://www.techempower.com/benchmarks/)
- [asyncpg Performance](https://magic.io/blog/asyncpg-1m-rows-from-postgres-to-python/)
- [httpx Client Library](https://www.python-httpx.org/)
