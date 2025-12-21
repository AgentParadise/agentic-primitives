---
title: "ADR-027: Provider-Based Workspace Images"
status: accepted
created: 2025-12-17
updated: 2025-12-17
author: Neural
---

# ADR-027: Provider-Based Workspace Images

## Status

**Accepted**

- Created: 2025-12-17
- Author(s): Neural
- Related: ADR-026 (OTel-First Observability), ADR-025 (Universal Agent Integration Layer)

## Context

The agentic-primitives library needs to provide workspace images for running AI agents in isolated containers. Currently:

1. **AEF defines its own image** (`aef-workspace-claude`) in `docker/workspace/Dockerfile`
2. **agentic_isolation defaults** to `python:3.12-slim` which has no agent runtime
3. **No standard image** exists for Claude CLI with OTel support

### Problem

Different agent runtimes have different requirements:

| Runtime | Requirements | OTel Support |
|---------|--------------|--------------|
| **Claude CLI** | Node.js, `@anthropic-ai/claude-code` | ✅ Native |
| **Claude SDK** | Python, `claude-agent-sdk` | ❌ None |
| **OpenAI** | Python, `openai` | ❌ Manual |

Without provider-specific images as primitives:
- Each platform (AEF, custom apps) rebuilds the same images
- Security hardening is inconsistent
- OTel configuration differs between implementations
- Hook installation varies

## Decision

Define **provider-based workspace images** as primitives, with each provider having:

1. **Dockerfile** - Security-hardened image with agent runtime
2. **Manifest** - Build configuration and defaults
3. **Hooks** - Pre-installed from `primitives/v1/hooks/`

### Directory Structure

```
providers/
├── claude-cli/                 # Claude CLI (OTel-enabled)
│   ├── manifest.yaml           # Build configuration
│   ├── Dockerfile              # Image definition
│   └── README.md               # Provider docs
├── claude-sdk/                 # Claude Agent SDK
│   ├── manifest.yaml
│   └── Dockerfile
├── base/                       # Minimal secure base
│   └── Dockerfile
└── README.md                   # Provider overview
```

### Manifest Schema

```yaml
name: claude-cli
version: "1.0.0"
description: Claude CLI workspace with native OTel support

image:
  dockerfile: ./Dockerfile
  tag: agentic-workspace-claude-cli
  base: node:22-slim

hooks:
  source: ../../primitives/v1/hooks/
  handlers:
    - pre-tool-use
    - post-tool-use
    - user-prompt
  validators:
    - security/bash
    - security/file
    - prompt/pii

defaults:
  allowed_tools:
    - Bash
    - Read
    - Write
    - Glob
    - Grep
    - LS
  otel_enabled: true
  security:
    remove_setuid: true
    read_only_root: false  # Claude CLI needs writes
    non_root_user: true
```

### Image Security Requirements

All provider images MUST include:

1. **Non-root user** - Run as `agent` user (UID 1000)
2. **Setuid removal** - `find / -perm /6000 -exec chmod a-s {} \;`
3. **Minimal packages** - Only what's needed for the runtime
4. **No secrets** - Credentials injected at runtime
5. **Hooks pre-installed** - From `primitives/v1/hooks/`
6. **OTel packages** - `agentic-otel`, `agentic-security`

### Build Process

```bash
# Build a provider image
python scripts/build-provider.py --provider claude-cli

# This:
# 1. Reads providers/claude-cli/manifest.yaml
# 2. Copies hooks from primitives/v1/hooks/
# 3. Builds Docker image
# 4. Tags as agentic-workspace-claude-cli:v1.0.0
# 5. Outputs to build/claude-cli/
```

## Alternatives Considered

### Alternative 1: Single Universal Image

**Description**: One image with all runtimes (Node.js + Python + Claude CLI + SDK)

**Pros**:
- Simpler to maintain
- One image for everything

**Cons**:
- Large image size (2GB+)
- Unnecessary dependencies for each use case
- Security surface area increased

**Reason for rejection**: Violates principle of minimal images.

### Alternative 2: Runtime Installation at Container Start

**Description**: Use base image and install runtime on container start

**Pros**:
- Smaller base images
- Always latest runtime

**Cons**:
- Slow container startup (npm install takes seconds)
- Network required at start
- Version inconsistency

**Reason for rejection**: Startup time is critical for agent execution.

### Alternative 3: Keep Images in Platform (AEF)

**Description**: Each platform defines its own images

**Pros**:
- Platform-specific customization
- No primitives changes

**Cons**:
- Duplication across platforms
- Inconsistent security
- Each platform reinvents hooks integration

**Reason for rejection**: Primitives should encode best practices.

## Consequences

### Positive

✅ **Consistent security** - All images follow same hardening

✅ **OTel built-in** - Claude CLI image has native OTel support

✅ **Hooks pre-installed** - No setup at runtime

✅ **Reusable** - Any platform can use primitive images

✅ **Versioned** - Images tagged with primitives version

### Negative

⚠️ **Build complexity** - Need build system for images

⚠️ **Registry required** - For distribution (or local builds)

⚠️ **Version coupling** - Image version tied to primitives version

### Mitigations

1. **Build complexity** - Simple Python script, CI automation
2. **Registry** - Document local build, optionally publish to GHCR
3. **Version coupling** - Semantic versioning, clear upgrade path

## Implementation Notes

### Claude CLI Image Features

```dockerfile
FROM node:22-slim

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# Install Python for hooks
RUN apt-get install -y python3 python3-pip

# Install agentic packages
RUN pip install agentic-otel agentic-security

# Copy hooks
COPY primitives/v1/hooks/ /opt/agentic/hooks/

# Security hardening
RUN useradd -m agent
RUN find / -perm /6000 -exec chmod a-s {} \; 2>/dev/null || true

USER agent
WORKDIR /workspace
```

### Using the Image

```python
from agentic_isolation import IsolatedWorkspace, WorkspaceConfig

config = WorkspaceConfig(
    provider="docker",
    image="agentic-workspace-claude-cli:latest",
    # ... tool config, otel config
)

async with IsolatedWorkspace.create(config) as ws:
    result = await ws.execute("claude --print 'Hello'")
```

## References

- [ADR-026: OTel-First Observability](026-otel-first-observability.md)
- [ADR-025: Universal Agent Integration Layer](025-universal-agent-integration-layer.md)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Claude CLI Documentation](https://docs.anthropic.com/en/docs/claude-code)
