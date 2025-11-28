---
title: "ADR-015: Parallel QA Workflows with Modular Component-Based Architecture"
status: accepted
created: 2025-11-25
updated: 2025-11-25
author: Agentic Primitives Team
---

# ADR-015: Parallel QA Workflows with Modular Component-Based Architecture

## Status

**Accepted**

- Created: 2025-11-25
- Updated: 2025-11-25
- Author(s): Agentic Primitives Team

## Context

The agentic-primitives project is a polyglot monorepo with multiple components:
- **Rust CLI** (`cli/`) - Core command-line tool
- **Python Analytics Service** (`services/analytics/`) - Analytics middleware
- **Python Logging Library** (`lib/python/agentic_logging/`) - Centralized logging
- **Python Hooks** (`primitives/v1/hooks/`) - Hook implementations
- **Python Unit Tests** (`tests/unit/claude/`) - Test suites

### Current CI/CD State

The existing `.github/workflows/ci.yml` only validates Rust components:
- Format checking (cargo fmt)
- Linting (cargo clippy)
- Testing on 3 platforms (Ubuntu, macOS, Windows)
- Coverage reporting (Ubuntu only)

**Gaps Identified:**
1. **No Python validation** - Python packages never checked in CI
2. **Sequential execution** - Jobs run one after another where parallelization is possible
3. **No UV integration** - Project uses UV but CI doesn't
4. **Slow feedback** - ~15 minutes to complete all checks
5. **Limited coverage** - Only Rust code coverage tracked

### Requirements

1. **Comprehensive validation** - All Rust + Python components must be checked
2. **Fast feedback** - Target <10 minutes total CI time
3. **Clear attribution** - Easy to identify which component failed
4. **Efficient caching** - Minimize redundant work across runs
5. **Scalability** - Easy to add new components or languages
6. **Modern tooling** - Use UV for Python, latest GitHub Actions features

### Constraints

- Must maintain backward compatibility with existing workflows (security, benchmarks)
- Must work across all platforms (Ubuntu, macOS, Windows for Rust)
- Cannot significantly increase GitHub Actions quota usage
- Must preserve existing test coverage requirements (80%/90%)

## Decision

**We will implement a modular component-based QA workflow architecture** with maximum parallelization, replacing the existing `ci.yml` workflow with a new `qa.yml` workflow.

### Key Architectural Decisions

1. **Separate job per component type** (Rust format, Rust lint, Python analytics, etc.)
2. **No dependencies between independent checks** (all format/lint/type checks run in parallel)
3. **Granular caching strategy** (per-job cache keys based on file hashes)
4. **UV for Python** (using `astral-sh/setup-uv@v1` official action)
5. **Summary gate job** (`qa-success`) as required status check for PRs

### Workflow Structure

```yaml
qa.yml (Triggers: PR, push to main)
├── Rust Jobs (All Parallel)
│   ├── rust-format (cargo fmt --check)
│   ├── rust-lint (cargo clippy)
│   ├── rust-typecheck (cargo check)
│   └── rust-test (Matrix: ubuntu, macos, windows)
│
├── Python Jobs (All Parallel)
│   ├── python-analytics-checks (format, lint, type, test)
│   ├── python-logging-checks (format, lint, type, test)
│   ├── python-hooks-checks (format, lint, type)
│   └── python-unit-tests (pytest)
│
├── Integration Jobs (Depends: rust-test ubuntu, python-*)
│   ├── validate-primitives (agentic-p validate)
│   └── e2e-integration (placeholder)
│
└── qa-success (Depends: all above, required status check)
```

### Execution Strategy

- **Phase 1**: Fast checks (format, lint, typecheck) - 2-3 minutes
- **Phase 2**: Tests (unit, integration) - 5-7 minutes  
- **Phase 3**: Integration validation - 1-2 minutes

Total target: **<10 minutes** vs current **~15 minutes**

## Alternatives Considered

### Alternative 1: Monolithic Matrix-Based QA

**Description**: Single workflow with large job matrix covering all components using matrix strategy.

**Pros**:
- Single workflow file to manage
- Unified caching strategy
- All checks visible in one place

**Cons**:
- Complex matrix configuration (mixing Rust and Python)
- Harder to debug individual failures
- May hit GitHub Actions matrix limits (256 jobs max)
- Difficult to optimize caching per component
- Single point of failure

**Reason for rejection**: Complexity outweighs benefits. Mixed-language matrices are hard to maintain and debug. Component-specific optimization is difficult.

### Alternative 2: Separate Workflows Per Ecosystem

**Description**: Individual workflows: `rust-ci.yml`, `python-ci.yml`, `integration-ci.yml`

**Pros**:
- Clean technology separation
- Independent evolution
- Different trigger conditions possible
- Technology-specific maintainers

**Cons**:
- Multiple workflows to coordinate
- Harder to ensure all checks complete
- No single required status check
- Duplicate YAML boilerplate
- Complex branch protection rules

**Reason for rejection**: Coordination overhead too high. Need single "qa-success" gate for PRs. Multiple required status checks confusing for contributors.

### Alternative 3: Keep Current CI, Add Python CI

**Description**: Minimal change - keep `ci.yml` for Rust, add new `python-ci.yml` for Python

**Pros**:
- Minimal disruption
- Preserves working Rust CI
- Incremental improvement

**Cons**:
- Misses parallelization opportunities
- Doesn't address slow Rust checks
- No unified caching strategy
- Still no integration validation
- Perpetuates technical debt

**Reason for rejection**: Misses opportunity to optimize entire CI/CD pipeline. Half-measure that doesn't solve underlying problems.

## Consequences

### Positive Consequences

1. **Faster feedback** - Parallel execution reduces CI time by 30-40%
2. **Comprehensive validation** - All components checked automatically
3. **Clear failure attribution** - Job name immediately shows what failed
4. **Better caching** - Per-component cache keys improve hit rates
5. **Scalability** - Easy to add new components (just add new job)
6. **Modern tooling** - UV integration brings latest Python tooling benefits
7. **Quality assurance** - Python packages get same rigor as Rust code
8. **Developer experience** - Faster CI means faster iteration

### Negative Consequences

1. **More jobs to manage** - 13+ jobs vs 4 currently (complexity increase)
2. **Larger workflow file** - ~500 lines vs ~160 lines currently
3. **Learning curve** - Team needs to understand job dependencies
4. **Cache management** - More granular caches need monitoring
5. **Potential for cache thrashing** - If keys change frequently
6. **GitHub Actions quota** - More parallel jobs use quota faster

### Neutral Consequences

1. **Different failure patterns** - May see new failure modes initially
2. **Branch protection updates** - Need to update required checks
3. **Documentation updates** - CI/CD docs need rewriting
4. **Old workflow archived** - Moved to `workflows_archive/`

### Mitigation Strategies

**For complexity:**
- Comprehensive inline documentation in YAML
- Clear naming conventions (component-check pattern)
- Maintain CI/CD documentation

**For quota usage:**
- Monitor usage in first month
- Optimize caching strategy
- Consider self-hosted runners long-term

**For cache management:**
- Weekly cache cleanup (built-in GitHub feature)
- Monitor cache hit rates
- Document cache key patterns

## Implementation Notes

### Migration Path

1. **Phase 1: Setup** (Milestone 1)
   - Archive old `ci.yml` to `.github/workflows_archive/`
   - Create ADR-015 (this document)

2. **Phase 2: Rust Jobs** (Milestone 2)
   - Create `qa.yml` with Rust jobs
   - Implement granular caching
   - Test on current branch

3. **Phase 3: Python Jobs** (Milestones 3-6)
   - Add Python analytics checks
   - Add Python logging checks
   - Add Python hooks validation
   - Add Python unit tests

4. **Phase 4: Integration** (Milestones 7-8)
   - Add primitives validation
   - Add e2e integration placeholder
   - Add qa-success summary job

5. **Phase 5: Optimization** (Milestones 9-10)
   - Optimize caching strategy
   - Add concurrency controls
   - Performance tuning

6. **Phase 6: Release Enhancement** (Milestone 11)
   - Update release workflow
   - Add Python wheel builds (WIP)

7. **Phase 7: Documentation** (Milestones 12-13)
   - Update branch protection
   - Update CI/CD documentation
   - Add troubleshooting guide

### Systems Affected

- `.github/workflows/ci.yml` → archived
- `.github/workflows/qa.yml` → new (replaces ci.yml)
- `.github/workflows/release.yml` → enhanced
- `docs/ci-cd.md` → updated
- Branch protection rules → updated
- README.md badges → potentially updated

### Breaking Changes

- **Required status check name changes** from "CI Success" to "QA Success"
- **Old ci.yml workflow removed** (archived in workflows_archive/)
- **Branch protection rules must be updated** before merging

### Configuration Details

**Rust Caching:**
```yaml
cache-key: ${{ runner.os }}-cargo-${{ job.name }}-${{ hashFiles('cli/Cargo.lock') }}
cache-paths: 
  - ~/.cargo/registry
  - ~/.cargo/git
  - cli/target
```

**Python Caching:**
```yaml
# UV has built-in caching support
uses: astral-sh/setup-uv@v1
# Caches automatically based on pyproject.toml and uv.lock
```

**Concurrency:**
```yaml
concurrency:
  group: qa-${{ github.ref }}
  cancel-in-progress: true
```

### Validation Criteria

- [ ] All existing CI checks still run
- [ ] New Python checks execute successfully
- [ ] Total CI time <= 10 minutes
- [ ] Cache hit rate > 80% on subsequent runs
- [ ] Clear failure attribution in GitHub UI
- [ ] No false positives
- [ ] Branch protection works correctly

## References

- [GitHub Actions: Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [astral-sh/setup-uv Action](https://github.com/astral-sh/setup-uv)
- [GitHub Actions: Caching Dependencies](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows)
- [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain)
- ADR-008: Test-Driven Development (testing strategy)
- ADR-014: Wrapper+Impl Pattern (hooks testing)
- `PROJECT-PLAN_20251125_github-actions-qa-workflows.md` (detailed implementation plan)
- `Makefile` (local QA commands that CI mirrors)

---

**Implementation Status**: ✅ Accepted - Ready for execution  
**Timeline**: 13 milestones over 1-2 sessions  
**Success Metric**: <10min CI time, >80% cache hit rate, zero false positives

