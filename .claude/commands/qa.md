# /qa - Run QA Checks

Run comprehensive QA checks for the agentic-primitives repository.

## Quick Commands

```bash
# Run all checks (format check, lint, typecheck, test)
make qa

# Run checks with auto-fix for formatting/linting
make qa-fix

# Run specific checks
make lint           # Rust clippy + Python ruff
make fmt-check      # Check formatting only
make test           # Run all tests
```

## Workflow

### Step 1: Check Current Status

```bash
cd /Users/neural/Code/AgentParadise/agentic-primitives
git status --short
```

### Step 2: Run Full QA

```bash
make qa
```

If issues are found, run with auto-fix:

```bash
make qa-fix
```

### Step 3: Component-Specific Checks

#### Rust CLI (`cli/`)

```bash
# Format
cargo fmt --manifest-path cli/Cargo.toml --check

# Lint
cargo clippy --manifest-path cli/Cargo.toml -- -D warnings

# Test
cargo test --manifest-path cli/Cargo.toml
```

#### Python Libraries (`lib/python/`)

```bash
# agentic_settings
cd lib/python/agentic_settings
uv run python -m pytest

# agentic_analytics
cd lib/python/agentic_analytics
uv run python -m pytest

# agentic_logging
cd lib/python/agentic_logging
uv run python -m pytest
```

#### Tool Primitives

```bash
# Firecrawl scraper
cd primitives/v1/tools/scrape/firecrawl-scraper
uv run python -m pytest
uv run ruff check .
```

### Step 4: Validate Primitives

```bash
# Build and validate all primitives
cargo run --manifest-path cli/Cargo.toml -- validate primitives/v1/
```

## QA Checklist

- [ ] `make qa` passes (or individual components pass)
- [ ] No uncommitted changes (or changes are intentional)
- [ ] Primitives validate successfully
- [ ] Coverage targets met (Rust: see output, Python: 80%+)

## Report Format

```markdown
## QA Results

| Component | Status | Notes |
|-----------|--------|-------|
| Rust CLI (clippy) | ✅/❌ | |
| Rust CLI (fmt) | ✅/❌ | |
| Rust CLI (test) | ✅/❌ | X passed |
| Python libs | ✅/❌ | |
| Tool primitives | ✅/❌ | |
| Primitive validation | ✅/❌ | |

**Verdict:** ✅ READY TO COMMIT / ❌ NEEDS FIXES
```

## Troubleshooting

### Rust Issues

```bash
# If clippy fails with warnings
cargo clippy --manifest-path cli/Cargo.toml --fix --allow-dirty

# If fmt fails
cargo fmt --manifest-path cli/Cargo.toml
```

### Python Issues

```bash
# If ruff fails
cd lib/python/<package>
uv run ruff check --fix .

# If mypy fails (check types)
uv run mypy .
```

### Missing Dependencies

```bash
# Rust
cargo build --manifest-path cli/Cargo.toml

# Python (per package)
cd lib/python/<package>
uv pip install -e ".[dev]"
```

---

**Run this before every commit to ensure code quality.**

