# Workspace Plugin

Observability hooks for isolated agent workspaces. This plugin captures lifecycle events (session start/end, tool usage, compaction, stops) and emits structured JSONL events via the `agentic_events` library.

## What it does

- **Session lifecycle** — tracks session start, end, and compaction events
- **Tool observability** — logs post-tool-use results for audit and analytics
- **Notifications** — captures agent notification events
- **User prompts** — records user prompt submissions
- **Stop signals** — handles stop and subagent-stop events

## Hooks

| Hook | Handler | Description |
|------|---------|-------------|
| SessionStart | session-start.py | Emits session start event |
| SessionEnd | session-end.py | Emits session end event with summary |
| PostToolUse | post-tool-use.py | Records tool usage results |
| PreCompact | pre-compact.py | Captures context before compaction |
| Notification | notification.py | Logs notification events |
| Stop | stop.py | Handles agent stop signals |
| SubagentStop | subagent-stop.py | Handles subagent stop signals |
| UserPromptSubmit | user-prompt.py | Records user prompt submissions |

## Event Format

All events are emitted as JSONL to the workspace event log via `agentic_events`. See `lib/python/agentic_events/` for the event schema and emitter.
