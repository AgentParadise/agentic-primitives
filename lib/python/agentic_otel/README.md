# agentic-otel

OpenTelemetry configuration and emission for AI agents.

## Overview

This package provides OTel-first observability for AI agent systems:

- **OTelConfig**: Configuration for Claude CLI's native OTel support
- **AgentSemanticConventions**: Standardized attribute names for agent telemetry
- **HookOTelEmitter**: Emit spans and events from hook scripts

## Installation

```bash
pip install agentic-otel
```

## Quick Start

### Configure OTel for Claude CLI

```python
from agentic_otel import OTelConfig

config = OTelConfig(
    endpoint="http://collector:4317",
    service_name="my-agent",
    resource_attributes={
        "deployment.environment": "production",
    }
)

# Get environment variables for Claude CLI
env = config.to_env()
# Pass to subprocess or container
```

### Emit spans from hooks

```python
from agentic_otel import HookOTelEmitter, OTelConfig

config = OTelConfig(endpoint="http://collector:4317")
emitter = HookOTelEmitter(config)

# In pre_tool_use hook
with emitter.start_tool_span("Bash", tool_use_id, tool_input) as span:
    result = run_security_checks()
    span.set_attribute("tool.success", result.safe)

    if not result.safe:
        emitter.emit_security_event(
            hook_type="pre_tool_use",
            decision="block",
            tool_name="Bash",
            tool_use_id=tool_use_id,
            reason=result.reason,
        )
```

## Semantic Conventions

This package follows OpenTelemetry semantic conventions with extensions for AI agents:

| Attribute | Description |
|-----------|-------------|
| `agent.session.id` | Agent session identifier (from Claude CLI) |
| `tool.name` | Name of the tool being executed |
| `tool.use_id` | Unique identifier for tool invocation |
| `hook.decision` | Security decision (allow, block, warn) |

## Architecture

```
Claude CLI (native OTel) ─────────────────┐
                                          │
Hooks (HookOTelEmitter) ──────────────────┼──► OTel Collector ──► Backend
                                          │
Platform injects resource attributes ─────┘
```

## Related

- [ADR-026: OTel-First Observability](../../docs/adrs/026-otel-first-observability.md)
- [Claude Code Telemetry Docs](https://docs.anthropic.com/claude-code/monitoring)
