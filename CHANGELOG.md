# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [Unreleased]

### Planned for 1.1.0
- GitHub Actions CI/CD workflows
- Automated release pipeline
- Installation script (`curl | sh`)
- Homebrew formula
- Pre-built binaries for major platforms

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

