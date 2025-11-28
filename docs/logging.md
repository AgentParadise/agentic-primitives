# Centralized Logging System

This document describes the centralized logging system implemented across all Python code in the agentic-primitives repository.

## Overview

The agentic logging system provides a unified, AI-agent-optimized logging infrastructure that works across all Python services, hooks, and utilities in the repository.

### Key Features

- **Zero Configuration**: Works out of the box with sensible defaults
- **AI-Optimized**: JSON output for easy parsing, structured context fields
- **Granular Control**: Per-component log level configuration via environment variables
- **Session Tracking**: Automatic session ID correlation across distributed operations
- **Fail-Safe Design**: Logging errors never crash your application
- **Human-Friendly**: Optional human-readable console output with color and structure

## Quick Start

### Basic Usage

```python
from agentic_logging import get_logger

logger = get_logger(__name__)

logger.info("Processing started")
logger.debug("Detailed information", extra={"user_id": 123})
logger.error("Something failed", exc_info=True)
```

### With Session Tracking

```python
from agentic_logging import get_logger

# Pass session_id explicitly
session_id = hook_event.get('session_id')
logger = get_logger(__name__, session_id=session_id)

logger.info("Processing event", extra={"event_type": "PreToolUse"})
```

## Configuration

All configuration is done via environment variables:

### System-Wide Settings

```bash
# Default log level (default: WARNING)
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR|CRITICAL

# Log file path (default: ./logs/agentic.jsonl)
LOG_FILE=./logs/my-app.jsonl

# Console output format (default: human)
LOG_CONSOLE_FORMAT=human|json

# File rotation settings
LOG_MAX_BYTES=10485760      # 10MB default
LOG_BACKUP_COUNT=5          # Keep 5 backups
```

### Per-Component Log Levels

Override the log level for specific components:

```bash
# Format: LOG_LEVEL_{NORMALIZED_COMPONENT_NAME}
# Component name: dots → underscores, UPPERCASE

# Example: hooks.core.hooks_collector
export LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR=DEBUG

# Example: analytics.publishers.file
export LOG_LEVEL_ANALYTICS_PUBLISHERS_FILE=INFO

# Example: security.bash_validator
export LOG_LEVEL_SECURITY_BASH_VALIDATOR=WARNING
```

**Component Name Normalization Rules:**
1. Replace `.` with `_`
2. Convert to UPPERCASE
3. Prefix with `LOG_LEVEL_`

## Log Levels

### When to Use Each Level

**DEBUG** - Detailed diagnostic information
- Use for: Development, troubleshooting, AI agent investigation
- Examples: Input/output values, state transitions, algorithm steps
- Production: Usually OFF (use per-component override when needed)

**INFO** - General informational messages
- Use for: Normal operation milestones, audit trails
- Examples: Service started, configuration loaded, operation completed
- Production: GOOD for high-level monitoring

**WARNING** (Default)
- Use for: Potentially problematic situations
- Examples: Degraded performance, deprecated API, recoverable errors
- Production: DEFAULT level

**ERROR** - Error events that might allow operation to continue
- Use for: Failed operations, external service failures
- Examples: API call failed, validation error, database timeout
- Production: ALWAYS logged

**CRITICAL** - Severe errors causing shutdown
- Use for: Unrecoverable failures
- Examples: Data corruption, security breaches
- Production: ALWAYS logged, triggers alerts

## Output Formats

### JSON Format (File + Optional Console)

All logs are written to file in JSONL format:

```json
{
  "timestamp": "2025-11-25T12:30:45.123456Z",
  "level": "INFO",
  "component": "hooks.core.hooks_collector",
  "session_id": "abc123",
  "message": "Middleware executed successfully",
  "event_type": "PreToolUse",
  "middleware_count": 3,
  "exc_info": null
}
```

**Standard Fields:**
- `timestamp`: ISO 8601 UTC with microseconds
- `level`: Log level name
- `component`: Module name (from `__name__`)
- `session_id`: Session identifier (if set)
- `message`: Log message
- `exc_info`: Exception traceback (if present)
- *All fields from `extra={}` parameter*

### Human Format (Console Default)

Developer-friendly console output:

```
[12:30:45.123] ℹ️  INFO    hooks.core.hooks_collector
  Middleware executed successfully
  ├─ session_id: abc123
  ├─ event_type: PreToolUse
  └─ middleware_count: 3
```

**Features:**
- Emoji indicators for quick scanning (🔍 ℹ️ ⚠️ ❌ 🚨)
- Minimal color (only on TTY terminals)
- Tree structure for context fields
- Millisecond-precision timestamps

## Common Use Cases

### For Development

```bash
# Debug everything
export LOG_LEVEL=DEBUG
export LOG_CONSOLE_FORMAT=human
python main.py
```

### For Production

```bash
# Quiet by default, errors to file
export LOG_LEVEL=WARNING
export LOG_FILE=/var/log/agentic/production.jsonl
export LOG_MAX_BYTES=52428800  # 50MB
export LOG_BACKUP_COUNT=10
python main.py
```

### For AI Agent Investigation

```bash
# Debug specific component, JSON output for parsing
export LOG_LEVEL=WARNING  # Quiet by default
export LOG_LEVEL_HOOKS_COLLECTOR=DEBUG  # Verbose for this component
export LOG_CONSOLE_FORMAT=json  # Machine-readable
python main.py 2>&1 | jq 'select(.component=="hooks.core.hooks_collector")'
```

### For Testing

```bash
# Capture all logs for test analysis
export LOG_LEVEL=DEBUG
export LOG_FILE=./test-logs/test-run.jsonl
pytest -v
```

## Integration Examples

### Analytics Service

```python
from agentic_logging import get_logger

logger = get_logger(__name__)  # analytics.publishers.file

async def publish(self, event: NormalizedEvent) -> None:
    try:
        await self._write_to_file(event)
        logger.debug("Event published", extra={
            "event_type": event.event_type,
            "session_id": event.session_id,
        })
    except Exception as e:
        logger.error("Failed to publish event", exc_info=True, extra={
            "event_type": event.event_type,
            "error": str(e),
        })
```

### Hooks

```python
from agentic_logging import get_logger

logger = get_logger(__name__)  # hooks.core.hooks_collector

async def execute(self, hook_event: Dict[str, Any]) -> Dict:
    try:
        # Extract session from event
        session_id = hook_event.get('session_id')
        
        logger.info("Executing middleware pipeline", extra={
            "session_id": session_id,
            "event_type": hook_event.get('event_type'),
        })
        
        result = await self._run_middleware(hook_event)
        
        logger.debug("Pipeline completed", extra={
            "middleware_executed": result.get('middleware_executed'),
        })
        
        return result
    except Exception as e:
        logger.error("Pipeline failed", exc_info=True)
        return {"action": "allow", "error": str(e)}
```

### Security Hooks

```python
from agentic_logging import get_logger

logger = get_logger(__name__)  # security.bash_validator

def validate_command(self, command: str) -> Dict[str, Any]:
    if dangerous_patterns:
        logger.warning("Dangerous command detected", extra={
            "command_preview": command[:100],
            "patterns": dangerous_patterns,
        })
        return {"safe": False, "reason": "..."}
    
    logger.debug("Command validated", extra={
        "command_preview": command[:100],
    })
    return {"safe": True}
```

## Troubleshooting

### Logs Not Appearing in File

**Check 1**: Directory permissions

```bash
ls -la logs/
# Ensure directory exists and is writable
```

**Check 2**: File path configuration

```bash
echo $LOG_FILE
# Verify path is correct
```

**Check 3**: Check for file creation errors in console

The logger will fall back to console-only if file creation fails.

### Component-Specific Log Level Not Working

**Check 1**: Verify component name normalization

```python
import logging
logger = logging.getLogger("my.component.name")
print(logger.name)  # Use this exact name
# Convert: my.component.name → MY_COMPONENT_NAME
# Set: LOG_LEVEL_MY_COMPONENT_NAME=DEBUG
```

**Check 2**: Environment variable is set

```bash
env | grep LOG_LEVEL_
# Verify your specific variable appears
```

### Too Many Logs in Production

**Solution 1**: Raise the default log level

```bash
export LOG_LEVEL=ERROR  # Only errors and critical
```

**Solution 2**: Quiet specific noisy components

```bash
export LOG_LEVEL=WARNING  # Default
export LOG_LEVEL_NOISY_COMPONENT=ERROR  # Quiet this one
```

**Solution 3**: Increase rotation size/count

```bash
export LOG_MAX_BYTES=104857600  # 100MB
export LOG_BACKUP_COUNT=20
```

### Missing Session IDs

**Check 1**: Ensure session_id is passed

```python
# Option 1: Explicit
logger = get_logger(__name__, session_id="abc123")

# Option 2: Context (for async)
from agentic_logging import set_session_context
set_session_context("abc123")
logger = get_logger(__name__)
```

**Check 2**: Verify session_id in source data

```python
# For hooks, extract from event
session_id = hook_event.get('session_id') or hook_event.get('metadata', {}).get('session_id')
```

## Performance Considerations

### Overhead

- **Log call**: < 1ms including formatting
- **File I/O**: Buffered, asynchronous write
- **Memory**: Minimal (rotating files limit size)

### Optimization Tips

1. **Use appropriate log levels**
   ```python
   # Good: Expensive computation only if DEBUG is enabled
   if logger.isEnabledFor(logging.DEBUG):
       expensive_debug_data = compute_debug_info()
       logger.debug("Debug info", extra={"data": expensive_debug_data})
   ```

2. **Lazy evaluation**
   ```python
   # Prefer %s formatting (lazy)
   logger.debug("Processing %d items", len(items))
   
   # Over f-strings (eager)
   logger.debug(f"Processing {len(items)} items")
   ```

3. **Per-component levels**
   ```bash
   # Set DEBUG only where needed
   export LOG_LEVEL=WARNING
   export LOG_LEVEL_SPECIFIC_COMPONENT=DEBUG
   ```

## Migration from Standard Logging

### Before

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.info("Hello")
```

### After

```python
from agentic_logging import get_logger

logger = get_logger(__name__)
# Log level now controlled by environment variables

logger.info("Hello")
```

### Breaking Changes

- **ANALYTICS_DEBUG removed**: Use `LOG_LEVEL_ANALYTICS=DEBUG` instead
- **Manual logging.basicConfig() removed**: Now handled automatically
- **Log format**: Files now use JSONL instead of text

### Migration Checklist

- [ ] Replace `import logging` with `from agentic_logging import get_logger`
- [ ] Replace `logging.getLogger(__name__)` with `get_logger(__name__)`
- [ ] Remove manual `logger.setLevel()` calls (use env vars)
- [ ] Remove `logging.basicConfig()` calls
- [ ] Update environment variables:
  - Remove: `ANALYTICS_DEBUG`
  - Add: `LOG_LEVEL_ANALYTICS=DEBUG` (if needed)
- [ ] Update deployment configs with new environment variables
- [ ] Update log parsing tools to expect JSONL format

## Architecture Decision Record

See [ADR-014: Centralized Agentic Logging](/docs/adrs/014-centralized-agentic-logging.md) for the full design rationale and trade-offs.

## Related Documentation

- [Library README](/lib/python/agentic_logging/README.md) - Detailed API documentation
- [ADR-014](/docs/adrs/014-centralized-agentic-logging.md) - Architecture decision
- [Analytics Integration](/docs/analytics-integration.md) - Analytics-specific usage

---

**Questions or Issues?**

If you encounter problems with logging or have suggestions for improvements, please file an issue with the `logging` label.

