# agentic-events

Simple JSONL event emission for AI agents. **Zero dependencies.**

## Overview

This package provides a lightweight event emission system for AI agent hooks:

- **EventEmitter**: Emit structured events to stdout as JSONL
- **EventType**: Standard event types (tool execution, security decisions, etc.)
- **BatchBuffer**: Buffer events for batch processing (used by AEF)

## Installation

```bash
pip install agentic-events
```

## Quick Start

```python
from agentic_events import EventEmitter, EventType

# Create emitter for a session
emitter = EventEmitter(session_id="session-123", provider="claude")

# Emit tool execution events
emitter.tool_started("Bash", "toolu_abc", "git status")
# ... tool executes ...
emitter.tool_completed("Bash", "toolu_abc", success=True, duration_ms=150)

# Emit security decisions
emitter.security_decision("Bash", "block", "Dangerous command: rm -rf /")
```

## Event Types

| Event Type | Description |
|------------|-------------|
| `session_started` | Session begins |
| `session_completed` | Session ends |
| `tool_execution_started` | Tool about to execute |
| `tool_execution_completed` | Tool finished |
| `security_decision` | Security check result |
| `agent_stopped` | Agent stopped |
| `subagent_stopped` | Subagent stopped |
| `context_compacted` | Context window compacted |
| `system_notification` | System notification |
| `user_prompt_submitted` | User submitted prompt |
| `permission_requested` | Permission dialog shown |

## Output Format

Events are emitted as JSON lines to stdout:

```json
{"event_type": "tool_execution_started", "timestamp": "2025-12-17T10:00:00Z", "session_id": "session-123", "provider": "claude", "context": {"tool_name": "Bash", "tool_use_id": "toolu_abc", "input_preview": "git status"}}
```

## Design Principles

1. **Zero dependencies** - No external packages required
2. **Simple** - Just emit JSON to stdout
3. **Scalable** - Designed for 10,000+ concurrent agents
4. **Standard** - Uses JSONL format, easy to parse

## Related

- [Analytics Event Reference](../../docs/analytics-event-reference.md)
- [ADR-029: Simplified Event System](../../docs/adrs/029-simplified-event-system.md)
