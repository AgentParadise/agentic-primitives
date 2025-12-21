# Analytics Event Reference

Complete reference for all analytics event types in the agentic-primitives system.

> **⚠️ Deprecation Notice (v0.2.0)**
>
> The JSONL-based analytics system documented here is **deprecated** in favor of
> **OTel-first observability**. New implementations should use `agentic_otel` for
> telemetry emission.
>
> **Migration Path:**
> - Custom JSONL backends → OTel Collector with file exporter
> - Custom HTTP backends → OTLP exporter to OTel Collector
> - Event parsing scripts → OTel Collector processors
>
> See [ADR-026: OTel-First Observability](./adrs/026-otel-first-observability.md)
> for architectural details and migration guidance.

---

## OTel-First Approach (Recommended)

The recommended approach uses OpenTelemetry for all observability:

```python
from agentic_otel import OTelConfig, HookOTelEmitter

# Configure OTel endpoint (typically OTel Collector)
config = OTelConfig(
    endpoint="http://collector:4317",
    service_name="agentic-hooks",
    resource_attributes={
        "deployment.environment": "production",
        "service.version": "1.0.0",
    },
)

# Emit events as OTel signals
emitter = HookOTelEmitter(config)

# Tool spans (traces)
with emitter.start_tool_span("Bash", tool_use_id, tool_input) as span:
    result = execute_tool()
    span.set_attribute("tool.success", result.success)

# Security events (logs/events)
emitter.emit_security_event(
    hook_type="pre_tool_use",
    decision="block",
    tool_name="Bash",
    tool_use_id=tool_use_id,
    reason="Dangerous command blocked",
)
```

**Benefits of OTel-first:**
- Native Claude CLI support (metrics exported automatically)
- Industry-standard format (vendor-neutral)
- Rich correlation (traces link to metrics to logs)
- Powerful collectors (filtering, sampling, routing)

---

## Legacy JSONL Format (Deprecated)

The following documentation covers the legacy JSONL event format.
It remains functional but is not recommended for new implementations.

---

## Overview

The analytics system normalizes provider-specific hook events into 10 standard event types. This document provides detailed documentation for each event type.

### Event Type Summary

| Event Type | Description | Hook Event | Category |
|-----------|-------------|------------|----------|
| [`session_started`](#session_started) | Session begins or resumes | SessionStart | Session |
| [`session_completed`](#session_completed) | Session ends | SessionEnd | Session |
| [`user_prompt_submitted`](#user_prompt_submitted) | User submits a prompt | UserPromptSubmit | User Interaction |
| [`tool_execution_started`](#tool_execution_started) | Tool about to execute | PreToolUse | Tool Usage |
| [`tool_execution_completed`](#tool_execution_completed) | Tool finished executing | PostToolUse | Tool Usage |
| [`permission_requested`](#permission_requested) | Permission dialog shown | PermissionRequest | Permission |
| [`agent_stopped`](#agent_stopped) | Main agent stops | Stop | Agent Control |
| [`subagent_stopped`](#subagent_stopped) | Subagent stops | SubagentStop | Agent Control |
| [`system_notification`](#system_notification) | System notification sent | Notification | System |
| [`context_compacted`](#context_compacted) | Context window compacted | PreCompact | System |

---

## Event Type Details

### `session_started`

**Description**: Fired when an AI agent session begins or resumes.

**Hook Event Source**: `SessionStart`

**When It Fires**:
- At application startup
- When resuming a previous session
- After clearing conversation history
- After context compaction (creates new session)

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | How session started: `startup`, `resume`, `clear`, `compact` |

**Example**:

```json
{
  "event_type": "session_started",
  "timestamp": "2025-11-19T10:00:00.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "source": "startup"
  },
  "metadata": {
    "hook_event_name": "SessionStart",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Session frequency**: Count how many sessions are started per day
- **Usage patterns**: Understand when users typically start sessions
- **Session source analysis**: Compare startup vs resume vs clear
- **Onboarding metrics**: Track first-time vs returning sessions

**Querying Examples**:

```bash
# Count sessions by source
cat events.jsonl | jq -r 'select(.event_type == "session_started") | .context.source' | sort | uniq -c

# Find all sessions started today
cat events.jsonl | jq 'select(.event_type == "session_started" and (.timestamp | startswith("2025-11-19")))'

# Extract session IDs
cat events.jsonl | jq -r 'select(.event_type == "session_started") | .session_id'
```

---

### `session_completed`

**Description**: Fired when an AI agent session ends.

**Hook Event Source**: `SessionEnd`

**When It Fires**:
- User exits the application
- Session cleared with `/clear` command
- User logs out
- Error causes session termination

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `reason` | string | Why session ended: `exit`, `error`, `compact`, `clear`, `logout`, `other` |

**Example**:

```json
{
  "event_type": "session_completed",
  "timestamp": "2025-11-19T12:30:00.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "reason": "exit"
  },
  "metadata": {
    "hook_event_name": "SessionEnd",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Session duration**: Calculate time between `session_started` and `session_completed`
- **Exit reasons**: Understand why sessions end (normal vs error)
- **Error tracking**: Identify sessions that ended due to errors
- **Engagement metrics**: Compare planned exits vs unexpected terminations

**Calculating Session Duration**:

```bash
# Extract session start and end times
cat events.jsonl | jq -r 'select(.event_type | contains("session")) |
  {session_id, event_type, timestamp}' |
  jq -s 'group_by(.session_id) |
  map({session: .[0].session_id, start: .[0].timestamp, end: .[1].timestamp})'
```

---

### `user_prompt_submitted`

**Description**: Fired when a user submits a prompt to the AI agent.

**Hook Event Source**: `UserPromptSubmit`

**When It Fires**: Immediately after user presses Enter to submit a prompt

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `prompt` | string | The full prompt text submitted by user |
| `prompt_length` | integer | Character count of the prompt |

**Example**:

```json
{
  "event_type": "user_prompt_submitted",
  "timestamp": "2025-11-19T10:05:23.456Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "prompt": "Write a Python function to calculate the factorial of a number",
    "prompt_length": 63
  },
  "metadata": {
    "hook_event_name": "UserPromptSubmit",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **User engagement**: Track prompt frequency and timing
- **Prompt length analysis**: Understand typical prompt sizes
- **Interaction patterns**: Identify power users vs casual users
- **Content analysis**: Analyze prompt topics (with NLP)

**Privacy Considerations**:

⚠️ **Important**: The `prompt` field contains user input which may include:
- Personally Identifiable Information (PII)
- Proprietary code or data
- Sensitive business information

Consider:
- **Filtering**: Remove or redact sensitive data before storage
- **Hashing**: Store hash of prompt instead of full text
- **Length only**: Store only `prompt_length`, discard `prompt` text
- **Retention policies**: Delete old prompts per your data policy
- **Access control**: Restrict who can view prompt data

**Querying Examples**:

```bash
# Analyze prompt lengths
cat events.jsonl | jq 'select(.event_type == "user_prompt_submitted") | .context.prompt_length' |
  jq -s 'add / length'  # Average length

# Count prompts per session
cat events.jsonl | jq -r 'select(.event_type == "user_prompt_submitted") | .session_id' |
  sort | uniq -c

# Find long prompts (>500 chars)
cat events.jsonl | jq 'select(.event_type == "user_prompt_submitted" and .context.prompt_length > 500)'
```

---

### `tool_execution_started`

**Description**: Fired when an AI agent is about to execute a tool.

**Hook Event Source**: `PreToolUse`

**When It Fires**: After agent creates tool parameters, before tool execution begins

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Name of the tool (Write, Read, Bash, Edit, etc.) |
| `tool_input` | object | Input parameters for the tool (varies by tool) |
| `tool_use_id` | string | Unique identifier for this tool use |
| `tool_response` | null | Always null for started events |

**Example (Write Tool)**:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T10:05:45.123Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/factorial.py",
      "contents": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n"
    },
    "tool_use_id": "toolu_01ABC123DEF456",
    "tool_response": null
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Example (Bash Tool)**:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T10:06:12.789Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Bash",
    "tool_input": {
      "command": "python src/factorial.py"
    },
    "tool_use_id": "toolu_01GHI789JKL012",
    "tool_response": null
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Tool usage analytics**: Which tools are most popular?
- **Permission tracking**: Pair with `permission_requested` events
- **Performance baselines**: When did tool start? (pair with completed event)
- **Security auditing**: Track what tools are being used and how
- **Debugging**: Capture tool inputs that caused failures

**Common Tool Names**:
- `Write` - Create or overwrite files
- `Read` - Read file contents
- `Edit` - Edit existing files
- `Bash` - Run shell commands
- `Glob` - File pattern matching
- `Grep` - Content search
- `WebFetch` - Fetch web content
- `WebSearch` - Search the web
- `Task` - Create subagent task

**Querying Examples**:

```bash
# Most popular tools
cat events.jsonl | jq -r 'select(.event_type == "tool_execution_started") | .context.tool_name' |
  sort | uniq -c | sort -rn

# File write operations
cat events.jsonl | jq 'select(.event_type == "tool_execution_started" and .context.tool_name == "Write") |
  .context.tool_input.file_path'

# Bash commands executed
cat events.jsonl | jq -r 'select(.event_type == "tool_execution_started" and .context.tool_name == "Bash") |
  .context.tool_input.command'
```

---

### `tool_execution_completed`

**Description**: Fired when an AI agent finishes executing a tool.

**Hook Event Source**: `PostToolUse`

**When It Fires**: Immediately after tool execution completes (success or failure)

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Name of the tool that was executed |
| `tool_input` | object | Input parameters that were used |
| `tool_use_id` | string | Unique identifier matching the started event |
| `tool_response` | object | Response from the tool execution |

**Example (Successful Write)**:

```json
{
  "event_type": "tool_execution_completed",
  "timestamp": "2025-11-19T10:05:45.234Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/factorial.py",
      "contents": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n"
    },
    "tool_use_id": "toolu_01ABC123DEF456",
    "tool_response": {
      "success": true,
      "file_path": "src/factorial.py"
    }
  },
  "metadata": {
    "hook_event_name": "PostToolUse",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Example (Failed Bash Command)**:

```json
{
  "event_type": "tool_execution_completed",
  "timestamp": "2025-11-19T10:06:13.012Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Bash",
    "tool_input": {
      "command": "python src/missing.py"
    },
    "tool_use_id": "toolu_01MNO345PQR678",
    "tool_response": {
      "success": false,
      "error": "FileNotFoundError: [Errno 2] No such file or directory: 'src/missing.py'",
      "exit_code": 1
    }
  },
  "metadata": {
    "hook_event_name": "PostToolUse",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Performance monitoring**: Calculate execution time (timestamp diff from started event)
- **Success rate tracking**: Count successful vs failed tool executions
- **Error analysis**: Identify which tools fail most often
- **Output validation**: Verify tool responses match expectations
- **Debugging**: Capture tool responses that caused issues

**Calculating Tool Execution Time**:

```bash
# Match start and complete events by tool_use_id
cat events.jsonl | jq -r '
  select(.event_type | contains("tool_execution")) |
  {tool_use_id: .context.tool_use_id, event_type, timestamp}' |
  jq -s 'group_by(.tool_use_id) |
  map(select(length == 2) |
  {tool: .[0].tool_use_id, duration: (.[1].timestamp | fromdate) - (.[0].timestamp | fromdate)})'
```

**Tracking Success Rates**:

```bash
# Count successful vs failed executions
cat events.jsonl | jq 'select(.event_type == "tool_execution_completed") |
  .context.tool_response.success' |
  sort | uniq -c
```

---

### `permission_requested`

**Description**: Fired when the AI agent requests permission to execute a tool.

**Hook Event Source**: `PermissionRequest`

**When It Fires**: When permission dialog is shown to the user

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Tool requiring permission |
| `tool_input` | object | Parameters for the tool |
| `tool_use_id` | string | Unique identifier for this tool use |
| `tool_response` | null | Always null for permission events |

**Example**:

```json
{
  "event_type": "permission_requested",
  "timestamp": "2025-11-19T10:05:44.500Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/factorial.py",
      "contents": "def factorial(n):\n..."
    },
    "tool_use_id": "toolu_01ABC123DEF456",
    "tool_response": null
  },
  "metadata": {
    "hook_event_name": "PermissionRequest",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Permission audit trail**: Track what permissions were requested
- **Security compliance**: Demonstrate permission controls are active
- **UX improvement**: Identify tools that frequently need permission (annoying users)
- **Permission model analysis**: Which tools trigger permission most?
- **Policy validation**: Verify permission system is working correctly

**Relationship to Other Events**:

Permission request typically happens before tool execution:

```
1. permission_requested (PermissionRequest)
   ↓
2. User approves or denies
   ↓
3. tool_execution_started (PreToolUse) - if approved
   ↓
4. tool_execution_completed (PostToolUse)
```

**Querying Examples**:

```bash
# Most common tools requiring permission
cat events.jsonl | jq -r 'select(.event_type == "permission_requested") | .context.tool_name' |
  sort | uniq -c | sort -rn

# Permission requests by permission mode
cat events.jsonl | jq 'select(.event_type == "permission_requested") |
  {tool: .context.tool_name, mode: .metadata.permission_mode}'

# Find tools that always need permission
cat events.jsonl | jq -r '
  select(.event_type | contains("tool_execution")) |
  {tool: .context.tool_name, event: .event_type}' |
  jq -s 'group_by(.tool) |
  map({tool: .[0].tool, count: length})'
```

---

### `agent_stopped`

**Description**: Fired when the main AI agent finishes responding.

**Hook Event Source**: `Stop`

**When It Fires**: After agent completes its response turn

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `stop_hook_active` | boolean | True if already continuing due to a stop hook |

**Example**:

```json
{
  "event_type": "agent_stopped",
  "timestamp": "2025-11-19T10:07:00.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "stop_hook_active": false
  },
  "metadata": {
    "hook_event_name": "Stop",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Response time**: Calculate time from prompt to agent stop
- **Turn counting**: How many turns per session?
- **Stop hook monitoring**: Track if stop hooks are keeping agent running
- **Session flow analysis**: Understand conversation patterns

**⚠️ Important Note**:

The `stop_hook_active` field prevents infinite loops. If your stop hook keeps the agent running, this will be `true` on subsequent stops. Check this field to avoid infinite continuation.

**Querying Examples**:

```bash
# Count agent stops per session
cat events.jsonl | jq -r 'select(.event_type == "agent_stopped") | .session_id' |
  sort | uniq -c

# Find sessions with stop hooks active
cat events.jsonl | jq 'select(.event_type == "agent_stopped" and .context.stop_hook_active == true)'

# Calculate response time (prompt to stop)
cat events.jsonl | jq -r '
  select(.event_type == "user_prompt_submitted" or .event_type == "agent_stopped") |
  {event: .event_type, timestamp, session_id}' |
  jq -s 'group_by(.session_id) | map(select(length >= 2))'
```

---

### `subagent_stopped`

**Description**: Fired when a subagent (Task tool) finishes responding.

**Hook Event Source**: `SubagentStop`

**When It Fires**: After subagent completes its task

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `stop_hook_active` | boolean | True if already continuing due to a stop hook |

**Example**:

```json
{
  "event_type": "subagent_stopped",
  "timestamp": "2025-11-19T10:06:45.678Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "stop_hook_active": false
  },
  "metadata": {
    "hook_event_name": "SubagentStop",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Subagent usage**: Track how often subagents are used
- **Task completion time**: Calculate subagent execution duration
- **Subagent effectiveness**: Analyze when subagents are stopped
- **Nesting analysis**: Track subagent hierarchies

**Querying Examples**:

```bash
# Count subagent stops
cat events.jsonl | jq -r 'select(.event_type == "subagent_stopped")' | wc -l

# Find subagent tasks
cat events.jsonl | jq 'select(.event_type == "tool_execution_started" and .context.tool_name == "Task")'
```

---

### `system_notification`

**Description**: Fired when the system sends a notification to the user.

**Hook Event Source**: `Notification`

**When It Fires**: When various system notifications are triggered

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `notification_type` | string | Type of notification (permission_prompt, idle_prompt, etc.) |
| `message` | string | Notification message text |

**Example (Permission Prompt)**:

```json
{
  "event_type": "system_notification",
  "timestamp": "2025-11-19T10:05:44.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "notification_type": "permission_prompt",
    "message": "Claude needs your permission to use Write"
  },
  "metadata": {
    "hook_event_name": "Notification",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Example (Idle Prompt)**:

```json
{
  "event_type": "system_notification",
  "timestamp": "2025-11-19T10:10:00.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "notification_type": "idle_prompt",
    "message": "Claude has been idle for over 60 seconds"
  },
  "metadata": {
    "hook_event_name": "Notification",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Common Notification Types**:
- `permission_prompt` - Permission dialog shown
- `idle_prompt` - Agent idle for extended period
- `auth_success` - Authentication successful
- `elicitation_dialog` - MCP tool needs user input
- Other provider-specific notifications

**Use Cases**:
- **Notification frequency**: Track how often users see notifications
- **Idle detection**: Identify inactive sessions
- **UX metrics**: Measure notification impact on user experience
- **Permission correlation**: Link with permission events

**Querying Examples**:

```bash
# Count notifications by type
cat events.jsonl | jq -r 'select(.event_type == "system_notification") | .context.notification_type' |
  sort | uniq -c

# Find idle notifications
cat events.jsonl | jq 'select(.event_type == "system_notification" and .context.notification_type == "idle_prompt")'
```

---

### `context_compacted`

**Description**: Fired before the system compacts the context window.

**Hook Event Source**: `PreCompact`

**When It Fires**:
- Manually via `/compact` command
- Automatically when context window is full

**Context Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | string | How compaction was triggered: `manual` or `auto` |
| `custom_instructions` | string \| null | User instructions for manual compact (optional) |

**Example (Manual Compact)**:

```json
{
  "event_type": "context_compacted",
  "timestamp": "2025-11-19T10:15:00.000Z",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "trigger": "manual",
    "custom_instructions": "Keep the discussion about Python functions"
  },
  "metadata": {
    "hook_event_name": "PreCompact",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Example (Auto Compact)**:

```json
{
  "event_type": "context_compacted",
  "timestamp": "2025-11-19T11:45:00.000Z",
  "session_id": "xyz789-uvw012-rst345",
  "provider": "claude",
  "context": {
    "trigger": "auto",
    "custom_instructions": null
  },
  "metadata": {
    "hook_event_name": "PreCompact",
    "transcript_path": "/Users/dev/.claude/projects/my-project/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/my-project"
}
```

**Use Cases**:
- **Context window analysis**: How often does context fill up?
- **Manual vs auto compact**: Which is more common?
- **Session continuity**: Track session before/after compact
- **Performance impact**: Does compaction affect user experience?

**Querying Examples**:

```bash
# Count compactions by trigger type
cat events.jsonl | jq -r 'select(.event_type == "context_compacted") | .context.trigger' |
  sort | uniq -c

# Find sessions with auto compaction (long conversations)
cat events.jsonl | jq 'select(.event_type == "context_compacted" and .context.trigger == "auto") | .session_id'
```

---

## Schema Reference

### Common Fields

All normalized events have these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_type` | string | Yes | One of the 10 event types |
| `timestamp` | string (ISO 8601) | Yes | When event occurred |
| `session_id` | string | Yes | Session identifier |
| `provider` | string | Yes | Provider name (claude, openai, etc.) |
| `context` | object | Yes | Event-specific data (varies by type) |
| `metadata` | object | Yes | Event metadata and provenance |
| `cwd` | string | No | Current working directory |

### Metadata Fields

The `metadata` object contains information about the event source:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hook_event_name` | string | Yes | Original hook event name from provider |
| `transcript_path` | string | No | Path to conversation transcript |
| `permission_mode` | string | No | Permission mode at event time |
| `raw_event` | object | No | Original event data from provider (optional) |

### JSON Schema

The complete JSON schema is available at: `specs/v1/analytics-events.schema.json`

Validate events against the schema:

```bash
# Using jq
cat event.json | jq -e -f specs/v1/analytics-events.schema.json

# Using Python
uv run python -c "
from analytics.models.events import NormalizedEvent
import json
event = NormalizedEvent.model_validate_json(open('event.json').read())
print('Valid!')
"
```

## Querying Analytics Data

### Using jq

```bash
# Filter by event type
cat events.jsonl | jq 'select(.event_type == "tool_execution_started")'

# Count events
cat events.jsonl | jq -r '.event_type' | sort | uniq -c

# Extract specific fields
cat events.jsonl | jq '{type: .event_type, time: .timestamp, provider: .provider}'

# Group by session
cat events.jsonl | jq -s 'group_by(.session_id)'

# Time range filtering
cat events.jsonl | jq 'select(.timestamp >= "2025-11-19T10:00:00Z" and .timestamp <= "2025-11-19T11:00:00Z")'
```

### Loading into Python

```python
import json
from pathlib import Path
from analytics.models.events import NormalizedEvent

# Load all events
events = []
with open("events.jsonl") as f:
    for line in f:
        event = NormalizedEvent.model_validate_json(line)
        events.append(event)

# Filter tool executions
tool_events = [e for e in events if "tool_execution" in e.event_type]

# Group by session
from collections import defaultdict
sessions = defaultdict(list)
for event in events:
    sessions[event.session_id].append(event)

# Calculate metrics
print(f"Total events: {len(events)}")
print(f"Unique sessions: {len(sessions)}")
print(f"Tool executions: {len(tool_events)}")
```

### Loading into pandas

```python
import pandas as pd
import json

# Load JSONL into DataFrame
events = []
with open("events.jsonl") as f:
    for line in f:
        events.append(json.loads(line))

df = pd.DataFrame(events)

# Convert timestamp to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Analyze event counts
print(df['event_type'].value_counts())

# Group by session
session_stats = df.groupby('session_id').agg({
    'event_type': 'count',
    'timestamp': ['min', 'max']
})

# Time series analysis
df.set_index('timestamp').resample('1H')['event_type'].count().plot()
```

## Additional Resources

- [Analytics Integration Guide](./analytics-integration.md) - Setup and configuration
- [Analytics Troubleshooting](./analytics-troubleshooting.md) - Common issues
- [Analytics Examples](./examples/analytics/) - Example configurations
- [ADR-011: Analytics Middleware](./adrs/011-analytics-middleware.md) - Architecture decisions
- [JSON Schema](../specs/v1/analytics-events.schema.json) - Complete schema definition
