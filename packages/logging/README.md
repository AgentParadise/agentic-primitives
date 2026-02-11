# Agentic Logging

A centralized logging system designed for AI agents and human developers.

## Design Philosophy

This logging system is built on three core principles:

### 1. **AI-First, Human-Friendly**

The logging system is optimized for AI agent consumption while remaining useful for human developers:

- **Structured JSON output** for easy parsing and analysis by AI agents
- **Human-readable console format** with visual structure and minimal color
- **Session tracking** to correlate logs across distributed operations
- **Granular control** via environment variables to prevent context window overload

### 2. **Fail-Safe Operation**

Logging should never crash your application:

- **Graceful degradation**: Falls back to console-only if file logging fails
- **No external dependencies** (beyond python-json-logger)
- **Standard library foundation**: Built on Python's robust logging module
- **Validated configuration**: Invalid settings fall back to safe defaults

### 3. **Zero-Configuration with Full Control**

Works out of the box, configurable when needed:

- **Sane defaults**: WARNING level, human-readable console, JSONL file
- **Environment variable configuration**: No code changes for different environments
- **Per-component log levels**: Fine-tune verbosity for specific modules
- **Global session context**: Automatic session tracking across async boundaries

---

## Quick Start

### Installation

```bash
pip install agentic-logging
```

Or with UV (recommended for workspace projects):

```bash
uv add agentic-logging
```

### Basic Usage

```python
from agentic_logging import get_logger

logger = get_logger(__name__)

# Basic logging
logger.info("Processing started")
logger.warning("High memory usage detected")
logger.error("Failed to connect to service", exc_info=True)

# Structured logging with context
logger.info(
    "User action completed",
    extra={
        "user_id": 123,
        "action": "file_upload",
        "duration_ms": 450,
    }
)

# With session tracking
logger = get_logger(__name__, session_id="abc123")
logger.debug("Processing item", extra={"item_id": 456})
```

---

## Configuration Reference

All configuration is done via environment variables:

### System-Wide Settings

```bash
# Log level for all components (default: WARNING)
LOG_LEVEL=DEBUG|INFO|WARNING|ERROR|CRITICAL

# Path to log file (default: ./logs/agentic.jsonl)
LOG_FILE=./logs/myapp.jsonl

# Console output format (default: human)
LOG_CONSOLE_FORMAT=human|json

# File rotation settings
LOG_MAX_BYTES=10485760      # Max file size: 10MB (default)
LOG_BACKUP_COUNT=5          # Number of backup files (default)
```

### Per-Component Log Levels

Override log level for specific components:

```bash
# Format: LOG_LEVEL_{COMPONENT_NAME}
# Component name: Module path with dots → underscores, UPPERCASE

# Example: hooks.core.hooks_collector
export LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR=DEBUG

# Example: analytics.publishers.file
export LOG_LEVEL_ANALYTICS_PUBLISHERS_FILE=INFO

# Example: services.myservice
export LOG_LEVEL_SERVICES_MYSERVICE=DEBUG
```

---

## Log Levels Strategy

### When to Use Each Level

**DEBUG** - Detailed diagnostic information for troubleshooting
- Input/output values
- State transitions
- Algorithm steps
- Use for: AI agent investigation, local development

**INFO** - General informational messages about normal operation
- Service started/stopped
- Configuration loaded
- Major operations completed
- Use for: Monitoring, audit trails

**WARNING** - Potentially problematic situations that aren't errors
- Degraded performance
- Deprecated API usage
- Recoverable failures
- Use for: Production default level

**ERROR** - Error events that might still allow the application to continue
- Failed operations with fallback
- External service failures
- Invalid input data
- Use for: Production monitoring, alerting

**CRITICAL** - Severe errors causing application shutdown
- Unrecoverable errors
- Data corruption
- Security breaches
- Use for: Immediate attention required

---

## Output Formats

### JSON Format (Files & Optional Console)

All logs are written to file in JSONL format (one JSON object per line):

```json
{
  "timestamp": "2025-11-25T10:30:45.123456Z",
  "level": "DEBUG",
  "component": "hooks.core.hooks_collector",
  "session_id": "abc123def456",
  "message": "Middleware filtered for event",
  "event_type": "PreToolUse",
  "middleware_count": 3,
  "middleware_executed": ["analytics-collector"],
  "exc_info": null
}
```

**Standard Fields:**
- `timestamp` - ISO 8601 UTC timestamp with microseconds
- `level` - Log level name (DEBUG, INFO, etc.)
- `component` - Logger name (module path)
- `session_id` - Session identifier (if set)
- `message` - Log message string
- `exc_info` - Exception traceback (if present)
- *All fields from `extra={}` parameter*

### Human Format (Console)

Developer-friendly format with visual structure:

```
[10:30:45.123] 🔍 DEBUG  hooks.core.hooks_collector
  Middleware filtered for event
  ├─ session_id: abc123def456
  ├─ event_type: PreToolUse
  ├─ middleware_count: 3
  └─ middleware_executed: ['analytics-collector']
```

**Features:**
- Emoji indicators for quick visual scanning (🔍 ℹ️ ⚠️ ❌ 🚨)
- Minimal color (only on TTY terminals)
- Tree structure for extra fields
- Millisecond timestamps
- Indented exception tracebacks

---

## Usage Patterns

### For Developers

**Local development:**
```bash
export LOG_LEVEL=DEBUG
export LOG_CONSOLE_FORMAT=human
python main.py
```

**Debugging specific component:**
```bash
export LOG_LEVEL=WARNING  # Quiet by default
export LOG_LEVEL_HOOKS_COLLECTOR=DEBUG  # Verbose for one component
python main.py
```

### For AI Agents

**Investigation mode - Parse logs programmatically:**
```bash
export LOG_LEVEL=DEBUG
export LOG_CONSOLE_FORMAT=json  # All output as JSON
python main.py 2>&1 | grep "component.*hooks_collector"
```

**Session-based debugging:**
```python
from agentic_logging import get_logger, set_session_context

# Set session context once
set_session_context("investigation-20251125-001")

# All loggers in this context will include the session_id
logger = get_logger(__name__)
logger.debug("Starting investigation")

# Later, filter logs by session_id
# jq -r 'select(.session_id=="investigation-20251125-001")' logs/agentic.jsonl
```

### For Production

**Standard production setup:**
```bash
export LOG_LEVEL=WARNING
export LOG_FILE=/var/log/myapp/agentic.jsonl
export LOG_MAX_BYTES=52428800  # 50MB
export LOG_BACKUP_COUNT=10
python main.py
```

**Component-specific production debugging:**
```bash
# Keep most logs quiet, but debug one problematic component
export LOG_LEVEL=WARNING
export LOG_LEVEL_SERVICES_PAYMENT=DEBUG
python main.py
```

---

## Integration Guide

### Step 1: Install in Your Project

```bash
# If using UV workspace
uv add agentic-logging

# If using pip
pip install agentic-logging
```

### Step 2: Replace Existing Logging

**Before:**
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Hello world")
```

**After:**
```python
from agentic_logging import get_logger

logger = get_logger(__name__)
logger.info("Hello world")
```

### Step 3: Add Structured Context

Enhance logs with extra context for better analysis:

```python
logger.info(
    "Request processed",
    extra={
        "user_id": user.id,
        "endpoint": request.path,
        "duration_ms": elapsed_time,
        "status_code": response.status,
    }
)
```

### Step 4: Add Session Tracking

For correlated operations:

```python
# Option 1: Explicit session_id
logger = get_logger(__name__, session_id=request.session_id)

# Option 2: Context-based (for async)
from agentic_logging import set_session_context

set_session_context(request.session_id)
logger = get_logger(__name__)  # Automatically includes session_id
```

### Step 5: Configure for Your Environment

Create an `.env` file:

```bash
# Development
LOG_LEVEL=DEBUG
LOG_CONSOLE_FORMAT=human
LOG_FILE=./logs/dev.jsonl

# Production
# LOG_LEVEL=WARNING
# LOG_CONSOLE_FORMAT=json
# LOG_FILE=/var/log/app/production.jsonl
# LOG_MAX_BYTES=52428800
# LOG_BACKUP_COUNT=10
```

---

## Examples

### Example 1: Simple Service Logging

```python
from agentic_logging import get_logger

logger = get_logger(__name__)

def process_data(data):
    logger.info("Processing started", extra={"data_size": len(data)})
    
    try:
        result = expensive_operation(data)
        logger.info("Processing completed", extra={"result_size": len(result)})
        return result
    except Exception as e:
        logger.error("Processing failed", exc_info=True, extra={"data_size": len(data)})
        raise
```

### Example 2: Component-Specific Debugging

```python
# hooks_collector.py
from agentic_logging import get_logger

logger = get_logger(__name__)  # Logger name: hooks.core.hooks_collector

def collect_hooks():
    logger.debug("Starting hook collection")
    
    for hook in discover_hooks():
        logger.debug("Found hook", extra={"hook_name": hook.name, "hook_path": hook.path})
    
    logger.info("Hook collection complete", extra={"total_hooks": len(hooks)})
```

```bash
# Enable DEBUG only for hooks_collector
export LOG_LEVEL=WARNING
export LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR=DEBUG
python main.py
```

### Example 3: Session Tracking

```python
from agentic_logging import get_logger
import uuid

def handle_request(request):
    # Generate unique session ID for this request
    session_id = str(uuid.uuid4())
    logger = get_logger(__name__, session_id=session_id)
    
    logger.info("Request received", extra={"method": request.method, "path": request.path})
    
    # Call other services/functions
    data = fetch_data()  # Also uses logger with same session_id
    result = process_data(data)  # Logs will have same session_id
    
    logger.info("Request completed", extra={"status": 200})
    return result

# Later, find all logs for this request:
# jq 'select(.session_id=="abc-123-def")' logs/agentic.jsonl
```

### Example 4: High-Frequency Logging with Levels

```python
from agentic_logging import get_logger

logger = get_logger(__name__)

def process_items(items):
    logger.info("Batch processing started", extra={"batch_size": len(items)})
    
    for i, item in enumerate(items):
        # DEBUG logs only appear when LOG_LEVEL_PROCESSOR=DEBUG
        logger.debug("Processing item", extra={"index": i, "item_id": item.id})
        
        if item.needs_attention():
            # WARNING always appears (default level)
            logger.warning("Item requires attention", extra={"item_id": item.id})
    
    logger.info("Batch processing complete")
```

---

## Performance Characteristics

### Overhead

- **Log call overhead**: < 1ms per call (including formatting)
- **File I/O**: Buffered, asynchronous write to disk
- **Memory usage**: Minimal (rotating log files, max 10MB * backup_count)

### Optimization Tips

1. **Use appropriate log levels**: DEBUG logs are expensive
2. **Lazy evaluation**: Use `%` formatting or f-strings in message only
3. **Structured extra fields**: Prefer `extra={}` over string formatting
4. **Per-component levels**: Set DEBUG only where needed

```python
# Good: Lazy evaluation
logger.debug("Processing %d items", len(items))

# Better: Only compute if DEBUG is enabled
if logger.isEnabledFor(logging.DEBUG):
    expensive_data = compute_debug_info()
    logger.debug("Debug info", extra={"data": expensive_data})
```

---

## Troubleshooting

### Logs not appearing in file

**Problem**: Console logs work, but no file is created

**Solution**: Check log directory permissions and path
```bash
ls -la logs/
# Ensure directory exists and is writable

# Check config
echo $LOG_FILE
# Ensure path is valid
```

### Component log level not working

**Problem**: `LOG_LEVEL_MY_MODULE=DEBUG` has no effect

**Solution**: Verify component name normalization
```python
import logging
logger = logging.getLogger("my.module.name")
print(logger.name)  # Use this name

# Convert to env var:
# my.module.name → MY_MODULE_NAME
# Export: LOG_LEVEL_MY_MODULE_NAME=DEBUG
```

### Too many logs in production

**Problem**: Log file growing too fast

**Solution 1**: Increase rotation size
```bash
export LOG_MAX_BYTES=104857600  # 100MB
export LOG_BACKUP_COUNT=20
```

**Solution 2**: Raise log level
```bash
export LOG_LEVEL=ERROR  # Only errors and critical
```

**Solution 3**: Disable specific noisy components
```bash
export LOG_LEVEL=WARNING
export LOG_LEVEL_NOISY_MODULE=ERROR  # Quiet this one down
```

### Can't see DEBUG logs

**Problem**: DEBUG logs not appearing despite `LOG_LEVEL=DEBUG`

**Solution**: Check for component-level overrides
```bash
# Clear all LOG_LEVEL_* variables
env | grep LOG_LEVEL_

# Or set explicitly
export LOG_LEVEL=DEBUG
export LOG_LEVEL_YOUR_MODULE=DEBUG
```

### Logs missing session_id

**Problem**: Expected session_id in logs but it's not there

**Solution**: Ensure session_id is passed to get_logger or context
```python
# Option 1: Explicit
logger = get_logger(__name__, session_id="abc123")

# Option 2: Context
from agentic_logging import set_session_context
set_session_context("abc123")
logger = get_logger(__name__)  # Will include session_id
```

---

## Contributing

This is part of the agentic-primitives project. See the main repository for contribution guidelines.

---

## License

MIT License - See LICENSE file in repository root

