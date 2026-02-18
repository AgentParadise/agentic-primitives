# Hooks System Documentation

Welcome to the documentation for the Agentic Primitives hooks system.

---

## 📚 Documentation Index

### Core Documentation

- **[Architecture Overview](architecture.md)** - System design and data flow
- **[ADR-014: Atomic Hook Architecture](../adrs/014-wrapper-impl-pattern.md)** - Architecture decisions
- **[ADR-016: Hook Event Correlation](../adrs/016-hook-event-correlation.md)** - Event correlation design
- **[ADR-017: Hook Client Library](../adrs/017-hook-client-library.md)** - High-performance client for agent swarms

### High-Performance Hooks (Agent Swarms)

- **[Client Library Guide](client-library.md)** - Using `agentic-hooks` for 1000+ concurrent agents
- **[Backend Service Guide](backend-service.md)** - Deploying the hook backend service

### Specifications

- **[Hook Metadata Schema](../../specs/v1/hook-meta.schema.json)** - Hook primitive specification
- **[Analytics Events Schema](../../specs/v1/analytics-events.schema.json)** - Event schema specification

---

## 🚀 Choosing the Right Approach

| Use Case | Approach | Documentation |
|----------|----------|---------------|
| Single agent (Claude Desktop, Cursor) | Subprocess hooks | This page |
| Agent swarms (1000+ concurrent) | Client library + Backend | [Client Library](client-library.md) |
| Local development | JSONL file storage | Both approaches |
| Production at scale | PostgreSQL backend | [Backend Service](backend-service.md) |

---

## 🎯 Quick Start

### Using Hooks

Hooks are automatically installed when you copy the `.claude/` directory to your project:

```bash
# From example projects
cp -r examples/001-claude-agent-sdk-integration/.claude ~/your-project/
```

The hooks will automatically:
- Validate dangerous bash commands (block `rm -rf /`, etc.)
- Check file operations for security issues
- Detect PII in user prompts
- Log all decisions to `.agentic/analytics/events.jsonl`

### Testing Hooks

```bash
# Test the pre-tool-use handler
echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | \
  python3 .claude/hooks/handlers/pre-tool-use.py
# Output: {"decision": "allow"}

# Test with dangerous command
echo '{"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}' | \
  python3 .claude/hooks/handlers/pre-tool-use.py
# Output: {"decision": "block", "reason": "Dangerous command blocked: rm -rf / (root deletion)"}
```

---

## 🏗️ Architecture

The hooks system uses an **Atomic Architecture** with two types of components:

### Handlers (Entry Points)

Three handlers serve as entry points for Claude's hook events:

```
.claude/hooks/handlers/
├── pre-tool-use.py      # Validates tools before execution
├── post-tool-use.py     # Logs tool execution results
└── user-prompt.py       # Validates user prompts
```

### Validators (Pure Functions)

Validators are atomic, single-purpose validation functions:

```
.claude/hooks/validators/
├── security/
│   ├── bash.py          # Shell command validation
│   └── file.py          # File operation validation
└── prompt/
    └── pii.py           # PII detection
```

### Data Flow

```
Claude Event (stdin JSON)
        │
        ▼
┌──────────────────────────────────────────────┐
│  Handler (e.g., pre-tool-use.py)             │
│                                              │
│  1. Parse event from stdin                   │
│  2. Route to validators based on tool_name   │
│  3. Import validators in-process             │
│  4. Call validate() functions                │
│  5. Log to analytics (inline)                │
│  6. Output decision to stdout                │
└──────────────────────────────────────────────┘
        │
        ▼
   JSON Response (stdout)
```

---

## 📖 Key Concepts

### Validator Contract

Every validator exports a `validate()` function:

```python
def validate(tool_input: dict, context: dict | None = None) -> dict:
    """
    Args:
        tool_input: The tool_input from the hook event
        context: Optional context (session_id, tool_name, etc.)

    Returns:
        {
            "safe": bool,
            "reason": str | None,      # Required if safe=False
            "metadata": dict | None    # Optional extra data
        }
    """
```

### No External Dependencies

Hooks use **Python stdlib only** - no package imports:

```python
# ✅ Good - stdlib only
import json
import os
import sys
from pathlib import Path

# ❌ Bad - external package
from agentic_analytics import AnalyticsClient
```

### Inline Analytics

Analytics logging is built into handlers (6 lines, no imports):

```python
def log_analytics(event: dict) -> None:
    try:
        path = Path(os.getenv("ANALYTICS_PATH", ".agentic/analytics/events.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps({"timestamp": datetime.now(UTC).isoformat(), **event}) + "\n")
    except Exception:
        pass  # Never block on analytics
```

---

## 🔧 Adding New Validators

### Step 1: Create Validator

```python
# primitives/v1/hooks/validators/security/my_validator.py
def validate(tool_input: dict, context: dict | None = None) -> dict:
    command = tool_input.get("command", "")

    if "dangerous_pattern" in command:
        return {
            "safe": False,
            "reason": "Dangerous pattern detected",
            "metadata": {"pattern": "dangerous_pattern"}
        }

    return {"safe": True}
```

### Step 2: Register in Handler

```python
# In handlers/pre-tool-use.py
TOOL_VALIDATORS = {
    "Bash": ["security.bash", "security.my_validator"],  # Add here
    "Write": ["security.file"],
}
```

### Step 3: Test

```bash
echo '{"tool_name": "Bash", "tool_input": {"command": "dangerous_pattern"}}' | \
  python3 .claude/hooks/handlers/pre-tool-use.py
```

---

## 📊 Analytics

### Event Format

Hook decisions are logged to `.agentic/analytics/events.jsonl`:

```json
{
  "timestamp": "2025-11-27T17:45:27.833215+00:00",
  "event_type": "hook_decision",
  "handler": "pre-tool-use",
  "tool_name": "Bash",
  "decision": "block",
  "reason": "Dangerous command blocked: rm -rf / (root deletion)",
  "session_id": "abc123",
  "tool_use_id": "toolu_456",
  "validators_run": ["security.bash"],
  "metadata": {"risk_level": "critical"}
}
```

### Configuration

```bash
# Default path
export ANALYTICS_PATH=".agentic/analytics/events.jsonl"

# Custom path
export ANALYTICS_PATH="/var/log/agentic/events.jsonl"
```

---

## 🔒 Security

The hooks provide several security protections:

| Validator | Protection |
|-----------|------------|
| `security/bash.py` | Blocks dangerous shell commands (rm -rf /, fork bombs, etc.) |
| `security/file.py` | Blocks writes to sensitive files (.env, keys, /etc/) |
| `prompt/pii.py` | Detects and blocks high-risk PII (SSN, credit cards) |

### Blocked Patterns (Bash)

- `rm -rf /` - Root deletion
- `dd if=... of=/dev/...` - Disk overwrite
- `curl ... | bash` - Remote code execution
- `git push --force` - Force push
- `git add -A` - Adding all files (may include secrets)

---

## 🧪 Testing

### Unit Test Validators

```bash
# Test bash validator directly
echo '{"command": "rm -rf /"}' | python3 validators/security/bash.py
# {"safe": false, "reason": "Dangerous command blocked: rm -rf / (root deletion)", ...}
```

### Integration Test Handlers

```bash
# Test full handler flow
echo '{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}' | \
  python3 handlers/pre-tool-use.py
# {"decision": "allow"}
```

### Verify Analytics

```bash
# Check events were logged
cat .agentic/analytics/events.jsonl | jq .
```

---

## 📝 Examples

- **[Example 000](../../examples/000-claude-integration/)** - Basic Claude integration
- **[Example 001](../../examples/001-claude-agent-sdk-integration/)** - Claude Agent SDK integration

---

## 🐛 Troubleshooting

### Hooks Not Running

1. Check settings.json is configured:
   ```bash
   cat .claude/settings.json | jq .hooks
   ```

2. Verify handlers are executable:
   ```bash
   chmod +x .claude/hooks/handlers/*.py
   ```

3. Test handler manually:
   ```bash
   echo '{}' | python3 .claude/hooks/handlers/pre-tool-use.py
   ```

### Analytics Not Logging

1. Check directory is writable:
   ```bash
   mkdir -p .agentic/analytics && touch .agentic/analytics/test
   ```

2. Check ANALYTICS_PATH:
   ```bash
   echo $ANALYTICS_PATH
   ```

3. Run handler with debug:
   ```bash
   echo '{"tool_name": "Bash", "tool_input": {"command": "ls"}}' | \
     python3 .claude/hooks/handlers/pre-tool-use.py
   cat .agentic/analytics/events.jsonl
   ```

---

## 🚀 High-Performance Hooks for Agent Swarms

For scenarios with 1000+ concurrent agents, the subprocess-per-hook approach creates significant overhead. We provide a **client-server architecture** for high-performance event emission:

### Quick Start (Agent Swarms)

```python
from agentic_hooks import HookClient, HookEvent, EventType

# 3 lines of code for high-performance event emission
async with HookClient(backend_url="http://hooks:8080") as client:
    await client.emit(HookEvent(
        event_type=EventType.TOOL_EXECUTION_STARTED,
        session_id="session-123",
        data={"tool_name": "Write"},
    ))
```

### Performance

| Metric | Subprocess Approach | Client Library |
|--------|---------------------|----------------|
| p99 Latency | ~50ms | **0.02ms** |
| Throughput | ~100 events/sec | **143,000+ events/sec** |
| Concurrent Agents | ~10 | **1000+** |

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Agent Process (1 of 1000)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  from agentic_hooks import HookClient, HookEvent                     │   │
│  │  client = HookClient(backend_url="http://hooks:8080")               │   │
│  │  await client.emit(event)  # Buffered, batched, async               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                              │ HTTP POST (batched)
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Hook Backend Service                            │
│  POST /events/batch    - Receive batched events                             │
│  POST /events          - Receive single event                               │
│  GET  /health          - Health check                                       │
│  Storage: PostgreSQL (production) or JSONL (development)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Installation

```bash
# Client library (zero runtime deps)
pip install agentic-hooks

# With HTTP backend support
pip install agentic-hooks[http]

# Backend service via Docker
cd services/hooks && docker compose up -d
```

### Learn More

- **[Client Library Guide](client-library.md)** - Full API documentation
- **[Backend Service Guide](backend-service.md)** - Deployment and operations
- **[ADR-017: Hook Client Library](../adrs/017-hook-client-library.md)** - Architecture decision

---

## 🔀 Git Observability Hooks

The workspace plugin includes **four git hooks** that emit structured observability events to stderr via the `agentic_events` library. These hooks provide visibility into all git operations performed during an agent session.

### Hooks

| Hook | Event Type | Trigger |
|------|-----------|---------|
| `post-commit` | `git_commit` | After every commit |
| `post-rewrite` | `git_rewrite` | After `git commit --amend` or `git rebase` |
| `post-merge` | `git_merge` | After `git merge` or `git pull` |
| `pre-push` | `git_push` | Before `git push` (emits, never blocks) |

### How It Works

1. Hook scripts live in `plugins/workspace/hooks/git/`
2. They are auto-installed via `git config core.hooksPath` in the workspace entrypoint
3. Each hook collects git metadata (SHA, branch, diff stats) using shell commands
4. A small inline Python snippet imports `agentic_events.EventEmitter` and emits a JSONL event to stderr
5. The agent runner captures stderr and routes events to storage/analytics

### Token Estimation (ADR-022)

The `post-commit` hook estimates tokens added and removed using the `chars/4` approximation defined in [ADR-022](../adrs/022-token-estimation.md). These are emitted as `estimated_tokens_added` and `estimated_tokens_removed` in the `git_commit` event context, enabling cost and impact tracking without an actual tokenizer.

### Example Event

```json
{
  "event_type": "git_commit",
  "timestamp": "2026-02-18T03:00:02+00:00",
  "session_id": "session-abc",
  "provider": "claude",
  "context": {
    "sha": "a1b2c3d4...",
    "branch": "feat/example",
    "repo": "my-project",
    "files_changed": 3,
    "insertions": 45,
    "deletions": 12,
    "message_preview": "feat: add new widget",
    "author": "Dev <dev@example.com>",
    "estimated_tokens_added": 280,
    "estimated_tokens_removed": 75
  }
}
```

### Testing

Integration tests in `lib/python/agentic_events/tests/test_git_hooks_integration.py` exercise the hooks end-to-end by creating real git repos, installing hooks, and verifying emitted events. A recording fixture at `tests/fixtures/git-events-recording/events.jsonl` provides realistic git event data for downstream consumers.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.
