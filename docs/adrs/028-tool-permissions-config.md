---
title: "ADR-028: Configuration-Driven Tool Permissions"
status: accepted
created: 2025-12-17
updated: 2025-12-17
author: Neural
---

# ADR-028: Configuration-Driven Tool Permissions

## Status

**Accepted**

- Created: 2025-12-17
- Author(s): Neural
- Related: ADR-027 (Provider Workspace Images), ADR-026 (OTel-First Observability)

## Context

Different agent executions require different tool permissions:

| Use Case | Allowed Tools | Security Level |
|----------|---------------|----------------|
| **Code Review** | Read, Grep, Glob | High (read-only) |
| **Development** | Bash, Read, Write, Glob | Medium |
| **Security Audit** | Read, Grep | Very High |
| **Full Access** | All tools | Low (trusted) |

Currently, tool permissions are either:
1. **Hardcoded in images** - No runtime flexibility
2. **Passed via CLI flags** - Limited to what Claude CLI supports
3. **Defined in hooks** - Requires regenerating hooks

### Problem

We need a way to:
1. Configure tool permissions **per workspace** at creation time
2. Enforce permissions at **multiple layers** (CLI + hooks + container)
3. Pass configuration to hooks **without regenerating** them
4. Support **fine-grained control** (specific Bash commands, file paths)

## Decision

Adopt a **configuration-driven tool permissions** model with:

1. **WorkspaceToolConfig** - Dataclass for tool permissions
2. **Environment variable injection** - Config passed to container
3. **Hooks read config at runtime** - No regeneration needed
4. **Layered enforcement** - CLI flags + hooks + container isolation

### WorkspaceToolConfig

```python
@dataclass
class WorkspaceToolConfig:
    """Tool permissions for a workspace."""

    # Tool allowlist/blocklist
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Bash", "Read", "Write", "Glob", "Grep", "LS"
    ])
    disallowed_tools: list[str] = field(default_factory=list)

    # Fine-grained Bash control
    blocked_bash_patterns: list[tuple[str, str]] = field(default_factory=lambda: [
        ("rm", "-rf /"),
        ("rm", "-rf ~"),
        ("curl", "*"),
        ("wget", "*"),
    ])

    # File access control
    blocked_paths: list[str] = field(default_factory=lambda: [
        "/etc/passwd",
        "/etc/shadow",
        "~/.ssh/*",
        "~/.aws/*",
        "~/.config/gh/*",
    ])

    # Network control
    allow_network: bool = True
    allowed_hosts: list[str] = field(default_factory=lambda: [
        "api.anthropic.com",
        "github.com",
        "api.github.com",
        "pypi.org",
        "registry.npmjs.org",
    ])

    def to_env(self) -> dict[str, str]:
        """Convert to environment variables for container injection."""
        return {
            "AGENTIC_ALLOWED_TOOLS": ",".join(self.allowed_tools),
            "AGENTIC_DISALLOWED_TOOLS": ",".join(self.disallowed_tools),
            "AGENTIC_BLOCKED_BASH": json.dumps(self.blocked_bash_patterns),
            "AGENTIC_BLOCKED_PATHS": ",".join(self.blocked_paths),
            "AGENTIC_ALLOW_NETWORK": str(self.allow_network).lower(),
            "AGENTIC_ALLOWED_HOSTS": ",".join(self.allowed_hosts),
        }

    def to_cli_args(self) -> list[str]:
        """Convert to Claude CLI arguments."""
        args = []
        if self.allowed_tools:
            args.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.disallowed_tools:
            args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])
        return args
```

### Layered Enforcement

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Tool Execution Request                            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 1: Claude CLI Native                                              │
│  --allowedTools, --disallowedTools                                       │
│  ✓ Prevents Claude from suggesting disallowed tools                     │
│  ✓ Fast, no hook overhead                                                │
│  ✗ Cannot inspect tool input content                                     │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 2: Pre-Tool-Use Hook                                              │
│  primitives/v1/hooks/handlers/pre-tool-use.py                           │
│  ✓ Inspects tool input (command content, file paths)                    │
│  ✓ Uses SecurityPolicy from agentic_security                            │
│  ✓ Reads config from AGENTIC_* env vars                                  │
│  ✓ Emits OTel events for blocked tools                                   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 3: Container Isolation                                            │
│  agentic_isolation providers                                             │
│  ✓ Network isolation (--network=none or egress proxy)                   │
│  ✓ Filesystem isolation (read-only mounts, blocked paths)               │
│  ✓ Resource limits (memory, CPU, PIDs)                                   │
│  ✓ No setuid binaries                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Hook Config Reading

Hooks read configuration from environment at runtime:

```python
# In primitives/v1/hooks/handlers/pre-tool-use.py

import os
import json

def get_tool_config() -> dict:
    """Read tool configuration from environment."""
    return {
        "allowed_tools": os.getenv("AGENTIC_ALLOWED_TOOLS", "").split(","),
        "disallowed_tools": os.getenv("AGENTIC_DISALLOWED_TOOLS", "").split(","),
        "blocked_bash": json.loads(os.getenv("AGENTIC_BLOCKED_BASH", "[]")),
        "blocked_paths": os.getenv("AGENTIC_BLOCKED_PATHS", "").split(","),
    }

def validate_tool(tool_name: str, tool_input: dict) -> dict:
    config = get_tool_config()

    # Check tool allowlist
    if config["allowed_tools"] and tool_name not in config["allowed_tools"]:
        return {"decision": "block", "reason": f"Tool {tool_name} not in allowlist"}

    # Check tool blocklist
    if tool_name in config["disallowed_tools"]:
        return {"decision": "block", "reason": f"Tool {tool_name} is blocked"}

    # Delegate to SecurityPolicy for content validation
    policy = SecurityPolicy.from_config(config)
    result = policy.validate(tool_name, tool_input)

    if not result.safe:
        return {"decision": "block", "reason": result.reason}

    return {"decision": "allow"}
```

### Usage Example

```python
from agentic_runner import AgentRunner
from agentic_isolation import WorkspaceToolConfig
from agentic_otel import OTelConfig

# Read-only agent for code review
tool_config = WorkspaceToolConfig(
    allowed_tools=["Read", "Grep", "Glob", "LS"],
    disallowed_tools=["Bash", "Write", "Edit"],
    allow_network=False,
)

runner = AgentRunner(
    backend="cli",
    tool_config=tool_config,
    otel_config=OTelConfig(endpoint="http://collector:4317"),
)

result = await runner.run("Review this codebase for security issues")
```

## Alternatives Considered

### Alternative 1: Config File in Workspace

**Description**: Write `.agentic/config.yaml` to workspace before execution

**Pros**:
- Human-readable
- Can include complex nested config

**Cons**:
- Requires file write before execution
- Hook must read file (slower than env)
- File might be modified by agent

**Reason for partial adoption**: Support both env vars (primary) and config file (optional).

### Alternative 2: Regenerate Hooks Per Execution

**Description**: Generate new hooks with embedded config for each workspace

**Pros**:
- Config is baked into hooks
- No runtime config reading

**Cons**:
- Slow - hook generation for every workspace
- Code duplication (generator templates)
- Can't update config without regenerating

**Reason for rejection**: Runtime config is more flexible.

### Alternative 3: MCP-Based Config

**Description**: Use MCP server to provide tool config

**Pros**:
- Dynamic config updates
- Centralized management

**Cons**:
- MCP dependency
- Network required
- Complex for simple use cases

**Reason for rejection**: Overkill for initial implementation.

## Consequences

### Positive

✅ **Per-workspace flexibility** - Different permissions per execution

✅ **No hook regeneration** - Config at runtime

✅ **Layered security** - Multiple enforcement points

✅ **Observable** - All decisions logged via OTel

✅ **Portable** - Works with any container runtime

### Negative

⚠️ **Environment parsing** - Hooks must parse env vars

⚠️ **Config complexity** - Multiple config sources (env, file)

⚠️ **Debugging** - Must check multiple layers for blocks

### Mitigations

1. **Environment parsing** - Use standard JSON for complex values
2. **Config complexity** - Clear precedence (env > file > defaults)
3. **Debugging** - OTel events include which layer blocked

## Implementation Notes

### Preset Configurations

```python
# Presets for common use cases
class ToolPresets:
    READ_ONLY = WorkspaceToolConfig(
        allowed_tools=["Read", "Grep", "Glob", "LS"],
        disallowed_tools=["Bash", "Write", "Edit"],
    )

    DEVELOPMENT = WorkspaceToolConfig(
        allowed_tools=["Bash", "Read", "Write", "Glob", "Grep", "LS"],
        blocked_bash_patterns=[("rm", "-rf /"), ("curl", "*")],
    )

    SECURITY_AUDIT = WorkspaceToolConfig(
        allowed_tools=["Read", "Grep"],
        disallowed_tools=["Bash", "Write", "Edit", "WebFetch"],
        allow_network=False,
    )

    FULL_ACCESS = WorkspaceToolConfig(
        allowed_tools=[],  # Empty = all allowed
        blocked_bash_patterns=[],
        blocked_paths=[],
    )
```

### OTel Events for Decisions

```python
# Emitted by pre-tool-use hook
{
    "name": "agentic.tool.decision",
    "attributes": {
        "tool.name": "Bash",
        "tool.decision": "block",
        "tool.decision.reason": "Command matches blocked pattern: curl *",
        "tool.decision.layer": "hook",
        "tool.decision.config_source": "env",
    }
}
```

## References

- [ADR-027: Provider Workspace Images](027-provider-workspace-images.md)
- [ADR-026: OTel-First Observability](026-otel-first-observability.md)
- [Claude CLI Headless Options](https://docs.anthropic.com/en/docs/claude-code/headless)
- [agentic_security Package](../../../lib/python/agentic_security/)
