# agentic-hooks

High-performance async hook client for agent swarms. Supports batched event emission with zero runtime dependencies for the core client.

## Features

- **Zero runtime dependencies** - Core client works with Python stdlib only
- **Async batching** - Events are buffered and sent in batches for efficiency
- **Pluggable backends** - JSONL (local dev), HTTP (production)
- **Fail-safe** - Never blocks agent execution on logging failures
- **Context manager support** - Easy resource cleanup

## Installation

```bash
# Core only (zero deps)
pip install agentic-hooks

# With HTTP backend support
pip install agentic-hooks[http]
```

## Quick Start

```python
from agentic_hooks import HookClient, HookEvent, EventType

# Simple usage with context manager
async with HookClient(backend_url="http://localhost:8080") as client:
    await client.emit(HookEvent(
        event_type=EventType.TOOL_EXECUTION_STARTED,
        session_id="session-123",
        data={"tool_name": "Write", "file_path": "app.py"}
    ))

# Local development with JSONL backend
from agentic_hooks.backends import JSONLBackend

backend = JSONLBackend(output_path=".agentic/analytics/events.jsonl")
async with HookClient(backend=backend) as client:
    await client.emit(HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id="session-123",
    ))
```

## Event Types

- `SESSION_STARTED` - Agent session begins
- `SESSION_COMPLETED` - Agent session ends
- `TOOL_EXECUTION_STARTED` - Tool execution begins
- `TOOL_EXECUTION_COMPLETED` - Tool execution ends
- `TOOL_BLOCKED` - Tool blocked by security hook
- `AGENT_REQUEST_STARTED` - Agent request begins
- `AGENT_REQUEST_COMPLETED` - Agent request ends
- `USER_PROMPT_SUBMITTED` - User prompt received
- `HOOK_DECISION` - Hook decision made
- `CUSTOM` - Custom event type

## Configuration

```python
client = HookClient(
    backend_url="http://localhost:8080",  # HTTP backend URL
    batch_size=50,                        # Events per batch
    flush_interval_seconds=1.0,           # Max wait before flush
    max_retry_attempts=3,                 # Retries on failure
)
```

## License

MIT
