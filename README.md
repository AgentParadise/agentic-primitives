# Agentic Primitives

> **Atomic building blocks for AI coding systems**

A source-of-truth repository of reusable, versionable, and provider-agnostic primitives for building agentic AI systems. Think of it as a standard library for AI agents—prompts, tools, and hooks that you can compose, version, and deploy across different LLM providers.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Rust](https://img.shields.io/badge/rust-1.75+-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## 🎯 What Are Agentic Primitives?

Agentic primitives are **atomic, reusable components** that define how AI agents think, act, and integrate into your workflows:

- **🧠 Prompt Primitives**: Personas (agents), tasks (commands), knowledge patterns (skills), and meta-prompts for generating other primitives
- **🔧 Tool Primitives**: Logical tool specifications with optional provider-specific implementations (Claude, OpenAI, local Rust/Python/Bun)
- **🪝 Hook Primitives**: Lifecycle event handlers with composable middleware for safety, observability, and control (UV-based, no bash required!)

All primitives are:
- ✅ **Version-controlled** with immutable hashes (BLAKE3)
- ✅ **Provider-agnostic** at their core, compiled to specific formats
- ✅ **Strictly validated** across structural, schema, and semantic layers
- ✅ **Composable** - mix and match to build complex agentic behaviors
- ✅ **Router-friendly** - organized by type/category/id for easy navigation

---

## 🚀 Quick Start

### Prerequisites

- **Rust** 1.75+ (for building the CLI)
- **UV** (for cross-platform Python execution)
- **Python** 3.11+ (managed by UV)
- **Make** (optional, for turnkey operations)

#### Installing UV

UV is **required** for running hooks with proper dependency management. It provides cross-platform Python execution without bash dependencies:

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Verify Installation:**
```bash
uv --version
```

#### Why UV?

- ✅ **Cross-platform:** Works on Windows, Mac, and Linux (no bash required!)
- ✅ **Fast:** Rust-based, 10-100x faster than pip
- ✅ **Isolated:** Manages Python environments per project automatically
- ✅ **Zero config:** Just works out of the box

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-primitives.git
cd agentic-primitives

# Build the CLI (requires Just: brew install just / winget install Casey.Just)
just build

# Install the CLI to your PATH
just install

# Verify installation
agentic-p --version
```

### Initialize a New Repository

```bash
# Create a new agentic-primitives repository
agentic-p init

# Or initialize in a specific directory
agentic-p init --path ./my-primitives
```

### Create Your First Primitive

```bash
# Create a Python expert agent
agentic-p new prompt agent python/python-pro

# Create a code review command
agentic-p new command review/code-review

# Create a testing knowledge skill
agentic-p new skill testing/pytest-patterns

# Create a safety hook
agentic-p new hook lifecycle/pre-tool-use
```

### Validate Everything

```bash
# Run all validation layers
agentic-p validate

# Check specific primitive
agentic-p inspect python/python-pro
```

### Configure Per-Project (Optional)

```bash
# Generate agentic.yaml with all options commented (tsconfig-style)
agentic-p config init

# List available primitives for version pinning
agentic-p config list
```

Pin specific versions like npm resolutions—only override what you need:

```yaml
# agentic.yaml
primitives:
  qa/review: 1          # Pin to v1
  qa/pre-commit-qa: latest
```

### Build for Your Provider

```bash
# Build for Claude Code (generates .agentic-manifest.yaml)
agentic-p build --provider claude

# Smart install - only updates changed primitives, preserves local files
agentic-p install --provider claude

# Or preview what would change with dry-run
agentic-p install --provider claude --dry-run --verbose

# Result: Primitives installed, local commands (like /doc-sync) preserved!
```

**Build Output** (organized by category):
```
build/claude/hooks/
├── hooks.json          ← All 9 events configured
├── core/               ← Universal hooks
├── security/           ← Security hooks
└── analytics/          ← Analytics hooks
```

---

## 📚 Core Concepts

### Terminology (Claude Agent SDK)

This framework uses [Claude Agent SDK](https://docs.anthropic.com/en/docs/claude-code) terminology:

| Term | What it does | How to invoke |
|------|--------------|---------------|
| **Command** | Performs a specific task | `/command-name` |
| **Skill** | Provides reusable expertise | Referenced in prompts |
| **Agent** | Maintains a persistent persona | `@agent-name` |
| **Tool** | Integrates external systems | Available to agents |
| **Hook** | Handles lifecycle events | Automatic |
| **Meta-prompt** | Generates other prompts | `/meta/prompt-name` |

### Primitive Types

Organized by **type** and **category** for router-like navigation (matching Claude Code `.claude/` conventions):

```
primitives/v1/
├── commands/<category>/<id>/        # User-invoked actions (/command-name)
│   └── meta/<id>/                   # Meta-prompts (prompt generators)
├── skills/<category>/<id>/          # Reusable capabilities (referenced)
├── agents/<category>/<id>/          # Persistent personas (@agent-name)
├── tools/<category>/<id>/           # MCP tool integrations
└── hooks/<category>/<id>/           # Lifecycle event handlers
```

**Example**: `primitives/v1/commands/qa/review/`

Each primitive contains:
- `review.meta.yaml` - Metadata with version registry, model preferences, tool dependencies
- `review.prompt.v1.md` - Versioned prompt content
- `review.prompt.v2.md` - Next version (when created)

### Tool Primitives

Logical capability definitions with optional provider bindings:

```
primitives/v1/tools/<category>/<id>/
├── <id>.tool.yaml             # Generic tool specification
├── impl.claude.yaml           # Claude SDK binding
├── impl.openai.json           # OpenAI function calling
└── impl.local.{rs|py|ts}      # Local implementation
```

### Hook Primitives

Lifecycle event handlers with **self-logging analytics**:

```
primitives/v1/hooks/
├── analytics/                   # Analytics hooks
│   └── analytics-collector/     # Session tracking
└── security/                    # Security hooks (with built-in analytics)
    ├── bash-validator/          # Dangerous command detection
    ├── file-security/           # Sensitive file protection
    └── prompt-filter/           # PII/credential scanning
```

**Self-Logging Architecture**:

Each hook logs its own decisions to a central analytics service:

| Hook | Purpose | Events | Actions |
|------|---------|--------|---------|
| `bash-validator` | Block dangerous commands | `PreToolUse` | Block `rm -rf`, `sudo rm`, etc. |
| `file-security` | Protect sensitive files | `PreToolUse` | Warn on `.env`, redact secrets |
| `prompt-filter` | Detect PII in prompts | `UserPromptSubmit` | Warn on emails, API keys |

**Key Benefits**:
- ✅ **Complete Audit Trail**: Every hook decision logged to `.agentic/analytics/events.jsonl`
- ✅ **Self-Contained**: Each hook handles its own analytics (no central collector needed)
- ✅ **Fail-Safe**: Analytics errors never block hook execution
- ✅ **DI-Friendly**: Configure file or API backend via environment variables

### Git Observability Hooks

Track git operations for developer analytics and token efficiency metrics:

```bash
# Install git hooks (cross-platform Python installer)
python primitives/v1/hooks/git/install.py

# Or install globally for all repos
python primitives/v1/hooks/git/install.py --global
```

| Hook | Event Type | Tracks |
|------|------------|--------|
| `post-commit` | `git_commit` | Commits with token estimates |
| `post-checkout` | `git_branch_created` / `git_branch_switched` | Branch operations |
| `post-merge` | `git_merge_completed` | Merges to stable branches |
| `post-rewrite` | `git_commits_rewritten` | Rebases and amends |
| `pre-push` | `git_push_started` | Push operations |

**Token Efficiency**: Calculates estimated tokens (chars/4) to measure "code committed / tokens used" ratio.

See [ADR-022: Git Hook Observability](docs/adrs/022-git-hook-observability.md) for architecture details.

**Agent-Centric Configuration**:

Hooks are **generic implementations**, configured per-agent:

```
providers/agents/claude-code/
├── hooks-supported.yaml         # All 9 Claude events
└── hooks-config/
    ├── bash-validator.yaml      # Security: dangerous commands
    ├── file-security.yaml       # Security: sensitive files
    └── prompt-filter.yaml       # Security: PII/credentials
```

Same hook primitives, different configs for Claude vs. Cursor vs. LangGraph!

**Use cases**:
- 🛡️ **Safety**: Block dangerous bash commands, protect sensitive files, validate tool inputs
- 📊 **Observability**: Log operations, emit metrics, track token usage, debug tracing
- 🎯 **Control**: Auto-approve safe operations, add context, enforce policies
- 📈 **Analytics**: Comprehensive event tracking with 97.30% test coverage

### Versioning

Agents, commands, and meta-prompts **require versioning**:

```yaml
# In <id>.yaml (e.g., python-pro.yaml)
spec_version: "v1"
versions:
  - version: 1
    status: active
    hash: blake3:abc123...
    created: "2025-11-13"
    notes: "Initial version"
  - version: 2
    status: draft
    hash: blake3:def456...
    created: "2025-11-14"
    notes: "Added async patterns expertise"

default_version: 1  # Use v1 by default
```

**Version management**:

```bash
# Create a new version
agentic-p version bump python/python-pro --notes "Added async expertise"

# List all versions
agentic-p version list python/python-pro

# Promote draft to active
agentic-p version promote python/python-pro --version 2

# Deprecate old version
agentic-p version deprecate python/python-pro --version 1
```

### Provider Taxonomy

Providers are organized into **models** (LLM APIs) and **agents** (runtime frameworks):

```
providers/
├── models/                      # LLM API providers
│   ├── anthropic/               # Claude models (Opus, Sonnet, Haiku)
│   ├── openai/                  # GPT models
│   └── google/                  # Gemini (future)
│
└── agents/                      # Agent runtime providers
    ├── claude-code/             # Claude Code (hooks: PreToolUse, PostToolUse, etc.)
    │   ├── config.yaml          # Agent metadata
    │   ├── hooks-supported.yaml # Supported hook events
    │   ├── hooks-format.yaml    # hooks.json format spec
    │   └── hooks-config/        # Hook configurations per primitive
    ├── cursor/                  # Cursor IDE (future)
    └── langgraph/               # LangGraph (future)
```

**Key Insight**: Agent providers *use* model providers. Claude Code can use Anthropic, OpenAI, or Google models!

Each agent provider includes:
- **Supported Events**: Which hook events the agent fires
- **Hook Format**: How to generate `hooks.json` for the agent
- **Hook Configurations**: Per-primitive middleware and matcher configs
- **Validation**: JSON schemas for all configuration files

**Build Process**:
1. Read primitive from `primitives/v1/`
2. Load agent provider config from `providers/agents/{agent}/`
3. Generate provider-specific output in `build/{agent}/`
4. Copy to project's `.{agent}/` directory

---

## 🛠️ Development Workflow

All development operations use **[Just](https://github.com/casey/just)** for cross-platform consistency:

```bash
# Install Just (if not already installed)
# macOS: brew install just
# Windows: winget install Casey.Just
# Linux: cargo install just

# Show all available commands
just

# Format code (Rust + Python)
just fmt

# Lint code
just lint

# Type check Python
just typecheck

# Run all tests
just test

# Full QA suite (format check, lint, typecheck, test)
just qa

# Auto-fix issues and run QA
just qa-fix

# Build debug version
just build

# Build release version
just build-release

# Clean, check, and build everything
just verify
```

### Install Git Hooks (Optional)

```bash
# Auto-run QA checks before commits
just git-hooks-install
```

---

## 📖 Documentation

- **[Getting Started Guide](docs/getting-started.md)** - Step-by-step tutorial
- **[Architecture](docs/architecture.md)** - System design and diagrams
- **[Versioning Guide](docs/versioning-guide.md)** - Complete versioning documentation
- **[CLI Reference](docs/cli-reference.md)** - All commands and options
- **[Hooks Guide](docs/hooks-guide.md)** - Writing middleware and orchestrators
- **[Contributing](docs/contributing.md)** - How to contribute

### Architecture Decision Records (ADRs)

- [ADR-000: Template](docs/adrs/000-adr-template.md)
- [ADR-001: Staged Bootstrap Strategy](docs/adrs/001-staged-bootstrap.md)
- [ADR-002: Strict Validation](docs/adrs/002-strict-validation.md)
- [ADR-003: Non-Interactive Scaffolding](docs/adrs/003-non-interactive-scaffolding.md)
- [ADR-004: Provider-Scoped Models](docs/adrs/004-provider-scoped-models.md)
- [ADR-005: Polyglot Implementations](docs/adrs/005-polyglot-implementations.md)
- [ADR-006: Middleware-Based Hooks](docs/adrs/006-middleware-hooks.md)
- [ADR-007: Generated Provider Outputs](docs/adrs/007-generated-outputs.md)
- [ADR-008: Test-Driven Development](docs/adrs/008-test-driven-development.md)
- [ADR-009: Versioned Primitives](docs/adrs/009-versioned-primitives.md)
- [ADR-010: System-Level Versioning](docs/adrs/010-system-level-versioning.md)
- [ADR-011: Analytics Middleware](docs/adrs/011-analytics-middleware.md) *(Rejected - see ADR-026)*
- [ADR-019: File Naming Convention](docs/adrs/019-file-naming-convention.md)
- [ADR-020: Agentic Prompt Taxonomy](docs/adrs/020-agentic-prompt-taxonomy.md)
- [ADR-021: Primitives Directory Structure](docs/adrs/021-primitives-directory-structure.md)
- [ADR-022: Git Hook Observability](docs/adrs/022-git-hook-observability.md)
- [ADR-025: Universal Agent Integration Layer](docs/adrs/025-universal-agent-integration-layer.md) ✨ *CLI-first approach*
- [ADR-026: OTel-First Observability](docs/adrs/026-otel-first-observability.md) ✨ *OTel-native architecture*

---

## 🧪 Testing

Comprehensive testing across Rust and Python:

```bash
# Run all tests
make test

# Rust tests only
cd cli && cargo test

# Python tests only
cd hooks && uv run pytest

# With coverage
cd cli && cargo test --coverage
cd hooks && uv run pytest --cov
```

**Coverage goals**: >80% for both Rust and Python code.

---

## 🏗️ Repository Structure

```
agentic-primitives/
├── specs/                      # Versioned specification contracts
│   └── v1/                     # v1 primitive schemas (active)
│       ├── prompt-meta.schema.json
│       ├── tool-meta.schema.json
│       ├── hook-meta.schema.json
│       ├── model-config.schema.json
│       └── provider-impl.schema.json
│
├── primitives/                 # Versioned primitive storage
│   └── v1/                     # v1 primitives (active)
│       ├── commands/           # User-invoked commands (/command-name)
│       │   ├── <category>/<id>/
│       │   └── meta/<id>/      # Meta-prompts (prompt generators)
│       ├── skills/             # Reusable capabilities (referenced)
│       │   └── <category>/<id>/
│       ├── agents/             # Persistent personas (@agent-name)
│       │   └── <category>/<id>/
│       ├── tools/              # MCP tool integrations
│       │   └── <category>/<id>/
│       └── hooks/              # Lifecycle event handlers
│           └── <category>/<id>/
│
├── providers/                  # Provider-specific adapters
│   ├── claude/
│   ├── openai/
│   ├── cursor/
│   └── gemini/
│
├── cli/                        # Rust CLI tool
└── docs/                       # Documentation
    ├── versioning-guide.md     # Complete versioning documentation
    └── adrs/                   # Architecture Decision Records
        └── 021-primitives-directory-structure.md
```

### Versioning

This repository uses system-level versioning (v1, v2, ...) for architectural evolution. The current active version is **v1**. For details, see `docs/versioning-guide.md`.

---

## 📦 Python Packages

The `lib/python/` directory contains reusable Python packages for building agentic systems:

### Core Packages (Active)

| Package | Description | PyPI |
|---------|-------------|------|
| **agentic_otel** | OTel-first observability with HookOTelEmitter | `pip install agentic-otel` |
| **agentic_adapters** | Claude CLI runner and hook generator | `pip install agentic-adapters` |
| **agentic_security** | Declarative security policies (Bash, File, Content) | `pip install agentic-security` |
| **agentic_isolation** | Docker/local workspace isolation | `pip install agentic-isolation` |
| **agentic_settings** | Settings discovery and configuration | `pip install agentic-settings` |
| **agentic_logging** | Structured logging utilities | `pip install agentic-logging` |

### Deprecated Packages

| Package | Status | Migration |
|---------|--------|-----------|
| **agentic_observability** | ❌ Removed | Use `agentic_otel` |
| **agentic_analytics** | ❌ Removed | Use `agentic_otel` with OTel Collector |
| **agentic_hooks** | ⚠️ Deprecated | Use `agentic_otel.HookOTelEmitter` |
| **agentic_agent** | ⚠️ Deprecated | Use `ClaudeCLIRunner` from `agentic_adapters` |

### OTel-First Architecture

The recommended observability approach uses OpenTelemetry:

```python
from agentic_otel import OTelConfig, HookOTelEmitter

# Configure OTel (endpoint is typically OTel Collector)
config = OTelConfig(
    endpoint="http://localhost:4317",
    service_name="my-agent",
    resource_attributes={
        "deployment.environment": "production",
    },
)

# Emit events via OTel
emitter = HookOTelEmitter(config)

# Emit security decisions (logs/events)
emitter.emit_security_event(
    hook_type="pre_tool_use",
    decision="block",
    tool_name="Bash",
    tool_use_id="toolu_123",
    reason="Dangerous command blocked",
)
```

**Why OTel-first?**
- ✅ Claude CLI has native OTel support (metrics exported automatically)
- ✅ Industry-standard format (vendor-neutral, portable)
- ✅ Rich correlation (traces, metrics, logs unified)
- ✅ Powerful collectors (filtering, sampling, routing to any backend)

See [ADR-026: OTel-First Observability](docs/adrs/026-otel-first-observability.md) for architecture details.

---

## 🎯 Use Cases

### 1. Build a Python Development Agent

```bash
# Create core components
agentic-p new prompt agent python/python-pro
agentic-p new command review/code-review
agentic-p new skill testing/pytest-patterns
agentic-p new tool shell/run-tests

# Build for Claude
agentic-p build --provider claude
agentic-p install --provider claude --global

# Now use with Claude Agent SDK
claude --agent python-pro "Review my FastAPI code"
```

### 2. Enforce Safety Policies

```bash
# Create safety hooks
agentic-p new hook safety/block-dangerous-commands
agentic-p new hook safety/protect-sensitive-files

# Test locally
agentic-p test-hook safety/block-dangerous-commands --input test-events/rm-rf.json

# Deploy
agentic-p install --provider claude --project
```

### 3. Track Agent Metrics

```bash
# Create observability hooks
agentic-p new hook observability/log-operations
agentic-p new hook observability/emit-metrics

# Configure metrics endpoint in emit-metrics.hook.yaml
# Deploy and watch metrics flow
```

### 4. Bootstrap New Primitives with Meta-Prompts

```bash
# Use the meta-prompt to generate new primitives
agentic-p inspect meta-prompts/generation/generate-primitive

# Feed to Claude with specifications
# Validate the generated output
agentic-p validate
```

**📖 For detailed real-world scenarios**, see the [Usage Guide](docs/examples/usage-guide.md) with 7 complete examples covering observability, security, regulated environments, team collaboration, and more.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](docs/contributing.md) for guidelines.

Key areas:
- 🧩 **New primitives**: Share your agents, commands, and skills
- 🔌 **Provider adapters**: Add support for new LLM providers
- 🪝 **Middleware**: Build new safety and observability functions
- 📚 **Documentation**: Improve guides and examples
- 🐛 **Bug fixes**: Report and fix issues

---

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Inspired by:
- [Claude Agent SDK](https://docs.claude.com/en/docs/claude-code) - Hooks and agent architecture
- [Model Context Protocol (MCP)](https://docs.claude.com/en/docs/mcp) - Tool protocol design
- Atomic Design principles - Composable primitives
- The open-source AI community

---

## 🗺️ Roadmap

### ✅ Phase 1: Core Framework (Complete - v1.0.0)

- [x] Core repository structure
- [x] Versioning system with hash validation (BLAKE3)
- [x] Three-layer validation engine (structural, schema, semantic)
- [x] Complete CLI with 10 commands
- [x] Claude provider adapter
- [x] OpenAI provider adapter
- [x] Middleware-based hook system
- [x] Build & install pipeline
- [x] E2E testing & benchmarks
- [x] Comprehensive documentation

### 🚧 Phase 2: CI/CD & Distribution (Planned)

- [ ] GitHub Actions workflows (CI/CD)
- [ ] Automated releases
- [ ] Installable via script (`curl | sh`)
- [ ] Homebrew formula
- [ ] NPM package wrapper
- [ ] Docker image

### 🔮 Phase 3: Ecosystem (Future)

- [ ] Cursor provider adapter
- [ ] Meta-prompt library
- [ ] Community primitive registry
- [ ] VS Code extension
- [ ] Web UI for browsing primitives
- [ ] Plugin system for custom providers

---

**Ready to build better AI systems?** Start with `just` and `agentic-p init`.

For questions, issues, or discussions, visit our [GitHub repository](https://github.com/yourusername/agentic-primitives).
