# agentic-adapters

Runtime adapters for AI agent integrations (Claude SDK, Claude CLI).

## Installation

```bash
pip install agentic-adapters
```

## Claude SDK Adapter

Generate `ClaudeAgentOptions` with security and observability hooks.

```python
from agentic_adapters.claude_sdk import create_agent_options
from agentic_security import SecurityPolicy

# Create options with security policy
options = create_agent_options(
    security_policy=SecurityPolicy.with_defaults(),
    observability_enabled=True,
    model="claude-sonnet-4-20250514",
    max_turns=50,
)

# Use with Claude SDK
from claude_code_sdk import Agent
agent = Agent(options=options)
result = await agent.run("Create a file")
```

### Security Hooks

```python
from agentic_adapters.claude_sdk import create_security_hooks
from agentic_security import SecurityPolicy

policy = SecurityPolicy.with_defaults()
pre_hook, _ = create_security_hooks(policy, block_on_violation=True)

# Validate a tool call
result = pre_hook("Bash", {"command": "rm -rf /"})
# Returns: {"__blocked__": True, "__reason__": "..."}
```

### Observability Hooks

```python
from agentic_adapters.claude_sdk import create_observability_hooks
from agentic_hooks import HookClient

client = HookClient()
pre_hook, post_hook = create_observability_hooks(hook_client=client)

# Note: These hooks only fire for custom/MCP tools
# Built-in tools require message parsing (see agentic_agent)
```

## Claude CLI Adapter

Generate `.claude/hooks/` Python files for Claude CLI integration.

```python
from agentic_adapters.claude_cli import generate_hooks

# Generate hook files
files = generate_hooks(
    output_dir=".claude/hooks",
    security_enabled=True,
    observability_enabled=True,
    observability_backend="jsonl",
)

print(f"Generated: {files}")
# ['.claude/hooks/pre_tool_use.py', '.claude/hooks/post_tool_use.py']
```

### Hook Templates

```python
from agentic_adapters.claude_cli import HookTemplate, generate_hooks

template = HookTemplate(
    # Security
    security_enabled=True,
    blocked_paths=["/etc/passwd", "~/.ssh/"],
    blocked_commands=[("rm -rf /", "Dangerous command")],

    # Observability
    observability_enabled=True,
    observability_backend="http",
    observability_endpoint="http://localhost:8080/events",
)

generate_hooks(".claude/hooks", template=template)
```

### Generated Files

**pre_tool_use.py** (Security):
```python
#!/usr/bin/env python3
from agentic_security import SecurityPolicy

policy = SecurityPolicy.with_defaults()

def validate_tool(tool_name, tool_input):
    result = policy.validate(tool_name, tool_input)
    if not result.safe:
        return {"decision": "block", "reason": result.reason}
    return {"decision": "allow"}
```

**post_tool_use.py** (Observability):
```python
#!/usr/bin/env python3
from datetime import datetime, UTC
from pathlib import Path

EVENTS_PATH = Path(".agentic/analytics/events.jsonl")

def record_tool_use(tool_name, tool_input, tool_result, error):
    event = {
        "type": "tool_completed",
        "timestamp": datetime.now(UTC).isoformat(),
        "tool_name": tool_name,
        "success": error is None,
    }
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")
```

## Hook Configuration

### HookConfig (SDK)

```python
from agentic_adapters.claude_sdk import HookConfig, create_agent_options

config = HookConfig(
    security_policy=policy,
    block_on_violation=True,
    observability_enabled=True,
    hook_client=client,
    log_tool_calls=True,
)

options = create_agent_options(config)
```

### HookTemplate (CLI)

```python
from agentic_adapters.claude_cli import HookTemplate

template = HookTemplate(
    security_enabled=True,
    observability_enabled=True,
    observability_backend="jsonl",  # or "http"
    jsonl_path=".agentic/analytics/events.jsonl",
    make_executable=True,
)
```

## Observability Backends

| Backend | Use Case |
|---------|----------|
| `jsonl` | Local development, simple logging |
| `http` | Send to observability service |
| `timescaledb` | Production (via agentic-hooks) |

## Important Notes

### Built-in Tool Limitation

Claude SDK's built-in tools (Bash, Write, Read, etc.) execute natively
and **bypass Python hooks**. For comprehensive tool observability:

1. Use `agentic_agent.InstrumentedAgent` for SDK
2. It parses `ToolUseBlock` from message stream
3. Hooks still work for security validation

### CLI vs SDK

| Feature | CLI Adapter | SDK Adapter |
|---------|-------------|-------------|
| Hook format | Python files | Function callbacks |
| Security | ✅ Works | ✅ Works |
| Observability | ✅ Works* | ⚠️ Custom tools only |
| Built-in tools | ✅ Works* | ❌ Use message parsing |

*CLI hooks receive all tool calls from the CLI runtime.

## License

MIT
