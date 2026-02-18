# Changelog — observability plugin

## 0.1.0 (2026-02-18)
- Initial release: full-spectrum observability across all 14 Claude Code hook events
- Single generic handler (`observe.py`) dispatches all events
- Added SubagentStart, PostToolUseFailure, TeammateIdle, TaskCompleted event types to agentic_events
- Git hooks: post-commit, post-merge, post-rewrite, pre-push emitting via agentic_events
- Git hook installer (`install.py`) with --global and --uninstall support
