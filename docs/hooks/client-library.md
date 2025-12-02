# Hook Client Library

The `agentic-hooks` client library provides a high-performance, async event emission system for agent observability. It supports batching, retry logic, and multiple backend adapters.

## Installation

```bash
# Core only (zero dependencies)
pip install agentic-hooks

# With HTTP backend support
pip install agentic-hooks[http]

# All features
pip install agentic-hooks[all]
```

## Quick Start

```python
from agentic_hooks import HookClient, HookEvent, EventType

# Simple usage with context manager
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id="session-123",
        data={"model": "claude-sonnet-4-5-20250929"},
    ))
```

## Configuration

### HookClient Options

```python
client = HookClient(
    # Backend configuration (choose one)
    backend_url="http://localhost:8080",  # HTTP backend
    backend=JSONLBackend(path="events.jsonl"),  # Custom backend

    # Batching configuration
    batch_size=50,  # Events per batch (default: 50)
    flush_interval_seconds=1.0,  # Max wait before flush (default: 1.0)

    # Retry configuration
    max_retry_attempts=3,  # Retries on failure (default: 3)
)
```

### HTTP Backend Options

```python
from agentic_hooks.backends import HTTPBackend

backend = HTTPBackend(
    base_url="http://localhost:8080",
    timeout=5.0,  # Request timeout (seconds)
    max_retries=3,  # Retry attempts
    retry_backoff_factor=0.5,  # Exponential backoff factor
    retry_max_delay=30.0,  # Max retry delay (seconds)
    retry_jitter=0.1,  # ±10% jitter on delays
    headers={"Authorization": "Bearer token"},  # Custom headers
)
```

## Event Types

```python
from agentic_hooks import EventType

# Session lifecycle
EventType.SESSION_STARTED
EventType.SESSION_COMPLETED

# Tool execution
EventType.TOOL_EXECUTION_STARTED
EventType.TOOL_EXECUTION_COMPLETED
EventType.TOOL_BLOCKED

# Agent requests
EventType.AGENT_REQUEST_STARTED
EventType.AGENT_REQUEST_COMPLETED

# User interaction
EventType.USER_PROMPT_SUBMITTED

# Hook decisions
EventType.HOOK_DECISION

# Custom events
EventType.CUSTOM
```

## Creating Events

```python
from agentic_hooks import HookEvent, EventType

# Minimal event
event = HookEvent(
    event_type=EventType.SESSION_STARTED,
    session_id="session-123",
)

# Full event with all fields
event = HookEvent(
    event_type=EventType.TOOL_EXECUTION_STARTED,
    session_id="session-123",
    workflow_id="workflow-456",
    phase_id="phase-1",
    milestone_id="milestone-1",
    data={
        "tool_name": "Write",
        "file_path": "app.py",
        "content_length": 1024,
    },
)

# Custom event type
event = HookEvent(
    event_type="my_custom_event",
    session_id="session-123",
    data={"custom_field": "value"},
)
```

## Usage Patterns

### Context Manager (Recommended)

```python
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(event1)
    await client.emit(event2)
    # Events are automatically flushed on exit
```

### Manual Lifecycle

```python
client = HookClient(backend_url="http://localhost:8080")
await client.start()

try:
    await client.emit(event)
finally:
    await client.close()  # Flushes remaining events
```

### Batch Emission

```python
events = [
    HookEvent(event_type=EventType.SESSION_STARTED, session_id=f"s-{i}")
    for i in range(100)
]

async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit_many(events)
```

### Force Flush

```python
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(important_event)
    await client.flush()  # Immediately send all buffered events
```

## Backends

### HTTP Backend (Production)

```python
from agentic_hooks import HookClient

client = HookClient(backend_url="http://hooks-service:8080")
```

### JSONL Backend (Development)

```python
from agentic_hooks import HookClient
from agentic_hooks.backends import JSONLBackend

backend = JSONLBackend(output_path=".agentic/analytics/events.jsonl")
client = HookClient(backend=backend)
```

### Null Backend (Testing)

```python
from agentic_hooks.backends import NullBackend

backend = NullBackend()
client = HookClient(backend=backend)

# After tests, inspect received events
print(backend.events_received)
```

## Error Handling

The client is fail-safe by default. Errors are logged but don't propagate to your application:

```python
# Events are not lost on transient failures
async with HookClient(backend_url="http://localhost:8080") as client:
    # If backend is down, events are retried with exponential backoff
    await client.emit(event)

    # After max_retry_attempts, events are silently dropped
    # (fail-safe: never block agent execution)
```

## Performance Tuning

### High Throughput

```python
client = HookClient(
    backend_url="http://localhost:8080",
    batch_size=100,  # Larger batches
    flush_interval_seconds=0.5,  # More frequent flushes
)
```

### Low Latency

```python
client = HookClient(
    backend_url="http://localhost:8080",
    batch_size=10,  # Smaller batches
    flush_interval_seconds=0.1,  # Very frequent flushes
)
```

### Memory Constrained

```python
client = HookClient(
    backend_url="http://localhost:8080",
    batch_size=25,  # Smaller buffer
)
```

## Metrics

Check pending events:

```python
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(event)
    print(f"Pending events: {client.pending_count}")
```

## Testing

Use `NullBackend` for unit tests:

```python
import pytest
from agentic_hooks import HookClient, HookEvent
from agentic_hooks.backends import NullBackend

@pytest.mark.asyncio
async def test_my_function():
    backend = NullBackend()
    async with HookClient(backend=backend) as client:
        # Your code that emits events
        await client.emit(HookEvent(
            event_type="test",
            session_id="test-session",
        ))

    # Assert events were emitted
    assert len(backend.events_received) == 1
    assert backend.events_received[0]["event_type"] == "test"
```
