# observability plugin

Full-spectrum agent observability — hooks every Claude Code lifecycle event and all git operations, emitting structured JSONL events via `agentic_events`.

## Event sources and ownership

Two independent sources, with **strict, non-overlapping ownership** of event types:

| Source | Mechanism | Owns these event types | Output channel |
|---|---|---|---|
| `observe.py` | Claude Code hooks (PreToolUse, PostToolUse, …) | `tool_execution_started`, `tool_execution_completed`, `tool_execution_failed`, `session_started`, `session_completed`, `user_prompt_submitted`, `permission_requested`, `system_notification`, `subagent_started`, `subagent_stopped`, `agent_stopped`, `teammate_idle`, `task_completed`, `context_compacted` | **stdout** |
| git hooks | Real git hooks (`post-commit`, `post-merge`, …) | `git_commit`, `git_push`, `git_merge`, `git_rewrite`, `git_checkout` — exclusively | **stderr** |

**Critical invariant: `observe.py` must never emit git event types. Git hooks are the sole source of truth for all `git_*` events.**

This separation ensures git events carry real post-operation metadata (actual SHA, files changed, token estimates) rather than intent inferred before the operation runs.

## Output channel rationale

### `observe.py` → stdout
Claude Code captures the stdout of each hook subprocess and embeds it in the `hook_response` stream-json event. The engine reads it from there.

### git hooks → stderr
Git hooks run as subprocesses triggered by git — they are **not** children of the Bash tool process. Their stderr flows into the docker exec stream, which the adapter merges into the stdout pipe via `stderr=asyncio.subprocess.STDOUT`. The engine reads every line of that merged stream and stores any line containing `event_type` as an observation.

**Do not switch git hooks to stdout.** Git hook stdout is surfaced to the user in the terminal (e.g. printed after `git commit`). Stderr is the conventional channel for diagnostic/observability output and avoids polluting the user-visible output.

## Claude Code lifecycle hooks

| Hook event | Claude Code version | Event type emitted |
|---|---|---|
| `SessionStart` | 1.0+ | `session_started` |
| `SessionEnd` | 1.0+ | `session_completed` |
| `UserPromptSubmit` | 1.0+ | `user_prompt_submitted` |
| `PreToolUse` | 1.0+ | `tool_execution_started` |
| `PostToolUse` | 1.0+ | `tool_execution_completed` |
| `PostToolUseFailure` | 1.1+ | `tool_execution_failed` |
| `PermissionRequest` | 1.0+ | `permission_requested` |
| `Notification` | 1.0+ | `system_notification` |
| `SubagentStart` | 1.1+ | `subagent_started` |
| `SubagentStop` | 1.0+ | `subagent_stopped` |
| `Stop` | 1.0+ | `agent_stopped` |
| `TeammateIdle` | 1.2+ | `teammate_idle` |
| `TaskCompleted` | 1.2+ | `task_completed` |
| `PreCompact` | 1.0+ | `context_compacted` |

Events from hooks not available in the installed Claude Code version are silently absent.

## Git hooks

| Git hook | Fires on | Event type emitted | Key fields |
|---|---|---|---|
| `post-commit` | `git commit` | `git_commit` | sha, branch, message, files\_changed, insertions, deletions, estimated tokens |
| `pre-push` | `git push` | `git_push` | remote, branch, commit count |
| `post-merge` | `git merge`, `git pull` (merge strategy) | `git_merge` | branch, merge sha, commits\_merged, is\_squash |
| `post-rewrite` | `git rebase`, `git commit --amend` | `git_rewrite` | rewrite\_type ("rebase"/"amend"), old→new sha mappings, commits\_folded |
| `post-checkout` | `git checkout`, `git switch`, `git clone` | `git_checkout` | branch, prev\_branch, sha, is\_clone |

> **`git pull` note:** git has no `post-pull` hook. Pull = fetch + merge/rebase. The fetch is invisible to hooks. The merge fires `post-merge` → `git_merge`; a rebase pull fires `post-rewrite` → `git_rewrite`. Both are covered.

All git hooks always exit 0 — observability never blocks a git operation.

### Installing git hooks

Git hooks are installed globally in the workspace container via `entrypoint.sh`:

```sh
git config --global core.hooksPath "${GIT_HOOKS_DIR}"
# → /opt/agentic/plugins/observability/hooks/git
```

This applies to every repo cloned or created inside the container without any per-repo setup.

For local development outside the container:

```bash
# Install globally (all repos on this machine)
python plugins/observability/hooks/git/install.py --global

# Install to current repo only
python plugins/observability/hooks/git/install.py

# Uninstall
python plugins/observability/hooks/git/install.py --uninstall
```

## Event schema

Every emitted event is a single JSON line:

```json
{
  "event_type": "git_commit",
  "timestamp": "2026-02-19T23:44:46+00:00",
  "session_id": "7d421b2d-bcd9-4f53-8421-a68fb9d2941f",
  "provider": "claude",
  "context": {
    "operation": "commit",
    "sha": "42c33b6685c582646b822dea5b8bfef59c505207",
    "branch": "feat/my-feature",
    "message": "feat: add observability hooks"
  },
  "metadata": {
    "repo": "my-repo",
    "files_changed": 4,
    "insertions": 572,
    "deletions": 0,
    "author": "agent[bot]",
    "estimated_tokens_added": 3429,
    "estimated_tokens_removed": 0
  }
}
```

Fields:
- `event_type` — canonical type string (see tables above)
- `timestamp` — ISO 8601 UTC
- `session_id` — from `CLAUDE_SESSION_ID` env var (set by the adapter at `docker exec` time)
- `provider` — always `"claude"`
- `context` — core event fields (operation type, identifiers)
- `metadata` — supplementary data (stats, estimates, secondary fields)

Consumers merge `{**context, **metadata}` to get all fields in a flat dict.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  SOURCE A — Claude Code lifecycle events                    │
│                                                             │
│  hooks.json (14 hook types)                                 │
│       │                                                     │
│       └─► observe.py                                        │
│                │                                            │
│                └─► EventEmitter(output=sys.stdout)          │
│                         │                                   │
│                         └─► stdout JSONL                    │
│                                  │                          │
│                    embedded in hook_response stream-json    │
│                                  │                          │
│                         engine reads → stores event         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SOURCE B — Git operations (sole source of truth for git_*) │
│                                                             │
│  git hooks (triggered by git itself, not by Claude Code)    │
│    post-commit / pre-push / post-merge /                    │
│    post-rewrite / post-checkout                             │
│       │                                                     │
│       └─► individual hook scripts                           │
│                │                                            │
│                └─► EventEmitter(output=sys.stderr)          │
│                         │                                   │
│                         └─► stderr JSONL                    │
│                                  │                          │
│          merged by adapter.py stderr=asyncio.STDOUT         │
│                                  │                          │
│          engine readline() → parse_jsonl_line()             │
│                                  │                          │
│                         stores git_* event in DB            │
└─────────────────────────────────────────────────────────────┘
```

## Event type ownership (exhaustive)

```
observe.py owns (Claude Code hook events):
    session_started         session_completed       user_prompt_submitted
    tool_execution_started  tool_execution_completed  tool_execution_failed
    permission_requested    system_notification     context_compacted
    subagent_started        subagent_stopped        agent_stopped
    teammate_idle           task_completed

git hooks own (git operation events):
    git_commit      ← post-commit
    git_push        ← pre-push
    git_merge       ← post-merge   (also fires on git pull with merge strategy)
    git_rewrite     ← post-rewrite (git rebase and git commit --amend)
    git_checkout    ← post-checkout (git checkout, git switch, git clone)
```

These sets are **mutually exclusive**. Adding a git event type to `observe.py`, or a Claude Code event type to a git hook, is a violation of this contract.
