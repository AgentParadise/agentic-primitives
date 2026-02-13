# Workspace Provider Images

Pre-configured Docker images for running AI agents in isolated environments.

## Available Providers

| Provider | Description | OTel Support |
|----------|-------------|--------------|
| `claude-cli` | Claude CLI with native OpenTelemetry | ✅ Native |
| `base` | Minimal secure base (no agent) | N/A |

## Building Images

Use the build script to create workspace images:

```bash
# Build Claude CLI workspace
uv run scripts/build-provider.py claude-cli

# With custom tag
uv run scripts/build-provider.py claude-cli --tag myregistry/workspace:v1.0

# Without Docker cache
uv run scripts/build-provider.py claude-cli --no-cache

# Stage files only (for debugging)
uv run scripts/build-provider.py claude-cli --stage-only
```

Or use just:

```bash
just build-provider claude-cli
```

## How It Works

The build process:

1. **Reads manifest** - `providers/workspaces/<provider>/manifest.yaml`
2. **Stages build context** - Creates `build/<provider>/` with:
   - Dockerfile
   - Plugins (from `plugins/`, per manifest `plugins.include`)
   - Python wheels (agentic_events)
3. **Builds Docker image** - Self-contained, reproducible

```
providers/workspaces/claude-cli/
├── Dockerfile          # Image definition
└── manifest.yaml       # Build configuration

        │
        ▼ build-provider.py

build/claude-cli/       # Staged context
├── Dockerfile
├── plugins/
│   ├── sdlc/           # Self-contained plugin
│   └── workspace/      # Self-contained plugin
└── packages/
    └── *.whl
```

## Manifest Schema

```yaml
name: claude-cli
version: "1.0.0"
description: Claude CLI with native OTel

image:
  dockerfile: ./Dockerfile
  tag: agentic-workspace-claude-cli

plugins:
  include:
    - sdlc
    - workspace

defaults:
  allowed_tools: [Read, Write, Bash]
  otel_enabled: true

security:
  non_root: true
  no_setuid: true
```

## Adding a New Provider

1. Create directory: `providers/workspaces/<name>/`
2. Add `Dockerfile` with your agent runtime
3. Add `manifest.yaml` with configuration
4. Build: `uv run scripts/build-provider.py <name>`

## Security

All workspace images include:

- **Non-root user** (`agent:1000`)
- **No setuid/setgid binaries**
- **Read-only plugins directory**
- **Health checks**

See [ADR-027: Provider-Based Workspace Images](../../docs/adrs/027-provider-workspace-images.md)

## Modern Tooling

Images use:

- **bun** - Fast Node.js runtime + package manager
- **uv** - Fast Python package manager
