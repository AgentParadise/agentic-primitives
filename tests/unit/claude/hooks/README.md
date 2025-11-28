# Claude Hooks Unit Tests

Offline unit tests for Claude Code hooks using Python + Pydantic.

## Purpose

Test hook logic without needing:
- Claude Code extension
- VS Code/Cursor
- Network access
- Real agent execution

Tests validate that hooks correctly:
- Parse input events
- Make correct decisions (allow/block)
- Return proper output format
- Handle edge cases

## Prerequisites

- Python 3.11+
- UV (for dependency management)

## Running Tests

### Run All Tests

```bash
cd tests/unit/claude/hooks
uv run pytest
```

### Run Specific Test Class

```bash
# Test bash-validator only
uv run pytest test_hooks.py::TestBashValidator

# Test file-security only
uv run pytest test_hooks.py::TestFileSecurity

# Test prompt-filter only
uv run pytest test_hooks.py::TestPromptFilter
```

### Run Specific Test

```bash
uv run pytest test_hooks.py::TestBashValidator::test_dangerous_command_blocked
```

### Run with Verbose Output

```bash
uv run pytest -v
```

### Run with Coverage

```bash
uv run pytest --cov=. --cov-report=html
```

## Test Structure

```
tests/unit/claude/hooks/
├── test_hooks.py          # Main test suite
├── fixtures/              # JSON test fixtures
│   ├── dangerous-bash.json
│   ├── safe-bash.json
│   ├── sensitive-file.json
│   ├── normal-file.json
│   ├── pii-prompt.json
│   └── normal-prompt.json
├── pyproject.toml         # Dependencies
└── README.md              # This file
```

## Test Coverage

### Bash Validator Tests
- ✅ Blocks dangerous commands (rm -rf, dd, mkfs, fork bomb)
- ✅ Allows safe commands (ls, cat, echo)
- ✅ Provides alternatives for blocked commands
- ✅ Various dangerous command patterns

### File Security Tests
- ✅ Blocks sensitive files (.env, keys, credentials)
- ✅ Allows normal files (src/, docs/, etc.)
- ✅ Various sensitive file patterns
- ✅ Different file operations (Read, Write, Edit, Delete)

### Prompt Filter Tests
- ✅ Detects PII in prompts (email, phone, SSN)
- ✅ Allows normal prompts
- ✅ Warns without blocking

### Hooks Collector Tests
- ✅ Never blocks operations
- ✅ Handles all event types
- ✅ Logs analytics

### Integration Tests
- ✅ Parallel execution simulation
- ✅ Multiple hooks for same event
- ✅ Decision combination logic

## Adding New Tests

### 1. Add Test Fixture

Create JSON file in `fixtures/`:

```json
{
  "session_id": "test-xyz",
  "transcript_path": "/test/session.jsonl",
  "cwd": "/test",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "YourTool",
  "tool_input": {"key": "value"},
  "tool_use_id": "toolu_test_xyz"
}
```

### 2. Add Test Method

```python
class TestYourHook:
    def test_your_scenario(self):
        hook_path = tester.get_hook_path("category", "hook-name")
        
        fixture = HookTestFixture(
            session_id="test-001",
            # ... other fields
        )
        
        result = tester.run_hook(hook_path, fixture)
        
        assert result.success
        assert result.decision == "expected_decision"
```

### 3. Run New Test

```bash
uv run pytest test_hooks.py::TestYourHook::test_your_scenario -v
```

## Cross-Platform Compatibility

These tests work on:
- ✅ macOS
- ✅ Linux
- ✅ Windows

Using Python + UV ensures consistent behavior across platforms.

## Continuous Integration

Add to CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Hook Unit Tests
  run: |
    cd tests/unit/claude/hooks
    uv run pytest --cov=. --cov-report=xml
```

## Troubleshooting

### Hooks Not Found

Ensure hooks are built first:

```bash
cd ../../../../
cargo run --manifest-path cli/Cargo.toml -- build --provider claude
```

### Import Errors

Install dependencies:

```bash
uv sync
```

### Test Failures

Run with verbose output to see details:

```bash
uv run pytest -vv --tb=long
```

## Next Steps

- Add more dangerous command patterns
- Test additional sensitive file patterns
- Add performance benchmarks
- Test with real Claude Code (see `examples/000-claude-integration`)


