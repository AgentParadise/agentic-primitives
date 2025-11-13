# Agentic Primitives

> **Atomic building blocks for AI coding systems**

A source-of-truth repository of reusable, versionable, and provider-agnostic primitives for building agentic AI systems. Think of it as a standard library for AI agents—prompts, tools, and hooks that you can compose, version, and deploy across different LLM providers.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Rust](https://img.shields.io/badge/rust-1.75+-orange.svg)](https://www.rust-lang.org/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## 🎯 What Are Agentic Primitives?

Agentic primitives are **atomic, reusable components** that define how AI agents think, act, and integrate into your workflows:

- **🧠 Prompt Primitives**: Personas (agents), tasks (commands), knowledge patterns (skills), and meta-prompts for generating other primitives
- **🔧 Tool Primitives**: Logical tool specifications with optional provider-specific implementations (Claude, OpenAI, local Rust/Python/Bun)
- **🪝 Hook Primitives**: Lifecycle event handlers with composable middleware for safety, observability, and control

All primitives are:
- ✅ **Version-controlled** with immutable hashes (BLAKE3)
- ✅ **Provider-agnostic** at their core, compiled to specific formats
- ✅ **Strictly validated** across structural, schema, and semantic layers
- ✅ **Composable** - mix and match to build complex agentic behaviors
- ✅ **Router-friendly** - organized by type/category/id for easy navigation

---

## 🚀 Quick Start

### Prerequisites

- **Rust** 1.75+ (for the CLI)
- **Python** 3.11+ with `uv` (for hooks)
- **Make** (for turnkey operations)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-primitives.git
cd agentic-primitives

# Build the CLI
make build

# Install the CLI to your PATH
cargo install --path cli
```

### Initialize a New Repository

```bash
# Create a new agentic-primitives repository
agentic init

# Or initialize in a specific directory
agentic init --path ./my-primitives
```

### Create Your First Primitive

```bash
# Create a Python expert agent
agentic new prompt agent python/python-pro

# Create a code review command
agentic new command review/code-review

# Create a testing knowledge skill
agentic new skill testing/pytest-patterns

# Create a safety hook
agentic new hook lifecycle/pre-tool-use
```

### Validate Everything

```bash
# Run all validation layers
agentic validate

# Check specific primitive
agentic inspect python/python-pro
```

### Build for Your Provider

```bash
# Build for Claude Agent SDK
agentic build --provider claude

# Install to project .claude/ directory
agentic install --provider claude --project

# Install globally to ~/.claude/
agentic install --provider claude --global
```

---

## 📚 Core Concepts

### Prompt Primitives

Organized by **kind** and **category** for router-like navigation:

```
prompts/
├── agents/<category>/<id>/          # Personas & roles
├── commands/<category>/<id>/        # Discrete tasks
├── skills/<category>/<id>/          # Knowledge overlays
└── meta-prompts/<category>/<id>/    # Prompt generators
```

**Example**: `prompts/agents/python/python-pro/`

Each primitive contains:
- `<id>.prompt.v1.md` - Versioned prompt content (for agents/commands/meta-prompts)
- `<id>.prompt.md` - Unversioned (for skills, or opt-in versioning)
- `<id>.meta.yaml` - Metadata with version registry, model preferences, tool dependencies

### Tool Primitives

Logical capability definitions with optional provider bindings:

```
tools/<category>/<id>/
├── tool.meta.yaml          # Generic specification
├── impl.claude.yaml        # Claude SDK binding
├── impl.openai.json        # OpenAI function calling
└── impl.local.{rs|py|ts}   # Local implementation
```

### Hook Primitives

Lifecycle event handlers with **middleware pipelines**:

```
hooks/<category>/<id>/
├── hook.meta.yaml          # Event config & middleware list
├── impl.python.py          # Orchestrator (uv)
├── impl.bun.ts             # Alternative (bun)
└── middleware/
    ├── safety/             # Blocking: dangerous commands, sensitive files
    └── observability/      # Non-blocking: logging, metrics
```

**Use cases**:
- 🛡️ **Safety**: Block dangerous bash commands, protect sensitive files, validate tool inputs
- 📊 **Observability**: Log operations, emit metrics, track token usage, debug tracing
- 🎯 **Control**: Auto-approve safe operations, add context, enforce policies

### Versioning

Agents, commands, and meta-prompts **require versioning**:

```yaml
# In meta.yaml
versions:
  - version: 1
    file: python-pro.prompt.v1.md
    status: active
    hash: blake3:abc123...
    created: "2025-11-13"
    notes: "Initial version"
  - version: 2
    file: python-pro.prompt.v2.md
    status: draft
    hash: blake3:def456...
    created: "2025-11-14"
    notes: "Added async patterns expertise"

default_version: 1  # Use v1 by default
```

**Version management**:

```bash
# Create a new version
agentic version bump python/python-pro --notes "Added async expertise"

# List all versions
agentic version list python/python-pro

# Promote draft to active
agentic version promote python/python-pro --version 2

# Deprecate old version
agentic version deprecate python/python-pro --version 1
```

### Provider Adapters

Primitives are **compiled** to provider-specific formats:

```
providers/
├── claude/           # Claude Agent SDK
├── openai/           # OpenAI API
├── cursor/           # Cursor IDE
└── gemini/           # Google Gemini (future)
```

Each provider has:
- **Models**: Provider-specific model configs (`claude/sonnet`, `openai/gpt-codex`)
- **Templates**: Handlebars templates for transforming primitives
- **Transformers**: Rust code that does the compilation

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

## 🏗️ Project Structure

```
agentic-primitives/
├── prompts/              # Prompt primitives (agents, commands, skills, meta-prompts)
├── tools/                # Tool capability primitives
├── hooks/                # Lifecycle event primitives
├── providers/            # Provider-specific adapters (Claude, OpenAI, Cursor)
├── schemas/              # JSON Schema validation
├── cli/                  # Rust CLI tool
├── docs/                 # Documentation and ADRs
├── primitives.config.yaml
├── Makefile
└── README.md
```

---

## 🎯 Use Cases

### 1. Build a Python Development Agent

```bash
# Create core components
agentic new prompt agent python/python-pro
agentic new command review/code-review
agentic new skill testing/pytest-patterns
agentic new tool shell/run-tests

# Build for Claude
agentic build --provider claude
agentic install --provider claude --global

# Now use with Claude Agent SDK
claude --agent python-pro "Review my FastAPI code"
```

### 2. Enforce Safety Policies

```bash
# Create safety hooks
agentic new hook safety/block-dangerous-commands
agentic new hook safety/protect-sensitive-files

# Test locally
agentic test-hook safety/block-dangerous-commands --input test-events/rm-rf.json

# Deploy
agentic install --provider claude --project
```

### 3. Track Agent Metrics

```bash
# Create observability hooks
agentic new hook observability/log-operations
agentic new hook observability/emit-metrics

# Configure metrics endpoint in hook.meta.yaml
# Deploy and watch metrics flow
```

### 4. Bootstrap New Primitives with Meta-Prompts

```bash
# Use the meta-prompt to generate new primitives
agentic inspect meta-prompts/generation/generate-primitive

# Feed to Claude with specifications
# Validate the generated output
agentic validate
```

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

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Inspired by:
- [Claude Agent SDK](https://docs.claude.com/en/docs/claude-code) - Hooks and agent architecture
- [Model Context Protocol (MCP)](https://docs.claude.com/en/docs/mcp) - Tool protocol design
- Atomic Design principles - Composable primitives
- The open-source AI community

---

## 🗺️ Roadmap

- [x] Core repository structure
- [x] Versioning system with hash validation
- [x] Three-layer validation engine
- [x] Claude provider adapter
- [x] Middleware-based hook system
- [ ] OpenAI provider adapter
- [ ] Cursor provider adapter
- [ ] Meta-prompt library
- [ ] Community primitive registry
- [ ] VS Code extension
- [ ] Web UI for browsing primitives

---

**Ready to build better AI systems?** Start with `make help` and `agentic init`.

For questions, issues, or discussions, visit our [GitHub repository](https://github.com/yourusername/agentic-primitives).

