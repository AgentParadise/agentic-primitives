# Agentic Analytics

Canonical event schemas and emission utilities for AI agent observability.

## Overview

This package provides:
- **Canonical Event Schemas**: `SessionStarted`, `TokensUsed`, `ToolCalled`, `SessionEnded`
- **Event Emitter**: Unified interface for writing events to JSONL files
- **Hook Decision Logging**: For safety/observability hooks
- **Validation Utilities**: For analyzing event streams

## Installation

```bash
# With uv (recommended)
uv add agentic-analytics

# With pip
pip install agentic-analytics
```

## Quick Start - Session Metrics

```python
from agentic_analytics import EventEmitter, SessionContext

# Create emitter (uses default file backend)
emitter = EventEmitter()

# Use context manager for automatic session start/end
with emitter.session(
    model="claude-sonnet-4-5-20250929",
    provider="anthropic",
    model_display_name="Claude Sonnet",
) as session:
    # Record token usage
    session.tokens_used(
        input_tokens=100,
        output_tokens=50,
        duration_ms=500,
    )
    
    # Record tool calls
    session.tool_called(
        tool_name="Write",
        tool_input={"file_path": "app.py"},
        duration_ms=10,
    )

# Events are automatically written to .agentic/analytics/events.jsonl
```

## Quick Start - Hook Decisions

```python
from agentic_analytics import AnalyticsClient, HookDecision

# Create client (uses default file backend)
analytics = AnalyticsClient()

# Log a hook decision
analytics.log(HookDecision(
    hook_id="bash-validator",
    event_type="PreToolUse",
    decision="block",
    session_id="sess-abc123",
    tool_name="Bash",
    reason="Dangerous command detected",
    metadata={"command": "rm -rf /"},
))
```

## Canonical Event Schemas

### SessionStarted

Emitted when an agent session begins.

```python
from agentic_analytics import SessionStarted

event = SessionStarted(
    session_id="sess-123",
    model="claude-sonnet-4-5-20250929",
    provider="anthropic",
    model_display_name="Claude Sonnet",  # Optional
    pricing={                             # Optional
        "input_per_1m_tokens": 3.0,
        "output_per_1m_tokens": 15.0,
    },
    milestone_id="M1",                    # Optional
    workflow_id="wf-456",                 # Optional
)
```

### TokensUsed

Emitted when tokens are consumed in an interaction.

```python
from agentic_analytics import TokensUsed

event = TokensUsed(
    session_id="sess-123",
    input_tokens=100,
    output_tokens=50,
    duration_ms=500,
    prompt_preview="Write a hello world...",
    response_preview="Here's the code...",
)
```

### ToolCalled

Emitted when a tool is invoked.

```python
from agentic_analytics import ToolCalled

event = ToolCalled(
    session_id="sess-123",
    tool_name="Write",
    tool_input={"file_path": "app.py", "content": "..."},
    tool_use_id="toolu_01ABC123",  # Correlation key
    duration_ms=10,
    blocked=False,
)
```

### SessionEnded

Emitted when a session completes.

```python
from agentic_analytics import SessionEnded

event = SessionEnded(
    session_id="sess-123",
    start_time=datetime(2025, 11, 28, 12, 0),
    total_input_tokens=1000,
    total_output_tokens=500,
    total_cost_usd=0.0525,
    interaction_count=5,
    tool_call_count=10,
    tool_calls_blocked=1,
    total_duration_ms=30000,
    model="claude-sonnet-4-5-20250929",
    exit_reason="completed",  # or "interrupted", "error"
)
```

## Configuration

### File Backend (Default)

```python
from pathlib import Path
from agentic_analytics import EventEmitter

# Default path: .agentic/analytics/events.jsonl
emitter = EventEmitter()

# Custom path
emitter = EventEmitter(output_path=Path("./logs/events.jsonl"))
```

### API Backend (Production)

```python
from agentic_analytics import EventEmitter

emitter = EventEmitter(
    api_endpoint="https://analytics.company.com/events",
    api_key="your-api-key",
)
```

### Environment Variables

```bash
export AGENTIC_EVENTS_PATH="./logs/events.jsonl"
export ANALYTICS_API_ENDPOINT="https://analytics.company.com/events"
export ANALYTICS_API_KEY="your-api-key"
```

## Output Format

Events are written as JSON Lines (one JSON object per line):

```json
{"timestamp": "2025-11-28T12:00:00+00:00", "event_type": "session.started", "session_id": "sess-123", "model": "claude-sonnet-4-5-20250929", "provider": "anthropic"}
{"timestamp": "2025-11-28T12:00:01+00:00", "event_type": "tokens.used", "session_id": "sess-123", "input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
{"timestamp": "2025-11-28T12:00:02+00:00", "event_type": "tool.called", "session_id": "sess-123", "tool_name": "Write", "tool_input": {"file_path": "app.py"}}
{"timestamp": "2025-11-28T12:00:03+00:00", "event_type": "session.ended", "session_id": "sess-123", "total_cost_usd": 0.0525}
```

## Design Principles

1. **Canonical**: Single source of truth for event schemas
2. **Simple**: Dataclasses for events, context manager for sessions
3. **Fast**: Synchronous file writes are <1ms
4. **Fail-safe**: Never blocks agent execution on errors
5. **Provider-agnostic**: Works with any AI agent provider

## Multi-Provider Support

```python
# Anthropic Claude
emitter.emit(SessionStarted(provider="anthropic", model="claude-sonnet-4-5-20250929", ...))

# OpenAI GPT
emitter.emit(SessionStarted(provider="openai", model="gpt-4o", ...))

# Google Gemini
emitter.emit(SessionStarted(provider="google", model="gemini-2.0-flash", ...))
```

## Development

```bash
cd lib/python/agentic_analytics

# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Type check
uv run mypy agentic_analytics/

# Lint
uv run ruff check agentic_analytics/
```

## License

MIT
