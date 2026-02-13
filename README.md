# Agentic Primitives

> **The composable platform for agentic engineering.**

Agentic Primitives is a batteries-included framework for building, observing, and isolating AI coding agents. It provides the atomic building blocks — prompts, tools, hooks, and workspaces — that compose into production-grade agentic systems.

`.claude/` is the canonical format. OpenCode and Codex generation planned.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## Three Pillars

### 1. 🧩 Plugins — Drop-in Primitives

Reusable commands, skills, agents, and tools that work with Claude Code today.

```
primitives/v1/
├── commands/       # /slash-commands (devops, qa, review, workflow, meta)
├── skills/         # Reusable knowledge (testing, docs, devops, review)
├── agents/         # Persistent personas (@agent-name)
├── tools/          # UV Python scripts, MCP integrations
└── hooks/          # Lifecycle event handlers
```

Every primitive is **atomic and composable**. Drop a markdown file in the right folder — it works. Need something more complex? Add tool implementations in Python or TypeScript alongside it.

### 2. 🔭 Observability — See What Your Agents Do

**You can't build reliable agentic systems if you can't see what they're doing.** Observability is a first-class primitive, not an afterthought.

Every agent action flows through a hook-based event pipeline:

| Hook | Lifecycle Event | What It Captures |
|------|----------------|------------------|
| `pre-tool-use` | Before any tool call | Security validation, dangerous command blocking |
| `post-tool-use` | After tool execution | Result logging, metrics emission |
| `session-start/end` | Session lifecycle | Session tracking, resource cleanup |
| `user-prompt` | User input | PII detection, credential scanning |
| `subagent-stop` | Subagent completion | Multi-agent coordination |
| `pre-compact` | Before context compaction | Context preservation |
| `notification` | Agent notifications | Alert routing |
| `stop` | Agent shutdown | Graceful cleanup |

**Architecture:** OTel-first. Events emit as OpenTelemetry traces, metrics, and logs — route them anywhere (Grafana, Datadog, local JSONL, your own dashboard).

```python
from agentic_otel import OTelConfig, HookOTelEmitter

emitter = HookOTelEmitter(OTelConfig(
    endpoint="http://localhost:4317",
    service_name="my-agent",
))
```

**Security hooks** run automatically — blocking dangerous bash commands, protecting sensitive files, and scanning for leaked credentials. Every decision is logged.

See the [Observability Dashboard example](examples/002-observability-dashboard/) for a full-stack demo.

### 3. 📦 Workspace Isolation — Batteries-Included Agent Environments

Production-ready Docker images for running agents in isolated, reproducible workspaces.

**What's in the box:**

| Feature | Details |
|---------|---------|
| **LSP Support** | Pyright, TypeScript, rust-analyzer — lazy-loaded, zero config |
| **Toolchains** | Node.js 22, Python 3.12, Rust stable, UV, GitHub CLI |
| **Observability** | Pre-wired hook pipeline, JSONL event streams |
| **Security** | Non-root user, no setuid binaries, isolated `/workspace` |
| **Artifacts** | Structured `input/` and `output/` directories (ADR-036) |
| **Claude Code** | Pre-installed with official LSP plugins enabled |

```bash
# Build the workspace image
python scripts/build-provider.py claude-cli

# Run an isolated agent
docker compose -f providers/workspaces/claude-cli/docker-compose.record.yaml up
```

LSP servers are **lazy** — they only start when Claude encounters files in that language. An agent working on Python won't spin up rust-analyzer. Safe for multi-agent orchestration.

---

## Python Libraries

Reusable packages in `lib/python/` for building your own agentic infrastructure:

| Package | Purpose |
|---------|---------|
| [`agentic_events`](lib/python/agentic_events/) | Event models and emission |
| [`agentic_isolation`](lib/python/agentic_isolation/) | Docker/local workspace isolation |
| [`agentic_security`](lib/python/agentic_security/) | Declarative security policies |
| [`agentic_adapters`](lib/python/agentic_adapters/) | Claude CLI runner and hook generator |
| [`agentic_settings`](lib/python/agentic_settings/) | Settings discovery and configuration |
| [`agentic_logging`](lib/python/agentic_logging/) | Structured logging utilities |
| [`agentic_workspace`](lib/python/agentic_workspace/) | Workspace management |

---

## Repo Structure

```
agentic-primitives/
├── primitives/              # The atomic building blocks
│   ├── v1/                  # Active primitives (commands, skills, tools, hooks)
│   └── v2/                  # Next-gen primitives (in development)
│
├── providers/               # Provider-specific adapters
│   ├── agents/claude-code/  # Claude Code hooks config, supported events
│   ├── models/              # Model specs (Anthropic, OpenAI, Google)
│   └── workspaces/          # Docker images (base, claude-cli)
│
├── .claude/                 # Canonical Claude Code integration
│   ├── commands/            # Slash commands (devops, qa, review, workflow)
│   ├── hooks/               # Hook handlers (Python, UV-based)
│   └── tools/               # Tool implementations
│
├── lib/python/              # Reusable Python packages
├── services/                # Backend services (hooks, analytics)
├── examples/                # Working examples with demos
├── docs/                    # Documentation + ADRs
├── docs-site-fuma/          # FumaDocs documentation site
├── playground/              # Local testing environment
├── specs/                   # JSON schemas for all primitives
├── schemas/                 # Frontmatter validation schemas
└── scripts/                 # Build and utility scripts
```

---

## Quick Start

### Prerequisites

- [UV](https://docs.astral.sh/uv/) (Python package management)
- [Just](https://github.com/casey/just) (task runner)
- Python 3.11+
- Docker (for workspace isolation)

### Install

```bash
git clone https://github.com/AgentParadise/agentic-primitives.git
cd agentic-primitives

# Install as a Claude Code plugin
# (from your project directory)
/plugin install /path/to/agentic-primitives
```

### Development

```bash
just          # Show all commands
just fmt      # Format code
just lint     # Lint
just test     # Run all tests
just qa       # Full QA suite
```

---

## Philosophy

**Atomic Agentic Design.** Every piece — a prompt, a tool, a hook, a workspace config — is a composable primitive. Mix and match to build exactly the agentic system you need.

**Observability is non-negotiable.** Every tool call, every security decision, every session lifecycle event is captured. If your agent did it, you can see it.

**`.claude/` as canonical, generate for the rest.** Claude Code is the primary target today. OpenCode and Codex converters are planned, following the [Compound Engineering](https://github.com/EveryInc/compound-engineering-plugin) approach.

**Compounding returns.** Inspired by compound engineering — each unit of work should make future work easier. Primitives are documented, versioned, and reusable by design.

---

## Documentation

- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Hooks System](docs/hooks/)
- [Versioning Guide](docs/versioning-guide.md)
- [Architecture Decision Records](docs/adrs/) (30+ ADRs)
- [Examples](examples/)

---

## Roadmap

- [x] Core primitives framework (commands, skills, agents, tools, hooks)
- [x] OTel-first observability pipeline
- [x] Workspace isolation with Docker images
- [x] LSP integration (Pyright, TypeScript, rust-analyzer)
- [x] Security hooks (bash validator, file protection, PII scanning)
- [ ] OpenCode / Codex generation
- [ ] Community primitive registry
- [ ] FumaDocs site deployment
- [ ] Installable via `curl | sh` / Homebrew / NPM

---

## License

[MIT](LICENSE)

---

**Built by [Agent Paradise](https://github.com/AgentParadise)** — where observability meets agentic engineering.
