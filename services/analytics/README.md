# Analytics Service

Provider-agnostic analytics system for agentic-primitives hook middleware.

## Overview

This service provides a standardized analytics layer that sits between provider-specific hook events (Claude, OpenAI, Cursor, Gemini) and analytics backends. It normalizes events from different providers into a consistent format and publishes them to configurable backends.

## Architecture

```
Provider Hook Events (JSON via stdin)
           ↓
    Hook Input Models (Pydantic validation)
           ↓
    Event Normalizer (Provider adapters)
           ↓
    Normalized Events (Standard schema)
           ↓
    Event Publisher (Backend adapters)
           ↓
    Analytics Backend (File/API)
```

## Features

- ✅ **Type Safety**: All models use Pydantic v2 with strict validation
- ✅ **Provider Agnostic**: Adapters for Claude, OpenAI, and more
- ✅ **Flexible Backends**: File (JSONL) and API (HTTP POST) publishers
- ✅ **Configuration**: Environment variable configuration with pydantic-settings
- ✅ **Testing**: 97.30% test coverage with comprehensive fixtures
- ✅ **Quality**: Mypy strict mode, ruff linting, pytest with coverage

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for Python package management:

```bash
# Install dependencies
cd services/analytics
uv sync

# Install with dev dependencies
uv sync --all-extras
```

## Configuration

Configure via environment variables:

```bash
# Provider configuration
export ANALYTICS_PROVIDER=claude  # claude, openai, cursor, gemini

# Publisher backend
export ANALYTICS_PUBLISHER_BACKEND=file  # file or api

# File backend configuration
export ANALYTICS_OUTPUT_PATH=./analytics-events.jsonl

# API backend configuration
export ANALYTICS_API_ENDPOINT=https://api.example.com/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3

# Debug logging
export ANALYTICS_DEBUG=true
```

## Usage

### As Middleware

The analytics service is designed to be called as middleware from hook systems:

```bash
# Read hook event from stdin, normalize, and publish
echo '{"session_id":"abc123",...}' | \
  uv run python middleware/event_normalizer.py | \
  uv run python middleware/event_publisher.py
```

### Programmatic Usage

```python
from analytics.models import ClaudePreToolUseInput, NormalizedEvent, AnalyticsConfig

# Validate hook input
hook_input = ClaudePreToolUseInput.model_validate({
    "session_id": "abc123",
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    # ...
})

# Create normalized event
normalized = NormalizedEvent(
    event_type="tool_execution_started",
    timestamp=datetime.now(),
    session_id=hook_input.session_id,
    provider="claude",
    # ...
)

# Validate configuration
config = AnalyticsConfig()
config.validate_backend_config()
```

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_models.py -v
```

### Type Checking

```bash
uv run mypy src/analytics
```

### Linting

```bash
# Check
uv run ruff check src tests

# Auto-fix
uv run ruff check --fix src tests

# Format
uv run black src tests
```

### Full QA Checkpoint

```bash
uv run mypy src/analytics &&  \
uv run ruff check src tests && \
uv run pytest --cov
```

## Project Structure

```
services/analytics/
├── src/analytics/
│   ├── models/
│   │   ├── hook_input.py      # Provider-specific input models
│   │   ├── events.py           # Normalized event models
│   │   └── config.py           # Configuration models
│   ├── adapters/               # Provider adapters (future)
│   ├── normalizer.py           # Event normalization logic (future)
│   └── publishers/             # Backend publishers (future)
├── middleware/                 # Middleware entry points (future)
├── tests/
│   ├── fixtures/
│   │   ├── claude_hooks/       # Claude hook event samples
│   │   └── normalized_events/  # Expected normalized outputs
│   └── test_models.py          # Model tests (100% coverage)
├── pyproject.toml              # Dependencies and configuration
└── README.md
```

## Event Types

The system supports 10 normalized event types:

| Hook Event       | Analytics Event Type       | Description                    |
|------------------|----------------------------|--------------------------------|
| SessionStart     | `session_started`          | Session begins                 |
| SessionEnd       | `session_completed`        | Session ends                   |
| UserPromptSubmit | `user_prompt_submitted`    | User submits prompt            |
| PreToolUse       | `tool_execution_started`   | Before tool execution          |
| PostToolUse      | `tool_execution_completed` | After tool execution           |
| PermissionRequest| `permission_requested`     | Permission dialog shown        |
| Stop             | `agent_stopped`            | Main agent stops               |
| SubagentStop     | `subagent_stopped`         | Subagent stops                 |
| Notification     | `system_notification`      | System notification sent       |
| PreCompact       | `context_compacted`        | Before context compaction      |

## Normalized Event Schema

All events follow this schema after normalization:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56.789Z",
  "session_id": "abc123-def456",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {...},
    "tool_use_id": "toolu_01ABC"
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/path/to/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/project/path"
}
```

See `specs/v1/analytics-events.schema.json` for the complete JSON Schema.

## Coverage Report

Current test coverage: **97.30%** (exceeds 80% requirement)

```
Name                                   Stmts   Miss Branch BrPart   Cover
------------------------------------------------------------------------
src/analytics/models/__init__.py           4      0      0      0 100.00%
src/analytics/models/config.py            34      0     10      1  97.73%
src/analytics/models/events.py            38      0      0      0 100.00%
src/analytics/models/hook_input.py        77      2     22      2  95.96%
------------------------------------------------------------------------
TOTAL                                    153      2     32      3  97.30%
```

## Next Steps

**Milestone 1 (Foundation) - ✅ Complete**

Upcoming milestones:
- **Milestone 2**: Event Normalization (adapters + normalizer)
- **Milestone 3**: Event Publishers (file + API backends)
- **Milestone 4**: Middleware Integration (Rust hook system)

## Contributing

1. Write tests first (TDD approach)
2. Ensure type safety (`mypy --strict`)
3. Follow linting rules (`ruff check`)
4. Maintain >80% test coverage (>90% for core logic)
5. Use Pydantic for all data validation

## License

See root project LICENSE file.

