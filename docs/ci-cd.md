# CI/CD Documentation

This document describes the continuous integration and deployment workflows for the Agentic Primitives project.

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

