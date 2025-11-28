# Claude Code Hook Configurations

This directory contains agent-specific configurations for hook primitives used with Claude Code.

## Purpose

Hook configurations define:
- **Which primitive** to use (via `primitive.path`)
- **Middleware pipeline** specific to Claude Code's needs
- **Event filtering** for middleware (validated against `hooks-supported.yaml`)
- **Execution overrides** for this specific agent

## Configuration Files

### Security Hooks

- `bash-validator.yaml` - Dangerous command detection
- `file-security.yaml` - Sensitive file protection  
- `prompt-filter.yaml` - PII/credential scanning

Each security hook **self-logs** its decisions to the analytics service.

**Usage:**
```bash
agentic-p build --provider claude
agentic-p install --provider claude --project
```

### Analytics Hooks

- `analytics-collector.yaml` - Session tracking and metrics

## Configuration Schema

All hook config files must follow the schema defined in:
```
providers/.schemas/hook-config.schema.json
```

## Key Concepts

### 1. Primitive Reference

```yaml
primitive:
  id: bash-validator
  path: "../../../../primitives/v1/hooks/security/bash-validator"
  impl_file: "bash-validator.py"
```

Points to the generic hook implementation in `primitives/`. The primitive is reusable across multiple agents.

### 2. Middleware Configuration

```yaml
middleware:
  - id: "analytics-normalizer"
    path: "../../../../services/analytics/middleware/event_normalizer.py"
    type: analytics
    enabled: true
    events: ["*"]  # Or specific events: ["PreToolUse", "PostToolUse"]
    priority: 10
```

Each agent can enable/disable different middleware and specify which events trigger each middleware component.

### 3. Event Validation

All `events` specified in middleware are validated against `../hooks-supported.yaml` during build time. Invalid events will cause a build error.

**Example:**
```yaml
# ✅ Valid - Claude Code supports PreToolUse
events: ["PreToolUse"]

# ❌ Invalid - Claude Code doesn't support this event
events: ["CustomEvent"]

# ✅ Valid - "*" means all supported events
events: ["*"]
```

### 4. Execution Overrides

```yaml
execution:
  strategy: parallel
  timeout_sec: 10
  fail_on_error: false
```

Override the primitive's default execution settings for this specific agent.

## Build Process

When building hooks for Claude Code:

1. **Load agent config:** `hooks-supported.yaml` defines available events
2. **Load hook config:** This directory defines which hooks to use
3. **Validate:** Middleware events checked against supported events
4. **Generate:** `hooks.json` with all events + Python wrapper
5. **Runtime:** Wrapper passes agent-specific config to orchestrator

## Examples

### Enable only analytics

```yaml
middleware:
  - id: "analytics-normalizer"
    enabled: true
  - id: "safety-validator"
    enabled: false  # Disabled
```

### Event-specific middleware

```yaml
middleware:
  - id: "safety-validator"
    enabled: true
    events: ["PreToolUse", "PostToolUse"]  # Only on tool use
  - id: "session-logger"
    enabled: true
    events: ["SessionStart", "SessionEnd"]  # Only on session events
```

### Custom middleware

```yaml
middleware:
  - id: "custom-processor"
    path: "../../../../services/custom/my_middleware.py"
    type: custom
    enabled: true
    events: ["*"]
    priority: 50
    config:
      custom_setting: "value"
```

## Contributing

When adding new hook configurations:

1. Create YAML file in this directory
2. Reference a valid primitive from `primitives/`
3. Configure middleware for Claude Code's needs
4. Test with: `agentic-p build --agent claude-code --hook <your-hook>`
5. Validate with: `agentic-p providers validate --agent claude-code`



