# Analytics Collector Hook Primitive

A reusable hook primitive for collecting, normalizing, and publishing analytics events from AI agent interactions.

## Overview

The `analytics-collector` hook provides a standardized way to capture analytics data from AI agents across different providers (Claude, OpenAI, Cursor, Gemini). It normalizes provider-specific events into a consistent schema and publishes them to your chosen backend.

### What It Does

1. **Receives** hook events from AI providers (via stdin)
2. **Normalizes** events using provider-specific adapters
3. **Publishes** normalized events to configured backends (file or API)
4. **Never blocks** agent execution (fail-safe design)

### Use Cases

- **Usage Analytics**: Track tool usage, session patterns, user interactions
- **Performance Monitoring**: Measure tool execution times and patterns
- **Debugging**: Rich context for troubleshooting agent behavior
- **Compliance**: Audit trail of agent actions
- **Product Insights**: Understand how users interact with AI agents

## Quick Start

### 1. Validate the Hook

```bash
agentic-p validate primitives/v1/hooks/analytics/analytics-collector/
```

### 2. Test the Hook

```bash
# Test with a sample PreToolUse event
echo '{
  "provider": "claude",
  "event": "PreToolUse",
  "data": {
    "hook_event_name": "PreToolUse",
    "session_id": "test-session-123",
    "tool_name": "Write",
    "tool_input": {"file_path": "test.py", "content": "print(\"hello\")"},
    "cwd": "/workspace",
    "permission_mode": "default"
  }
}' | python3 primitives/v1/hooks/analytics/analytics-collector/impl.python.py
```

Expected output:
```json
{"status": "success", "message": "Analytics event processed successfully"}
```

### 3. Check Output

```bash
# View the analytics events
cat ./analytics/events.jsonl | jq .
```

## Installation

### For Claude Code

Add to your `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 primitives/v1/hooks/analytics/analytics-collector/impl.python.py"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "python3 primitives/v1/hooks/analytics/analytics-collector/impl.python.py"
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 primitives/v1/hooks/analytics/analytics-collector/impl.python.py"
      }]
    }],
    "SessionEnd": [{
      "hooks": [{
        "type": "command",
        "command": "python3 primitives/v1/hooks/analytics/analytics-collector/impl.python.py"
      }]
    }]
  }
}
```

### Using the CLI (Future)

```bash
# Install analytics hooks for Claude
agentic-p install --hook analytics-collector --provider claude

# Install with custom configuration
agentic-p install --hook analytics-collector --provider claude \
  --config backend=api \
  --config api_endpoint=https://analytics.example.com/api/events
```

## Configuration

The hook is configured via environment variables passed to the middleware:

### Normalizer Configuration

```bash
# Provider name (claude, openai, cursor, etc.)
ANALYTICS_PROVIDER=claude

# Enable debug logging (optional)
ANALYTICS_DEBUG=false
```

### Publisher Configuration

```bash
# Backend type: "file" or "api"
ANALYTICS_PUBLISHER_BACKEND=file

# File backend - path to output JSONL file
ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# API backend - HTTP endpoint
ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
ANALYTICS_API_TIMEOUT=30
ANALYTICS_RETRY_ATTEMPTS=3
```

### Customizing the Hook

Edit `analytics-collector.hook.yaml` to customize:

```yaml
middleware:
  - id: "event-normalizer"
    path: "../../../../../services/analytics/middleware/event_normalizer.py"
    type: analytics
    config:
      provider: "claude"  # Change for different providers
      debug: false
  
  - id: "event-publisher"
    path: "../../../../../services/analytics/middleware/event_publisher.py"
    type: analytics
    config:
      backend: "file"  # or "api"
      output_path: "./analytics/events.jsonl"
```

## Event Schema

All events are normalized to a standard schema:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56.789Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {"file_path": "test.py"},
    "tool_use_id": "toolu_123",
    "tool_response": null
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/path/to/transcript.jsonl",
    "permission_mode": "default",
    "raw_event": {...}
  },
  "cwd": "/workspace"
}
```

### Event Types

| Hook Event | Analytics Event Type |
|------------|---------------------|
| `PreToolUse` | `tool_execution_started` |
| `PostToolUse` | `tool_execution_completed` |
| `UserPromptSubmit` | `user_prompt_submitted` |
| `SessionStart` | `session_started` |
| `SessionEnd` | `session_completed` |
| `Notification` | `system_notification` |
| `Stop` | `agent_stopped` |
| `SubagentStop` | `subagent_stopped` |
| `PreCompact` | `context_compacted` |

## Architecture

```
┌─────────────────────────────────────┐
│   AI Provider (Claude, OpenAI...)   │
│   Emits hook event (JSON)           │
└────────────────┬────────────────────┘
                 │ stdin
                 ▼
┌─────────────────────────────────────┐
│   Hook Orchestrator                 │
│   (impl.python.py)                  │
│   - Validates input                 │
│   - Orchestrates pipeline           │
│   - Handles errors                  │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│   Stage 1: Event Normalizer         │
│   (event_normalizer.py)             │
│   - Provider-specific adapter       │
│   - Maps to standard schema         │
│   - Validates with Pydantic         │
└────────────────┬────────────────────┘
                 │ NormalizedEvent
                 ▼
┌─────────────────────────────────────┐
│   Stage 2: Event Publisher          │
│   (event_publisher.py)              │
│   - File backend (JSONL)            │
│   - API backend (HTTP POST)         │
│   - Retry logic + error handling    │
└─────────────────────────────────────┘
```

## Supported Providers

### ✅ Claude Code (Fully Supported)
- All 9 hook events supported
- Comprehensive test coverage
- Production-ready

### 🚧 OpenAI (Planned)
- Adapter structure in place
- Waiting for OpenAI hook system
- See `services/analytics/src/analytics/adapters/openai.py`

### 🔮 Future Providers
- Cursor
- Gemini
- Custom providers

The system is designed to be provider-agnostic - adding new providers only requires implementing a provider adapter.

## Backends

### File Backend (JSONL)

Writes events to a JSON Lines file (one event per line):

```bash
# Configure
ANALYTICS_PUBLISHER_BACKEND=file
ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# Query with jq
cat ./analytics/events.jsonl | jq 'select(.event_type == "tool_execution_started")'

# Count events by type
cat ./analytics/events.jsonl | jq -r '.event_type' | sort | uniq -c

# Extract tool names
cat ./analytics/events.jsonl | jq -r '.context.tool_name' | sort | uniq
```

### API Backend (HTTP POST)

Sends events to a remote analytics service:

```bash
# Configure
ANALYTICS_PUBLISHER_BACKEND=api
ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
ANALYTICS_API_TIMEOUT=30
ANALYTICS_RETRY_ATTEMPTS=3
```

Features:
- Automatic retry with exponential backoff
- Timeout handling
- Never blocks on network failures

## Error Handling

The analytics hook is designed to **never block** agent execution:

- ✅ **Non-fatal errors**: Always exits with code 0
- ✅ **Graceful degradation**: Logs errors to stderr, continues
- ✅ **Fail-safe**: Analytics failures don't affect agent
- ✅ **Timeout protection**: 5-second timeout (configurable)

Example error output:

```json
{
  "status": "error",
  "message": "Analytics pipeline failed: Connection timeout"
}
```

The agent continues normally even if analytics fails.

## Troubleshooting

### No events in output file

1. **Check file path**:
   ```bash
   ls -la ./analytics/events.jsonl
   ```

2. **Check permissions**:
   ```bash
   mkdir -p ./analytics
   chmod 755 ./analytics
   ```

3. **Enable debug logging**:
   ```bash
   ANALYTICS_DEBUG=true python3 impl.python.py < test-event.json
   ```

### Invalid JSON errors

1. **Validate input format**:
   ```bash
   echo '{"provider":"claude","event":"PreToolUse","data":{...}}' | jq .
   ```

2. **Check middleware paths**:
   ```bash
   ls -la ../../../../../services/analytics/middleware/
   ```

### Middleware not found

The hook expects this directory structure:

```
agentic-primitives/
├── primitives/v1/hooks/analytics/analytics-collector/
│   ├── analytics-collector.hook.yaml
│   ├── impl.python.py
│   └── README.md
└── services/analytics/
    └── middleware/
        ├── event_normalizer.py
        └── event_publisher.py
```

Ensure you're running from the project root.

## Testing

### Unit Tests

```bash
# Test the normalizer
cd services/analytics
uv run pytest tests/test_normalizer.py -v

# Test the publisher
uv run pytest tests/test_publishers.py -v

# Test with coverage
uv run pytest --cov=src --cov-report=term
```

### Integration Tests

```bash
# Test the full pipeline
cd cli
cargo test test_analytics_middleware
```

### Manual Testing

```bash
# Create a test event
cat > test-event.json << 'EOF'
{
  "provider": "claude",
  "event": "PreToolUse",
  "data": {
    "hook_event_name": "PreToolUse",
    "session_id": "test-123",
    "tool_name": "Write",
    "tool_input": {"file_path": "test.py"},
    "cwd": "/workspace",
    "permission_mode": "default"
  }
}
EOF

# Run the hook
cat test-event.json | python3 impl.python.py

# Check output
cat ./analytics/events.jsonl | jq .
```

## Performance

- **Overhead**: <10ms per event (measured with benchmarks)
- **Throughput**: >1000 events/second (file backend)
- **Memory**: <50MB for normalizer + publisher
- **Non-blocking**: Runs asynchronously, doesn't slow agent

## Security

- ✅ **No PII leakage**: Raw events stored in metadata only
- ✅ **Safe file handling**: Atomic writes, proper permissions
- ✅ **Input validation**: Pydantic validates all data
- ✅ **Error sanitization**: No sensitive data in error messages

## Contributing

1. **Write tests first** (TDD approach)
2. **Ensure type safety** (`mypy --strict`)
3. **Follow linting rules** (`ruff check`)
4. **Maintain >80% coverage** (>90% for core logic)
5. **Use Pydantic** for all data validation

See `services/analytics/README.md` for development setup.

## License

See root project LICENSE file.

## Related Documentation

- [Analytics Integration Guide](../../../../../docs/analytics-integration.md)
- [Event Reference](../../../../../docs/analytics-event-reference.md)
- [Troubleshooting Guide](../../../../../docs/analytics-troubleshooting.md)
- [Architecture Decision Record](../../../../../docs/adrs/011-analytics-middleware.md)

## Support

For issues or questions:
1. Check the [Troubleshooting Guide](../../../../../docs/analytics-troubleshooting.md)
2. Review [examples](../../../../../docs/examples/analytics/)
3. Open an issue on GitHub

