# Git Observability Hooks

Git hooks that emit observability events for tracking developer workflows and agent-assisted coding sessions.

## Overview

These hooks capture git operations and emit JSONL events to `.agentic/analytics/events.jsonl`. This enables:

- **Session Analytics**: Track commits, branches, and merges per coding session
- **Token Efficiency**: Measure tokens added/removed vs tokens used by AI
- **Code Velocity**: Monitor code reaching stable branches
- **Workflow Patterns**: Analyze development patterns over time

## Installation

### Single Repository

```bash
# Navigate to your repo
cd /path/to/your/repo

# Run the installer (Python 3.8+ required)
python /path/to/primitives/v1/hooks/git/install.py
```

### Global (All Repositories)

```bash
# Install globally
python /path/to/primitives/v1/hooks/git/install.py --global
```

### Uninstall

```bash
# Remove from current repo
python /path/to/primitives/v1/hooks/git/install.py --uninstall

# Remove global hooks
python /path/to/primitives/v1/hooks/git/install.py --global --uninstall
```

### Windows

The installer is cross-platform and works on Windows, macOS, and Linux:

```powershell
# PowerShell
python C:\path\to\primitives\v1\hooks\git\install.py
```

## Hooks Included

| Hook | Event Type | Description |
|------|------------|-------------|
| `post-commit` | `git_commit` | Tracks commits with files changed, insertions/deletions, and token estimates |
| `post-checkout` | `git_branch_created` / `git_branch_switched` | Tracks branch creation and switches |
| `post-merge` | `git_merge_completed` | Tracks merges, especially to stable branches (main, master, etc.) |
| `post-rewrite` | `git_commits_rewritten` | Tracks rebases and amends |
| `pre-push` | `git_push_started` | Tracks push operations |

## Event Schema

### git_commit

```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_commit",
  "session_id": "abc123",
  "commit_hash": "a1b2c3d4...",
  "commit_message": "feat: add user authentication",
  "author": "Developer Name",
  "branch": "feat/auth",
  "files_changed": 5,
  "insertions": 120,
  "deletions": 30,
  "estimated_tokens_added": 450,
  "estimated_tokens_removed": 112
}
```

### git_branch_created / git_branch_switched

```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_branch_created",
  "session_id": "abc123",
  "branch": "feat/new-feature",
  "prev_ref": "abc123...",
  "new_ref": "def456..."
}
```

### git_merge_completed

```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_merge_completed",
  "session_id": "abc123",
  "target_branch": "main",
  "merged_ref": "abc123...",
  "is_stable_branch": true,
  "commits_merged": 3
}
```

### git_commits_rewritten

```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_commits_rewritten",
  "session_id": "abc123",
  "branch": "feat/auth",
  "rewrite_type": "rebase",
  "commits_rewritten": 5
}
```

### git_push_started

```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_push_started",
  "session_id": "abc123",
  "remote": "origin",
  "branch": "feat/auth",
  "commits_to_push": 3
}
```

## Configuration

### Analytics Path

Set `ANALYTICS_PATH` environment variable to customize the output location:

```bash
export ANALYTICS_PATH="/path/to/custom/events.jsonl"
```

Default: `.agentic/analytics/events.jsonl`

### Session ID

The hooks use `CLAUDE_SESSION_ID` or `AEF_SESSION_ID` environment variables to correlate git events with coding sessions. If neither is set, `"unknown"` is used.

## Token Estimation

Token estimates use a simple `characters / 4` approximation, which is reasonably accurate for most code. For more precise estimates, post-process the events with a tokenizer like `tiktoken`.

## Integration with AEF Collector

These events are designed to work with the AEF Collector, which:

1. Watches the JSONL file for new events
2. Converts them to `CollectedEvent` types
3. Streams them to the observability dashboard
4. Stores them for historical analysis

## Troubleshooting

### Hooks not firing

1. Check if hooks are installed: `ls -la .git/hooks/`
2. Verify hooks are executable: `chmod +x .git/hooks/*`
3. Check for global hooks override: `git config core.hooksPath`

### Events not appearing

1. Check the analytics file exists: `cat .agentic/analytics/events.jsonl`
2. Verify write permissions to the directory
3. Check for errors in hook output: `git commit -v` (verbose mode)

### Backup hooks

If you had existing hooks, they're backed up as `*.bak`. To restore:

```bash
cd .git/hooks
mv post-commit.bak post-commit
```
