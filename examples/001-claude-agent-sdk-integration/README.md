# 001-claude-agent-sdk-integration

Real Claude Agent SDK integration with comprehensive metrics collection, cost estimation, and security hooks.

## Overview

This example demonstrates how to:

- **Run real prompts** through the Claude Agent SDK
- **Capture comprehensive metrics** (tokens, duration, tool calls)
- **Estimate costs** from model pricing configurations
- **Integrate security hooks** (bash validation, file security, prompt filtering)
- **Output analytics** to JSONL for analysis

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY='sk-ant-...'

# Run the demo
./demo.sh

# Or run directly
uv run python main.py
```

## Prerequisites

- **Python 3.11+**
- **uv** package manager
- **ANTHROPIC_API_KEY** environment variable
- **Claude Code CLI** (for hooks to fire properly)

## Usage

### Run All Scenarios

```bash
uv run python main.py
```

### Run Specific Scenario

```bash
uv run python main.py --scenario create-file
```

### Use Different Model

```bash
# Use Haiku for cheaper testing (default)
uv run python main.py --model claude-haiku-4-5-20251001

# Use Sonnet for better results
uv run python main.py --model claude-sonnet-4-5-20250929
```

### Dry Run (Preview)

```bash
uv run python main.py --dry-run
```

### List Available Options

```bash
# List scenarios
uv run python main.py --list

# List models with pricing
uv run python main.py --list-models
```

## Test Scenarios

| Scenario | Description | Expected Tools | Should Block |
|----------|-------------|----------------|--------------|
| `create-file` | Create a Python file | Write | No |
| `read-file` | Read an existing file | Read | No |
| `edit-file` | Edit an existing file | Edit, Read | No |
| `bash-safe` | Run safe bash command | Bash | No |
| `bash-dangerous` | Run dangerous command | Bash | **Yes** (blocked) |
| `multi-step` | Multi-tool task | Write, Read | No |
| `simple-question` | No-tool question | (none) | No |

## Metrics Captured

### Per Interaction

- Input tokens
- Output tokens
- Duration (ms)
- Tool calls with timing

### Per Session

- Total tokens (input + output)
- Total cost (USD)
- Number of interactions
- Number of tool calls
- Tool calls blocked by hooks

### Computed KPIs

```
Cognitive Efficiency = Committed Tokens / Total Tokens
Cost Efficiency = Cost / Committed Tokens
Token Velocity = Total Tokens / Duration
```

## Model Pricing

Models and pricing are loaded from `providers/models/anthropic/`:

| Model | Input $/MTok | Output $/MTok |
|-------|-------------|---------------|
| claude-haiku-4-5 | $1.00 | $5.00 |
| claude-sonnet-4-5 | $3.00 | $15.00 |
| claude-opus-4-1 | $15.00 | $75.00 |

## Security Hooks

Hooks are automatically built from `000-claude-integration`:

### PreToolUse Hooks

- **bash-validator.py**: Blocks dangerous bash commands
  - `rm -rf /`, `dd if=`, fork bombs, etc.
- **file-security.py**: Warns on sensitive file access
  - `.env`, secrets, credentials

### UserPromptSubmit Hook

- **prompt-filter.py**: Filters prompt content

### Analytics Hook

- **analytics-collector.py**: Logs all events to JSONL

## Output

### Analytics File

Events are written to `.agentic/analytics/events.jsonl`:

```json
{"timestamp": "2025-11-26T12:00:00Z", "event_type": "agent_session_start", "session_id": "abc123", "data": {...}}
{"timestamp": "2025-11-26T12:00:01Z", "event_type": "agent_interaction", "session_id": "abc123", "data": {...}}
{"timestamp": "2025-11-26T12:00:02Z", "event_type": "tool_call", "session_id": "abc123", "data": {...}}
{"timestamp": "2025-11-26T12:00:03Z", "event_type": "agent_session_end", "session_id": "abc123", "data": {...}}
```

### Validate Events

```bash
uv run python validate_events.py
```

## Project Structure

```
001-claude-agent-sdk-integration/
├── .claude/
│   ├── settings.json           # Hook configuration
│   └── hooks/
│       ├── analytics/
│       │   └── analytics-collector.py
│       └── security/
│           ├── bash-validator.py
│           ├── file-security.py
│           └── prompt-filter.py
│
├── .agentic/
│   └── analytics/
│       └── events.jsonl        # Output metrics
│
├── .workspace/                 # Agent workspace (gitignored)
│
├── src/
│   ├── __init__.py
│   ├── agent.py                # InstrumentedAgent wrapper
│   ├── metrics.py              # MetricsCollector
│   ├── models.py               # Model config loader
│   └── scenarios.py            # Test scenarios
│
├── main.py                     # CLI entry point
├── validate_events.py          # Event validation
├── build-hooks.sh              # Build hooks script
├── demo.sh                     # Demo runner
├── pyproject.toml              # Dependencies
└── README.md
```

## Extending

### Add New Scenarios

Edit `src/scenarios.py`:

```python
SCENARIOS.append(
    Scenario(
        name="my-scenario",
        description="My custom scenario",
        prompt="Do something interesting",
        expected_tools=["Write", "Bash"],
    )
)
```

### Add New Metrics

Extend `src/metrics.py`:

```python
@dataclass
class CustomMetric:
    my_field: str
    # ...
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"

```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

### "Claude Code CLI not found"

The SDK uses Claude Code under the hood. Install from:
https://claude.ai/code

### "Hooks not firing"

Ensure hooks are built:

```bash
./build-hooks.sh
```

Check hooks are executable:

```bash
ls -la .claude/hooks/security/
```

## Related

- [000-claude-integration](../000-claude-integration/) - Hook testing example
- [agentic-analytics](../../lib/python/agentic_analytics/) - Analytics library
- [providers/models/anthropic](../../providers/models/anthropic/) - Model configs

