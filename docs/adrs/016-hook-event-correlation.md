---
title: "ADR-016: Provider-Agnostic Hook Event Correlation"
status: accepted
created: 2025-11-26
updated: 2025-11-26
author: AI Agent (Claude)
---

# ADR-016: Provider-Agnostic Hook Event Correlation

## Status

**Accepted** (2025-11-26)

## Context

The agentic-primitives system captures two distinct event streams:

1. **Agent Events**: Captured by instrumented agent wrappers (`InstrumentedAgent`)
   - `agent_session_start`, `agent_session_end`
   - `agent_interaction` (token usage, duration)
   - `tool_call` (tool name, input, output)

2. **Hook Events**: Captured by security/analytics hooks via `agentic_analytics`
   - `hook_decision` (allow/block/warn decisions)
   - Contains: `hook_id`, `decision`, `reason`, `metadata`

### The Problem

These event streams are **disconnected**. When reviewing analytics:

```jsonl
// Agent event - we see a tool was called
{"event_type": "tool_call", "tool_name": "Bash", "tool_input": {"command": "ls"}}

// Hook event - we see a hook decision, but no link to which tool_call
{"hook_id": "bash-validator", "decision": "allow", "tool_name": "Bash"}
```

**Missing audit trail**: We cannot answer "Which hooks evaluated tool_call X and what did they decide?"

### Root Causes

1. **No correlation key**: Tool calls and hook decisions don't share a unique identifier
2. **Different event schemas**: Agent events use `event_type`, hooks use `hook_id`
3. **Path/CWD issues**: Hooks may write to different locations than the agent
4. **Missing implementations**: `analytics-collector.impl.py` doesn't exist

### Requirements

1. **Provider-Agnostic**: Must work with Claude, OpenAI, future providers
2. **Correlation**: Link tool calls to hook decisions
3. **Audit Trail**: Complete trace from prompt → tool → hook → result
4. **Backward Compatible**: Don't break existing event consumers
5. **Self-Logging**: Hooks log their own decisions (established pattern)

## Decision

We will implement **correlation via `tool_use_id`** with unified event output to a single JSONL file.

### Correlation Key: `tool_use_id`

Every tool invocation gets a unique identifier:

| Provider | Source of `tool_use_id` |
|----------|------------------------|
| Claude Code | Provided in hook stdin: `hook_event.tool_use_id` |
| Claude Agent SDK | From `ToolUseBlock.id` |
| OpenAI | Generate UUID, pass via `TOOL_USE_ID` env var |
| Generic | Generate UUID per tool call |

### Event Schema Updates

#### Tool Call Event (Agent)

```jsonc
{
  "timestamp": "2025-11-26T12:00:00Z",
  "event_type": "tool_call",
  "session_id": "sess-abc123",
  "tool_use_id": "toolu_01ABC123",  // NEW: Correlation key
  "data": {
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "blocked": false,
    "block_reason": null
  }
}
```

#### Hook Decision Event (Hook)

```jsonc
{
  "timestamp": "2025-11-26T12:00:00Z",
  "event_type": "hook_decision",  // Unified event type
  "session_id": "sess-abc123",
  "tool_use_id": "toolu_01ABC123",  // Same correlation key
  "handler": "pre-tool-use",
  "tool_name": "Bash",
  "decision": "allow",
  "reason": null,
  "validators_run": ["security.bash"],
  "metadata": {
    "risk_level": "low"
  },
  // NEW: Audit trail - link to Claude Code conversation
  "audit": {
    "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
    "cwd": "/Users/project",
    "permission_mode": "default"
  }
}
```

### Audit Trail Fields

Claude Code provides additional context that enables full audit traceability:

| Field | Description | Use Case |
|-------|-------------|----------|
| `audit.transcript_path` | Path to Claude Code's conversation log | Read full context of what triggered the hook |
| `audit.cwd` | Current working directory | Understand file path context |
| `audit.permission_mode` | Security mode (`default`, `plan`, `bypassPermissions`) | Audit security posture |

These fields are captured when provided by Claude Code and omitted for other providers.

### Unified Output Path

All events write to the same file: `.agentic/analytics/events.jsonl`

- Agent wrapper writes agent events
- Hooks write hook_decision events via `agentic_analytics.AnalyticsClient`
- Single source of truth for analytics

### Hook Implementation Pattern

Hooks extract `tool_use_id` from Claude's stdin JSON and include it in logged decisions:

```python
# In hook implementation
hook_event = json.loads(sys.stdin.read())
tool_use_id = hook_event.get("tool_use_id", str(uuid.uuid4()))

# Log decision with correlation key
analytics.log(HookDecision(
    hook_id="bash-validator",
    event_type=hook_event.get("hook_event_name"),
    decision="allow",
    session_id=hook_event.get("session_id"),
    tool_use_id=tool_use_id,  # NEW
    metadata={...}
))
```

### Provider Adapter Pattern

Each provider adapter knows how to:
1. Generate/extract `tool_use_id`
2. Pass it to hooks (via stdin JSON or env var)
3. Include it in agent events

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Provider                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Claude    │  │   OpenAI    │  │   Generic   │         │
│  │   Adapter   │  │   Adapter   │  │   Adapter   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┴────────────────┘                 │
│                          │                                  │
│                          ▼                                  │
│              ┌─────────────────────┐                        │
│              │  tool_use_id        │                        │
│              │  (correlation key)  │                        │
│              └──────────┬──────────┘                        │
│                         │                                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
          ▼                               ▼
┌─────────────────┐             ┌─────────────────┐
│   Agent Event   │             │   Hook Event    │
│   (tool_call)   │             │ (hook_decision) │
│                 │             │                 │
│ tool_use_id: X  │             │ tool_use_id: X  │
└────────┬────────┘             └────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  events.jsonl       │
              │  (unified output)   │
              └─────────────────────┘
```

## Alternatives Considered

### Alternative 1: Embed Hook Decisions in Tool Call Events

**Description**: Agent wrapper captures hook stdout and embeds decisions in tool_call events.

```jsonc
{
  "event_type": "tool_call",
  "data": {
    "tool_name": "Bash",
    "hooks_evaluated": [
      {"hook_id": "bash-validator", "decision": "allow"}
    ]
  }
}
```

**Pros**:
- Single event per tool call
- No correlation needed
- Easy to analyze

**Cons**:
- Requires agent wrapper to capture hook output
- Provider-specific implementation
- Tight coupling between agent and hooks
- Hooks lose independence

**Reason for rejection**: Violates separation of concerns. Hooks should log independently.

### Alternative 2: Timestamp-Based Correlation

**Description**: Correlate events by matching timestamps within a window.

**Pros**:
- No schema changes
- Works with existing events

**Cons**:
- Unreliable (clock skew, overlapping calls)
- Cannot distinguish concurrent tool calls
- Fragile in high-throughput scenarios

**Reason for rejection**: Too unreliable for audit trail requirements.

### Alternative 3: Separate Event Files

**Description**: Agent events in `agent-events.jsonl`, hook events in `hook-events.jsonl`.

**Pros**:
- Clear separation
- Independent file management

**Cons**:
- Requires merging for analysis
- More files to manage
- Correlation still needed

**Reason for rejection**: Adds complexity without solving correlation problem.

## Consequences

### Positive Consequences

✅ **Complete Audit Trail**: Every tool call linked to hook decisions

✅ **Provider Agnostic**: Works with any provider via adapter pattern

✅ **Backward Compatible**: New fields are additive

✅ **Self-Logging Preserved**: Hooks remain independent

✅ **Single Output File**: Easy to analyze and query

✅ **Standard Correlation Key**: `tool_use_id` is already in Claude's protocol

### Negative Consequences

⚠️ **Schema Update Required**: Add `tool_use_id` to HookDecision model

⚠️ **Hook Updates Needed**: All hooks must extract and log `tool_use_id`

⚠️ **Agent Wrapper Updates**: Must include `tool_use_id` in tool_call events

### Mitigations

1. **Schema Update**: Add optional `tool_use_id` field with default fallback to UUID
2. **Hook Updates**: Update hook templates, rebuild existing hooks
3. **Agent Wrapper**: Simple change to extract ID from SDK responses

## Implementation Plan

### Phase 1: Schema Updates
1. Update `HookDecision` model to include `tool_use_id: str | None`
2. Update `AnalyticsClient` to handle new field
3. Update JSON schema

### Phase 2: Hook Updates
1. Create `analytics-collector.impl.py` (missing file)
2. Update security hooks to extract `tool_use_id`
3. Rebuild hooks with `agentic-p build`

### Phase 3: Agent Wrapper Updates
1. Update `InstrumentedAgent` to include `tool_use_id` in tool_call events
2. Extract ID from `ToolUseBlock` in Claude SDK

### Phase 4: Testing
1. Run scenarios and verify correlation
2. Validate complete audit trail
3. Test with multiple providers

## Success Criteria

1. ✅ Every `tool_call` event has a `tool_use_id`
2. ✅ Every `hook_decision` event has matching `tool_use_id`
3. ✅ Can query: "Show all events for tool_use_id X"
4. ✅ Works with Claude Code, Claude Agent SDK
5. ✅ No breaking changes to existing consumers

## Related Decisions

- **ADR-006**: Middleware-Based Hooks (foundation)
- **ADR-011**: Analytics Middleware (event schema)
- **ADR-013**: Hybrid Hook Architecture (self-logging pattern)
- **ADR-014**: Centralized Logging (superseded, informs approach)

## References

- [Claude Hooks Documentation](https://code.claude.com/docs/en/hooks) - `tool_use_id` in hook input
- [OpenTelemetry Trace Context](https://www.w3.org/TR/trace-context/) - Inspiration for correlation


