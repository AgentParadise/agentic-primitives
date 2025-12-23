---
title: "ADR-025: Just as Universal Task Runner"
status: accepted
created: 2024-12-15
updated: 2024-12-15
author: Agent Paradise Team
---

# ADR-025: Just as Universal Task Runner

## Status

**Accepted**

- Created: 2024-12-15
- Updated: 2024-12-15
- Author(s): Agent Paradise Team

## Context

Modern polyglot projects require a consistent way to run common tasks (linting, testing, building) across different language ecosystems. Without a universal task runner:

1. **Cognitive overhead**: Developers must remember different commands for each language
   - Python: `uv run pytest`, `uv run ruff check`
   - Rust: `cargo test`, `cargo clippy`
   - Node: `npm run test`, `npm run lint`

2. **CI/CD complexity**: Pipelines must handle multiple toolchains with different syntax

3. **Onboarding friction**: New contributors need to learn each ecosystem's conventions

4. **No discoverability**: Without a central task definition, developers grep scripts or read READMEs

The agentic-primitives project is polyglot (Rust CLI, Python services, TypeScript docs) and needs a single interface for:
- QA operations (`check`, `test`, `lint`, `format`)
- Development workflows (`init`, `clean`, `build`)
- Documentation (`docs`, `docs-build`)

## Decision

We will use **[Just](https://github.com/casey/just)** as the universal task runner for all Agent Paradise projects.

Every repository MUST have a `justfile` at the root exposing standardized commands:

```just
# Required commands
check        # Run all QA checks
check-fix    # Run all QA checks with auto-fix
lint         # Run linters
format       # Check formatting
format-fix   # Fix formatting  
typecheck    # Run type checkers
test         # Run test suite
build        # Build project
clean        # Clean artifacts
```

Language-specific commands should be namespaced:
- `rust-*` for Rust operations
- `python-*` for Python operations
- `docs-*` for documentation

## Alternatives Considered

### Alternative 1: Make

**Description**: Use GNU Make, the traditional build system.

**Pros**:
- Ubiquitous on Unix systems
- No installation required on most dev machines
- Familiar to many developers

**Cons**:
- Arcane syntax with significant whitespace (tabs vs spaces)
- Poor Windows support without additional tools
- Recipe dependencies are confusing
- No built-in help/listing

**Reason for rejection**: Syntax is hostile to newcomers. Tab sensitivity causes frustrating errors. Windows portability requires WSL or additional tools.

---

### Alternative 2: npm scripts

**Description**: Use `package.json` scripts even for non-Node projects.

**Pros**:
- Familiar to JavaScript developers
- Good tooling integration

**Cons**:
- Requires Node.js installation even for non-Node projects
- Limited cross-platform support without shell workarounds
- No recipe dependencies
- Verbose for complex scripts

**Reason for rejection**: Imposing Node.js on Rust/Python projects is backwards. Limited expressiveness for multi-language builds.

---

### Alternative 3: Task (taskfile.dev)

**Description**: Modern task runner using YAML configuration.

**Pros**:
- Cross-platform
- Good documentation
- Active development

**Cons**:
- YAML syntax is verbose for task definitions
- Less community adoption than Just
- More configuration overhead

**Reason for rejection**: Just's syntax is more readable and concise. YAML indentation can cause subtle errors.

---

### Alternative 4: cargo xtask

**Description**: Rust-native task runner pattern using a separate crate.

**Pros**:
- Pure Rust, no external dependencies
- Type-safe task definitions
- Great for Rust-only projects

**Cons**:
- Rust-only solution
- Significant boilerplate for simple tasks
- Compile time overhead

**Reason for rejection**: We have Python and TypeScript components. Would require maintaining multiple task systems.

---

### Alternative 5: Shell scripts

**Description**: Individual shell scripts for each task.

**Pros**:
- No dependencies
- Maximum flexibility

**Cons**:
- No discoverability (`just --list`)
- No dependency management between scripts
- Cross-platform support is DIY
- Scattered across filesystem

**Reason for rejection**: Poor developer experience. No unified interface.

## Consequences

### Positive Consequences

- **Unified interface**: `just check` works regardless of underlying tech stack
- **Discoverability**: `just --list` shows all available commands with descriptions
- **Cross-platform**: Built-in Windows PowerShell support with `[windows]` recipes
- **Simple syntax**: Shell commands with named targets, no arcane rules
- **Fast**: Single binary, no runtime dependencies

### Negative Consequences

- **Installation required**: Developers must install Just (`cargo install just` or `brew install just`)
- **Less ubiquitous than Make**: Some systems won't have it pre-installed

### Neutral Consequences

- **One more tool to learn**: Just syntax is simple enough that the learning curve is minimal
- **File at repo root**: `justfile` becomes a top-level file in every repository

## Implementation Notes

### Installation

```bash
# macOS
brew install just

# Cargo
cargo install just

# Other
# See https://github.com/casey/just#installation
```

### Justfile Structure

Use grouping for organization:

```just
# Settings
set shell := ["bash", "-euc"]
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Commands are grouped with [group('name')]
[group('qa')]
check: lint format typecheck test

[group('rust')]
rust-test:
    cargo test --workspace
```

### CI Integration

```yaml
# GitHub Actions
- name: Install Just
  uses: extractions/setup-just@v1

- name: Run checks
  run: just check
```

### Standard Command Mapping

| Just Command | Python | Rust | Node |
|--------------|--------|------|------|
| `lint` | `ruff check` | `cargo clippy` | `eslint` |
| `format` | `ruff format --check` | `cargo fmt --check` | `prettier --check` |
| `typecheck` | `mypy` / `pyright` | `cargo check` | `tsc --noEmit` |
| `test` | `pytest` | `cargo test` | `jest` / `vitest` |
| `build` | N/A | `cargo build` | `npm run build` |

## References

- [Just - Command Runner](https://github.com/casey/just) - Official repository
- [Just Manual](https://just.systems/man/en/) - Complete documentation
- ADR-015: Parallel QA Workflows - Related QA standardization
- [Taskfile.dev](https://taskfile.dev/) - Alternative considered
- [cargo-xtask](https://github.com/matklad/cargo-xtask) - Rust-native alternative

