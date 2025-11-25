# Universal Hooks Collector

**Status:** Generic Primitive (v1.1.0)  
**Architecture:** Agent-Configured  
**Category:** Core Hook Primitive

A generic hook primitive that captures all agent events and routes them through a configurable middleware pipeline.

## Purpose

The hooks-collector is a **universal, reusable primitive** that:
- Works with ANY agent provider (Claude Code, Cursor, LangGraph, etc.)
- Registers for ALL events supported by the agent
- Routes events through an agent-specific middleware pipeline
- Supports analytics, observability, safety checks, and custom processing

## Architecture: Primitives are Generic, Agents Configure Them

This primitive is **intentionally generic** - it contains NO agent-specific configuration.

**Where Configuration Lives:**
```
primitives/v1/hooks/core/hooks-collector/  ← Generic implementation (this)
providers/agents/{agent}/hooks-config/      ← Agent-specific config
```

**Example:**
- Same primitive works for Claude Code, Cursor, and LangGraph
- Each agent configures it differently via `hooks-config/hooks-collector.yaml`
- Claude might enable analytics + observability
- Cursor might enable only safety checks
- LangGraph might enable custom workflow middleware

## Key Features

- **Universal Event Capture:** Automatically registers for all hook events supported by the agent provider
- **Agent-Configured Middleware:** Each agent defines its own middleware pipeline
- **Priority-Based Execution:** Middleware runs in configurable order
- **Event Filtering:** Middleware can be triggered by specific events or all events
- **Fail-Safe:** Hook errors never block the agent
- **Reusable:** Same implementation across all agents
- **Hybrid Architecture:** Works alongside specialized hooks for complete coverage

## Hybrid Architecture

This hook is part of a **hybrid hook architecture**:

### Universal Collector (This Hook)
- **Purpose:** Observability (analytics, logging, metrics)
- **Matcher:** `*` (catches all events)
- **Priority:** Low (never blocks)
- **Middleware:** Configurable pipeline (normalizer + publisher)
- **Coverage:** ALL agent events

### Specialized Hooks (Companions)
- **Purpose:** Control (security, validation, blocking)
- **Matcher:** Targeted (e.g., "Bash", "Read|Write|Edit|Delete")
- **Priority:** High (can block operations)
- **Middleware:** Minimal (focused on one task)
- **Coverage:** Specific events/tools only

### Why Both?

**Composition over Choice:**
```
Universal Collector + Specialized Hooks = Complete Coverage + Targeted Control
```

**Example:** PreToolUse with Bash command
```
┌──────────────────────────────────────┐
│ hooks-collector (matcher: "*")       │  ← Logs analytics
│ bash-validator (matcher: "Bash")     │  ← Validates command
└──────────────────────────────────────┘
         Both run in parallel
```

**See:** [ADR-013: Hybrid Hook Architecture](../../../../../docs/adrs/013-hybrid-hook-architecture.md)

## How It Works

### 1. Build Time

```bash
agentic-p build --agent claude-code --hook hooks-collector --output build/claude
```

Build system:
1. Loads agent's supported events from `providers/agents/claude-code/hooks-supported.yaml`
2. Loads agent's hook config from `providers/agents/claude-code/hooks-config/hooks-collector.yaml`
3. Validates middleware events against supported events
4. Generates `hooks.json` with ALL supported events (e.g., 9 for Claude)
5. Generates Python wrapper with agent-specific middleware config embedded
6. Organizes by category: `build/claude/hooks/core/hooks-collector.py`

**Build Output Structure:**
```
build/claude/hooks/
├── hooks.json                   ← Hook registry
└── core/                        ← Category-based organization
    ├── hooks-collector.py       ← Python wrapper
    └── hooks-collector.impl.py  ← Implementation
```

**Installation:**
```bash
cp -r build/claude/hooks .claude/
```

**Result:** `.claude/hooks/core/hooks-collector.py` ready to use!

### 2. Runtime

When an agent event occurs:
1. Event data arrives via stdin (JSON)
2. Wrapper executes `impl.python.py` with agent-specific middleware config
3. Orchestrator loads middleware configuration
4. Filters middleware by event type
5. Executes enabled middleware in priority order
6. Returns decision (allow/deny) to agent

## Configuration

### Primitive Configuration (Generic)

`hooks-collector.hook.yaml` contains only generic metadata:
- Hook ID and category
- Execution defaults
- Provider implementations
- NO middleware configuration

### Agent Configuration (Specific)

`providers/agents/claude-code/hooks-config/hooks-collector.yaml` contains:
- Reference to this primitive
- Agent-specific middleware pipeline
- Event filtering per middleware
- Execution overrides

**Example:**
```yaml
agent: claude-code
hook_id: hooks-collector

primitive:
  id: hooks-collector
  path: "../../../../primitives/v1/hooks/core/hooks-collector"
  impl_file: "impl.python.py"

middleware:
  - id: "analytics-normalizer"
    path: "../../../../services/analytics/middleware/event_normalizer.py"
    type: analytics
    enabled: true
    events: ["*"]  # All Claude events
    priority: 10
```

## Middleware Types

The hooks-collector supports various middleware types:

### Analytics
- Event normalization
- Data publishing
- Usage tracking

### Safety
- Dangerous command detection
- Permission validation
- Content filtering

### Observability
- Metrics collection
- Performance monitoring
- Logging

### Custom
- User-defined workflows
- Business logic
- Integration hooks

## Usage

### Building for Claude Code

```bash
# Build with hooks-collector
agentic-p build \
  --agent claude-code \
  --hook hooks-collector \
  --output build/claude

# Verify hooks.json has all 9 events
jq 'keys' build/claude/hooks/hooks.json
```

### Building for Other Agents

```bash
# Same command, different agent
agentic-p build \
  --agent cursor \
  --hook hooks-collector \
  --output build/cursor

# Different middleware, same primitive
agentic-p build \
  --agent langgraph \
  --hook hooks-collector \
  --output build/langgraph
```

## Testing

```bash
# Test the hook with sample event
echo '{"event_type": "PreToolUse", "tool": "read_file"}' | \
  ./build/claude/hooks/scripts/hooks-collector.py

# Expected output (JSON):
# {"action": "allow", "metadata": {...}}
```

## Development

### Adding New Middleware

1. Create middleware Python script
2. Add to agent's `hooks-config/hooks-collector.yaml`
3. Rebuild hooks
4. Test with sample events

### Customizing Per Agent

1. Edit `providers/agents/{agent}/hooks-config/hooks-collector.yaml`
2. Enable/disable middleware
3. Adjust priorities
4. Filter events
5. Rebuild

## Files

- `hooks-collector.hook.yaml` - Generic primitive metadata
- `impl.python.py` - Generic Python orchestrator
- `README.md` - This file

## Agent Configurations

Each agent that uses this primitive has its own configuration:
- `providers/agents/claude-code/hooks-config/hooks-collector.yaml`
- `providers/agents/cursor/hooks-config/hooks-collector.yaml`
- `providers/agents/langgraph/hooks-config/hooks-collector.yaml`

## Version History

### v1.1.0 (2025-11-23)
- Refactored to agent-specific middleware configuration
- Middleware moved from primitive to agent config
- Improved reusability across agents

### v1.0.0 (2025-11-23)
- Initial universal hooks collector
- Pluggable middleware architecture
- Multi-event support

## See Also

- [Agent Hook Configuration Guide](../../../../../providers/agents/claude-code/hooks-config/README.md)
- [Middleware Development](../../../../../services/analytics/README.md)
- [Provider Architecture](../../../../../docs/providers.md)
