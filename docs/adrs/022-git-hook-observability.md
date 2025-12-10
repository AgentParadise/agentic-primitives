---
title: "ADR-022: Git Hook Observability Architecture"
status: accepted
created: 2024-12-09
updated: 2024-12-09
author: Agent
---

# ADR-022: Git Hook Observability Architecture

## Status

**Accepted**

- Created: 2024-12-09
- Updated: 2024-12-09
- Author(s): Agent

## Context

Developer analytics and agent observability require tracking git operations to understand:

1. **Token Efficiency**: How many tokens are consumed vs. how much code is committed?
2. **Code Velocity**: How quickly does code reach stable branches (main, staging)?
3. **Development Patterns**: Branch creation frequency, merge patterns, rebase usage
4. **Session Correlation**: Which git operations occurred during which agent session?

Currently, Claude Code hooks capture tool usage and session events, but git operations are invisible. When an agent makes 10 commits in a session, we have no visibility into the actual code changes or their size.

**Constraints:**
- Must work in local, Docker, and E2B environments
- Must not require external services for basic operation
- Must follow the same event pattern as Claude Code hooks (JSONL)
- Must be cross-platform (Windows, macOS, Linux)

## Decision

We will implement git hooks that emit JSONL observability events to the same analytics file used by Claude Code hooks (`.agentic/analytics/events.jsonl`).

**Components:**

1. **Git Hooks** (`primitives/v1/hooks/git/`):
   - `post-commit` - Emits `git_commit` with token estimates
   - `post-checkout` - Emits `git_branch_created` or `git_branch_switched`
   - `post-merge` - Emits `git_merge_completed`
   - `post-rewrite` - Emits `git_commits_rewritten`
   - `pre-push` - Emits `git_push_started`

2. **Token Estimation**: Use `chars/4` approximation for quick estimates without external dependencies

3. **Cross-Platform Installer**: Python script (`install.py`) that works on all platforms

**Event Schema** (example for `git_commit`):
```json
{
  "timestamp": "2024-12-09T10:30:00Z",
  "event_type": "git_commit",
  "session_id": "abc123",
  "commit_hash": "a1b2c3d...",
  "commit_message": "feat: add user auth",
  "author": "Developer",
  "branch": "feat/auth",
  "files_changed": 5,
  "insertions": 120,
  "deletions": 30,
  "estimated_tokens_added": 450,
  "estimated_tokens_removed": 112
}
```

## Alternatives Considered

### Alternative 1: Server-Side Webhooks

**Description**: Use GitHub/GitLab webhooks to capture git events server-side

**Pros**:
- No local installation required
- Works across all contributors automatically
- More reliable event delivery

**Cons**:
- Requires external service dependency
- Doesn't work for local-only commits
- Adds latency to analytics pipeline
- Can't access local session context (session_id)

**Reason for rejection**: Violates constraint of working without external services

---

### Alternative 2: Git Commit Message Parsing

**Description**: Parse commit history retroactively to extract metrics

**Pros**:
- No hooks installation needed
- Works with existing history

**Cons**:
- Loses real-time correlation with sessions
- Can't capture branch switches, merges in progress
- Post-hoc analysis only

**Reason for rejection**: Need real-time event correlation with agent sessions

---

### Alternative 3: IDE Integration (VSCode Extension)

**Description**: Build VSCode extension that monitors git operations

**Pros**:
- Rich context about developer actions
- Can capture UI interactions

**Cons**:
- IDE-specific (not portable)
- Agent sessions often run in terminal, not IDE
- More complex implementation

**Reason for rejection**: Agents often run headless; need IDE-agnostic solution

## Consequences

### Positive Consequences

- **Unified Event Stream**: Git events flow through same pipeline as Claude Code hooks
- **Session Correlation**: Git operations can be linked to agent sessions via `session_id`
- **Token Efficiency Metrics**: Can calculate "code committed / tokens used" ratio
- **No Dependencies**: Works immediately after hook installation

### Negative Consequences

- **Installation Required**: Users must run `install.py` to enable hooks
- **Approximate Tokens**: `chars/4` is an estimate, not exact tokenization
- **Bash Hooks**: The actual hooks are bash scripts (not cross-platform), but installer handles this

### Neutral Consequences

- Hooks are opt-in per repository or global
- Events can be ignored if not consumed by collector

## Implementation Notes

**Files Created:**
- `primitives/v1/hooks/git/post-commit` - Bash hook
- `primitives/v1/hooks/git/post-checkout` - Bash hook
- `primitives/v1/hooks/git/post-merge` - Bash hook
- `primitives/v1/hooks/git/post-rewrite` - Bash hook
- `primitives/v1/hooks/git/pre-push` - Bash hook
- `primitives/v1/hooks/git/install.py` - Cross-platform installer
- `primitives/v1/hooks/git/README.md` - Documentation

**Installation:**
```bash
# Single repository
python primitives/v1/hooks/git/install.py

# Global (all repos)
python primitives/v1/hooks/git/install.py --global

# Uninstall
python primitives/v1/hooks/git/install.py --uninstall
```

**Environment Variables:**
- `ANALYTICS_PATH` - Custom path for events file (default: `.agentic/analytics/events.jsonl`)
- `CLAUDE_SESSION_ID` or `AEF_SESSION_ID` - Session correlation

## References

- ADR-011: Analytics Middleware - Establishes JSONL event pattern
- ADR-016: Hook Event Correlation - Session ID propagation
- [Git Hooks Documentation](https://git-scm.com/docs/githooks)
- PR #24: Implementation of this ADR
