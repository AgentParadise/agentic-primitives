# observability plugin

Full-spectrum agent observability — hooks **every** Claude Code lifecycle event and all git operations, emitting structured JSONL events via `agentic_events`. Designed to be composable with other plugins.

## What it does

Two independent sources of observability events, with strict ownership of event types:

| Source | Mechanism | Event types owned | Output channel |
|---|---|---|---|
| `observe.py` | Claude Code hooks (PreToolUse, PostToolUse, etc.) | `tool_execution_started/completed/failed`, `session_started/completed`, `user_prompt_submitted`, and all other Claude Code lifecycle events | **stdout** |
| git hooks | Real git hooks (`post-commit`, `pre-push`, etc.) | `git_commit`, `git_push`, `git_merge`, `git_rewrite` — exclusively | **stderr** |

**Critical invariant**: `observe.py` never emits git event types. Git hooks are the sole source of truth for `git_commit`/`git_push`/`git_merge`/`git_rewrite`. This ensures git events carry real post-operation metadata (SHA, files changed, token estimates) rather than inferred pre-operation intent.

### Why different output channels?

- **`observe.py` → stdout**: Claude Code captures Claude Code hook subprocess stdout and embeds it in the `hook_response` stream-json event. Consumers read it from there.
- **git hooks → stderr**: Git hooks run inside the Bash tool subprocess. Their output (stdout and stderr) is captured by Claude Code as the Bash tool result, then packaged in the `tool_result` content. Consumers scan `tool_result` content for embedded JSONL lines.

Both channels are consumed, just through different paths in the engine. Neither blocks execution — always exits 0.

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

Each emitted event is a single JSON line (stdout for Claude Code hook events, stderr for git hook events — see Architecture below):

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

Unlike the SDLC plugin's bash-based git hooks (which write raw JSONL to a file), these use `agentic_events.EventEmitter(output=sys.stderr)` for consistent structured output. Stderr is used (not stdout) because git hook output ends up as part of the Bash tool result — both channels get captured — but stderr is conventional for diagnostic/observability output and avoids any ambiguity.

## Architecture

```
SOURCE A — Claude Code lifecycle events
  hooks.json (14 events)
       │
       └─► observe.py (single dispatcher)
                │
                └─► agentic_events.EventEmitter(output=sys.stdout)
                         │
                         └─► stdout JSONL → captured in Claude Code hook_response stream-json
                                  │
                                  └─► engine reads from hook_response.output / .stderr fields

SOURCE B — Git operations (source of truth for git events)
  git hooks (post-commit, pre-push, post-merge, post-rewrite)
       │
       └─► post-commit / pre-push / ... (individual scripts)
                │
                └─► agentic_events.EventEmitter(output=sys.stderr)
                         │
                         └─► stderr → captured by Claude Code as Bash tool output
                                  │
                                  └─► engine scans tool_result content for embedded JSONL
```

One dispatch handler for Claude Code events, four focused scripts for git events. Zero blocking. No cross-emission between sources.

### Event type ownership (strict)

```
observe.py owns:      tool_execution_started, tool_execution_completed, tool_execution_failed,
                      session_started, session_completed, user_prompt_submitted,
                      permission_requested, system_notification, subagent_started,
                      subagent_stopped, agent_stopped, teammate_idle, task_completed,
                      context_compacted

git hooks own:        git_commit, git_push, git_merge, git_rewrite
```

These sets are mutually exclusive by design. `observe.py` must never emit git event types.
