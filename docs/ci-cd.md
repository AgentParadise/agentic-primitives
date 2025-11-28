# CI/CD Documentation

This document describes the continuous integration and deployment workflows for the Agentic Primitives project.

## Overview

The project uses GitHub Actions for automated quality assurance, testing, and releases. The CI/CD system is designed for:

- **Maximum parallelization** - Independent checks run simultaneously
- **Fast feedback** - Target <10 minutes for full QA suite
- **Clear attribution** - Each component has dedicated jobs for easy debugging
- **Comprehensive coverage** - Both Rust CLI and Python packages validated

## Workflows

### QA Workflow (`qa.yml`)

**Triggers:** Pull requests, pushes to `main` and `feat/*` branches, manual dispatch

The main quality assurance workflow runs all checks in parallel:

```
qa.yml
├── Rust Jobs (Parallel)
│   ├── rust-format      - cargo fmt --check
│   ├── rust-lint        - cargo clippy
│   ├── rust-typecheck   - cargo check
│   └── rust-test        - cargo test (Ubuntu, macOS, Windows)
│
├── Python Jobs (Parallel)
│   ├── python-analytics-checks  - Format, lint, type, test (services/analytics)
│   ├── python-logging-checks    - Format, lint, type, test (lib/python/agentic_logging)
│   ├── python-hooks-checks      - Format, lint, type (primitives/v1/hooks)
│   └── python-unit-tests        - pytest (tests/unit/claude)
│
├── Integration Jobs (Sequential, after above)
│   ├── validate-primitives      - agentic-p validate
│   └── e2e-integration          - Placeholder for future E2E tests
│
└── qa-success                   - Required status check for PRs
```

**Required Status Check:** `QA Success` must pass before merging PRs.

### Release Workflow (`release.yml`)

**Triggers:** Git tags matching `v*` (e.g., `v1.2.0`)

Handles versioned releases of the Rust CLI:

1. **Validate Release** - Check version in Cargo.toml matches tag
2. **Run QA** - Execute full QA workflow
3. **Build Binaries** - Cross-platform builds:
   - Linux x64
   - macOS x64
   - macOS ARM64
   - Windows x64
4. **Create GitHub Release** - Upload binaries with checksums
5. **Publish to crates.io** - Optional, requires `CARGO_REGISTRY_TOKEN`

### Security Workflow (`security.yml`)

**Schedule:** Every Monday at 9:00 AM UTC

- Runs `cargo audit` for vulnerability scanning
- Checks for outdated dependencies
- Generates SBOM (Software Bill of Materials)

### Benchmarks Workflow (`benchmarks.yml`)

**Schedule:** Every Sunday at 2:00 AM UTC

- Runs Criterion benchmarks
- Tracks performance over time
- Results published to GitHub Pages

## Running QA Locally

Use the Makefile for local QA checks that mirror CI:

```bash
# Run full QA suite (format check, lint, typecheck, test)
make qa

# Run with auto-fixes applied
make qa-fix

# Run individual checks
make rust-fmt rust-lint rust-test
make python-fmt python-lint python-typecheck python-test

# Simulate CI pipeline
make ci
```

### Python Checks with UV

The CI uses [UV](https://github.com/astral-sh/uv) for Python package management:

```bash
# Analytics service
cd services/analytics
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest

# Logging library
cd lib/python/agentic_logging
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest
```

## Caching Strategy

The workflows use granular caching for optimal performance:

| Component | Cache Key Pattern | Paths Cached |
|-----------|------------------|--------------|
| Rust | `{os}-cargo-{job}-{hash(Cargo.lock)}` | `~/.cargo/registry`, `cli/target` |
| Python | UV built-in caching | Managed by `astral-sh/setup-uv` |

Cache invalidation:
- Rust caches invalidate when `Cargo.lock` changes
- Python caches invalidate when `pyproject.toml` changes
- Caches expire after 7 days of no access

## Troubleshooting

### Common Issues

**"QA Success" check fails:**
- Check individual job results in the workflow run
- Each component has its own job for easy identification
- Look at the job summary for specific failures

**Rust tests pass locally but fail in CI:**
- CI runs on Ubuntu, macOS, and Windows
- Check platform-specific issues
- Verify all features are tested: `cargo test --all-features`

**Python checks fail:**
- Ensure you're using Python 3.11+
- Run `uv sync` to install dependencies
- Check `pyproject.toml` for required dev dependencies

**Cache not hitting:**
- Lock files may have changed
- Check cache key in workflow logs
- Caches may have expired (7-day limit)

### Debugging Workflow Runs

1. Go to Actions tab in GitHub
2. Select the workflow run
3. Expand failed job
4. Check step logs and annotations
5. Download artifacts if needed

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Full QA time | <10 minutes | All parallel jobs combined |
| Cache hit rate | >80% | On subsequent runs |
| Rust format check | <30 seconds | Fastest check |
| Rust test suite | <5 minutes | Longest individual job |

## Performance Benchmarks

We track performance metrics weekly to catch regressions early.

### Automated Benchmarks

- **Schedule**: Every Sunday at 2:00 AM UTC
- **What We Measure**:
  - Validation performance (all primitive types)
  - Build command performance
  - Provider transformation speed

### Running Benchmarks Locally

```bash
cd cli
cargo bench --workspace
```

Results are saved to `target/criterion/`.

### Viewing Historical Data

Benchmark data is stored in the `gh-pages` branch and visualized at:
https://neural.github.io/agentic-primitives/dev/bench

### Performance Targets

| Operation | Target | Current |
|-----------|--------|---------|
| Validate single primitive | <10ms | TBD |
| Build 100 primitives | <1s | TBD |
| Transform to Claude format | <50ms | TBD |

## Architecture Decision

See [ADR-015: Parallel QA Workflows](adrs/015-parallel-qa-workflows.md) for the architectural rationale behind the modular component-based QA design.

## Future Enhancements

- [ ] Differential testing (only test changed packages)
- [ ] Self-hosted runners for faster builds
- [ ] PyPI publishing for Python packages (if needed)
- [ ] Visual regression testing for documentation
- [ ] Automated dependency updates (Dependabot/Renovate)
