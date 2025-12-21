# Agentic Playground

Interactive playground for testing agentic-primitives with live OpenTelemetry events.

## Overview

The playground provides a simple way to:

1. **Run agents** in isolated Docker containers
2. **See live OTel events** as the agent executes
3. **Configure scenarios** via YAML files
4. **Validate OTel integration** with otel-tui visualization

## Quick Start

```bash
# Install dependencies
cd playground
uv sync

# Run a simple task
uv run python run.py "Create a hello world script"

# Run with live OTel events displayed inline
uv run python run.py "Create a hello world script" --live

# Run with otel-tui visualization (requires Docker)
docker compose up -d
uv run python run.py "Create a hello world script" --tui

# Use a specific scenario
uv run python run.py "Review this code" --scenario security-audit

# Use local provider (no Docker)
uv run python run.py "List files" --local
```

## Scenarios

Scenarios are YAML files in `scenarios/` that configure:

- **Headless options**: Allowed/disallowed tools, output format, system prompt
- **Isolation options**: Provider (docker/local), image, timeout, memory

Example scenario (`scenarios/default.yaml`):

```yaml
name: Default
description: Standard agent execution with common tools

headless:
  allowed_tools:
    - Bash
    - Read
    - Write
    - Glob
    - Grep
  output_format: stream-json

isolation:
  provider: docker
  timeout: 300
  memory_mb: 2048
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Playground CLI                            │
│  run.py --live --scenario default "Create hello world"          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Executor                             │
│  - Loads scenario config                                        │
│  - Creates IsolatedWorkspace with OTel env vars                 │
│  - Runs Claude CLI inside container                             │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────────┐
│   Isolated Container    │     │        OTLP Receiver            │
│   - Claude CLI          │────▶│   - Receives OTel signals       │
│   - OTel env vars       │     │   - Parses spans/metrics/logs   │
│   - Security hooks      │     │   - Emits to Rich display       │
└─────────────────────────┘     └─────────────────────────────────┘
                                              │
                                              ▼
                                ┌─────────────────────────────────┐
                                │        Rich Display             │
                                │   - Live event table            │
                                │   - Token usage summary         │
                                │   - Execution timeline          │
                                └─────────────────────────────────┘
```

## Directory Structure

```
playground/
├── pyproject.toml          # Dependencies and configuration
├── run.py                  # CLI entry point
├── src/
│   ├── __init__.py
│   ├── config.py           # Scenario loading
│   ├── executor.py         # Agent execution wrapper
│   ├── display.py          # Rich terminal display
│   └── receiver.py         # OTLP gRPC receiver
├── scenarios/
│   ├── default.yaml        # Default scenario
│   ├── security-audit.yaml # Security-focused scenario
│   └── code-review.yaml    # Code review scenario
├── docker-compose.yaml     # otel-tui for --tui mode
└── README.md
```

## Options

| Flag | Description |
|------|-------------|
| `--live` | Show inline OTel events in terminal |
| `--tui` | Use otel-tui for visualization (requires Docker) |
| `--local` | Use local provider instead of Docker |
| `--scenario NAME` | Use a specific scenario from `scenarios/` |
| `--verbose` | Enable verbose output |

## Requirements

- Python 3.11+
- Docker (for container isolation and otel-tui)
- Claude CLI installed (in container or locally)
- uv package manager

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check --fix .

# Type check
uv run mypy src/
```

## Related Documentation

- [ADR-026: OTel-First Observability](../docs/adrs/026-otel-first-observability.md)
- [Claude CLI Headless Mode](https://docs.anthropic.com/en/docs/claude-code/headless)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
