# ADR-013: Hybrid Hook Architecture

**Status:** Superseded  
**Date:** 2025-11-24  
**Superseded By:** Self-logging hook architecture (2025-11-26)  
**Deciders:** Core Team  
**Related:** [ADR-006: Middleware-Based Hooks](./006-middleware-hooks.md)

> **Note:** This ADR describes the original hybrid architecture with a central `hooks-collector`. 
> This has been superseded by a simpler "self-logging" architecture where each hook logs its own 
> decisions directly to the analytics service. See `lib/python/agentic_analytics/` for the new approach.

## Context

We needed a hook architecture for agentic primitives that could handle both:

1. **Observability** - Track all agent interactions for analytics, debugging, and monitoring
2. **Control** - Block/modify specific operations for security and compliance

Initial designs explored two approaches:

### Approach A: Universal Collector Only

A single `hooks-collector` hook that:
- Registers for ALL events
- Routes through configurable middleware pipeline
- Handles both observability AND control

**Pros:**
- ✅ Single hook to maintain
- ✅ Unified configuration
- ✅ Comprehensive coverage

**Cons:**
- ❌ Every event triggers the full hook (even if no action needed)
- ❌ Security middleware must filter for relevant tools
- ❌ Mixed concerns (observability + control)
- ❌ Harder to reason about what runs when

### Approach B: Specialized Hooks Only

Multiple specialized hooks, each for a specific purpose:
- `bash-validator` - Only for Bash commands
- `file-security` - Only for file operations
- `prompt-filter` - Only for user prompts
- `analytics-collector` - Only for analytics

**Pros:**
- ✅ Targeted execution (only runs when needed)
- ✅ Clear separation of concerns
- ✅ Easy to enable/disable specific features

**Cons:**
- ❌ No comprehensive analytics (would need hooks for ALL 9 events)
- ❌ More hooks to maintain
- ❌ Potential gaps in coverage

## Decision

We chose **Approach C: Hybrid Architecture** - combining both patterns for optimal results.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  UNIVERSAL COLLECTOR (Observability)                │
│  • Hook: hooks-collector                            │
│  • Matcher: "*" (catches everything)                │
│  • Purpose: Analytics, logging, metrics             │
│  • Priority: Low (runs first, never blocks)         │
│  • Middleware: event_normalizer + event_publisher   │
│  • Coverage: All 9 Claude events                    │
└─────────────────────────────────────────────────────┘
                            +
┌─────────────────────────────────────────────────────┐
│  SPECIALIZED HOOKS (Control)                        │
│  • Hooks: bash-validator, file-security, etc.       │
│  • Matcher: Targeted (e.g., "Bash", "Read|Write")  │
│  • Purpose: Security, validation, blocking          │
│  • Priority: High (can block operations)            │
│  • Middleware: Minimal (focused on one task)        │
│  • Coverage: Specific events/tools only             │
└─────────────────────────────────────────────────────┘
                            =
              Composition over Choice
```

### How It Works

**1. Every event triggers universal collector:**
```json
{
  "PreToolUse": [
    {
      "matcher": "*",
      "hooks": [{"command": ".claude/hooks/core/hooks-collector.py"}]
    }
  ]
}
```

**2. Specific tools also trigger specialized hooks:**
```json
{
  "PreToolUse": [
    {"matcher": "*", "hooks": [{"command": ".../hooks-collector.py"}]},
    {"matcher": "Bash", "hooks": [{"command": ".../bash-validator.py"}]},
    {"matcher": "Read|Write|Edit|Delete", "hooks": [{"command": ".../file-security.py"}]}
  ]
}
```

**3. All matching hooks run in parallel:**
- Universal collector captures the event
- Specialized hooks validate/block if needed
- Agent proceeds only if all allow

### Example: Bash Command

```
User: "Delete all files with rm -rf logs/"
       ↓
Claude Code triggers PreToolUse with tool="Bash"
       ↓
  ┌────────────────────────────────────┐
  │ hooks-collector (matcher: "*")     │  ← Logs analytics
  │ bash-validator (matcher: "Bash")   │  ← Validates command
  └────────────────────────────────────┘
       ↓
bash-validator returns "block" + alternative
       ↓
Claude: "⚠️ That command is dangerous. Use 'rm -r logs/' instead."
```

### Benefits

#### 1. Complete Observability

**Universal collector sees everything:**
- Every tool use (PreToolUse, PostToolUse)
- Every user prompt (UserPromptSubmit)
- Every session (SessionStart, SessionEnd)
- Every stop (Stop, SubagentStop)
- Every compaction (PreCompact)
- Every notification (Notification)

**Result:** Comprehensive analytics with zero gaps.

#### 2. Targeted Control

**Specialized hooks only run when needed:**
- `bash-validator` only on Bash commands
- `file-security` only on file operations
- `prompt-filter` only on user prompts

**Result:** Minimal overhead, maximum relevance.

#### 3. Separation of Concerns

**Observability hooks:**
- Never block
- Never modify
- Always allow
- Focus: data collection

**Control hooks:**
- Can block
- Can modify
- Return decisions
- Focus: safety & compliance

**Result:** Clear responsibilities, easier to reason about.

#### 4. Composability

**Mix and match:**
- ✅ Universal only (observability)
- ✅ Specialized only (security)
- ✅ Both together (comprehensive)

**Result:** Flexible deployment options.

#### 5. Zero Overhead

**Parallel execution:**
- Hooks run simultaneously
- No sequential bottleneck
- Fast execution

**Result:** No performance penalty.

## Implementation

### Primitive Organization

```
primitives/v1/hooks/
├── core/                        # Universal hooks
│   └── hooks-collector/
│       ├── hooks-collector.hook.yaml
│       └── impl.python.py
└── security/                    # Specialized hooks
    ├── bash-validator/
    ├── file-security/
    └── prompt-filter/
```

### Agent Configuration

```
providers/agents/claude-code/
├── hooks-supported.yaml         # All 9 events defined
└── hooks-config/
    ├── hooks-collector.yaml     # Universal config
    ├── bash-validator.yaml      # Bash-specific config
    ├── file-security.yaml       # File-specific config
    └── prompt-filter.yaml       # Prompt-specific config
```

### Build Output

```
build/claude/hooks/
├── hooks.json                   # Combined registry
├── core/
│   └── hooks-collector.py
└── security/
    ├── bash-validator.py
    ├── file-security.py
    └── prompt-filter.py
```

### hooks.json Structure

```json
{
  "PreToolUse": [
    {
      "matcher": "*",
      "hooks": [{"command": ".claude/hooks/core/hooks-collector.py"}]
    },
    {
      "matcher": "Bash",
      "hooks": [{"command": ".claude/hooks/security/bash-validator.py"}]
    },
    {
      "matcher": "Read|Write|Edit|Delete",
      "hooks": [{"command": ".claude/hooks/security/file-security.py"}]
    }
  ],
  "UserPromptSubmit": [
    {
      "matcher": "*",
      "hooks": [{"command": ".claude/hooks/core/hooks-collector.py"}]
    },
    {
      "matcher": "*",
      "hooks": [{"command": ".claude/hooks/security/prompt-filter.py"}]
    }
  ],
  "PostToolUse": [
    {
      "matcher": "*",
      "hooks": [{"command": ".claude/hooks/core/hooks-collector.py"}]
    }
  ]
  // ... all other events with universal collector
}
```

## Consequences

### Positive

✅ **Best of both worlds** - Observability + Control

✅ **No gaps in analytics** - Universal collector sees everything

✅ **Efficient execution** - Specialized hooks only when needed

✅ **Clear architecture** - Separate concerns, easy to understand

✅ **Flexible deployment** - Install what you need

✅ **Extensible** - Easy to add new specialized hooks

✅ **Testable** - Each hook can be tested independently

✅ **Production-ready** - Analytics has 97.30% test coverage

### Negative

⚠️ **More hooks to maintain** - But each is simpler

⚠️ **Larger hooks.json** - But more readable (organized by event)

⚠️ **Potential for overlap** - Must coordinate between hooks

### Mitigation

**Coordination strategy:**
1. Universal collector never blocks (observability only)
2. Specialized hooks have clear responsibilities (one job each)
3. Each hook returns explicit decision (allow/block/skip)
4. Agent combines decisions (block wins, allow if all allow)

## Comparison with Alternatives

| Aspect | Universal Only | Specialized Only | Hybrid (Chosen) |
|--------|----------------|------------------|-----------------|
| **Analytics Coverage** | ✅ Complete | ❌ Gaps | ✅ Complete |
| **Targeted Security** | ⚠️ Filters needed | ✅ Native | ✅ Native |
| **Performance** | ⚠️ Runs on all events | ✅ Selective | ✅ Selective |
| **Maintenance** | ✅ Single hook | ⚠️ Many hooks | ⚠️ Multiple (simpler) |
| **Flexibility** | ❌ All or nothing | ✅ Mix & match | ✅ Mix & match |
| **Clarity** | ⚠️ Mixed concerns | ✅ Focused | ✅ Focused |

## Examples

### Example 1: Observability Only

```bash
# Install only universal collector
cp -r build/claude/hooks/core .claude/hooks/
cp build/claude/hooks/hooks.json .claude/hooks/
# (Edit hooks.json to remove specialized hooks)
```

**Result:**
- ✅ Complete analytics
- ✅ Zero blocking
- ✅ Minimal configuration

### Example 2: Security Only

```bash
# Install only specialized security hooks
cp -r build/claude/hooks/security .claude/hooks/
cp build/claude/hooks/hooks.json .claude/hooks/
# (Edit hooks.json to remove universal collector)
```

**Result:**
- ✅ Targeted security
- ✅ Minimal overhead
- ❌ No comprehensive analytics

### Example 3: Full Stack (Recommended)

```bash
# Install everything
cp -r build/claude/hooks .claude/
```

**Result:**
- ✅ Complete analytics
- ✅ Full security
- ✅ Production-ready

## Future Enhancements

### 1. Additional Specialized Hooks

Potential additions:
- `network-validator` - Validate API calls
- `resource-limiter` - Prevent resource exhaustion
- `compliance-checker` - Enforce organizational policies
- `cost-tracker` - Track token usage and costs

### 2. Hook Coordination

Advanced coordination:
- Hooks can communicate via shared state
- Precedence rules (security > observability)
- Conditional execution (only if X allows)

### 3. Dynamic Configuration

Runtime configuration:
- Enable/disable hooks via config file
- Adjust matchers dynamically
- Hot-reload configurations

### 4. Hook Marketplace

Community contributions:
- Share custom hooks
- Version and distribute
- Discover new patterns

## References

- [ADR-006: Middleware-Based Hooks](./006-middleware-hooks.md) - Foundation for hook system
- [Claude Hooks Documentation](https://docs.claude.com/en/docs/claude-code/hooks) - Agent hooks specification
- [INSTALLATION.md](../../INSTALLATION.md) - Installation guide
- [USAGE_EXAMPLES.md](../../USAGE_EXAMPLES.md) - Real-world usage patterns

## Revision History

- **2025-11-24**: Initial version - Hybrid architecture decision


