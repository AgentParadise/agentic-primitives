# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🎯 Agentic Prompts & Smart Sync

Major additions for prompt primitives and improved install workflow.

### Added

- **Prompt primitives**: New prompt types with full taxonomy
  - `commands/` - Task execution prompts (e.g., `/review`, `/pre-commit-qa`, `/qa-setup`)
  - `meta-prompts/` - Prompt generators (e.g., `/create-prime`, `/create-doc-sync`, `/prompt-generator`)
  - `agents/` and `skills/` - Directory structure for future expansion

- **Manifest-based smart sync**: `build` and `install` commands now track managed files
  - `.agentic-manifest.yaml` generated during build with primitive metadata
  - Install shows sync preview (new/updated/unchanged primitives)
  - **Local files preserved** - files not in manifest (e.g., generated `/doc-sync`) are not overwritten

- **Per-project configuration**: `agentic.yaml` for version overrides
  - `agentic-p config init` - Generate config template (tsconfig-style with commented options)
  - `agentic-p config show` - Display current configuration
  - `agentic-p config list` - List available primitives

- **agentic_settings package**: Centralized configuration management
  - Pydantic-settings based API key management
  - Auto-discovery of `.env` files
  - Type-safe settings with validation

### Changed

- Build command now outputs manifest for tracking installed primitives
- Install command uses manifest diff to only update changed files
- Prompt frontmatter uses model aliases (e.g., `sonnet`) instead of explicit versions

### Fixed

- **Claude CLI attribution in commits**: Updated `.claude/settings.json` format per official docs
  - Changed to `attribution: {commit: "", pr: ""}` (empty strings disable attribution)
  - Fixes issue where "Generated with Claude Code" and Co-Authored-By attribution appeared in commits
  - Added regression test (`test_claude_cli_attribution.py`) to validate attribution is disabled
  - See: https://code.claude.com/docs/en/settings#attribution-settings

---

## [1.2.0] - 2025-11-26

### 🔄 Self-Logging Hooks Architecture

Major refactoring of the analytics architecture from centralized hooks-collector to self-logging hooks.

### Added

- **agentic-analytics library**: New Python client library for hook decision logging
  - `AnalyticsClient` for logging to JSONL files and/or API endpoints
  - `HookDecision` dataclass for standardized decision tracking
  - Validation utilities for E2E testing of analytics events
  - DI-friendly configuration via environment variables or constructor

- **Provider configurations**: Added missing `config.yaml` files for Google and OpenAI model providers

### Changed

- **Security hooks now self-log**: `bash-validator`, `file-security`, and `prompt-filter` hooks now log decisions directly via `AnalyticsClient`
- **Rust CLI ModelConfig**: Updated to match actual YAML file format used in model definitions
- **Hook scaffold template**: Fixed YAML indentation in generated hook files
- **Claude transformer tests**: Updated to use new `.claude/settings.json` structure

### Removed

- **hooks-collector**: Removed centralized hooks-collector infrastructure (superseded by self-logging pattern)
- **Middleware pipeline**: Simplified architecture removes complex middleware orchestration

### Architecture

- ADR-013 (Hybrid Hook Architecture) marked as superseded
- Each hook now directly logs its decisions, eliminating middleware complexity
- Enables easier dependency injection of analytics backends

---

## [1.0.0] - 2025-11-15

### 🎉 Initial Release - Production Ready

The first production-ready release of Agentic Primitives, a complete framework for managing atomic AI agent components with industrial-grade validation, versioning, and multi-provider support.

### Added

#### Core CLI Commands (10/10)
- **`init`** - Initialize new primitives repository with scaffolding
- **`new`** - Create new primitives from templates (agents, commands, skills, meta-prompts, tools, hooks)
- **`validate`** - Three-layer validation system (structural, schema, semantic)
- **`list`** - Discover and list all primitives with filtering
- **`inspect`** - Detailed primitive information and metadata
- **`version`** - Version management (bump, list, promote, deprecate)
- **`migrate`** - Cross-version migration support
- **`build`** - Transform primitives to provider-specific formats
- **`install`** - Deploy built outputs to project or global locations
- **`test-hook`** - Local hook testing with mock events

#### Validation System
- **Structural validation**: Directory structure, required files, naming conventions
- **Schema validation**: JSON schema validation against versioned specs
- **Semantic validation**: Cross-references, version integrity, hash verification
- BLAKE3 hashing for content integrity
- Kebab-case naming enforcement
- Comprehensive error messages with actionable suggestions

#### Versioning System
- System-level versioning for architectural shifts (`/v1/`, `/v2/`)
- Prompt-level versioning with hash validation
- Version status management (draft, active, deprecated)
- Immutable version content with BLAKE3 hashes
- Version promotion and deprecation workflows
- Migration support between system versions

#### Provider Support
- **Claude**: Full support for Claude Agent SDK format
  - Transform prompts to `.claude/agents/`, `.claude/commands/`
  - Tool transformations with MCP bindings
  - Hook middleware orchestration
- **OpenAI**: Full support for OpenAI API format
  - Function calling transformations
  - System/user prompt formatting
  - Tool schema conversions

#### Primitive Types

##### Prompt Primitives
- **Agents**: Personas and roles with context usage preferences
- **Commands**: Discrete tasks with input/output specs
- **Skills**: Knowledge overlays and pattern libraries
- **Meta-Prompts**: Prompt generators for bootstrapping new primitives

##### Tool Primitives
- Logical tool specifications (provider-agnostic)
- Provider-specific implementations (Claude MCP, OpenAI functions, local Rust/Python/Bun)
- Safety constraints (runtime limits, working directory, write permissions)
- Argument validation and type checking

##### Hook Primitives
- Lifecycle event handlers (PreToolUse, PostToolUse, etc.)
- Middleware pipeline architecture:
  - **Safety middleware**: Blocking, fail-fast validation
  - **Observability middleware**: Non-blocking, parallel execution
- Python (uv) and Bun runtime support
- Decision-based control flow (allow, deny, modify)

#### Build & Install System
- Streaming transformation pipeline for memory efficiency
- Provider-native output generation
- Project-local installation (`.claude/`, `.openai/`)
- Global installation (`~/.claude/`, `~/.openai/`)
- Automatic backup with timestamping
- Dry-run mode for safety
- Type and kind filtering

#### Templates
- Handlebars-based template system
- Templates for all primitive types
- Consistent YAML structure generation
- Schema-compliant output
- Proper indentation and formatting

#### Testing
- **302 tests passing** (204 unit + 98 integration)
- E2E integration tests for full lifecycle
- Performance benchmarks with criterion.rs
- Cross-version compatibility tests
- Provider transformation validation
- Error handling coverage
- Test fixtures for all primitive types

#### Documentation
- Comprehensive README with quick start
- Architecture documentation with diagrams
- Versioning guide with best practices
- Getting started tutorial
- 10 Architecture Decision Records (ADRs):
  - ADR-001: Staged Bootstrap Strategy
  - ADR-002: Strict Validation
  - ADR-003: Non-Interactive Scaffolding
  - ADR-004: Provider-Scoped Models
  - ADR-005: Polyglot Implementations
  - ADR-006: Middleware-Based Hooks
  - ADR-007: Generated Provider Outputs
  - ADR-008: Test-Driven Development
  - ADR-009: Versioned Primitives
  - ADR-010: System-Level Versioning

#### Repository Structure
- Organized primitive storage (`primitives/v1/`)
- Versioned JSON schemas (`specs/v1/`)
- Provider configuration and models
- Experimental sandbox for v2+ testing
- Clean separation of concerns

#### Developer Experience
- Makefile for turnkey operations
- Automated formatting (Rust + Python)
- Linting with clippy and ruff
- Type checking with mypy
- QA checkpoint automation
- Git hooks support

### Technical Details

#### Dependencies
- **Rust**: 1.75+ with modern features
- **Key Crates**: clap, serde, anyhow, thiserror, walkdir, blake3, chrono, dirs, criterion
- **Python**: 3.11+ with uv for fast dependency management
- **Node**: Bun for TypeScript/JavaScript hook implementations

#### Performance
- Streaming transformations for large primitive sets
- Efficient directory traversal
- Parallel test execution
- Benchmarked critical paths (validation, build)

#### Quality Metrics
- 302 tests with >90% coverage
- Zero clippy warnings
- Full type safety (Rust + Python)
- Schema validation for all YAML
- Consistent error handling with anyhow/thiserror

### Breaking Changes
None - this is the initial release.

### Migration Guide
None - this is the initial release.

### Known Issues
None - all tests passing, production ready.

### Contributors
- Built with love for the AI agent community 🤖

---

## [1.1.0] - 2025-11-15

### 🚀 Phase 2: CI/CD & Distribution

Complete CI/CD pipeline with automated testing, releases, security audits, and universal installation system.

### Added

#### GitHub Actions Workflows
- **CI Workflow** (`.github/workflows/ci.yml`)
  - Multi-OS testing (Ubuntu, macOS, Windows)
  - Format checking with `cargo fmt`
  - Linting with clippy (zero warnings)
  - Fixture validation
  - Code coverage with codecov
  - Triggers on PRs and pushes to main

- **Release Workflow** (`.github/workflows/release.yml`)
  - Automated releases on version tags
  - Multi-platform binary builds (Linux x64/ARM64, macOS x64/ARM, Windows x64)
  - SHA256 checksum generation
  - GitHub Release creation with binaries
  - Optional crates.io publishing

- **Security Workflow** (`.github/workflows/security.yml`)
  - Weekly cargo audit for vulnerability scanning
  - Dependency review on PRs
  - SBOM (Software Bill of Materials) generation
  - Automated security reporting

- **Benchmarks Workflow** (`.github/workflows/benchmarks.yml`)
  - Weekly performance benchmarking
  - Baseline comparison tracking
  - Regression detection
  - Performance trend reporting

#### Installation System
- **Universal Install Script** (`scripts/install.sh`)
  - One-line installation: `curl -fsSL ... | sh`
  - OS/architecture auto-detection
  - GitHub Release binary download
  - SHA256 checksum verification
  - Automatic PATH integration
  - Version selection support
  - Clean uninstall option

- **Bootstrap Script** (`scripts/bootstrap.sh`)
  - One-command repository setup
  - Automatic CLI installation
  - Stack detection (Python, TypeScript, React, NestJS, TurboRepo, Rust)
  - Stack-specific primitive installation
  - `.gitignore` configuration
  - Optional git hook setup
  - Composable integration for any tech stack

#### Stack Presets
Pre-configured primitive sets for popular stacks:
- **Python** (`scripts/stacks/python.yaml`)
  - UV-based tooling hooks
  - Python testing agents
  - Code quality commands
- **TypeScript** (`scripts/stacks/typescript.yaml`)
  - Bun runtime support
  - TS linting hooks
  - Type checking agents
- **React** (`scripts/stacks/react.yaml`)
  - Component generation agents
  - React hooks validation
  - UI best practices skills
- **NestJS** (`scripts/stacks/nestjs.yaml`)
  - API endpoint agents
  - Dependency injection hooks
  - Service scaffolding commands
- **TurboRepo** (`scripts/stacks/turborepo.yaml`)
  - Monorepo management agents
  - Workspace coordination hooks
  - Build orchestration commands
- **Rust** (`scripts/stacks/rust.yaml`)
  - Cargo integration hooks
  - Rust best practices agents
  - Safety validation commands

#### Documentation
- **CI/CD Guide** (`docs/ci-cd.md`)
  - Workflow architecture
  - Trigger conditions
  - Badge integration
  - Troubleshooting guide
- **Release Process** (`docs/release-process.md`)
  - Version bumping workflow
  - Release checklist
  - Rollback procedures
  - Distribution channels
- **Security Policy** (`docs/security.md`)
  - Vulnerability reporting
  - Security audit schedule
  - Dependency management
  - SBOM usage

#### Validation & Quality
- Stack preset validation script (`scripts/validate-stacks.sh`)
- Bash script syntax validation
- YAML workflow validation with yamllint
- All 302 tests continue to pass

### Improvements
- **Code Quality**: Fixed remaining clippy warnings
  - Replaced `vec![]` with array `[]` for static lists
  - Simplified identical if blocks
  - Improved code clarity

### Breaking Changes
None - fully backward compatible with v1.0.0.

### Migration from v1.0.0
No migration needed - drop-in replacement. Simply:
```bash
curl -fsSL https://raw.githubusercontent.com/AgentParadise/agentic-primitives/main/scripts/install.sh | sh
```

### Contributors
Built with ❤️ for the AI agent community 🤖

---

## [Unreleased]

### Planned Features
- Homebrew formula for macOS installation
- Chocolatey package for Windows
- Docker images for containerized usage
- VSCode extension for primitive development
- Web-based primitive explorer
- Community primitive registry

---

**Legend**:
- 🎉 Major milestone
- ✨ New feature
- 🐛 Bug fix
- 📚 Documentation
- ⚡ Performance
- 🔒 Security
- ♻️ Refactoring
- 🧪 Testing
- 🎨 UI/UX
