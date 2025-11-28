# Agentic Analytics

Simple, DI-friendly analytics client for agentic hooks.

## Overview

This package provides a lightweight client that hooks use to log their decisions to a central audit trail. Every hook logs its own decision, creating a complete audit log of all hook activity.

## Installation

```bash
# With uv (recommended)
uv add agentic-analytics

# With pip
pip install agentic-analytics
```

## Quick Start

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

## Configuration

### File Backend (Default)

```python
from pathlib import Path
from agentic_analytics import AnalyticsClient

# Default path: .agentic/analytics/events.jsonl
analytics = AnalyticsClient()

# Custom path
analytics = AnalyticsClient(output_path=Path("./logs/events.jsonl"))
```

### API Backend (Production)

```python
from agentic_analytics import AnalyticsClient

analytics = AnalyticsClient(
    api_endpoint="https://analytics.company.com/events",
    api_key="your-api-key",
)
```

### Environment Variables

```bash
export ANALYTICS_OUTPUT_PATH="./logs/events.jsonl"
export ANALYTICS_API_ENDPOINT="https://analytics.company.com/events"
export ANALYTICS_API_KEY="your-api-key"
```

```python
from agentic_analytics import AnalyticsClient

# Load from environment
analytics = AnalyticsClient.from_env()
```

## HookDecision Model

```python
from agentic_analytics import HookDecision

decision = HookDecision(
    # Required
    hook_id="bash-validator",       # Unique hook identifier
    event_type="PreToolUse",        # Hook event type
    decision="block",               # "allow", "block", or "warn"
    session_id="sess-123",          # Session ID from agent
    
    # Optional
    provider="claude",              # Agent provider (default: "claude")
    tool_name="Bash",               # Tool being used
    reason="Dangerous command",     # Reason for decision
    metadata={"key": "value"},      # Additional context
)
```

## Output Format

Events are written as JSON Lines (one JSON object per line):

```json
{"timestamp": "2025-11-26T10:30:00.000000+00:00", "hook_id": "bash-validator", "event_type": "PreToolUse", "decision": "block", "session_id": "sess-123", "provider": "claude", "tool_name": "Bash", "reason": "Dangerous command", "metadata": {"command": "rm -rf /"}}
```

## Design Principles

1. **Simple**: One class, one model, zero config needed
2. **Fast**: Synchronous file writes are <1ms
3. **Fail-safe**: Never blocks hook execution on errors
4. **DI-friendly**: Easy to inject different backends for testing

## Multi-Provider Support

The client is provider-agnostic. Use with any agent:

```python
# Claude Code
analytics.log(HookDecision(provider="claude", ...))

# OpenAI (future)
analytics.log(HookDecision(provider="openai", ...))

# Cursor (future)
analytics.log(HookDecision(provider="cursor", ...))
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

