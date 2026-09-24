# Changelog

## 1.0.1

- Preserve Claude's native `agent_id` in subagent stop events. Keep the older
  `subagent_id` adapter field as a fallback, independently of the root session ID.

## 1.0.0

- Initial release — split from `sdlc` plugin
- Moved observability hooks: SessionStart, SessionEnd, PostToolUse, PreCompact, Notification, Stop, SubagentStop, UserPromptSubmit
