# Claude Code Hooks Integration Example

**Purpose:** Demonstrate agentic-primitives hooks working with the Claude Agent SDK in Python.

This example shows:
- ✅ Hooks firing during real agent execution
- ✅ Analytics collection in `.agentic/analytics/events.jsonl`
- ✅ Security hooks blocking dangerous operations
- ✅ Observability across all agent interactions

## Prerequisites

1. **Claude API Key:**
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   ```

2. **UV installed:**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Build the hooks:**
   ```bash
   cd ../..
   cargo run --manifest-path cli/Cargo.toml -- build --provider claude
   ```

## Setup

The hooks are already installed in `.claude/` directory. They include:

**Universal Collector (`hooks-collector`):**
- Captures all 9 Claude events
- Logs to `.agentic/analytics/events.jsonl`
- Never blocks operations

**Security Hooks:**
- `bash-validator` - Blocks dangerous bash commands (rm -rf, dd, etc.)
- `file-security` - Protects sensitive files (.env, keys, credentials)
- `prompt-filter` - Warns about PII in prompts

## Running the Example

### Option 1: Interactive Demo

```bash
./demo.sh
```

This will:
1. Start a Claude agent with hooks enabled
2. Execute a series of tasks (safe and dangerous)
3. Show hooks firing in real-time
4. Display collected analytics

### Option 2: Run Python Script Directly

```bash
uv run python main.py
```

### Option 3: Specific Scenarios

```bash
# Test dangerous bash command (should be blocked)
uv run python main.py --scenario dangerous-bash

# Test safe operations (should pass)
uv run python main.py --scenario safe-ops

# Test file security (should block .env access)
uv run python main.py --scenario sensitive-file

# Test PII detection (should warn)
uv run python main.py --scenario pii-prompt
```

## What to Observe

### 1. Console Output

Watch for hook decisions in real-time:

```
🛡️ Hook: bash-validator
   Event: PreToolUse
   Tool: Bash
   Command: rm -rf /
   Decision: ❌ BLOCKED
   Reason: Dangerous command detected
   Alternative: Use specific paths, not root directory

✅ Hook: hooks-collector
   Event: PreToolUse
   Logged to: .agentic/analytics/events.jsonl
```

### 2. Analytics File

Check `.agentic/analytics/events.jsonl`:

```bash
# View all events
cat .agentic/analytics/events.jsonl | jq '.'

# Count events by type
cat .agentic/analytics/events.jsonl | jq -r '.event_type' | sort | uniq -c

# See tool usage
cat .agentic/analytics/events.jsonl | jq 'select(.event_type == "tool_execution_started") | .tool_name'

# Find blocked operations
cat .agentic/analytics/events.jsonl | jq 'select(.decision == "block")'
```

### 3. Hook Files

The hooks are organized by category:

```
.claude/hooks/
├── core/
│   └── hooks-collector.py       ← Universal observability
├── security/
│   ├── bash-validator.py        ← Bash security
│   ├── file-security.py         ← File protection
│   └── prompt-filter.py         ← PII detection
└── analytics/
    └── analytics-collector.py   ← Legacy analytics
```

### 4. Settings Configuration

View `.claude/settings.json` to see how hooks are registered:

```bash
cat .claude/settings.json | jq '.hooks.PreToolUse'
```

## Expected Results

### Scenario: Safe Operations

```
Task: List files in current directory
Hook: hooks-collector → ✅ Allow (logged)
Hook: bash-validator → ✅ Allow
Result: Files listed successfully
Analytics: Event logged to .agentic/analytics/events.jsonl
```

### Scenario: Dangerous Bash Command

```
Task: Delete all files with rm -rf /
Hook: hooks-collector → ✅ Allow (logged, never blocks)
Hook: bash-validator → ❌ BLOCK
Result: Operation blocked before execution
Analytics: Blocked event logged
Alternative: Suggested safer command
```

### Scenario: Sensitive File Access

```
Task: Read .env file
Hook: hooks-collector → ✅ Allow (logged)
Hook: file-security → ❌ BLOCK
Result: File access denied
Analytics: Access attempt logged
Reason: Sensitive configuration file
```

### Scenario: PII in Prompt

```
Task: "Add my email john@company.com to config"
Hook: hooks-collector → ✅ Allow (logged)
Hook: prompt-filter → ⚠️ WARN (allows with warning)
Result: Prompt processed with warning
Analytics: PII detection logged
Warning: Email address detected in prompt
```

## Understanding the Output

### Hook Execution Flow

```
User → Claude Agent → PreToolUse Event → Hooks Fire (Parallel)
                                          ├─ hooks-collector (logs)
                                          ├─ bash-validator (validates)
                                          └─ file-security (protects)
                                          ↓
                                      All hooks return decisions
                                          ↓
                                      Agent combines decisions
                                      (block wins, allow if all allow)
                                          ↓
                                      Tool executes (if allowed)
```

### Analytics Data Structure

Each event in `.agentic/analytics/events.jsonl`:

```json
{
  "event_id": "evt_abc123",
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-24T12:00:00Z",
  "session_id": "sess_xyz789",
  "provider": "claude",
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la"},
  "decision": "allow",
  "metadata": {
    "hook": "bash-validator",
    "duration_ms": 5
  }
}
```

## Customization

### Adjust Hook Behavior

Edit hook configs before building:

```bash
# Make bash-validator more strict
vim ../../providers/agents/claude-code/hooks-config/bash-validator.yaml

# Add custom patterns
dangerous_patterns:
  - "DROP DATABASE"
  - "eval("
```

Then rebuild:

```bash
cd ../.. && cargo run --manifest-path cli/Cargo.toml -- build --provider claude
cp -r build/claude/.claude examples/000-claude-integration/
```

### Change Analytics Backend

Edit hooks-collector config to use API instead of file:

```yaml
middleware:
  - id: event_publisher
    config:
      backend: api
      api_endpoint: https://your-analytics-api.com/events
      api_key: ${ANALYTICS_API_KEY}
```

### Disable Specific Hooks

Edit `.claude/settings.json` to remove unwanted hooks:

```bash
# Remove file-security hook
jq 'del(.hooks.PreToolUse[] | select(.hooks[0].command | contains("file-security")))' .claude/settings.json > tmp.json
mv tmp.json .claude/settings.json
```

## Troubleshooting

### Hooks Not Firing

1. **Check settings.json exists:**
   ```bash
   ls -la .claude/settings.json
   ```

2. **Verify hook paths:**
   ```bash
   cat .claude/settings.json | jq '.hooks.PreToolUse[0].hooks[0].command'
   ```

3. **Test hook manually:**
   ```bash
   echo '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"}}' | \
     .claude/hooks/security/bash-validator.py
   ```

### No Analytics Data

1. **Check output directory:**
   ```bash
   ls -la .agentic/analytics/
   ```

2. **Verify hooks-collector is registered:**
   ```bash
   cat .claude/settings.json | jq '.hooks | keys'
   ```

3. **Check hook execution:**
   ```bash
   # Run with debug output
   DEBUG=1 uv run python main.py
   ```

### Permission Errors

```bash
# Make hooks executable
chmod +x .claude/hooks/**/*.py
```

## Next Steps

- **Try your own tasks:** Modify `main.py` to test different scenarios
- **Add custom hooks:** See [Creating Custom Hooks](../../docs/hooks-guide.md)
- **Deploy to production:** Copy `.claude/` to your actual projects
- **Team setup:** Share hook configurations with your team

## Resources

- [Installation Guide](../../INSTALLATION.md)
- [Usage Examples](../../USAGE_EXAMPLES.md)
- [Hybrid Hook Architecture](../../docs/adrs/013-hybrid-hook-architecture.md)
- [Claude Code Hooks Documentation](https://docs.claude.com/en/docs/claude-code/hooks)


