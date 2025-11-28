# Hooks System Documentation

Welcome to the documentation for the Agentic Primitives hooks system.

---

## 📚 Documentation Index

### Core Documentation

- **[Architecture Overview](../architecture/hooks-system-overview.md)** - System design and data flow
- **[ADR-014: Atomic Hook Architecture](../adrs/014-wrapper-impl-pattern.md)** - Architecture decisions
- **[ADR-016: Hook Event Correlation](../adrs/016-hook-event-correlation.md)** - Event correlation design

### Specifications

- **[Hook Metadata Schema](../../specs/v1/hook-meta.schema.json)** - Hook primitive specification
- **[Analytics Events Schema](../../specs/v1/analytics-events.schema.json)** - Event schema specification

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

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.
