# Agentic Primitives

> Atomic building blocks for AI agent systems

[![Version](https://img.shields.io/badge/version-3.0.0-purple.svg)](VERSION)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## What Are Agentic Primitives?

This repository contains two kinds of primitives for building AI agent systems:

### Prompt Primitives

Reusable prompts deployed as **Claude Code plugins** — commands, skills, hooks, and tools that agents use during software development.

### Infrastructure Primitives

**Python packages** that power agent execution — isolation, security, events, logging, adapters, and settings. Used by the [Agentic Engineering Framework (AEF)](https://github.com/AgentParadise/agentic-engineering-framework) as its foundation.

---

## Quick Start

### Prerequisites

- [Python 3.11+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- [just](https://github.com/casey/just) — command runner (optional, recommended)

### Install a Plugin

```bash
# Add the marketplace (one-time)
claude plugin marketplace add AgentParadise/agentic-primitives

# Install a plugin globally
claude plugin install sdlc@agentic-primitives --scope user

# Or install to current project only
claude plugin install sdlc@agentic-primitives --scope project
```

Or use the interactive UI: type `/plugin` inside Claude Code.

---

## Available Plugins

| Plugin | Description | Includes |
|--------|-------------|----------|
| **sdlc** | Software Development Lifecycle | `/commit`, `/push`, `/merge`, `/merge-cycle`, `/review`, `/fetch` commands; `testing-expert`, `pre-commit-qa`, `prioritize` skills; security hooks, git hooks |
| **workspace** | Observable isolated workspaces | Session lifecycle hooks, tool observability, structured JSONL event emission |
| **research** | Information gathering | `/doc-scraper` command, Firecrawl web scraping tool |
| **meta** | Primitive generators | `/create-command`, `/create-prime`, `/create-doc-sync` commands |
| **docs** | Documentation tools | Fumadocs integration skill |

---

## Python Packages

Infrastructure primitives in `lib/python/`, installable via `pip` or `uv`:

| Package | Version | Description |
|---------|---------|-------------|
| [`agentic-isolation`](lib/python/agentic_isolation/) | 0.3.0 | Docker workspace sandboxing for agent execution |
| [`agentic-security`](lib/python/agentic_security/) | 0.1.0 | Declarative bash/file/content security policies |
| [`agentic-events`](lib/python/agentic_events/) | 0.1.0 | Zero-dependency JSONL event emission |
| [`agentic-logging`](lib/python/agentic_logging/) | 0.1.0 | Structured logging for agents and humans |
| [`agentic-adapters`](lib/python/agentic_adapters/) | 0.1.0 | Claude SDK/CLI runtime integration |
| [`agentic-settings`](lib/python/agentic_settings/) | 0.1.0 | Configuration discovery via Pydantic |

```bash
# Install a package for development
cd lib/python/agentic_isolation
uv sync --all-extras

# Run tests
uv run pytest -x -q
```

---

## Repository Structure

```
agentic-primitives/
├── plugins/                    # Prompt Primitives
│   ├── sdlc/                   #   SDLC plugin (commands, skills, hooks)
│   ├── workspace/              #   Workspace observability hooks
│   ├── research/               #   Research tools (firecrawl, doc-scraper)
│   ├── meta/                   #   Primitive generators
│   └── docs/                   #   Documentation tools
├── lib/python/                 # Infrastructure Primitives
│   ├── agentic_isolation/      #   Docker workspace sandboxing
│   ├── agentic_security/       #   Security policies
│   ├── agentic_events/         #   JSONL event emission
│   ├── agentic_logging/        #   Structured logging
│   ├── agentic_adapters/       #   Claude SDK/CLI adapters
│   └── agentic_settings/       #   Configuration management
├── providers/                  # Workspace providers & model data
│   ├── workspaces/claude-cli/  #   Claude CLI Docker workspace
│   ├── models/                 #   Model cards (pricing, context windows)
│   └── agents/                 #   Agent configuration templates
├── scripts/                    # QA runner, benchmark tools
├── tests/                      # Integration & unit tests
├── docs/adrs/                  # Architecture Decision Records (32 ADRs)
├── VERSION                     # Repo version (3.0.0)
└── justfile                    # Task runner (just --list)
```

---

## Development

```bash
# Initialize environment
just init

# Run all tests
just test

# Run QA (format check + lint + test)
just qa

# Auto-fix formatting and lint issues
just qa-fix

# Run full CI pipeline
just ci
```

### Docker Workspace Images

```bash
# Build Claude CLI workspace image
just build-workspace-claude-cli

# List available providers
just list-providers
```

---

## Architecture Decision Records

This project's design decisions are documented in [32 ADRs](docs/adrs/), including:

- [ADR-020: Agentic Prompt Taxonomy](docs/adrs/020-agentic-prompt-taxonomy.md)
- [ADR-025: Just Task Runner](docs/adrs/025-just-task-runner.md)
- [ADR-027: Provider Workspace Images](docs/adrs/027-provider-workspace-images.md)
- [ADR-029: Simplified Event System](docs/adrs/029-simplified-event-system.md)

---

## License

[Apache 2.0](LICENSE)
