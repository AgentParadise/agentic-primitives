# Analytics Troubleshooting Guide

Common issues and solutions for the agentic-primitives analytics system.

## Quick Diagnostics

Before diving into specific issues, run these quick checks:

### 1. Check Analytics Service

```bash
cd services/analytics

# Verify Python version
uv run python --version  # Should be 3.11+

# Check dependencies
uv sync --verbose

# Run tests
uv run pytest -v
```

### 2. Test Middleware Manually

```bash
# Create test input
cat > test-input.json <<'EOF'
{
  "provider": "claude",
  "event": "SessionStart",
  "data": {
    "session_id": "test-123",
    "transcript_path": "/tmp/transcript.jsonl",
    "cwd": "/tmp",
    "permission_mode": "default",
    "hook_event_name": "SessionStart",
    "source": "startup"
  }
}
EOF

# Test normalizer
cat test-input.json | uv run python middleware/event_normalizer.py

# Test full pipeline
cat test-input.json | \
  uv run python middleware/event_normalizer.py | \
  uv run python middleware/event_publisher.py
```

### 3. Enable Debug Logging

```bash
export ANALYTICS_DEBUG=true
# Then run your tests/hooks again
```

---

## Installation Issues

### Problem: `uv` not found

**Symptom**: Command `uv` not recognized

**Cause**: uv not installed or not in PATH

**Solution**:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Restart shell or source profile
source ~/.bashrc  # or ~/.zshrc

# Verify installation
uv --version

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Alternative**: Install via pip:

```bash
pip install uv
```

---

### Problem: Python version mismatch

**Symptom**: Error like "Python 3.11+ required" or dependency installation fails

**Cause**: System Python is too old (< 3.11)

**Solution**:

```bash
# Check Python version
python --version
uv run python --version

# Install Python 3.11+ (macOS with Homebrew)
brew install python@3.11

# Install Python 3.11+ (Ubuntu/Debian)
sudo apt update
sudo apt install python3.11 python3.11-venv

# Install Python 3.11+ (Windows)
# Download from python.org

# Tell uv to use specific Python version
uv sync --python python3.11
```

---

### Problem: Dependency installation failures

**Symptom**: `uv sync` fails with network errors or dependency conflicts

**Causes**:
- Network connectivity issues
- Proxy/firewall blocking PyPI
- Dependency version conflicts
- Disk space issues

**Solutions**:

```bash
# Check network connectivity
ping pypi.org

# Verbose output to see what's failing
uv sync --verbose

# Clear uv cache and retry
uv cache clean
uv sync

# Check disk space
df -h

# If behind proxy
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
uv sync

# Force reinstall
rm -rf .venv
uv sync
```

---

## Configuration Issues

### Problem: Environment variables not set

**Symptom**: "Missing required configuration" or "KeyError" for env vars

**Cause**: Required environment variables not configured

**Solution**:

```bash
# Check current environment
printenv | grep ANALYTICS

# Set required variables
export ANALYTICS_PROVIDER=claude
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# Verify they're set
echo $ANALYTICS_PROVIDER
echo $ANALYTICS_PUBLISHER_BACKEND
echo $ANALYTICS_OUTPUT_PATH

# Make permanent (add to shell profile)
echo 'export ANALYTICS_PROVIDER=claude' >> ~/.bashrc
echo 'export ANALYTICS_PUBLISHER_BACKEND=file' >> ~/.bashrc
echo 'export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl' >> ~/.bashrc

# Reload shell configuration
source ~/.bashrc
```

**Debugging**: Create a `.env` file:

```bash
# services/analytics/.env
ANALYTICS_PROVIDER=claude
ANALYTICS_PUBLISHER_BACKEND=file
ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl
ANALYTICS_DEBUG=true
```

The analytics service will automatically load this file.

---

### Problem: Invalid provider name

**Symptom**: Events have `provider: "unknown"` or warnings about provider

**Cause**: `ANALYTICS_PROVIDER` not set or incorrect

**Note**: The analytics system is **provider-agnostic** and doesn't validate provider names. However, setting the correct provider helps with debugging and analytics queries.

**Solution**:

```bash
# Set provider to match your AI system
export ANALYTICS_PROVIDER=claude    # For Claude Code
export ANALYTICS_PROVIDER=openai    # For OpenAI-based systems
export ANALYTICS_PROVIDER=cursor    # For Cursor IDE
# Or any custom provider name

# Verify in output
cat analytics-events.jsonl | jq -r '.provider' | sort | uniq
```

---

### Problem: Missing output path for file backend

**Symptom**: "output_path is required when publisher_backend is 'file'"

**Cause**: File backend selected but no output path configured

**Solution**:

```bash
# Set output path
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# Or use absolute path
export ANALYTICS_OUTPUT_PATH=/Users/you/analytics/events.jsonl

# Or use home directory shorthand
export ANALYTICS_OUTPUT_PATH=~/analytics/events.jsonl
```

The publisher creates parent directories automatically.

---

### Problem: Invalid API endpoint

**Symptom**: "api_endpoint is required when publisher_backend is 'api'" or connection failures

**Cause**: API backend selected but no endpoint configured, or endpoint unreachable

**Solution**:

```bash
# Set API endpoint
export ANALYTICS_PUBLISHER_BACKEND=api
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/api/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3

# Test endpoint connectivity
curl -X POST $ANALYTICS_API_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"test": true}'

# Check DNS resolution
nslookup analytics.example.com

# Check SSL certificate (if HTTPS)
openssl s_client -connect analytics.example.com:443
```

**Debugging API issues**:

```bash
# Enable debug to see full request/response
export ANALYTICS_DEBUG=true

# Check for firewall/proxy issues
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

---

## Runtime Errors

### Problem: "Analytics normalizer error: validation error"

**Symptom**: Middleware logs validation error, outputs empty JSON `{}`

**Cause**: Input JSON doesn't match expected Pydantic model schema

**Solution**:

1. Capture the input to a file:

```bash
# Add debug output to your hook configuration
cat > test-input.json <<'EOF'
{
  "provider": "claude",
  "event": "PreToolUse",
  "data": {
    "session_id": "test-123",
    "transcript_path": "/tmp/transcript.jsonl",
    "cwd": "/tmp",
    "permission_mode": "default",
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "tool_input": {"file_path": "test.txt", "contents": "hello"},
    "tool_use_id": "toolu_123"
  }
}
EOF
```

2. Test the normalizer manually:

```bash
cat test-input.json | uv run python middleware/event_normalizer.py
```

3. Check the detailed Pydantic error in stderr:

```bash
cat test-input.json | uv run python middleware/event_normalizer.py 2>&1 | grep -A 10 "validation error"
```

4. Fix the input JSON to match the expected schema (see [Analytics Event Reference](./analytics-event-reference.md))

**Common validation errors**:

- **Missing required field**: Add the missing field to `data`
- **Wrong field type**: Check that strings are strings, integers are integers
- **Invalid enum value**: Check `permission_mode`, `source`, `trigger`, etc.
- **Nested object mismatch**: Verify `tool_input` structure matches tool

**Prevention**:
- Use test fixtures from `services/analytics/tests/fixtures/`
- Validate provider adapter implementation
- Enable debug logging during development

---

### Problem: "Analytics publisher error"

**Symptom**: Publisher logs error, events not written to backend

**Causes**:
- File backend: Permission denied, disk full, invalid path
- API backend: Network error, timeout, server error

**Solution (File Backend)**:

```bash
# Check file permissions
ls -la analytics/events.jsonl
ls -la analytics/  # Check directory permissions

# Check disk space
df -h

# Try writing to file manually
echo '{"test": true}' >> analytics/events.jsonl

# Create directory if missing
mkdir -p analytics

# Fix permissions
chmod 755 analytics
chmod 644 analytics/events.jsonl

# Try different location
export ANALYTICS_OUTPUT_PATH=/tmp/analytics-events.jsonl
```

**Solution (API Backend)**:

```bash
# Test API endpoint
curl -v -X POST $ANALYTICS_API_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"event_type":"session_started","timestamp":"2025-11-19T12:00:00Z"}'

# Check timeout settings
export ANALYTICS_API_TIMEOUT=60  # Increase timeout

# Check retry settings
export ANALYTICS_RETRY_ATTEMPTS=5  # More retries

# Enable debug logging
export ANALYTICS_DEBUG=true
```

---

### Problem: File permission denied

**Symptom**: "PermissionError: [Errno 13] Permission denied: 'analytics/events.jsonl'"

**Cause**: Analytics process doesn't have write permission to output directory

**Solution**:

```bash
# Check current permissions
ls -la analytics/

# Fix directory permissions
chmod 755 analytics/

# Fix file permissions (if file exists)
chmod 644 analytics/events.jsonl

# If file owned by different user
sudo chown $USER:$USER analytics/events.jsonl

# Use a directory you definitely have access to
export ANALYTICS_OUTPUT_PATH=/tmp/analytics-events.jsonl

# Or use home directory
export ANALYTICS_OUTPUT_PATH=~/analytics/events.jsonl
```

---

### Problem: API timeout

**Symptom**: "Request timeout after 30 seconds"

**Cause**: Analytics API is slow or unreachable

**Solution**:

```bash
# Increase timeout
export ANALYTICS_API_TIMEOUT=60  # 60 seconds

# Check API response time manually
time curl -X POST $ANALYTICS_API_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"test": true}'

# Verify network latency
ping analytics-server.example.com

# Check if API is under heavy load
curl $ANALYTICS_API_ENDPOINT/health

# Fall back to file backend temporarily
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl
```

---

## Validation Errors

### Problem: Hook doesn't validate

**Symptom**: `agentic validate` fails with schema errors

**Cause**: Hook configuration doesn't match `hook-meta.schema.json`

**Solution**:

1. Check the schema error message:

```bash
agentic validate docs/examples/analytics/session-tracking.hook.yaml
```

2. Common schema errors:

**Missing required field**:

```yaml
# ❌ BAD: Missing 'version'
id: session-tracking
name: "Session Tracker"

# ✅ GOOD: All required fields
version: 1
id: session-tracking
name: "Session Tracker"
description: "Track sessions"
events: [SessionStart]
middleware: [...]
execution: pipeline
```

**Invalid middleware type**:

```yaml
# ❌ BAD: Invalid type
middleware:
  - name: "normalizer"
    type: invalid  # Not in schema

# ✅ GOOD: Valid type
middleware:
  - name: "normalizer"
    type: analytics  # or "safety" or "observability"
```

**Invalid execution mode**:

```yaml
# ❌ BAD: Invalid execution
execution: parallel  # Wrong for analytics

# ✅ GOOD: Pipeline execution
execution: pipeline  # Normalizer → Publisher
```

---

### Problem: Middleware path not found

**Symptom**: "FileNotFoundError: [Errno 2] No such file or directory: 'middleware/event_normalizer.py'"

**Cause**: Middleware path in hook config doesn't point to actual file

**Solution**:

Check your path configuration in the hook YAML:

```yaml
# Relative path (from repository root)
path: "services/analytics/middleware/event_normalizer.py"

# Relative path (from current directory)
path: "../../../services/analytics/middleware/event_normalizer.py"

# Absolute path
path: "/usr/local/share/agentic/analytics/middleware/event_normalizer.py"

# Using environment variables (Claude Code)
path: "${CLAUDE_PROJECT_DIR}/services/analytics/middleware/event_normalizer.py"
```

**Verify the file exists**:

```bash
# From repository root
ls -la services/analytics/middleware/event_normalizer.py

# From example directory
ls -la ../../../services/analytics/middleware/event_normalizer.py
```

---

### Problem: Execution mode error

**Symptom**: "Invalid execution mode for analytics middleware"

**Cause**: Analytics middleware requires `execution: pipeline`, not `parallel`

**Explanation**: Analytics has two stages (normalizer → publisher) that must run sequentially. The normalizer output becomes the publisher input.

**Solution**:

```yaml
# ❌ BAD: Parallel execution
execution: parallel

# ✅ GOOD: Pipeline execution
execution: pipeline
```

---

## Testing Issues

### Problem: `agentic test-hook` fails

**Symptom**: Hook validation passes but testing fails

**Causes**:
- Middleware scripts have bugs
- Environment variables not set
- Test input doesn't match expected format

**Solution**:

1. **Test middleware individually**:

```bash
# Test normalizer only
cat test-input.json | uv run python middleware/event_normalizer.py

# Test publisher only (with normalized input)
cat normalized-event.json | uv run python middleware/event_publisher.py
```

2. **Check environment variables**:

```bash
# Print all analytics env vars
printenv | grep ANALYTICS

# Set them if missing
export ANALYTICS_PROVIDER=claude
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=/tmp/test-output.jsonl
```

3. **Use valid test fixtures**:

```bash
# Use fixtures from the repository
cd services/analytics
cat tests/fixtures/claude_hooks/pre_tool_use.json | \
  uv run python middleware/event_normalizer.py
```

4. **Enable debug mode**:

```bash
export ANALYTICS_DEBUG=true
agentic test-hook docs/examples/analytics/session-tracking.hook.yaml \
  --input test-input.json
```

---

### Problem: Pydantic validation errors

**Symptom**: "ValidationError: X validation error(s) for Model"

**Cause**: Data doesn't match Pydantic model schema

**Solution**:

1. **Read the validation error carefully**:

```python
ValidationError: 2 validation errors for HookInput
data.tool_name
  field required (type=value_error.missing)
data.tool_input
  field required (type=value_error.missing)
```

This tells you exactly what's missing: `tool_name` and `tool_input`.

2. **Check your input data structure**:

```bash
# Validate JSON structure
cat test-input.json | jq .

# Validate against Pydantic model manually
uv run python -c "
from analytics.models.hook_input import HookInput
import json
with open('test-input.json') as f:
    data = json.load(f)
    hook_input = HookInput.model_validate(data)
    print('Valid!')
"
```

3. **Use test fixtures as templates**:

```bash
# Copy a working fixture
cp services/analytics/tests/fixtures/claude_hooks/pre_tool_use.json my-test.json

# Modify for your needs
nano my-test.json
```

---

### Problem: Type checking errors

**Symptom**: `mypy` reports type errors

**Cause**: Type annotations don't match actual usage

**Solution**:

```bash
# Run type checking
cd services/analytics
uv run mypy src/analytics

# Run with verbose output to see details
uv run mypy --verbose src/analytics

# Ignore specific errors temporarily (not recommended for production)
uv run mypy --ignore-missing-imports src/analytics

# Fix common type errors:
# - Add type hints to functions
# - Import types correctly
# - Use Optional[T] for optional fields
# - Use Union[A, B] for multiple types
```

**Example fixes**:

```python
# ❌ BAD: No type hints
def normalize_event(hook_input):
    return NormalizedEvent(...)

# ✅ GOOD: With type hints
def normalize_event(hook_input: HookInput) -> NormalizedEvent:
    return NormalizedEvent(...)
```

---

## Performance Issues

### Problem: Analytics adds significant overhead

**Symptom**: Hook execution is slow, agent feels sluggish

**Causes**:
- Slow disk I/O
- Slow API backend
- Large event payloads
- Network latency

**Diagnosis**:

```bash
# Time the middleware
time cat test-input.json | uv run python middleware/event_normalizer.py
time cat normalized.json | uv run python middleware/event_publisher.py

# Profile Python code
uv run python -m cProfile middleware/event_normalizer.py < test-input.json
```

**Solutions**:

1. **Use file backend instead of API**:

```bash
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl
```

2. **Reduce timeout for API backend**:

```bash
export ANALYTICS_API_TIMEOUT=5  # Fail fast instead of waiting
```

3. **Filter out large fields**:

Modify normalizer to skip large fields like full prompt text or tool responses.

4. **Use SSD for file backend**:

```bash
# Store events on fast SSD
export ANALYTICS_OUTPUT_PATH=/mnt/fast-ssd/analytics/events.jsonl
```

5. **Reduce retry attempts**:

```bash
export ANALYTICS_RETRY_ATTEMPTS=1  # Fail fast, don't retry
```

---

### Problem: File I/O is slow

**Symptom**: File backend takes long time to write events

**Causes**:
- Slow disk (HDD instead of SSD)
- NFS/network filesystem
- Disk full or fragmented
- Many concurrent writes

**Solutions**:

```bash
# Check disk performance
dd if=/dev/zero of=test.img bs=1M count=100 conv=fdatasync
rm test.img

# Use local SSD instead of network filesystem
export ANALYTICS_OUTPUT_PATH=/local/ssd/analytics/events.jsonl

# Check disk usage
df -h

# Check inode usage
df -i

# Optimize disk (Linux)
sudo fstrim -v /

# Use tmpfs for temporary analytics (Linux)
sudo mkdir -p /mnt/tmpfs
sudo mount -t tmpfs -o size=1G tmpfs /mnt/tmpfs
export ANALYTICS_OUTPUT_PATH=/mnt/tmpfs/analytics/events.jsonl
```

---

### Problem: API publisher is slow

**Symptom**: API backend takes long time to respond

**Causes**:
- High network latency
- Server under load
- Slow API implementation
- Large payloads

**Solutions**:

```bash
# Measure network latency
ping analytics-server.example.com

# Measure API response time
time curl -X POST $ANALYTICS_API_ENDPOINT \
  -H "Content-Type: application/json" \
  -d @normalized-event.json

# Reduce timeout to fail fast
export ANALYTICS_API_TIMEOUT=5

# Reduce retry attempts
export ANALYTICS_RETRY_ATTEMPTS=1

# Switch to file backend temporarily
export ANALYTICS_PUBLISHER_BACKEND=file
```

---

## Debugging Tips

### Enable Verbose Logging

```bash
# Enable debug mode
export ANALYTICS_DEBUG=true

# Run your middleware
cat test-input.json | uv run python middleware/event_normalizer.py 2>&1 | less

# Check for error messages in stderr
```

### Test Middleware in Isolation

```bash
# Test just the normalizer
echo '{"provider":"claude","event":"SessionStart","data":{...}}' | \
  uv run python services/analytics/middleware/event_normalizer.py

# Test just the publisher
echo '{"event_type":"session_started","timestamp":"2025-11-19T12:00:00Z",...}' | \
  uv run python services/analytics/middleware/event_publisher.py
```

### Check Pydantic Validation

```bash
# Validate input manually
uv run python -c "
from analytics.models.hook_input import HookInput
import json
import sys

data = json.load(sys.stdin)
try:
    hook_input = HookInput.model_validate(data)
    print('✓ Valid input')
    print(hook_input.model_dump_json(indent=2))
except Exception as e:
    print(f'✗ Invalid input: {e}')
    sys.exit(1)
" < test-input.json
```

### Inspect Raw Events

```bash
# Capture stdin to file for debugging
# Add this to your hook script
tee /tmp/hook-input.json | python middleware/event_normalizer.py

# Later inspect the captured input
cat /tmp/hook-input.json | jq .
```

### Monitor Output Files

```bash
# Watch output file for new events
tail -f analytics/events.jsonl

# Watch with pretty printing
tail -f analytics/events.jsonl | jq .

# Count events
wc -l analytics/events.jsonl

# Validate JSON format
cat analytics/events.jsonl | jq . > /dev/null && echo "Valid JSON"
```

---

## Getting Help

If you're still stuck after trying these solutions:

1. **Check existing documentation**:
   - [Analytics Integration Guide](./analytics-integration.md)
   - [Analytics Event Reference](./analytics-event-reference.md)
   - [ADR-011: Analytics Middleware](./adrs/011-analytics-middleware.md)

2. **Enable debug logging** and collect diagnostics:

```bash
export ANALYTICS_DEBUG=true

# Capture full output
cat test-input.json | \
  uv run python middleware/event_normalizer.py 2>&1 | \
  tee debug-output.log
```

3. **Check test coverage** to see if your use case is covered:

```bash
cd services/analytics
uv run pytest tests/ -v --cov=src --cov-report=html
open htmlcov/index.html
```

4. **Report issues** with:
   - Python version (`uv run python --version`)
   - uv version (`uv --version`)
   - OS and version
   - Complete error message
   - Input JSON (sanitize sensitive data!)
   - Environment variables (sanitize secrets!)
   - Debug logs

---

## Common Error Messages

### "ModuleNotFoundError: No module named 'analytics'"

**Cause**: Python can't find the analytics module

**Solution**:

```bash
cd services/analytics
uv sync
uv run python -c "import analytics; print('Success!')"
```

### "FileNotFoundError: middleware/event_normalizer.py"

**Cause**: Running from wrong directory or incorrect path

**Solution**:

```bash
# Run from services/analytics
cd services/analytics
uv run python middleware/event_normalizer.py

# Or use absolute path
uv run python /path/to/services/analytics/middleware/event_normalizer.py
```

### "JSONDecodeError: Expecting value"

**Cause**: Input is not valid JSON

**Solution**:

```bash
# Validate JSON
cat test-input.json | jq . > /dev/null

# Fix JSON formatting
cat test-input.json | jq . > fixed-input.json
```

### "KeyError: 'ANALYTICS_OUTPUT_PATH'"

**Cause**: Required environment variable not set

**Solution**:

```bash
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl
```

---

## Prevention Best Practices

1. **Always validate hooks before deploying**:

```bash
agentic validate hook.yaml
```

2. **Test with fixtures**:

```bash
agentic test-hook hook.yaml --input fixture.json
```

3. **Use debug mode during development**:

```bash
export ANALYTICS_DEBUG=true
```

4. **Version control your configuration**:

```bash
git add docs/examples/analytics/my-hook.yaml
git commit -m "Add analytics hook configuration"
```

5. **Monitor output regularly**:

```bash
# Check file grows
ls -lh analytics/events.jsonl

# Check recent events
tail analytics/events.jsonl | jq .
```

6. **Set up alerts for failures**:

Create a monitoring script that checks for errors in logs.

---

## Related Documentation

- [Analytics Integration Guide](./analytics-integration.md)
- [Analytics Event Reference](./analytics-event-reference.md)
- [Analytics Examples](./examples/analytics/)
- [ADR-011: Analytics Middleware](./adrs/011-analytics-middleware.md)

