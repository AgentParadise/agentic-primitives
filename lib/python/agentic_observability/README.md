# agentic-observability

Observability protocol for AI agent operations. Part of the [agentic-primitives](https://github.com/AgentParadise/agentic-primitives) collection.

## Overview

This library provides the core `ObservabilityPort` protocol that all agent executors MUST depend on, ensuring consistent observability across the system. This is a Poka-Yoke pattern that makes it **impossible** to run agents without observability configured.

## Quick Start

```python
from agentic_observability import (
    ObservabilityPort,
    ObservationType,
    ObservationContext,
    NullObservability,
)

# In production: use TimescaleObservability (from aef-adapters)
# In tests: use NullObservability

class WorkflowExecutor:
    """Example executor that REQUIRES observability."""

    def __init__(self, observability: ObservabilityPort) -> None:
        # Observability is REQUIRED - no default None!
        self._observability = observability

    async def execute(self, workflow_id: str) -> None:
        context = ObservationContext(
            session_id="session-123",
            workflow_id=workflow_id,
        )

        # Record tool usage
        op_id = await self._observability.record_tool_started(
            context,
            tool_name="Bash",
            tool_input={"command": "echo 'hello'"},
        )

        # ... execute tool ...

        await self._observability.record_tool_completed(
            context,
            operation_id=op_id,
            tool_name="Bash",
            success=True,
            duration_ms=150,
        )

        # Record token usage
        await self._observability.record_token_usage(
            context,
            input_tokens=1000,
            output_tokens=500,
            model="claude-sonnet-4-20250514",
        )
```

## Testing

For tests, use `NullObservability`:

```python
import os
import pytest
from agentic_observability import NullObservability, ObservationType

@pytest.fixture
def observability():
    # Required: must be in test environment
    os.environ["AEF_ENVIRONMENT"] = "test"
    return NullObservability()

async def test_executor(observability):
    executor = WorkflowExecutor(observability=observability)
    await executor.execute("workflow-123")

    # Assert observations were recorded
    assert observability.count > 0
    assert observability.has_observation(ObservationType.TOOL_COMPLETED)

    # Get specific observations
    token_obs = observability.get_observations(ObservationType.TOKEN_USAGE)
    assert len(token_obs) == 1
    assert token_obs[0].data["input_tokens"] == 1000
```

## Safety Guard

`NullObservability` throws `TestOnlyAdapterError` if used outside test environment:

```python
# Without AEF_ENVIRONMENT='test':
from agentic_observability import NullObservability

# Raises TestOnlyAdapterError!
observability = NullObservability()
```

This prevents:
- False positives (thinking observability works when it doesn't)
- Data loss (in-memory implementations lose data)
- Silent failures (forgetting to configure real observability)

## Protocol

The `ObservabilityPort` protocol defines these methods:

| Method | Description |
|--------|-------------|
| `record(type, context, data)` | Generic observation recording |
| `record_tool_started(...)` | Convenience for tool start events |
| `record_tool_completed(...)` | Convenience for tool completion events |
| `record_token_usage(...)` | Convenience for token usage events |
| `flush()` | Flush buffered observations |
| `close()` | Release resources |

## Observation Types

```python
class ObservationType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    SESSION_ERROR = "session_error"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOKEN_USAGE = "token_usage"
    # ... and more
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    agentic-primitives                        │
├─────────────────────────────────────────────────────────────┤
│ agentic_observability                                        │
│  ├── ObservabilityPort (Protocol)   ◄── Required interface  │
│  ├── ObservationType (Enum)         ◄── Standard types      │
│  ├── ObservationContext (Dataclass) ◄── Context carrier     │
│  ├── NullObservability              ◄── Tests only!         │
│  └── TestOnlyAdapterError           ◄── Safety guard        │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ implements
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       aef-adapters                           │
├─────────────────────────────────────────────────────────────┤
│ TimescaleObservability                                       │
│  └── Writes to TimescaleDB for production                   │
└─────────────────────────────────────────────────────────────┘
```

## License

MIT
