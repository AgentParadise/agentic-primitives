# Security Hooks

**Status:** Production-Ready (v1.0.0)  
**Architecture:** Specialized, Targeted Hooks  
**Category:** Security & Control

Specialized hook primitives for targeted security validation and control.

## Overview

Security hooks are **specialized, single-purpose hooks** that:
- Target specific tools or events
- Validate operations before execution
- Can block dangerous or unauthorized actions
- Provide safe alternatives when blocking
- Work alongside universal collector for complete coverage

## Available Hooks

### bash-validator

**Purpose:** Validate bash commands for dangerous patterns

**Matcher:** `Bash` (only Bash tool calls)

**Features:**
- Detects dangerous commands (rm -rf, dd, mkfs, etc.)
- Returns decision: "block" or "allow"
- Suggests safe alternatives
- Customizable danger patterns

**Example:**
```
Input: rm -rf /
Decision: block
Alternative: Use specific paths, not root directory
```

### file-security

**Purpose:** Protect sensitive files from unauthorized access

**Matcher:** `Read|Write|Edit|Delete` (file operation tools)

**Features:**
- Protects sensitive files (.env, keys, credentials)
- Blocks unauthorized access
- Logs all file operations
- Customizable protection patterns

**Example:**
```
Input: Read .env
Decision: block
Reason: Sensitive configuration file
```

### prompt-filter

**Purpose:** Scan user prompts for PII and credentials

**Matcher:** `*` (all prompts)

**Features:**
- Detects PII (emails, SSNs, credit cards)
- Finds hardcoded credentials
- Warns before sending sensitive data
- Customizable detection patterns

**Example:**
```
Input: "Add john@company.com to config"
Decision: allow (with warning)
Warning: Email address detected
```

## Hybrid Architecture

Security hooks work alongside the **universal collector** for complete coverage:

### Universal Collector (hooks-collector)
- **Purpose:** Observability (analytics, logging, metrics)
- **Matcher:** `*` (catches all events)
- **Behavior:** Never blocks, always allows
- **Coverage:** ALL 9 Claude events

### Specialized Hooks (these security hooks)
- **Purpose:** Control (security, validation, blocking)
- **Matcher:** Targeted (only relevant tools)
- **Behavior:** Can block dangerous operations
- **Coverage:** Specific events/tools only

### Example: Bash Command

```
User: "Delete logs with rm -rf logs/"
       ↓
Claude Code triggers PreToolUse event
       ↓
  ┌──────────────────────────────────────┐
  │ hooks-collector (matcher: "*")       │  ← Logs analytics
  │ bash-validator (matcher: "Bash")     │  ← Validates command
  └──────────────────────────────────────┘
         Both run in parallel
       ↓
bash-validator blocks + suggests alternative
       ↓
Claude: "⚠️ That command is dangerous. Use 'rm -r logs/' instead."
```

**See:** [ADR-013: Hybrid Hook Architecture](../../../../docs/adrs/013-hybrid-hook-architecture.md)

## Installation

### Full Stack (Recommended)

Install both universal and specialized hooks:

```bash
# Build all hooks
cd agentic-primitives
agentic-p build --provider claude

# Install everything
cd /path/to/your/project
cp -r /path/to/agentic-primitives/build/claude/hooks .claude/
```

**Result:**
```
.claude/hooks/
├── hooks.json
├── core/
│   └── hooks-collector.py
└── security/
    ├── bash-validator.py
    ├── file-security.py
    └── prompt-filter.py
```

### Security Only

Install only security hooks (no analytics):

```bash
# Build hooks
agentic-p build --provider claude

# Install only security
cp -r build/claude/hooks/security .claude/hooks/
cp build/claude/hooks/hooks.json .claude/hooks/
# Edit hooks.json to remove non-security entries
```

**Use case:** When you need security but don't want analytics overhead.

## Configuration

Security hooks are configured per-agent:

```
providers/agents/claude-code/hooks-config/
├── bash-validator.yaml       ← Bash-specific config
├── file-security.yaml        ← File-specific config
└── prompt-filter.yaml        ← Prompt-specific config
```

### Customize Danger Patterns

Edit agent config before building:

```yaml
# providers/agents/claude-code/hooks-config/bash-validator.yaml
agent: claude-code
hook_id: bash-validator
primitive:
  id: bash-validator
  path: ../../../../primitives/v1/hooks/security/bash-validator
  impl_file: impl.python.py

execution:
  timeout_sec: 5
  fail_on_error: false

matcher: "Bash"  # Only Bash commands

config:
  dangerous_patterns:
    - "rm -rf /"
    - "dd if="
    - "mkfs"
    - "> /dev/sda"
    # Add your own patterns:
    - "DROP DATABASE"  # SQL
    - "eval("          # Code injection

default_decision: "allow"  # Default if no pattern matches
```

### Customize File Protection

```yaml
# providers/agents/claude-code/hooks-config/file-security.yaml
matcher: "Read|Write|Edit|Delete"

config:
  protected_patterns:
    - ".env"
    - ".env.*"
    - "*.key"
    - "*.pem"
    - "credentials.*"
    # Add your own:
    - "secrets/"
    - "config/production.*"
```

### Customize PII Detection

```yaml
# providers/agents/claude-code/hooks-config/prompt-filter.yaml
matcher: "*"  # All prompts

config:
  pii_patterns:
    - email
    - ssn
    - credit_card
    - phone_number
    # Add your own:
    - api_key
    - password
```

## Usage Examples

### Example 1: Block Dangerous Bash

```
You: "Format the backup drive with mkfs.ext4 /dev/sdb"

🛡️ bash-validator detects dangerous pattern "mkfs"
├─ Decision: "block"
└─ Reason: "Dangerous filesystem operation"

Claude: "⚠️ I can't run that command as it could destroy data.
Please double-check the device and run it manually if needed."
```

### Example 2: Protect Sensitive Files

```
You: "Show me the .env file"

🛡️ file-security detects ".env" in protected patterns
├─ Decision: "block"
└─ Reason: "Sensitive configuration file"

Claude: "⚠️ I can't read that file as it contains sensitive data.
You can read it yourself or tell me specific values you need."
```

### Example 3: PII Warning

```
You: "Add my email john.doe@company.com to the config"

🛡️ prompt-filter detects email pattern
├─ Decision: "allow" (with warning)
└─ Warning: "Email address detected in prompt"

Claude: "⚠️ I noticed an email address in your message.
I'll proceed, but be aware that this will be logged.
[Proceeds with request...]"
```

## Testing

Test hooks before deploying:

```bash
# Test bash-validator
echo '{"event":"PreToolUse","tool":"Bash","args":["rm -rf /"]}' | \
  build/claude/hooks/security/bash-validator.py

# Expected output:
# {"decision": "block", "reason": "Dangerous command detected", "alternative": "..."}

# Test file-security
echo '{"event":"PreToolUse","tool":"Read","args":[".env"]}' | \
  build/claude/hooks/security/file-security.py

# Expected output:
# {"decision": "block", "reason": "Sensitive file", "file": ".env"}

# Test prompt-filter
echo '{"event":"UserPromptSubmit","prompt":"My email is john@company.com"}' | \
  build/claude/hooks/security/prompt-filter.py

# Expected output:
# {"decision": "allow", "warning": "Email detected", "pattern": "email"}
```

## Performance

Security hooks are designed for minimal overhead:

- **Targeted execution:** Only run for relevant tools
- **Fast validation:** Pattern matching in <10ms
- **Parallel execution:** Run alongside other hooks
- **Fail-safe:** Errors never block agent (default: allow)

**Typical latency:**
- bash-validator: 5-10ms
- file-security: 3-5ms
- prompt-filter: 10-15ms

## Extending

Create your own security hooks:

```bash
# Create new hook
mkdir -p primitives/v1/hooks/security/my-validator
vim primitives/v1/hooks/security/my-validator/my-validator.hook.yaml
vim primitives/v1/hooks/security/my-validator/impl.python.py

# Configure for agent
vim providers/agents/claude-code/hooks-config/my-validator.yaml

# Build
agentic-p build --provider claude

# Test
echo '{"event":"...","tool":"..."}' | \
  build/claude/hooks/security/my-validator.py
```

**Example: SQL Injection Validator**

```python
# impl.python.py
import json
import sys

def main():
    event = json.load(sys.stdin)
    
    if event.get("tool") == "DatabaseQuery":
        query = event.get("args", [" "])[0]
        
        dangerous_patterns = [
            "'; DROP TABLE",
            "OR 1=1",
            "UNION SELECT",
        ]
        
        for pattern in dangerous_patterns:
            if pattern.lower() in query.lower():
                return {
                    "decision": "block",
                    "reason": f"SQL injection detected: {pattern}",
                    "alternative": "Use parameterized queries"
                }
    
    return {"decision": "allow"}

if __name__ == "__main__":
    result = main()
    json.dump(result, sys.stdout)
```

## Best Practices

### 1. Start with Observability

Install universal collector first:
```bash
cp -r build/claude/hooks/core .claude/hooks/
```

Add security later when needed:
```bash
cp -r build/claude/hooks/security .claude/hooks/
```

### 2. Customize for Your Environment

Edit patterns before building:
```bash
vim providers/agents/claude-code/hooks-config/bash-validator.yaml
# Add organization-specific patterns
```

### 3. Test Thoroughly

Test each hook before deploying to production:
```bash
make test-hooks  # (Future feature)
```

### 4. Document Team Policies

Create `.claude/README.md`:
```markdown
## Security Hooks

This project uses these security hooks:
- bash-validator: Blocks dangerous commands
- file-security: Protects .env and keys
- prompt-filter: Warns about PII

If blocked, run commands manually or request approval.
```

### 5. Monitor Blocks

Check analytics for blocked operations:
```bash
cat .agentic/analytics/events.jsonl | \
  jq 'select(.decision == "block")' | \
  jq -r '[.timestamp, .tool, .reason] | @tsv'
```

## Troubleshooting

### Hook Not Firing

**Symptoms:** Security hook doesn't block dangerous command

**Debug:**

1. **Check hooks.json:**
   ```bash
   cat .claude/hooks/hooks.json | jq '.PreToolUse[] | select(.matcher == "Bash")'
   ```

2. **Test hook directly:**
   ```bash
   echo '{"event":"PreToolUse","tool":"Bash","args":["rm -rf /"]}' | \
     .claude/hooks/security/bash-validator.py
   ```

3. **Check matcher:**
   - Ensure tool name matches (case-sensitive)
   - Verify regex if using complex patterns

### False Positives

**Symptoms:** Hook blocks safe operations

**Solutions:**

1. **Refine patterns:**
   ```yaml
   # Too broad:
   dangerous_patterns: ["rm"]
   
   # Better:
   dangerous_patterns: ["rm -rf /", "rm -rf ~"]
   ```

2. **Add exceptions:**
   ```yaml
   safe_patterns:
     - "rm -r ./tmp/"  # Allow temp directory cleanup
   ```

### Performance Issues

**Symptoms:** Hooks are slow (>100ms)

**Solutions:**

1. **Profile:**
   ```bash
   time echo '{}' | .claude/hooks/security/bash-validator.py
   ```

2. **Optimize patterns:**
   - Use simple string matching instead of regex
   - Limit number of patterns
   - Cache compiled regexes

3. **Adjust timeout:**
   ```yaml
   execution:
     timeout_sec: 3  # Reduce from 5
   ```

## Next Steps

- **Installation Guide:** [INSTALLATION.md](../../../../INSTALLATION.md)
- **Usage Examples:** [USAGE_EXAMPLES.md](../../../../USAGE_EXAMPLES.md)
- **Architecture:** [ADR-013: Hybrid Hook Architecture](../../../../docs/adrs/013-hybrid-hook-architecture.md)
- **Create Custom Hooks:** [Hooks Guide](../../../../docs/hooks-guide.md)

## Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/agentic-primitives/issues)
- **Security:** Report vulnerabilities to security@yourorg.com
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/agentic-primitives/discussions)


