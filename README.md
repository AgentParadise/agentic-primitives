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

# Build the CLI
make build

# Install the CLI to your PATH
cargo install --path cli

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
# Build for Claude Code
agentic-p build --provider claude

# View the generated output
ls -R build/claude/hooks

# Install to project .claude/ directory
cp -r build/claude/.claude /path/to/your/project/

# Result: All hooks installed and ready to use!
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

### Prompt Primitives

Organized by **kind** and **category** for router-like navigation:

```
primitives/v1/prompts/
├── agents/<category>/<id>/          # Personas & roles
├── commands/<category>/<id>/        # Discrete tasks
├── skills/<category>/<id>/          # Knowledge overlays
└── meta-prompts/<category>/<id>/    # Prompt generators
```

**Example**: `primitives/v1/prompts/agents/python/python-pro/`

Each primitive contains:
- `python-pro.v1.md` - Versioned prompt content (filename matches ID)
- `python-pro.v2.md` - Next version
- `python-pro.yaml` - Metadata with version registry, model preferences, tool dependencies (filename matches directory name)

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

All development operations use the **Makefile** for consistency:

```bash
# Show all available commands
make help

# Format code (Rust + Python)
make fmt

# Lint code
make lint

# Type check Python
make typecheck

# Run all tests
make test

# Full QA suite (format check, lint, typecheck, test)
make qa

# Auto-fix issues and run QA
make qa-fix

# Build debug version
make build

# Build release version
make build-release

# Clean, check, and build everything
make verify
```

### Install Git Hooks (Optional)

```bash
# Auto-run QA checks before commits
make git-hooks-install
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
│   ├── v1/                     # v1 primitives (active)
│   │   ├── prompts/
│   │   │   ├── agents/<category>/<id>/
│   │   │   ├── commands/<category>/<id>/
│   │   │   ├── skills/<category>/<id>/
│   │   │   └── meta-prompts/<category>/<id>/
│   │   ├── tools/<category>/<id>/
│   │   └── hooks/<category>/<id>/
│   └── experimental/           # Sandbox for v2+ testing
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
        └── 010-system-level-versioning.md
```

### Versioning

This repository uses system-level versioning (v1, v2, ...) for architectural evolution. The current active version is **v1**. For details, see `docs/versioning-guide.md`.

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

**Ready to build better AI systems?** Start with `make help` and `agentic-p init`.

For questions, issues, or discussions, visit our [GitHub repository](https://github.com/yourusername/agentic-primitives).

