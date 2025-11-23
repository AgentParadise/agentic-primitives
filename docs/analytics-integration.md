# Analytics Integration Guide

Complete guide for integrating provider-agnostic analytics into the agentic-primitives hook system.

## Overview

The analytics integration provides a consistent way to collect, normalize, and publish events from AI agent interactions across multiple providers (Claude, OpenAI, Cursor, Gemini).

### What is the Analytics System?

The analytics system captures detailed lifecycle events from AI agents:
- **Session tracking**: When sessions start/end and why
- **Tool usage**: Which tools agents use and how often
- **User interactions**: When users submit prompts
- **Permission patterns**: When agents request permissions
- **System events**: Notifications, context compaction, stops

### Why Use It?

- **Cross-Provider Insights**: Consistent data regardless of AI provider
- **Usage Analytics**: Understand how agents are being used
- **Performance Monitoring**: Track tool execution patterns
- **Debugging**: Rich context for troubleshooting agent behavior
- **Compliance**: Audit trail of agent actions

### Architecture Overview

```
┌──────────────────────────────────────────────┐
│  AI Provider (Claude, OpenAI, Cursor, etc.)  │
│  Emits hook events in provider format        │
└───────────────┬──────────────────────────────┘
                │
                ▼ stdin (JSON)
┌──────────────────────────────────────────────┐
│  Stage 1: Event Normalizer                   │
│  - Validates provider-specific input         │
│  - Maps to normalized analytics schema       │
│  - Extracts context and metadata             │
└───────────────┬──────────────────────────────┘
                │
                ▼ stdout (JSON)
┌──────────────────────────────────────────────┐
│  Stage 2: Event Publisher                    │
│  - Publishes to configured backend           │
│  - Handles retries and errors                │
│  - Supports: file (JSONL), API (HTTP)        │
└───────────────┬──────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────┐
│  Analytics Backend                           │
│  - File: Local JSONL files                   │
│  - API: Remote analytics service             │
│  - Future: Redis, Kafka, etc.                │
└──────────────────────────────────────────────┘
```

The system is **provider-agnostic**: adding new AI providers requires zero analytics code changes.

## Getting Started

### Prerequisites

- **Python 3.11+**: Required for analytics service
- **uv**: Python package and project manager
- **agentic CLI**: The agentic-primitives command-line tool

Install uv if you don't have it:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Via pip
pip install uv
```

### Installation

1. **Navigate to analytics service**:

```bash
cd services/analytics
```

2. **Install dependencies**:

```bash
# Sync all dependencies (including dev)
uv sync

# Sync only production dependencies
uv sync --no-dev
```

This creates a `.venv` directory with all dependencies.

3. **Verify installation**:

```bash
# Check Python version
uv run python --version  # Should be 3.11+

# Run tests to verify setup
uv run pytest
```

### Quick Start Example

Let's capture analytics from Claude Code tool usage:

1. **Set environment variables**:

```bash
export ANALYTICS_PROVIDER=claude
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics-events.jsonl
```

2. **Test the middleware manually**:

```bash
# Create test input (PreToolUse event)
cat > test-input.json <<'EOF'
{
  "provider": "claude",
  "event": "PreToolUse",
  "data": {
    "session_id": "abc123-def456",
    "transcript_path": "/Users/dev/.claude/transcript.jsonl",
    "cwd": "/Users/dev/project",
    "permission_mode": "default",
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/main.py",
      "contents": "print('Hello, World!')"
    },
    "tool_use_id": "toolu_01ABC123"
  }
}
EOF

# Run through the pipeline
cat test-input.json | \
  uv run python middleware/event_normalizer.py | \
  uv run python middleware/event_publisher.py

# Check output file
cat analytics-events.jsonl | jq .
```

3. **Expected output**:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56.789000Z",
  "session_id": "abc123-def456",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/main.py",
      "contents": "print('Hello, World!')"
    },
    "tool_use_id": "toolu_01ABC123",
    "tool_response": null
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/Users/dev/.claude/transcript.jsonl",
    "permission_mode": "default",
    "raw_event": null
  },
  "cwd": "/Users/dev/project"
}
```

Success! The provider-specific Claude event was normalized to the standard analytics schema.

## Configuration

### Environment Variables Reference

Analytics middleware is configured via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANALYTICS_PROVIDER` | No | `unknown` | Provider name (claude, openai, etc.) |
| `ANALYTICS_PUBLISHER_BACKEND` | Yes | `file` | Backend type: `file` or `api` |
| `ANALYTICS_OUTPUT_PATH` | If `backend=file` | - | Output file path (JSONL format) |
| `ANALYTICS_API_ENDPOINT` | If `backend=api` | - | API endpoint URL |
| `ANALYTICS_API_TIMEOUT` | No | `30` | API request timeout (seconds, 1-300) |
| `ANALYTICS_RETRY_ATTEMPTS` | No | `3` | Number of retry attempts (0-10) |
| `ANALYTICS_DEBUG` | No | `false` | Enable debug logging |

### Configuration Examples

#### File Backend (Local JSONL)

```bash
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=~/analytics/claude-events.jsonl
```

The file publisher:
- Creates parent directories automatically
- Appends events to file (one JSON object per line)
- Expands `~` to user home directory
- Uses atomic writes to prevent corruption

#### API Backend (Remote Service)

```bash
export ANALYTICS_PUBLISHER_BACKEND=api
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3
```

The API publisher:
- POSTs JSON to endpoint
- Retries on network errors (exponential backoff)
- Times out after configured seconds
- Logs errors but doesn't block agent

#### Debug Mode

```bash
export ANALYTICS_DEBUG=true
```

Enables verbose logging to stderr for troubleshooting.

### Provider-Specific Settings

While analytics is provider-agnostic, you might want different configurations per provider:

```bash
# Claude configuration
export ANALYTICS_PROVIDER=claude
export ANALYTICS_OUTPUT_PATH=~/analytics/claude-events.jsonl

# OpenAI configuration (future)
export ANALYTICS_PROVIDER=openai
export ANALYTICS_OUTPUT_PATH=~/analytics/openai-events.jsonl
```

## Event Schema

### Normalized Event Structure

All events follow this consistent structure after normalization:

```json
{
  "event_type": "string",         // One of 10 event types
  "timestamp": "ISO 8601 string", // When event occurred
  "session_id": "string",          // Session identifier
  "provider": "string",            // Provider name (claude, openai, etc.)
  "context": {                     // Event-specific data (varies by type)
    "...": "..."
  },
  "metadata": {                    // Event metadata
    "hook_event_name": "string",   // Original hook event name
    "transcript_path": "string",   // Path to transcript (optional)
    "permission_mode": "string",   // Permission mode (optional)
    "raw_event": {}                // Original event data (optional)
  },
  "cwd": "string"                  // Current working directory (optional)
}
```

### Event Types

The analytics system normalizes all provider-specific events to 10 standard event types:

| Event Type | Description | Hook Event Source |
|------------|-------------|-------------------|
| `session_started` | Session begins or resumes | SessionStart |
| `session_completed` | Session ends | SessionEnd |
| `user_prompt_submitted` | User submits a prompt | UserPromptSubmit |
| `tool_execution_started` | Agent about to execute tool | PreToolUse |
| `tool_execution_completed` | Agent finished executing tool | PostToolUse |
| `permission_requested` | Agent asks for permission | PermissionRequest |
| `agent_stopped` | Main agent stops responding | Stop |
| `subagent_stopped` | Subagent stops responding | SubagentStop |
| `system_notification` | System sends notification | Notification |
| `context_compacted` | Context window compacted | PreCompact |

See [Analytics Event Reference](./analytics-event-reference.md) for detailed documentation of each event type with examples.

### Context Fields by Event Type

Each event type has specific context fields:

#### Tool Execution Events

```json
{
  "event_type": "tool_execution_started",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/main.py",
      "contents": "..."
    },
    "tool_response": null,        // Only in "completed" events
    "tool_use_id": "toolu_01ABC"
  }
}
```

#### User Prompt Events

```json
{
  "event_type": "user_prompt_submitted",
  "context": {
    "prompt": "Write a Python function to...",
    "prompt_length": 45
  }
}
```

#### Session Events

```json
{
  "event_type": "session_started",
  "context": {
    "source": "startup"  // or "resume", "clear", "compact"
  }
}
```

#### Notification Events

```json
{
  "event_type": "system_notification",
  "context": {
    "notification_type": "permission_prompt",
    "message": "Claude needs permission to..."
  }
}
```

## Provider Adapters

### How Adapters Work

Adapters translate provider-specific event formats into the normalized analytics schema:

```
Provider Event → Adapter → Normalized Event
```

Each provider has its own adapter that:
1. Validates the provider's JSON format
2. Extracts relevant fields
3. Maps to normalized schema
4. Adds provider-specific context

### Supported Providers

#### Claude Adapter

Handles all 10 Claude Code hook events:

- SessionStart, SessionEnd
- UserPromptSubmit
- PreToolUse, PostToolUse
- PermissionRequest
- Stop, SubagentStop
- Notification
- PreCompact

**Status**: ✅ Implemented with 100% test coverage

#### OpenAI Adapter

**Status**: 🚧 Planned for future implementation

Will handle OpenAI-specific event formats when OpenAI adds hook support.

### Adding a New Provider Adapter

To add support for a new provider:

1. **Create adapter module**:

```python
# services/analytics/src/analytics/adapters/newprovider.py
from analytics.models.events import NormalizedEvent
from analytics.models.hook_input import HookInput
from datetime import datetime

def normalize_newprovider_event(hook_input: HookInput) -> NormalizedEvent:
    """Normalize NewProvider events to standard schema"""
    
    # Extract fields from provider format
    data = hook_input.data
    
    # Map to normalized event
    return NormalizedEvent(
        event_type="tool_execution_started",  # Map event type
        timestamp=datetime.now(),
        session_id=data["session_id"],
        provider=hook_input.provider,
        context={...},  # Extract context
        metadata={...}, # Add metadata
    )
```

2. **Add to normalizer**:

```python
# services/analytics/src/analytics/normalizer.py
from analytics.adapters import claude, newprovider

def normalize_event(hook_input: HookInput) -> NormalizedEvent:
    if hook_input.provider == "claude":
        return claude.normalize_claude_event(hook_input)
    elif hook_input.provider == "newprovider":
        return newprovider.normalize_newprovider_event(hook_input)
    else:
        # Generic normalization
        return generic_normalize(hook_input)
```

3. **Write tests**:

```python
# services/analytics/tests/test_adapters.py
def test_newprovider_adapter():
    hook_input = HookInput(
        provider="newprovider",
        event="ToolStart",
        data={...}
    )
    
    normalized = normalize_newprovider_event(hook_input)
    
    assert normalized.event_type == "tool_execution_started"
    assert normalized.provider == "newprovider"
```

**No changes needed** to:
- Pydantic models (provider-agnostic)
- Publisher code (works with any normalized event)
- Configuration (provider name is just a string)

## Publisher Backends

### File Publisher (JSONL Format)

Writes events to local files in JSON Lines format (one JSON object per line).

**Configuration**:

```bash
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=~/analytics/events.jsonl
```

**Features**:
- Creates parent directories automatically
- Appends events atomically (safe for concurrent writes)
- Expands `~` to home directory
- Human-readable format (easy to inspect with `jq`, `grep`, etc.)

**Output format**:

```jsonl
{"event_type":"session_started","timestamp":"2025-11-19T10:00:00Z",...}
{"event_type":"tool_execution_started","timestamp":"2025-11-19T10:01:23Z",...}
{"event_type":"tool_execution_completed","timestamp":"2025-11-19T10:01:25Z",...}
```

**Reading JSONL files**:

```bash
# Pretty-print all events
cat events.jsonl | jq .

# Filter by event type
cat events.jsonl | jq 'select(.event_type == "tool_execution_started")'

# Count events by type
cat events.jsonl | jq -r '.event_type' | sort | uniq -c

# Extract tool names
cat events.jsonl | jq -r 'select(.event_type == "tool_execution_started") | .context.tool_name'
```

### API Publisher (HTTP POST)

POSTs events to a remote analytics service via HTTP.

**Configuration**:

```bash
export ANALYTICS_PUBLISHER_BACKEND=api
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3
```

**Features**:
- HTTP POST with JSON body
- Retry on failure (exponential backoff)
- Configurable timeout
- Non-blocking (errors logged, agent continues)

**Request format**:

```http
POST /api/events HTTP/1.1
Host: analytics.example.com
Content-Type: application/json

{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56Z",
  ...
}
```

**Expected response**:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "accepted",
  "event_id": "evt_abc123"
}
```

### Adding a New Publisher Backend

To add support for a new backend (Redis, Kafka, etc.):

1. **Create publisher module**:

```python
# services/analytics/src/analytics/publishers/custom.py
from analytics.models.events import NormalizedEvent

async def publish_to_custom(event: NormalizedEvent) -> None:
    """Publish event to custom backend"""
    # Your implementation here
    pass
```

2. **Add to publisher**:

```python
# services/analytics/middleware/event_publisher.py
from analytics.publishers import file, api, custom

backend = config.publisher_backend
if backend == "file":
    await file.publish_to_file(event, config)
elif backend == "api":
    await api.publish_to_api(event, config)
elif backend == "custom":
    await custom.publish_to_custom(event, config)
```

3. **Add configuration**:

```python
# services/analytics/src/analytics/models/config.py
class AnalyticsConfig(BaseSettings):
    publisher_backend: Literal["file", "api", "custom"] = "file"
    # Add custom backend config fields
```

## Middleware Integration

### How Analytics Fits into Hook System

Analytics integrates as middleware in the hook system (see [ADR-006: Middleware-Based Hooks](./adrs/006-middleware-hooks.md)):

```
Hook Event Triggered
        ↓
[Hook Orchestrator Loads hook.meta.yaml]
        ↓
[Executes Middleware Pipeline]
        ↓
├─ Safety Middleware (sequential, fail-fast)
│  └─ If any blocks → stop, return block
│
├─ Observability Middleware (parallel, non-blocking)
│  └─ Errors logged, don't block
│
└─ Analytics Middleware (parallel, non-blocking)
   ├─ Stage 1: Event Normalizer
   └─ Stage 2: Event Publisher
        ↓
[Aggregate Results → Output Decision]
```

### Middleware Type: Analytics

Analytics is a new middleware type alongside safety and observability:

```rust
pub enum MiddlewareType {
    Safety,         // Blocking, fail-fast
    Observability,  // Non-blocking, best-effort
    Analytics,      // Non-blocking, best-effort (NEW)
}
```

### Execution Order

Analytics middleware runs:
- **After** safety middleware (safety can block before analytics sees event)
- **In parallel** with observability middleware
- **Non-blocking** (errors don't affect agent execution)

### Parallelization

Within analytics, the two stages run **sequentially** (pipeline):

```
Stage 1: Normalizer → Stage 2: Publisher
```

But analytics middleware runs **in parallel** with other observability middleware.

### Error Handling

Analytics failures are non-fatal:

- **Normalizer errors**: Logged to stderr, empty JSON to stdout, publisher skips
- **Publisher errors**: Logged to stderr, agent continues
- **No exit code 2**: Analytics never blocks hook execution

This ensures agent reliability even if analytics has issues.

## Hook Primitive Usage

### The `analytics-collector` Hook Primitive

The analytics system provides a reusable hook primitive that you can install and use:

```
primitives/v1/hooks/analytics/analytics-collector/
├── analytics-collector.hook.yaml   # Hook metadata
├── impl.python.py                  # Hook orchestrator
└── README.md                       # Usage documentation
```

**Status**: 🚧 To be implemented in Phase 3

### Using the Hook Primitive

1. **Validate the hook**:

```bash
agentic-p validate primitives/v1/hooks/analytics/analytics-collector/
```

2. **Test the hook**:

```bash
agentic-p test-hook primitives/v1/hooks/analytics/analytics-collector/ \
  --event PreToolUse \
  --input test-input.json
```

3. **Install for a provider**:

```bash
agentic-p install --hook analytics-collector --provider claude
```

### Configuring for Different Providers

The hook primitive can be configured per provider:

```yaml
# .claude/settings.json (Claude Code)
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "agentic run-hook analytics-collector"
      }]
    }]
  }
}
```

## Development

### Setting Up Development Environment

1. **Clone repository**:

```bash
git clone https://github.com/your-org/agentic-primitives.git
cd agentic-primitives/services/analytics
```

2. **Install dev dependencies**:

```bash
uv sync
```

3. **Install pre-commit hooks**:

```bash
uv run pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
uv run pytest tests/test_models.py

# Run with verbose output
uv run pytest -v

# Run tests matching pattern
uv run pytest -k "test_claude"
```

### Type Checking

```bash
# Check types with mypy
uv run mypy src/analytics

# Strict mode (all checks)
uv run mypy --strict src/analytics
```

### Linting

```bash
# Check code with ruff
uv run ruff check src tests

# Auto-fix issues
uv run ruff check --fix src tests

# Format code
uv run ruff format src tests
```

### Running All QA Checks

```bash
# From project root
make python-check       # Type check + lint
make python-test        # Run tests
make python-test-coverage  # Tests with coverage report

# Or from services/analytics
cd services/analytics
uv run pytest --cov=src --cov-report=term
uv run mypy src/analytics
uv run ruff check src tests
```

### Contributing Guidelines

1. **Write tests first** (TDD approach per ADR-008)
2. **Achieve >90% coverage** for core logic, >80% for overall
3. **Type all functions** (mypy strict mode)
4. **Format code** with ruff before committing
5. **Update documentation** for any API changes
6. **Follow conventional commits** for commit messages

## Troubleshooting

For comprehensive troubleshooting guide, see [Analytics Troubleshooting](./analytics-troubleshooting.md).

### Quick Diagnostics

**Check if middleware is working**:

```bash
echo '{"provider":"claude","event":"PreToolUse","data":{...}}' | \
  uv run python services/analytics/middleware/event_normalizer.py
```

**Enable debug logging**:

```bash
export ANALYTICS_DEBUG=true
```

**Inspect output file**:

```bash
# Validate JSON format
cat analytics-events.jsonl | jq . > /dev/null && echo "Valid JSON"

# Count events
wc -l analytics-events.jsonl

# Check for errors
tail -f analytics-events.jsonl
```

## Next Steps

1. **Set up configuration** for your environment
2. **Test manually** with sample events
3. **Integrate into hooks** (once Phase 3 complete)
4. **Monitor output** and verify events are captured
5. **Build dashboards** on top of collected data

## Additional Resources

- [Analytics Event Reference](./analytics-event-reference.md) - Detailed event documentation
- [Analytics Troubleshooting Guide](./analytics-troubleshooting.md) - Common issues and solutions
- [Analytics Examples](../docs/examples/analytics/) - Example hook configurations
- [ADR-011: Analytics Middleware](./adrs/011-analytics-middleware.md) - Architecture decision record
- [ARCHITECTURE.md](../services/analytics/ARCHITECTURE.md) - Technical design details

