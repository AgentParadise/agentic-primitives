# ADR-025: Universal Agent Integration Layer

```yaml
---
status: proposed
created: 2025-12-16
updated: 2025-12-16
deciders: System Architect
consulted: AEF Team
informed: All Stakeholders
---
```

## Context

As AI agent platforms scale from single-agent development to orchestrating thousands of concurrent agents, we face several challenges:

1. **Security**: Dangerous operations (rm -rf /, reading secrets) must be blocked consistently
2. **Observability**: Token usage, tool calls, and costs must be captured for analysis
3. **Isolation**: Agents need secure, reproducible execution environments
4. **Runtime Diversity**: Different runtimes (Claude CLI, Claude SDK, OpenAI) have different integration patterns

Currently, each platform (like AEF) implements these concerns from scratch, leading to:
- Duplicated code across projects
- Inconsistent security policies
- Ad-hoc observability that's hard to query
- Tight coupling to specific runtimes

### Current State

`agentic-primitives` already provides:
- `agentic_hooks`: Event emission with HookClient and pluggable backends
- `agentic_analytics`: Analytics normalization and publishing
- `agentic_logging`: Centralized logging configuration
- `agentic_settings`: Configuration discovery

What's missing:
- Consolidated security package
- Workspace isolation abstraction
- Runtime adapters (CLI vs SDK)
- Unified configuration

## Decision

Evolve `agentic-primitives` into a **universal agent integration layer** with four core packages and runtime adapters.

### Package Architecture

```
agentic-primitives/
├── lib/python/
│   ├── agentic_hooks/       # ✅ EXISTS - Event emission
│   ├── agentic_security/    # 🆕 NEW - Security policies
│   ├── agentic_isolation/   # 🆕 NEW - Workspace abstraction
│   ├── agentic_agent/       # 🆕 NEW - Instrumented agent
│   └── adapters/            # 🆕 NEW - Runtime adapters
│       ├── claude_cli/      # .claude/hooks generator
│       └── claude_sdk/      # ClaudeAgentOptions builder
```

### Core Packages

#### 1. `agentic_security` - Security Policies

Consolidates security validators into a declarative policy system:

```python
from agentic_security import SecurityPolicy

policy = SecurityPolicy(
    blocked_paths=["/etc/passwd", "~/.ssh/"],
    blocked_commands=["rm -rf /", "curl | bash"],
    blocked_content_patterns=["AKIA[0-9A-Z]{16}"],  # AWS keys
)

result = policy.validate(tool_name="Bash", tool_input={"command": "rm -rf /"})
# result.safe = False, result.reason = "Dangerous command: rm -rf /"
```

#### 2. `agentic_isolation` - Workspace Abstraction

Provides secure, isolated execution environments:

```python
from agentic_isolation import IsolatedWorkspace

async with IsolatedWorkspace.create(
    provider="docker",
    image="aef-workspace:latest",
    secrets={"GITHUB_TOKEN": token},
) as workspace:
    await workspace.execute("echo hello")
```

Providers:
- `DockerProvider`: Docker containers (production)
- `E2BProvider`: E2B sandboxes (cloud)
- `LocalProvider`: Local filesystem (development)

#### 3. `agentic_agent` - Instrumented Agent

Wraps agent runtimes with observability:

```python
from agentic_agent import InstrumentedAgent

async with InstrumentedAgent(
    hook_client=hook_client,
    security_policy=policy,
) as agent:
    result = await agent.run("Create a file")
    print(f"Tokens: {result.metrics.total_tokens}")
```

#### 4. Runtime Adapters

**Claude CLI Adapter** - Generates `.claude/hooks/*.py` files:
```python
from agentic_primitives.adapters.claude_cli import generate_hooks

generate_hooks(
    output_dir=".claude/hooks",
    security_policy=policy,
    observability_backend="http://localhost:8080",
)
```

**Claude SDK Adapter** - Builds `ClaudeAgentOptions`:
```python
from agentic_primitives.adapters.claude_sdk import create_options

options = create_options(
    model="claude-sonnet-4-20250514",
    security_policy=policy,
    hook_client=hook_client,
)
```

### Unified Configuration

Single configuration object that works across all runtimes:

```python
from agentic_primitives import AgentConfig

config = AgentConfig(
    security=SecurityPolicy(...),
    observability=ObservabilityConfig(backend="timescaledb"),
    isolation=IsolationConfig(provider="docker"),
)

# Same config, any runtime
config.generate_cli_hooks()          # For Claude CLI
options = config.to_claude_sdk()     # For Claude SDK
```

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        APPLICATIONS                                      │
│   AEF Platform  │  Custom Apps  │  SaaS Products  │  Future Platforms   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AGENTIC-PRIMITIVES (Breakout Board)                  │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Hooks     │  │  Security   │  │  Isolation  │  │   Agent     │    │
│  │ HookClient  │  │ Validators  │  │  Workspace  │  │ Instrumented│    │
│  │ Backends    │  │ Policies    │  │  Providers  │  │ Metrics     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                     Runtime Adapters                              │ │
│  │   claude_cli (hooks/*.py)  │  claude_sdk (options)  │  openai    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                  Observability Backends                           │ │
│  │   JSONL  │  HTTP  │  TimescaleDB  │  OpenTelemetry  │  Custom    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT RUNTIMES                                    │
│   Claude CLI  │  Claude SDK  │  OpenAI Assistants  │  Future Runtimes   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Rationale

### Why Consolidate Security?

- **Consistency**: Same patterns blocked everywhere
- **Testability**: Unit test validators in isolation
- **Maintainability**: Single source of truth for dangerous patterns
- **Composability**: Mix validators via policy configuration

### Why Workspace Abstraction?

- **Portability**: Same agent code works in Docker, E2B, or locally
- **Security**: Secrets injected at workspace level, not agent level
- **Reproducibility**: Consistent environments across runs
- **Scalability**: Swap providers without changing agent code

### Why Runtime Adapters?

- **Decoupling**: Agent code independent of runtime
- **Testing**: Test with LocalProvider, deploy with DockerProvider
- **Future-Proofing**: Easy to add OpenAI, Gemini adapters

### Why Unified Configuration?

- **DRY**: One config file for all environments
- **Declarative**: Security, observability, isolation in YAML
- **Auditable**: Version control configuration

## Consequences

### Positive

✅ **Security-by-default**: All integrations inherit security policies
✅ **Observability-by-default**: All integrations emit events via HookClient
✅ **Portable**: Same agent code works across runtimes and environments
✅ **Testable**: Each package tested in isolation with mocks
✅ **Extensible**: Add backends/providers without changing core
✅ **Reduced duplication**: Platforms use primitives, not custom code

### Negative

⚠️ **Learning curve**: New abstraction layer to understand
⚠️ **Dependency**: Platforms depend on agentic-primitives releases
⚠️ **Abstraction cost**: Some runtime-specific features may not fit

### Mitigations

1. **Documentation**: Comprehensive guides for each integration pattern
2. **Semantic versioning**: Clear compatibility guarantees
3. **Escape hatches**: Raw access to underlying APIs when needed

## Implementation Plan

| Phase | Description | Duration |
|-------|-------------|----------|
| 1 | Extract `agentic_security` from validators | 1 day |
| 2 | Promote `InstrumentedAgent` to package | 1 day |
| 3 | Create `agentic_isolation` with Docker provider | 2 days |
| 4 | Create runtime adapters (CLI, SDK) | 2 days |
| 5 | Add `AgentConfig` unified configuration | 1 day |
| 6 | Add TimescaleDB backend | 1 day |
| 7 | Integrate with AEF | 1 day |
| 8 | Documentation and examples | 1 day |

## Success Criteria

1. `pip install agentic-primitives` works with optional extras
2. Security validators block dangerous operations in all runtimes
3. Events captured in all backends (JSONL, HTTP, TimescaleDB)
4. Docker workspaces created and destroyed reliably
5. AEF uses primitives, removing duplicated code
6. All packages have >80% test coverage

## Related Decisions

- **ADR-006**: Middleware-based hook system (foundation)
- **ADR-017**: Hook client library (HookClient design)
- **ADR-018 (AEF)**: Commands vs observations event architecture
- **ADR-026 (AEF)**: TimescaleDB observability storage
- **ADR-027 (AEF)**: SDK wrapper architecture

## References

- [Claude Hooks Documentation](https://docs.anthropic.com/claude-code/hooks)
- [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/)
- [E2B Sandbox](https://e2b.dev/)
- [Express.js Middleware](https://expressjs.com/en/guide/using-middleware.html) (inspiration)

---

**Status**: Proposed
**Last Updated**: 2025-12-16
