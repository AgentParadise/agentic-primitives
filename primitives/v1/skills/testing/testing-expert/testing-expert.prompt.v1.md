---
description: Expert knowledge for analyzing testing architecture and planning improvements
model: sonnet
allowed-tools: Read, Grep, Glob, Bash
---

# Testing Expert

Expert knowledge for analyzing repository testing architecture, identifying gaps, and planning comprehensive testing improvements—with special focus on AI agent verification.

## Philosophy

### Core Principles

> **"Testing code is as important as production code."**
>
> **"Don't trust the agent, verify the world."**

Tests are not second-class citizens. They:
- Document expected behavior
- Enable safe refactoring
- Catch regressions before production
- Provide deployment confidence

For AI agents specifically, tests must **verify reality**, not just that the agent claimed success.

---

## The 5 Verification Levels

This is the most important concept for testing AI agent systems.

### The Problem: Tests That Lie

Traditional tests verify function returns. Agent tests often only verify:
- The code didn't crash
- The agent claimed success

**This is insufficient.** AI agents can claim success while failing. We found this actual code:

```python
def test_github_app_works(self):
    """Verify GitHub App can create files."""
    assert True  # ← Tests NOTHING
```

### The Verification Hierarchy

| Level | Name | Description | Confidence |
|-------|------|-------------|------------|
| 5 | **Invariant** | Property is ALWAYS true | ⭐⭐⭐⭐⭐ |
| 4 | **Outcome** | World state changed correctly | ⭐⭐⭐⭐ |
| 3 | **Event** | Correct events were emitted | ⭐⭐⭐ |
| 2 | **Output** | Function returned success | ⭐⭐ |
| 1 | **Existence** | Code didn't crash | ⭐ |

**Minimum acceptable: Level 3**
**Critical paths: Level 4-5**

### Anti-Patterns to Find

```python
# ❌ Level 1: USELESS - Tests nothing
def test_agent_works():
    agent.run("do something")
    assert True

# ❌ Level 2: WEAK - Trusts agent's claim
def test_agent_creates_file():
    result = agent.run("create file.py")
    assert result.status == "success"  # Agent could be lying

# ✅ Level 4: GOOD - Verifies reality
def test_agent_creates_file():
    result = agent.run("create file.py")
    assert Path("file.py").exists()  # Check filesystem
    content = Path("file.py").read_text()
    compile(content, "file.py", "exec")  # Verify valid Python
```

### Three-Source Verification

For critical claims, verify from THREE independent sources:

```python
async def verify_pr_created(execution_id: str, pr_number: int) -> bool:
    # Source 1: Our event store
    events = await event_store.read(f"execution-{execution_id}")
    pr_event = next((e for e in events if e.type == "PRCreated"), None)

    # Source 2: External API
    github_pr = await github.get_pr(pr_number)

    # Source 3: Ground truth
    branch_exists = await git_branch_exists(f"aef/{execution_id}")

    # ALL THREE must agree
    return pr_event and github_pr and branch_exists
```

---

## Analysis Workflow

### Step 1: Discover Test Structure

```bash
# Find test configuration
cat pytest.ini pyproject.toml setup.cfg 2>/dev/null | grep -A20 "\[tool.pytest"
cat jest.config.* vitest.config.* 2>/dev/null

# Find test directories
find . -type d -name "test*" -o -name "*tests*" | head -20

# Count test files
find . -name "test_*.py" -o -name "*_test.py" | wc -l
find . -name "*.test.ts" -o -name "*.spec.ts" | wc -l
```

### Step 2: Assess Test Types

```bash
# Find test markers/categories
grep -r "@pytest.mark\." --include="*.py" | cut -d: -f2 | sort | uniq -c

# Find integration tests
find . -path "*/integration/*" -name "test_*.py"

# Find E2E tests
find . -path "*/e2e/*" -name "*.py" -o -name "e2e_*.py"
```

### Step 3: Find Anti-Patterns

```bash
# Level 1: assert True (useless)
grep -rn "assert True" --include="*.py"

# Level 2: Only checking status
grep -rn "assert.*\.status\|assert.*\.success" --include="*.py"

# Missing assertions
grep -rn "def test_" --include="*.py" -A10 | grep -B5 "^--$"
```

### Step 4: Assess Coverage

```bash
# Check coverage configuration
grep -r "cov" pyproject.toml pytest.ini

# Find coverage reports
find . -name "*.coverage" -o -name "coverage.xml" -o -name "htmlcov"

# Check CI for coverage gates
cat .github/workflows/*.yml | grep -i "coverage\|cov-fail"
```

### Step 5: Check CI Integration

```bash
# What runs in CI?
cat .github/workflows/*.yml | grep -E "pytest|jest|vitest|test"

# Coverage gates?
cat .github/workflows/*.yml | grep "cov-fail-under"

# Test parallelization?
cat .github/workflows/*.yml | grep -i "parallel\|matrix"
```

---

## Assessment Report Template

```markdown
# Testing Architecture Assessment

## Summary

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Test Files | X | - | - |
| Test Functions | X | - | - |
| Coverage | X% | 80% | X% |
| Unit:Integration:E2E | X:X:X | 70:20:10 | - |

## Test Structure

### Strengths
- ✅ [What's working well]

### Gaps
- ❌ [What's missing or broken]

## Anti-Patterns Found

### Level 1 Violations (assert True)
| File | Line | Issue |
|------|------|-------|
| path/file.py | 42 | `assert True` |

### Level 2 Violations (Trust without verify)
| File | Line | Issue |
|------|------|-------|
| path/file.py | 88 | `assert result.success` without verification |

## Recommendations

### Priority 1: Critical (Do Now)
1. [Action item]

### Priority 2: Important (This Sprint)
1. [Action item]

### Priority 3: Nice to Have (Backlog)
1. [Action item]

## Implementation Plan

### Week 1: Foundation
- [ ] Task 1
- [ ] Task 2

### Week 2: Core Improvements
- [ ] Task 3
- [ ] Task 4
```

---

## Testing Patterns

### Pattern 1: Arrange-Act-Assert (AAA)

```python
def test_user_creation():
    # Arrange
    user_data = {"name": "Alice", "email": "alice@example.com"}

    # Act
    user = create_user(user_data)

    # Assert
    assert user.id is not None
    assert user.name == "Alice"
```

### Pattern 2: Given-When-Then (BDD)

```python
def test_checkout_applies_discount():
    # Given a cart with items over $100
    cart = Cart()
    cart.add(Item(price=150))

    # When checkout is performed
    order = checkout(cart, discount_code="SAVE10")

    # Then 10% discount is applied
    assert order.total == 135
```

### Pattern 3: Fixture Factory

```python
@pytest.fixture
def make_user():
    """Factory fixture for creating test users."""
    created = []

    def _make_user(**kwargs):
        user = User(
            name=kwargs.get("name", "Test User"),
            email=kwargs.get("email", f"test-{uuid4()}@example.com"),
        )
        created.append(user)
        return user

    yield _make_user

    # Cleanup
    for user in created:
        user.delete()
```

### Pattern 4: Test Doubles

| Double | Use Case |
|--------|----------|
| **Dummy** | Fill parameters, never used |
| **Stub** | Return predetermined values |
| **Spy** | Record calls for later verification |
| **Mock** | Pre-programmed expectations |
| **Fake** | Working implementation (in-memory DB) |

### Pattern 5: Property-Based Testing

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sort_is_idempotent(items):
    """Sorting twice gives same result as sorting once."""
    once = sorted(items)
    twice = sorted(sorted(items))
    assert once == twice

@given(st.lists(st.integers()))
def test_sort_preserves_length(items):
    """Sorting doesn't change list length."""
    assert len(sorted(items)) == len(items)
```

---

## Coverage Best Practices

### Coverage Targets by Component Type

| Component | Target | Rationale |
|-----------|--------|-----------|
| Business Logic | 90%+ | Core value, must be correct |
| API Handlers | 80%+ | User-facing, critical paths |
| Utilities | 85%+ | Widely used, high leverage |
| Infrastructure | 70%+ | Integration tested |
| Generated Code | 0% | Skip, test generator instead |

### Coverage Exclusions

```python
# pyproject.toml
[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

### Coverage vs Quality

> **High coverage ≠ Good tests**

100% coverage with bad assertions is worse than 60% coverage with thorough verification.

**Focus on:**
- Critical path coverage
- Edge case coverage
- Verification quality (Level 4+)

---

## CI/CD Integration

### Essential CI Gates

```yaml
# Required for merge
- name: Run tests
  run: pytest --cov --cov-fail-under=70

- name: Check types
  run: mypy src

- name: Lint
  run: ruff check .
```

### Test Parallelization

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - run: pytest --shard-id=${{ matrix.shard }} --num-shards=4
```

### Flaky Test Detection

```yaml
- name: Run tests with retries
  run: pytest --reruns 2 --reruns-delay 1
```

---

## Common Gaps & Fixes

### Gap 1: No Integration Tests

**Symptom:** All tests mock everything
**Fix:** Add tests with real database/services using testcontainers

### Gap 2: Tests Without Assertions

**Symptom:** `def test_x(): some_code()` with no assert
**Fix:** Add explicit verification of expected outcomes

### Gap 3: Flaky Tests

**Symptom:** Tests pass/fail randomly
**Fix:**
- Remove time-dependencies (use freezegun)
- Add proper async handling
- Use deterministic test data

### Gap 4: Slow Test Suite

**Symptom:** Tests take >5 minutes
**Fix:**
- Parallelize with pytest-xdist
- Use fixtures with proper scope
- Mock expensive external calls

### Gap 5: Missing Edge Cases

**Symptom:** Bugs in production that "tests should have caught"
**Fix:**
- Add property-based testing
- Review with mutation testing
- Add regression tests for each bug found

---

## Related Skills

- `testing/ai-agent-verification` - Deep dive on AI agent testing
- `devops/ci-cd` - CI/CD pipeline configuration
- `review/prioritize` - Prioritize issues by severity
