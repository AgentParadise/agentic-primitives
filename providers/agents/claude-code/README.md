# Claude Code Agent Provider

Claude Code is Anthropic's AI-powered coding assistant that provides intelligent code generation, analysis, and workspace understanding.

## Overview

- **Vendor:** Anthropic
- **Type:** Agent (Coding Assistant)
- **Default Model:** Claude 3 Sonnet
- **Hook Support:** 9 event types
- **Tool Protocol:** MCP (Model Context Protocol)

## Hook Events

Claude Code supports 9 hook events for customization:

### Decision Control Hooks (Can modify/block)
- **PreToolUse**: Before tool execution (requires matcher)
- **PostToolUse**: After tool completion (requires matcher)
- **UserPromptSubmit**: When user submits prompt
- **Stop**: When conversation stops normally
- **SubagentStop**: When subagent completes

### Notification Hooks (Observe only)
- **SessionStart**: Session initialization (matchers: startup, resume, clear, compact)
- **SessionEnd**: Session termination
- **PreCompact**: Before context compaction (matchers: manual, auto)
- **Notification**: Various notifications (matchers: permission_prompt, idle_prompt, error, warning)

## Configuration

### Project Structure

```
your-project/
└── .claude/
    ├── settings.json          # Agent configuration
    └── hooks/
        └── hooks.json         # Hook definitions
```

### Example hooks.json

```json
{
  "PreToolUse": [
    {
      "matcher": "write_*",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/validate-write.py",
          "timeout": 5
        }
      ]
    }
  ],
  "SessionStart": [
    {
      "matcher": "startup",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/session-init.py",
          "timeout": 10
        }
      ]
    }
  ]
}
```

## Hook Implementation

All hooks receive event data via stdin as JSON and can:
- Observe the event
- Modify data (decision control events only)
- Block execution (decision control events only)
- Log analytics

### Input Format

```json
{
  "event": "PreToolUse",
  "timestamp": "2025-11-23T10:30:00Z",
  "tool": "write_file",
  "args": {
    "path": "src/main.py",
    "content": "..."
  },
  "context": {
    "session_id": "abc123",
    "user_prompt": "Create a main.py file"
  }
}
```

### Output Format

```json
{
  "action": "allow",
  "modified_data": null,
  "metadata": {
    "hook_id": "analytics-collector",
    "execution_time_ms": 45
  }
}
```

## Features

- ✅ Multi-file editing
- ✅ Terminal access
- ✅ Web search integration
- ✅ Image understanding
- ✅ Subagent support
- ✅ Auto context compaction
- ✅ MCP tool protocol
- ✅ Custom hooks

## Permission Modes

- **default**: Ask for dangerous operations
- **plan**: Plan before executing changes
- **acceptEdits**: Auto-approve file edits
- **bypassPermissions**: Skip all permission checks (use carefully!)

## Building Hooks

Use `agentic-p` to build hooks for Claude Code:

```bash
# Build all hooks
agentic-p build --agent claude-code --output build/claude

# Install to project
agentic-p install --agent claude-code --project ./my-project
```

## Documentation

- [Official Docs](https://code.claude.com/docs)
- [Hook System](https://code.claude.com/docs/hooks)
- [MCP Protocol](https://code.claude.com/docs/mcp)
- [GitHub](https://github.com/anthropics/claude-code)

## Support

- **Website:** https://code.claude.com
- **Support:** https://support.anthropic.com
- **Community:** https://discord.gg/anthropic



