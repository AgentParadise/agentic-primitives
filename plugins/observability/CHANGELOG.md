# Changelog — observability plugin

## 0.2.3
- Claude hook handler now supports the `AGENTIC_EVENTS_JSONL` sink so workspace
  drivers can capture hook JSONL without using hook stdout
- Documented stderr plus sink output semantics for Claude hooks

## 0.2.2
- Git hooks (post-merge, post-rewrite, pre-push) now emit structured sha/branch/repo context via the typed git event payloads in agentic_events

## 0.1.0 (2026-02-18)
- Initial release: full-spectrum observability across all 14 Claude Code hook events
- Single generic handler (`observe.py`) dispatches all events
- Added SubagentStart, PostToolUseFailure, TeammateIdle, TaskCompleted event types to agentic_events
- Git hooks: post-commit, post-merge, post-rewrite, pre-push emitting via agentic_events
- Git hook installer (`install.py`) with --global and --uninstall support
