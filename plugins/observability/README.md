# observability plugin

Full-spectrum agent observability — hooks **every** Claude Code lifecycle event and emits structured JSONL events via `agentic_events`. Designed to be composable with other plugins.

## What it does

A single handler (`observe.py`) receives all 14 Claude Code hook events and dispatches them through `agentic_events.EventEmitter` as structured JSONL on stderr. It never blocks execution (always exits 0).

## Hook-to-Claude-Code-version compatibility

| Hook Event | Claude Code Version | Event Type Emitted |
|---|---|---|
| SessionStart | 1.0+ | `session_started` |
| SessionEnd | 1.0+ | `session_completed` |
| UserPromptSubmit | 1.0+ | `user_prompt_submitted` |
| PreToolUse | 1.0+ | `tool_execution_started` |
| PostToolUse | 1.0+ | `tool_execution_completed` |
| PostToolUseFailure | 1.1+ | `tool_execution_failed` |
| PermissionRequest | 1.0+ | `permission_requested` |
| Notification | 1.0+ | `system_notification` |
| SubagentStart | 1.1+ | `subagent_started` |
| SubagentStop | 1.0+ | `subagent_stopped` |
| Stop | 1.0+ | `agent_stopped` |
| TeammateIdle | 1.2+ | `teammate_idle` |
| TaskCompleted | 1.2+ | `task_completed` |
| PreCompact | 1.0+ | `context_compacted` |

> **Note:** Hook availability depends on your Claude Code version. Events from newer versions are silently ignored by older Claude Code installations.

## Usage

Install this plugin alongside other plugins in your `.claude/plugins/` directory. It is purely additive — it observes and logs but never modifies behavior or blocks tool execution.

```
.claude/plugins/observability/  →  this plugin
.claude/plugins/workspace/      →  your workspace plugin
```

Both plugins can coexist. The observability plugin provides comprehensive event coverage while workspace handlers can add domain-specific logic.

## Event schema

Each emitted event is a single JSON line on stderr:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2026-02-18T22:00:00+00:00",
  "session_id": "session-abc123",
  "provider": "claude",
  "context": {
    "tool_name": "Bash",
    "tool_use_id": "toolu_xyz",
    "input_preview": "git status"
  }
}
```

Fields:
- `event_type` — one of the event types from the table above
- `timestamp` — ISO 8601 UTC timestamp
- `session_id` — Claude session identifier
- `provider` — always `"claude"`
- `context` — event-specific payload (varies by event type)
- `metadata` — optional additional data (when provided by the hook)

## Git hooks

In addition to Claude Code lifecycle hooks, this plugin includes git hooks that emit events for git operations:

| Git Hook | Event Type Emitted |
|---|---|
| `post-commit` | `git_commit` (with sha, branch, files changed, insertions/deletions, token estimates) |
| `post-merge` | `git_merge` (with branch, merge sha, commits merged, squash detection) |
| `post-rewrite` | `git_rewrite` (with rewrite type, old→new sha mappings) |
| `pre-push` | `git_push` (with remote, branch, commit count, commit range) |

### Installing git hooks

```bash
# Install to current repo
python plugins/observability/hooks/git/install.py

# Install globally (all repos)
python plugins/observability/hooks/git/install.py --global

# Uninstall
python plugins/observability/hooks/git/install.py --uninstall
```

The installer backs up any existing hooks before overwriting and restores them on uninstall.

Unlike the SDLC plugin's bash-based git hooks (which write raw JSONL to a file), these use `agentic_events.EventEmitter` for consistent structured output on stderr.

## Architecture

```
hooks.json (14 events)  →  observe.py (single dispatcher)  →  agentic_events.EventEmitter  →  stderr JSONL
git hooks (4 hooks)      →  post-commit/merge/rewrite/pre-push  →  agentic_events.EventEmitter  →  stderr JSONL
```

One dispatch handler for Claude Code events, four focused scripts for git events. Zero blocking.
