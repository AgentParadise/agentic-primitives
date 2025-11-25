# Usage Examples

Real-world scenarios showing how to use Agentic Primitives hooks effectively.

## Table of Contents

- [Scenario 1: Complete Observability](#scenario-1-complete-observability)
- [Scenario 2: Security-First Development](#scenario-2-security-first-development)
- [Scenario 3: Regulated Environment](#scenario-3-regulated-environment)
- [Scenario 4: Personal Productivity](#scenario-4-personal-productivity)
- [Scenario 5: Team Collaboration](#scenario-5-team-collaboration)
- [Scenario 6: Cost Tracking](#scenario-6-cost-tracking)
- [Scenario 7: Debug & Troubleshooting](#scenario-7-debug--troubleshooting)

---

## Scenario 1: Complete Observability

**Goal:** Track all agent interactions for analytics and debugging.

### Setup

```bash
# Build hooks
cd agentic-primitives
agentic-p build --provider claude

# Install observability hooks
cd /path/to/your/project
mkdir -p .claude/hooks
cp -r /path/to/agentic-primitives/build/claude/hooks/core .claude/hooks/
cp -r /path/to/agentic-primitives/build/claude/hooks/analytics .claude/hooks/
cp /path/to/agentic-primitives/build/claude/hooks/hooks.json .claude/hooks/
```

### What You Get

**hooks-collector** captures all 9 Claude events:
- `PreToolUse` - Before every tool execution
- `PostToolUse` - After every tool execution
- `UserPromptSubmit` - Every user message
- `SessionStart` - Session begins
- `SessionEnd` - Session ends
- `Stop` - Agent stops
- `SubagentStop` - Subagent stops
- `PreCompact` - Before context compaction
- `Notification` - System notifications

**analytics-collector** processes and stores event data:
- Normalized JSON format
- Published to `.agentic/analytics/events.jsonl`
- Ready for analysis

### Usage

```bash
# Work normally with Claude Code
# All interactions are automatically tracked

# View analytics
cat .agentic/analytics/events.jsonl | jq '.'

# Count tool uses
cat .agentic/analytics/events.jsonl | jq 'select(.event == "PreToolUse")' | wc -l

# Find bash commands
cat .agentic/analytics/events.jsonl | jq 'select(.tool == "Bash") | .args'

# Session duration
cat .agentic/analytics/events.jsonl | jq 'select(.event == "SessionStart" or .event == "SessionEnd") | {event, timestamp}'
```

### Sample Output

```json
{
  "event": "PreToolUse",
  "tool": "Bash",
  "args": ["ls", "-la"],
  "timestamp": "2025-11-24T10:30:15.123Z",
  "session_id": "abc123",
  "normalized": true
}
```

---

## Scenario 2: Security-First Development

**Goal:** Block dangerous operations and protect sensitive files.

### Setup

```bash
# Install security + observability hooks
cd /path/to/your/project
mkdir -p .claude/hooks

cp -r /path/to/agentic-primitives/build/claude/hooks/core .claude/hooks/
cp -r /path/to/agentic-primitives/build/claude/hooks/security .claude/hooks/
cp /path/to/agentic-primitives/build/claude/hooks/hooks.json .claude/hooks/
```

### What You Get

**bash-validator** (Matcher: "Bash"):
- Detects dangerous commands (rm -rf, dd, mkfs, etc.)
- Returns decision: "block" or "allow"
- Provides safe alternatives

**file-security** (Matcher: "Read|Write|Edit|Delete"):
- Protects sensitive files (.env, credentials, keys)
- Blocks unauthorized access
- Logs all file operations

**prompt-filter** (Matcher: "*"):
- Scans prompts for PII (emails, SSNs, credit cards)
- Detects hardcoded credentials
- Warns before sending sensitive data

### Usage Example: Dangerous Command

```
You: "Delete all log files with rm -rf logs/"

🛡️ Claude Code calls bash-validator hook
├─ Detects: "rm -rf" pattern
├─ Decision: "block"
└─ Alternative: "Use 'rm -r logs/' or 'find logs/ -name '*.log' -delete'"

Claude: "⚠️ That command is too dangerous. Let me suggest a safer alternative..."
```

### Usage Example: Sensitive File

```
You: "Show me the contents of .env"

🛡️ Claude Code calls file-security hook
├─ Detects: ".env" in protected patterns
├─ Decision: "block"
└─ Reason: "Sensitive configuration file"

Claude: "⚠️ I can't read that file as it contains sensitive configuration..."
```

### Usage Example: PII Detection

```
You: "Add my email john@company.com to the config"

🛡️ Claude Code calls prompt-filter hook
├─ Detects: Email pattern "john@company.com"
├─ Decision: "allow" (with warning)
└─ Warning: "Email address detected in prompt"

Claude: "⚠️ I noticed an email address in your message. Proceeding with caution..."
```

### Configuration

Customize security policies:

```yaml
# providers/agents/claude-code/hooks-config/bash-validator.yaml
middleware:
  - id: bash_validator
    config:
      dangerous_patterns:
        - "rm -rf /"
        - "dd if="
        - "mkfs"
        - "> /dev/sda"
      custom_patterns:
        - "DROP DATABASE"  # SQL injection
        - "eval("          # Code injection
```

---

## Scenario 3: Regulated Environment

**Goal:** Full audit trail for compliance (HIPAA, SOC 2, etc.).

### Setup

```bash
# Install all hooks + custom audit middleware
cd /path/to/your/project
mkdir -p .claude/hooks

# Copy all hooks
cp -r /path/to/agentic-primitives/build/claude/hooks/* .claude/hooks/

# Configure audit backend
vim providers/agents/claude-code/hooks-config/hooks-collector.yaml
```

**Edit configuration:**
```yaml
middleware:
  - id: event_publisher
    config:
      backend: api  # Send to compliance system
      api_endpoint: https://audit.company.com/api/events
      api_key: ${AUDIT_API_KEY}
      retry: true
      batch_size: 100
```

### What You Get

- ✅ **Complete audit trail** of all AI interactions
- ✅ **Immutable logs** sent to compliance system
- ✅ **Security controls** with block/allow decisions
- ✅ **Sensitive data protection** (PII scanning)
- ✅ **Tool usage tracking** (who did what, when)

### Compliance Reports

```bash
# Daily activity report
curl https://audit.company.com/api/reports/daily?date=2025-11-24

# User activity
curl https://audit.company.com/api/reports/user?email=john@company.com

# Blocked operations
curl https://audit.company.com/api/reports/blocked?date=2025-11-24
```

---

## Scenario 4: Personal Productivity

**Goal:** Lightweight observability without heavy security.

### Setup

```bash
# Install only hooks-collector (universal observability)
cd /path/to/your/project
mkdir -p .claude/hooks/core

cp /path/to/agentic-primitives/build/claude/hooks/hooks.json .claude/hooks/
cp -r /path/to/agentic-primitives/build/claude/hooks/core .claude/hooks/

# Edit hooks.json to keep only hooks-collector entries
vim .claude/hooks/hooks.json
```

**Simplified hooks.json:**
```json
{
  "PreToolUse": [
    {"matcher": "*", "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/core/hooks-collector.py"}]}
  ],
  "PostToolUse": [
    {"matcher": "*", "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/core/hooks-collector.py"}]}
  ],
  "UserPromptSubmit": [
    {"matcher": "*", "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/core/hooks-collector.py"}]}
  ]
}
```

### What You Get

- ✅ Lightweight analytics
- ✅ No security blocking (work uninterrupted)
- ✅ Track your productivity
- ✅ Debug when needed

### Productivity Insights

```bash
# Tools you use most
cat .agentic/analytics/events.jsonl | jq -r 'select(.event=="PreToolUse") | .tool' | sort | uniq -c | sort -rn

# Sessions per day
cat .agentic/analytics/events.jsonl | jq -r 'select(.event=="SessionStart") | .timestamp[:10]' | sort | uniq -c

# Prompts per session
cat .agentic/analytics/events.jsonl | jq 'select(.event=="UserPromptSubmit") | .session_id' | sort | uniq -c
```

---

## Scenario 5: Team Collaboration

**Goal:** Shared hooks across team with project-specific overrides.

### Setup

**Team lead sets up global defaults:**
```bash
# Install global observability hooks
mkdir -p ~/.claude/hooks
cp -r /path/to/agentic-primitives/build/claude/hooks/core ~/.claude/hooks/
cp -r /path/to/agentic-primitives/build/claude/hooks/analytics ~/.claude/hooks/
cp /path/to/agentic-primitives/build/claude/hooks/hooks.json ~/.claude/hooks/

# Configure team analytics backend
vim ~/claude/hooks/core/hooks-collector.py
# (Edit to point to team analytics server)
```

**Project-specific security:**
```bash
# In high-security project
cd /path/to/secure/project
mkdir -p .claude/hooks

# Add security hooks (overrides global)
cp -r /path/to/agentic-primitives/build/claude/hooks/security .claude/hooks/
# Edit hooks.json to add security hooks
```

### What You Get

- ✅ **Consistent observability** across all team projects
- ✅ **Project-specific security** where needed
- ✅ **Team analytics** aggregated to central system
- ✅ **Easy onboarding** (global hooks work immediately)

### Team Dashboard

```bash
# Team activity (if using API backend)
curl https://analytics.company.com/api/team/dashboard

# Most active team members
curl https://analytics.company.com/api/team/leaderboard

# Common error patterns
curl https://analytics.company.com/api/team/errors
```

---

## Scenario 6: Cost Tracking

**Goal:** Track token usage and API costs.

### Setup

**Create custom middleware:**
```python
# services/custom-middleware/token_tracker.py
import json
import sys
from pathlib import Path

def main():
    # Read event from stdin
    event_data = json.load(sys.stdin)
    
    # Track token usage (if available)
    if "tokens" in event_data:
        tokens = event_data["tokens"]
        cost = calculate_cost(tokens, event_data.get("model"))
        
        # Append to cost log
        cost_log = Path(".agentic/costs/token_usage.jsonl")
        cost_log.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cost_log, "a") as f:
            json.dump({
                "timestamp": event_data.get("timestamp"),
                "tokens": tokens,
                "cost_usd": cost,
                "model": event_data.get("model")
            }, f)
            f.write("\n")
    
    # Pass through unchanged
    json.dump(event_data, sys.stdout)

def calculate_cost(tokens, model):
    # Simplified cost calculation
    rates = {
        "claude-3-opus": 0.015 / 1000,   # per input token
        "claude-3-sonnet": 0.003 / 1000,
        "claude-3-haiku": 0.00025 / 1000,
    }
    return tokens * rates.get(model, 0.003)

if __name__ == "__main__":
    main()
```

**Add to hook config:**
```yaml
# providers/agents/claude-code/hooks-config/hooks-collector.yaml
middleware:
  - id: token_tracker
    path: ../../../../services/custom-middleware/token_tracker.py
    type: action
    enabled: true
    events: ["PostToolUse", "Stop"]  # After operations
    priority: 60
```

### Usage

```bash
# Rebuild with custom middleware
agentic-p build --provider claude

# Install
cp -r build/claude/hooks /path/to/project/.claude/

# Use Claude Code normally
# Token costs are tracked automatically

# View costs
cat .agentic/costs/token_usage.jsonl | jq '.cost_usd' | paste -sd+ | bc

# Daily costs
cat .agentic/costs/token_usage.jsonl | jq -r '[.timestamp[:10], .cost_usd] | @tsv' | \
  awk '{sums[$1]+=$2} END {for (date in sums) print date, sums[date]}'
```

---

## Scenario 7: Debug & Troubleshooting

**Goal:** Detailed debugging when things go wrong.

### Setup

**Enable verbose logging:**
```yaml
# providers/agents/claude-code/hooks-config/hooks-collector.yaml
middleware:
  - id: debug_logger
    path: ../../../../services/custom-middleware/debug_logger.py
    type: action
    enabled: true
    events: ["*"]
    priority: 5  # Run first
    config:
      log_file: .agentic/debug/hooks.log
      log_level: DEBUG
      include_full_payload: true
```

### Usage

```bash
# Enable debug mode
export AGENTIC_DEBUG=1

# Run Claude Code
# All hooks log verbosely to .agentic/debug/hooks.log

# Tail logs in real-time
tail -f .agentic/debug/hooks.log

# Search for errors
grep ERROR .agentic/debug/hooks.log

# Filter by event
grep "PreToolUse" .agentic/debug/hooks.log | jq '.'
```

### Debug Output Example

```
[2025-11-24T10:30:15.123Z] DEBUG hooks-collector - Event received
{
  "event": "PreToolUse",
  "tool": "Bash",
  "args": ["ls", "-la"],
  "raw_payload": {...}
}

[2025-11-24T10:30:15.125Z] DEBUG middleware:event_normalizer - Normalizing event
[2025-11-24T10:30:15.126Z] DEBUG middleware:event_normalizer - Normalized successfully

[2025-11-24T10:30:15.127Z] DEBUG middleware:event_publisher - Publishing event
[2025-11-24T10:30:15.128Z] DEBUG middleware:event_publisher - Published to file: .agentic/analytics/events.jsonl

[2025-11-24T10:30:15.129Z] DEBUG hooks-collector - Decision: allow
```

---

## Common Patterns

### Pattern 1: Conditional Hook Execution

Use matchers to control when hooks fire:

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash",  // Only bash commands
      "hooks": [{"type": "command", "command": "..."}]
    },
    {
      "matcher": "Read|Write|Edit|Delete",  // Only file operations
      "hooks": [{"type": "command", "command": "..."}]
    }
  ]
}
```

### Pattern 2: Parallel Hooks

Multiple hooks run in parallel for the same event:

```json
{
  "PreToolUse": [
    {"matcher": "*", "hooks": [{"command": "...hooks-collector.py"}]},  // Observability
    {"matcher": "Bash", "hooks": [{"command": "...bash-validator.py"}]},  // Security
    {"matcher": "*", "hooks": [{"command": "...custom-logger.py"}]}  // Custom
  ]
}
```

All three run simultaneously when a Bash command is executed.

### Pattern 3: Sequential Middleware

Middleware runs in priority order within a hook:

```yaml
middleware:
  - id: validate
    priority: 10  // First
  - id: transform
    priority: 20  // Second
  - id: publish
    priority: 30  // Third
```

### Pattern 4: Event-Specific Middleware

Middleware only runs for specific events:

```yaml
middleware:
  - id: security_check
    events: ["PreToolUse"]  // Only before tools
  - id: result_logger
    events: ["PostToolUse"]  // Only after tools
  - id: analytics
    events: ["*"]  // All events
```

---

## Best Practices

### 1. Start Simple

Begin with observability only:
```bash
# Just hooks-collector for analytics
cp -r build/claude/hooks/core .claude/hooks/
```

Add security later:
```bash
# Add security when needed
cp -r build/claude/hooks/security .claude/hooks/
```

### 2. Test Before Deploying

```bash
# Test hook execution
echo '{"event":"PreToolUse","tool":"Bash","args":["ls"]}' | \
  .claude/hooks/core/hooks-collector.py

# Verify output
cat .agentic/analytics/events.jsonl
```

### 3. Version Control

```bash
# Commit hooks with your project
git add .claude/
git commit -m "Add agentic hooks for observability"
```

### 4. Document Team Policies

```markdown
# .claude/README.md

## Hooks Configuration

This project uses the following hooks:

- **hooks-collector**: Tracks all agent interactions
- **bash-validator**: Blocks dangerous bash commands
- **file-security**: Protects sensitive files (.env, keys)

Analytics are stored in `.agentic/analytics/events.jsonl`.

### For developers:

To update hooks, run:
\`\`\`bash
cd agentic-primitives
agentic-p build --provider claude
cp -r build/claude/hooks /path/to/project/.claude/
\`\`\`
```

### 5. Monitor Performance

```bash
# Check hook execution time
cat .agentic/analytics/events.jsonl | jq '.hook_duration_ms' | \
  awk '{sum+=$1; count++} END {print "Avg:", sum/count, "ms"}'
```

If hooks are slow (>100ms), optimize middleware.

---

## Next Steps

- **Installation Guide:** See [INSTALLATION.md](./INSTALLATION.md) for setup details
- **Architecture:** See [docs/adrs/013-hybrid-hook-architecture.md](./docs/adrs/013-hybrid-hook-architecture.md)
- **Create Custom Hooks:** See [docs/hooks-guide.md](./docs/hooks-guide.md)
- **Contributing:** See [CONTRIBUTING.md](./docs/contributing.md)

---

## Support

Have questions or ideas? Open a discussion on [GitHub](https://github.com/yourusername/agentic-primitives/discussions)!


