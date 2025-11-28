# Analytics Hook Examples

This directory contains example hook configurations demonstrating different analytics use cases with the agentic-primitives hook system.

## Overview

Each example shows how to configure analytics middleware for specific scenarios. All examples follow the hook metadata schema defined in `specs/v1/hook-meta.schema.json`.

## Examples

### Basic Examples

- **[session-tracking.hook.yaml](./session-tracking.hook.yaml)** - Track session start and end events
- **[tool-monitoring.hook.yaml](./tool-monitoring.hook.yaml)** - Monitor tool execution (PreToolUse/PostToolUse)
- **[user-prompts.hook.yaml](./user-prompts.hook.yaml)** - Track user prompt submissions
- **[permission-tracking.hook.yaml](./permission-tracking.hook.yaml)** - Track permission requests

### Comprehensive Example

- **[complete-analytics.hook.yaml](./complete-analytics.hook.yaml)** - Track all analytics events in one hook

### Provider-Specific Examples

- **[provider-specific/claude-analytics.hook.yaml](./provider-specific/claude-analytics.hook.yaml)** - Claude-specific configuration
- **[provider-specific/openai-analytics.hook.yaml](./provider-specific/openai-analytics.hook.yaml)** - OpenAI-specific configuration (future)

## Using These Examples

### Validation

Validate any example with the agentic CLI:

```bash
agentic-p validate docs/examples/analytics/session-tracking.hook.yaml
```

### Testing

Test with sample input:

```bash
# Create test input
cat > test-session-start.json <<'EOF'
{
  "provider": "claude",
  "event": "SessionStart",
  "data": {
    "session_id": "test-session-123",
    "transcript_path": "/tmp/transcript.jsonl",
    "cwd": "/Users/dev/project",
    "permission_mode": "default",
    "hook_event_name": "SessionStart",
    "source": "startup"
  }
}
EOF

# Test the hook
agentic-p test-hook docs/examples/analytics/session-tracking.hook.yaml \
  --input test-session-start.json
```

### Customization

All examples use environment variables for configuration. Customize by setting:

```bash
# Required for event normalizer
export ANALYTICS_PROVIDER=claude  # or openai, cursor, etc.

# Required for event publisher
export ANALYTICS_PUBLISHER_BACKEND=file  # or api
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# Optional: API backend
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3
```

## Configuration Structure

All analytics hooks follow this structure:

```yaml
version: 1                    # Schema version
id: unique-hook-id            # Unique identifier
name: "Human Readable Name"   # Display name
description: "What this hook does"

events:                       # Which hook events to capture
  - SessionStart
  - SessionEnd
  # ...

middleware:                   # Two-stage analytics pipeline
  - name: "analytics-normalizer"
    type: analytics           # Middleware type
    impl: python              # Python implementation
    path: "path/to/event_normalizer.py"
    env:                      # Environment variables
      ANALYTICS_PROVIDER: "claude"
  
  - name: "analytics-publisher"
    type: analytics
    impl: python
    path: "path/to/event_publisher.py"
    env:
      ANALYTICS_PUBLISHER_BACKEND: "file"
      ANALYTICS_OUTPUT_PATH: "./analytics/events.jsonl"

execution: pipeline           # Sequential execution (normalizer → publisher)
```

## Important Notes

### Path Configuration

The `path` field in middleware configuration should point to the actual middleware scripts:

```yaml
# If running from repository root
path: "services/analytics/middleware/event_normalizer.py"

# If analytics is installed system-wide
path: "/usr/local/share/agentic/analytics/middleware/event_normalizer.py"
```

Adjust paths based on your installation.

### Execution Mode

Analytics hooks use `execution: pipeline` because:
- Stage 1 (normalizer) produces output
- Stage 2 (publisher) consumes that output
- Must run sequentially, not in parallel

### Provider Configuration

The `ANALYTICS_PROVIDER` environment variable should match the AI provider generating events:
- `claude` for Claude Code
- `openai` for OpenAI-based systems (future)
- `cursor` for Cursor IDE (future)
- Custom provider names supported

### Output Paths

The publisher creates parent directories automatically:

```yaml
# This works even if ~/analytics doesn't exist
ANALYTICS_OUTPUT_PATH: "~/analytics/events.jsonl"
```

Use absolute paths or `~` for home directory.

## Next Steps

1. **Choose an example** that matches your use case
2. **Customize environment variables** for your setup
3. **Validate the configuration** with `agentic-p validate`
4. **Test with sample data** using `agentic-p test-hook`
5. **Deploy to your hook system** (e.g., Claude Code settings)

## Additional Resources

- [Analytics Integration Guide](../../analytics-integration.md)
- [Analytics Event Reference](../../analytics-event-reference.md)
- [Hook System Documentation](../../architecture.md)
- [ADR-011: Analytics Middleware](../../adrs/011-analytics-middleware.md)

