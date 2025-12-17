# 003 - OTel-First Agent Example

A minimal example demonstrating the **OTel-first observability** pattern for Claude CLI agents.

## Overview

This example shows how to:
1. Configure OTel for Claude CLI native telemetry
2. Generate security hooks that emit OTel events
3. Run agents with full observability in isolation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Your Application                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│   │  OTelConfig  │────▶│ClaudeCLIRunner│────▶│ Claude CLI   │   │
│   │              │     │              │     │ (native OTel)│   │
│   └──────────────┘     └──────────────┘     └──────┬───────┘   │
│                                                     │            │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                    Security Hooks                         │  │
│   │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐   │  │
│   │  │pre-tool-use│  │post-tool-use│ │HookOTelEmitter   │   │  │
│   │  │ (security) │  │ (logging)  │  │(emit OTel events)│   │  │
│   │  └────────────┘  └────────────┘  └──────────────────┘   │  │
│   └───────────────────────────┬──────────────────────────────┘  │
│                               │                                  │
└───────────────────────────────┼──────────────────────────────────┘
                                │
                                ▼
                     ┌──────────────────┐
                     │  OTel Collector  │
                     │  (OTLP receiver) │
                     └────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │  Traces  │   │ Metrics  │   │   Logs   │
        │(Jaeger)  │   │(Prometheus│   │(Loki)    │
        └──────────┘   └──────────┘   └──────────┘
```

## Prerequisites

- Python 3.11+
- Claude CLI installed (`claude --version`)
- Docker (for OTel Collector)

## Quick Start

### 1. Install dependencies

```bash
cd examples/003-otel-first-agent
uv sync
```

### 2. Start OTel Collector (optional - for viewing telemetry)

```bash
docker run -d --name otel-collector \
  -p 4317:4317 -p 4318:4318 \
  otel/opentelemetry-collector-contrib:latest
```

### 3. Generate hooks

```bash
uv run python generate_hooks.py
```

This creates `.claude/hooks/handlers/` with OTel-enabled security hooks.

### 4. Run the agent

```bash
uv run python main.py "Create a hello world Python script"
```

## Files

- `main.py` - Entry point that runs ClaudeCLIRunner with OTel
- `generate_hooks.py` - Generates security hooks with OTel backend
- `.claude/hooks/handlers/` - Generated hook scripts

## Key Concepts

### OTelConfig

Configuration for Claude CLI's native OTel support:

```python
from agentic_otel import OTelConfig

config = OTelConfig(
    endpoint="http://localhost:4317",
    service_name="my-agent",
    resource_attributes={
        "workflow.id": "my-workflow",
        "phase.id": "implement",
    },
)
```

### ClaudeCLIRunner

Runs Claude CLI with OTel environment injection:

```python
from agentic_adapters.claude_cli import ClaudeCLIRunner

runner = ClaudeCLIRunner(otel_config=config)
result = await runner.run("Your task here")
```

### HookOTelEmitter

Emits OTel spans and events from hook scripts:

```python
from agentic_otel import OTelConfig, HookOTelEmitter

config = OTelConfig.from_env()  # Reads OTEL_* env vars
emitter = HookOTelEmitter(config)

# Emit a security decision
emitter.emit_security_event(
    tool_name="Bash",
    allowed=False,
    reason="Dangerous command blocked",
)
```

## OTel Signals

The example emits:

| Signal | Description |
|--------|-------------|
| **Traces** | Tool executions with timing |
| **Metrics** | Token usage, cost counters |
| **Events** | Security decisions, blocked commands |

## Comparison with Legacy

| Aspect | Legacy (JSONL) | OTel-First |
|--------|----------------|------------|
| Format | Custom JSONL files | Standard OTLP |
| Transport | File-based | gRPC/HTTP |
| Correlation | Manual | Automatic (trace context) |
| Visualization | Custom parsing | Jaeger, Grafana, etc. |
| Scalability | Limited | Distributed |

## Next Steps

- View traces in Jaeger: `http://localhost:16686`
- View metrics in Prometheus: `http://localhost:9090`
- Integrate with Grafana for dashboards
