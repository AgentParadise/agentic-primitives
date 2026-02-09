# Core Security Plugin

Security hooks, validators, and git observability for Claude Code agents.

## Installation

```json
{ "plugins": { "core/security": true } }
```

## Components

### Hooks (Claude Code lifecycle)
- `pre-tool-use` — Routes tool validation to atomic validators
- `post-tool-use` — Logs tool execution results
- `session-start` / `session-end` — Session lifecycle tracking
- `pre-compact` — Context window compaction tracking
- `notification` — System notification logging
- `stop` / `subagent-stop` — Agent stop tracking
- `user-prompt` — Prompt submission logging

### Validators
- `security/bash` — Blocks dangerous shell commands (rm -rf /, fork bombs, etc.)
- `security/file` — Blocks writes to sensitive paths, detects secrets in content
- `prompt/pii` — Detects PII patterns in user prompts

### Git Hooks (observability)
- `post-commit` — Emit commit events with token metrics
- `post-checkout` — Track branch switches and creation
- `post-merge` — Track merges to stable branches
- `post-rewrite` — Track rebases and amends
- `pre-push` — Track push operations
