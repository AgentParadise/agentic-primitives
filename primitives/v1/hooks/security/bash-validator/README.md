# Bash Validator

**Specialized security hook for validating Bash commands before execution.**

## Overview

`bash-validator` is a targeted security primitive that validates Bash commands for dangerous patterns and security risks. It runs only on `PreToolUse` events with the `Bash` matcher, making it fast and focused.

## Architecture Pattern

This is a **specialized hook** as part of the hybrid architecture:

- **Universal Collector** (`hooks-collector`) → Observability (all events, all tools)
- **Specialized Hooks** (`bash-validator`) → Control (specific events, specific tools)

Both run in parallel for comprehensive coverage!

## Features

- ✅ **Fast Validation** - Typical response < 100ms
- ✅ **Dangerous Pattern Detection** - Blocks risky commands
- ✅ **Suspicious Pattern Warnings** - Alerts on potentially unsafe patterns
- ✅ **Fail-Safe** - Errors don't block execution
- ✅ **Configurable** - Can be enabled/disabled per agent

## Dangerous Patterns Detected

The validator blocks commands matching these patterns:

- `rm -rf /` - Recursive delete from root
- `dd if=...` - Direct disk writes
- `mkfs.` - Filesystem formatting
- `:(){:|:&};:` - Fork bomb
- `kill -9 -1` - Kill all processes
- `chmod -R 777 /` - Overly permissive permissions
- `curl ... | bash` - Pipe remote scripts to shell
- `wget ... | sh` - Pipe remote scripts to shell

## Suspicious Patterns (Warnings)

These patterns generate warnings but don't block:

- `>/dev/sd*` - Direct disk writes
- `eval` - Dynamic code evaluation
- `$()` - Command substitution (injection risk)
- `; rm -rf` - Chained destructive commands

## Usage

### Building for Claude

```bash
agentic-p build \
  --primitive primitives/v1/hooks/security/bash-validator \
  --provider claude \
  --output build/claude
```

### Expected Output

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/bash-validator.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

### Hook Response Format

**Safe Command:**
```json
{
  "action": "allow",
  "metadata": {
    "hook": "bash-validator",
    "risk_level": "low",
    "validated": true
  }
}
```

**Dangerous Command:**
```json
{
  "action": "deny",
  "reason": "Dangerous command pattern detected",
  "metadata": {
    "hook": "bash-validator",
    "risk_level": "high",
    "dangerous_patterns": ["\\\\brm\\\\s+-rf\\\\s+/"],
    "command": "rm -rf /"
  }
}
```

**Suspicious Command:**
```json
{
  "action": "allow",
  "warning": "Suspicious pattern detected (allowing with warning)",
  "metadata": {
    "hook": "bash-validator",
    "risk_level": "low",
    "suspicious_patterns": ["\\\\beval\\\\s+"]
  }
}
```

## Configuration

This is a **primitive** (generic implementation). Agent-specific configuration goes in:

```
providers/agents/claude-code/hooks-config/bash-validator.yaml
```

Example config:
```yaml
agent: claude-code
hook_id: bash-validator

primitive:
  id: bash-validator
  path: "../../../../primitives/v1/hooks/security/bash-validator"
  impl_file: "impl.python.py"

execution:
  strategy: sequential
  timeout_sec: 5
  fail_on_error: true

default_decision: "deny"  # Can override to be more strict
```

## Hybrid Architecture Example

**Together with hooks-collector:**

```json
{
  "PreToolUse": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/hooks-collector.py",
          "timeout": 10
        }
      ]
    },
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/scripts/bash-validator.py",
          "timeout": 5
        }
      ]
    }
  ]
}
```

Both hooks run in parallel:
- `hooks-collector` → Captures event for analytics
- `bash-validator` → Validates command for security

## Testing

```bash
# Test with safe command
echo '{"tool_input": {"command": "ls -la"}}' | \
  uv run python3 impl.python.py

# Test with dangerous command
echo '{"tool_input": {"command": "rm -rf /"}}' | \
  uv run python3 impl.python.py

# Test with suspicious command
echo '{"tool_input": {"command": "eval $SOME_VAR"}}' | \
  uv run python3 impl.python.py
```

## Performance

- **Validation Time:** < 100ms typical
- **Regex Patterns:** 9 dangerous, 4 suspicious
- **Memory:** < 10MB
- **Blocking:** Only on high-risk patterns

## Security Model

- **Risk Levels:**
  - `low` - Safe, no concerns
  - `medium` - Multiple suspicious patterns
  - `high` - Dangerous patterns detected

- **Actions:**
  - `allow` - Safe to execute
  - `deny` - Block execution
  - `allow` + `warning` - Execute with warning

## Extending

To add new patterns, edit `impl.python.py`:

```python
DANGEROUS_COMMANDS = [
    r'your_pattern_here',
]

SUSPICIOUS_PATTERNS = [
    r'your_pattern_here',
]
```

Then rebuild:

```bash
agentic-p build --primitive . --provider claude --output build/claude
```

## Integration

This primitive integrates with:
- **hooks-collector** - Parallel analytics
- **file-security** - File operation validation
- **prompt-filter** - Prompt sanitization

Together, they provide comprehensive security coverage!

## License

Part of the Agentic Primitives project.


