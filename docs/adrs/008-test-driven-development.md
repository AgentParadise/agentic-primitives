# ADR-008: Test-Driven Development

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team, QA Team
informed: All Stakeholders
---
```

## Context

Agentic primitives will be used in **automated, production-critical workflows** where failures can be costly:
- Agents making code changes
- Hooks blocking dangerous operations
- Tools executing commands
- Providers transforming primitives

Traditional "test later" approaches accumulate technical debt and lead to fragile systems. We need a testing strategy that ensures reliability from the start.

### The Testing Philosophy Question

Should we:
1. **Test After**: Write code first, add tests later
2. **Test Alongside**: Write tests as we write code
3. **Test-Driven**: Write tests first, then implement (TDD)

### Risk Assessment

**High-Risk Components**:
- ✅ Validation logic (structural, schema, semantic)
- ✅ Hook middleware (safety-critical)
- ✅ Provider transformers (correctness-critical)
- ✅ Version management (immutability-critical)
- ✅ CLI commands (user-facing)

**Medium-Risk Components**:
- ⚠️ Templates (scaffolding)
- ⚠️ Configuration loading
- ⚠️ Model resolution

**Low-Risk Components**:
- 📄 Documentation
- 📄 Examples

## Decision

We will adopt **Test-Driven Development (TDD)** with comprehensive coverage requirements:

### Coverage Requirements

1. **Rust Code**: >80% line coverage
   - All validation logic: >90%
   - All CLI commands: >80%
   - All provider transformers: >85%

2. **Python Code** (hooks): >80% line coverage
   - Safety middleware: >90%
   - Observability middleware: >75%

3. **Critical Paths**: 100% coverage
   - Hash calculation and verification
   - Dangerous command detection
   - Primitive resolution

### Testing Layers

#### Unit Tests
- Test individual functions/modules in isolation
- Mock external dependencies
- Fast (<1ms per test)
- Run on every save

#### Integration Tests
- Test component interactions
- Use test fixtures (valid and invalid primitives)
- Medium speed (~10-100ms per test)
- Run before commit

#### End-to-End Tests
- Test complete workflows
- Real file system operations (in temp dirs)
- Slower (~1s per test)
- Run in CI/CD

### Test Organization

```
cli/tests/
├── integration/           # Integration tests
│   ├── init_test.rs
│   ├── new_test.rs
│   ├── validate_test.rs
│   ├── build_test.rs
│   └── install_test.rs
├── validation/            # Validation tests
│   ├── structural_test.rs
│   ├── schema_test.rs
│   └── semantic_test.rs
├── providers/             # Provider transformer tests
│   ├── claude_test.rs
│   ├── openai_test.rs
│   └── cursor_test.rs
└── fixtures/              # Test data
    ├── valid/
    │   ├── prompts/
    │   ├── tools/
    │   └── hooks/
    └── invalid/
        ├── prompts/
        ├── tools/
        └── hooks/
```

### Testing Workflow

**TDD Cycle**:
1. 🔴 **Red**: Write failing test
2. 🟢 **Green**: Write minimal code to pass
3. 🔵 **Refactor**: Clean up code
4. 🔁 **Repeat**

**Example**:
```rust
// 1. RED: Write failing test
#[test]
fn test_validate_dangerous_command() {
    let result = validate_bash_command("rm -rf /");
    assert_eq!(result.decision, "block");
    assert!(result.reason.contains("dangerous"));
}

// 2. GREEN: Implement
fn validate_bash_command(cmd: &str) -> ValidationResult {
    if cmd.contains("rm -rf") {
        return ValidationResult {
            decision: "block",
            reason: "dangerous command detected"
        };
    }
    // ... minimal implementation
}

// 3. REFACTOR: Clean up
fn validate_bash_command(cmd: &str) -> ValidationResult {
    let dangerous_patterns = load_patterns();
    for pattern in dangerous_patterns {
        if pattern.matches(cmd) {
            return ValidationResult::blocked(
                format!("dangerous command: {}", pattern.name())
            );
        }
    }
    ValidationResult::allowed()
}
```

## Rationale

### Why TDD?

✅ **Design Driver**: Tests force thinking about API design upfront

✅ **Safety Net**: Catch regressions immediately

✅ **Documentation**: Tests serve as living documentation

✅ **Confidence**: Can refactor safely

✅ **Debugging**: Failing tests pinpoint issues

✅ **Coverage**: TDD naturally achieves high coverage

### Why >80% Coverage?

- Industry standard for production code
- Balance between thoroughness and pragmatism
- Higher for critical components (90%+)
- Some code doesn't need testing (trivial getters, etc.)

### Why Not Lower Coverage?

❌ **50% Coverage**: Too many untested paths, false confidence

❌ **60-70% Coverage**: Still leaves significant risk

### Why Not 100% Coverage?

❌ **Diminishing Returns**: Last 20% often not worth effort

❌ **False Confidence**: 100% coverage ≠ bug-free

❌ **Pragmatism**: Some code is trivial or generated

## Consequences

### Positive

✅ **Reliability**: High confidence in code correctness

✅ **Refactoring**: Can change code without fear

✅ **Regression Prevention**: Tests catch old bugs

✅ **Documentation**: Tests show how code should be used

✅ **Faster Debugging**: Failing tests isolate issues

✅ **Better Design**: TDD encourages testable, modular code

### Negative

⚠️ **Initial Slowdown**: Writing tests takes time upfront

⚠️ **Maintenance**: Tests need updating when code changes

⚠️ **Learning Curve**: TDD takes practice

⚠️ **False Security**: Tests can't catch all bugs

### Mitigations

1. **Start Simple**: Begin with basic tests, improve over time

2. **Test Helpers**: Build reusable test utilities

3. **Fixtures**: Maintain comprehensive test data

4. **Snapshot Testing**: Use `insta` for complex output validation

5. **Fast Tests**: Keep tests fast to encourage frequent running

6. **CI/CD**: Automate testing in pipelines

## Implementation

### Rust Testing

```rust
// Unit test
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_parse_model_ref() {
        let model_ref = ModelRef::parse("claude/sonnet").unwrap();
        assert_eq!(model_ref.provider, "claude");
        assert_eq!(model_ref.model, "sonnet");
    }
    
    #[test]
    fn test_parse_invalid_model_ref() {
        let result = ModelRef::parse("invalid");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("format"));
    }
}

// Integration test
#[test]
fn test_validate_command() {
    let temp_dir = tempfile::tempdir().unwrap();
    let repo = create_test_repo(&temp_dir);
    
    let result = validate_primitives(&repo);
    assert!(result.is_ok());
    assert_eq!(result.unwrap().errors.len(), 0);
}

// Snapshot test (with insta)
#[test]
fn test_build_claude_command() {
    let command = load_fixture("commands/code-review");
    let transformed = claude_transformer.transform(&command).unwrap();
    
    insta::assert_snapshot!(transformed);
}
```

### Python Testing

```python
# Unit test (pytest)
def test_block_dangerous_command():
    result = process(
        hook_input={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
        config={},
        previous_results=[]
    )
    
    assert result.decision == "block"
    assert "dangerous" in result.reason.lower()
    assert result.metrics["blocked"] == True

# Integration test
def test_middleware_pipeline(tmp_path):
    hook_config = load_hook_config(tmp_path / "hook.meta.yaml")
    hook_input = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    
    results = run_pipeline(hook_config, hook_input)
    
    assert len(results) > 0
    assert all(r["decision"] in ["allow", "block", "continue"] for r in results)

# Mock external dependencies
def test_emit_metrics(mocker):
    mock_socket = mocker.patch("socket.socket")
    
    result = emit_metrics({"tool_usage": 1})
    
    assert result.decision == "continue"
    mock_socket.assert_called_once()
```

### Test Fixtures

```
cli/tests/fixtures/
├── valid/
│   ├── prompts/
│   │   └── agents/
│   │       └── python/
│   │           └── test-agent/
│   │               ├── test-agent.prompt.v1.md
│   │               └── test-agent.meta.yaml
│   ├── tools/
│   └── hooks/
└── invalid/
    ├── missing-meta/
    ├── invalid-schema/
    ├── broken-references/
    └── hash-mismatch/
```

### Coverage Tools

**Rust**:
```bash
# Run tests with coverage
cargo test --coverage

# Generate HTML report
cargo tarpaulin --out Html
```

**Python**:
```bash
# Run tests with coverage
uv run pytest --cov=hooks --cov-report=html

# Check coverage threshold
uv run pytest --cov=hooks --cov-fail-under=80
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test-rust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: dtolnay/rust-toolchain@stable
      
      - name: Run tests
        run: cargo test --all-features
      
      - name: Check coverage
        run: cargo tarpaulin --fail-under 80
  
  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Run tests
        run: uv run pytest --cov=hooks --cov-fail-under=80
```

## Success Criteria

TDD is successful when:

1. ✅ All code has corresponding tests (>80% coverage)
2. ✅ Tests are written before implementation
3. ✅ Tests run fast (<30s for full suite)
4. ✅ Tests catch regressions reliably
5. ✅ CI/CD enforces coverage thresholds
6. ✅ Tests serve as documentation
7. ✅ Team follows TDD workflow consistently

## Related Decisions

- **ADR-002: Strict Validation** - Tests validate validation logic
- **ADR-006: Middleware-Based Hooks** - Tests verify middleware behavior
- **ADR-007: Generated Provider Outputs** - Tests check transformations

## References

- [Test-Driven Development by Kent Beck](https://www.amazon.com/Test-Driven-Development-Kent-Beck/dp/0321146530)
- [The Art of Unit Testing](https://www.manning.com/books/the-art-of-unit-testing-third-edition)
- [Cargo test](https://doc.rust-lang.org/cargo/commands/cargo-test.html)
- [pytest documentation](https://docs.pytest.org/)

## Notes

**Testing is not optional.**

For a system designed to be used in automated, production workflows, testing is not a "nice to have" - it's a critical requirement. Without comprehensive tests:
- Validation logic might miss dangerous operations
- Hooks might fail silently
- Provider transformations might produce invalid outputs
- Refactoring becomes risky

**Testing is part of the definition of "done".**

A feature is not complete until it has:
1. ✅ Implementation
2. ✅ Tests (unit + integration)
3. ✅ Documentation
4. ✅ Coverage >80%

**Tests are first-class code.**

Tests deserve the same care as production code:
- Clear, descriptive names
- Well-organized
- DRY (Don't Repeat Yourself)
- Maintainable

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

