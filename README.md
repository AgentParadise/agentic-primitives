# Agentic Primitives

> Atomic building blocks for AI agent systems

[![Version](https://img.shields.io/badge/version-3.1.2-purple.svg)](VERSION)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## What Are Agentic Primitives?

Atomic building blocks for AI agent systems — packaged as Claude Code plugins and Python libraries.

Designed to work in two contexts:
- **Human-in-the-loop** — a developer using Claude Code in the terminal, invoking commands explicitly, staying in control
- **Headless workspaces** — fully automated agents running in isolation with no human present, where tool scoping and policy hooks are the safety layer

The same primitives serve both. The difference is configuration: which tools are allowed, which hooks fire, which agents are trusted.

---

## The Primitives

### Commands
Explicit user-invocable slash commands (`/sdlc:git_push`). Granular, predictable, human-triggered. The developer stays in the loop.

→ Lives in: `plugins/<plugin>/commands/<name>.md`

### Skills
Reusable workflows Claude invokes automatically when a task matches the description — or that you invoke as `/sdlc:git`. Consolidated, intent-driven, works in both human and headless contexts.

→ Lives in: `plugins/<plugin>/skills/<name>/SKILL.md`

### Agents
Named specialist subagents with a scoped system prompt, explicit allowed/disallowed tools, and optional persistent memory. The tool scope is the key primitive — it determines what an agent *can* do, not just what it *should* do. Agents can preload skills and delegate to other agents via the `Task` tool.

→ Lives in: `plugins/<plugin>/agents/<name>/agent.md`

### Hooks
Event-driven automation that fires on Claude Code lifecycle events (`PreToolUse`, `PostToolUse`, `SubagentStop`, `SessionStart`, etc.). Observe, modify, or block — enforcing policies and emitting telemetry without touching workflow code.

→ Lives in: `plugins/<plugin>/hooks/hooks.json` + handlers

### Lib
Python packages that power agent runtimes — isolation, events, logging, security. Used by the [Agentic Engineering Framework (AEF)](https://github.com/AgentParadise/agentic-engineering-framework) as its foundation.

→ Lives in: `lib/python/`

---

### How They Compose

```
User: /sdlc:git_push          ← Command (explicit, human-in-loop)
  or
Claude detects push needed    ← Skill (auto-invoked, headless-friendly)
       │
       ├─► PreToolUse Hook validates git commands before execution
       │
       ├─► Skill delegates review to env-reviewer Agent (Task tool)
       │         ├─ tools: Read, Grep, Glob only (cannot modify anything)
       │         ├─ disallowedTools: Write, Edit (enforced, not just instructed)
       │         └─ SubagentStop Hook records telemetry
       │
       └─► PostToolUse Hook emits structured JSONL event (Lib: agentic-events)
```

**The pattern:**
- **Commands** give humans direct control at the right granularity
- **Skills** orchestrate work for agents — consolidated, intent-driven
- **Agents** specialize with enforced tool scopes — least privilege by design
- **Hooks** enforce policies and observability without touching workflow code
- **Lib** provides the runtime substrate — isolation, events, structured logging

---

## Quick Start

### Prerequisites

- [Python 3.11+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) — fast Python package manager
- [just](https://github.com/casey/just) — command runner (optional, recommended)

### Install Plugins

Plugins are installed via Claude Code's built-in plugin system. Requires Claude Code v1.0.33+.

You can also do all of this interactively by typing `/plugin` inside Claude Code.

**1. Add the marketplace (one-time setup):**

```bash
claude plugin marketplace add AgentParadise/agentic-primitives
```

**2. Install the plugins you need:**

```bash
# Install globally (available in all projects)
claude plugin install sdlc@agentic-primitives --scope user

# Or install to current project only
claude plugin install sdlc@agentic-primitives --scope project
```

**3. Update to the latest version:**

```bash
# Refresh the marketplace catalog first
claude plugin marketplace update agentic-primitives

# Then update the plugin
claude plugin update sdlc@agentic-primitives
```

Plugins are pinned to a version and never auto-update. Updates require both steps above.

**4. Disable / enable without uninstalling:**

```bash
claude plugin disable sdlc@agentic-primitives
claude plugin enable sdlc@agentic-primitives
```

**5. Uninstall:**

```bash
claude plugin uninstall sdlc@agentic-primitives
```

**6. Verify security hooks are active:**

```bash
# Inside a Claude Code session, run:
/sdlc:validate_security-hooks
```

Replace `sdlc` with any plugin name (`workspace`, `research`, `meta`, `docs`) in the commands above.

---

## Available Plugins

| Plugin | Install | Description |
|--------|---------|-------------|
| **sdlc** | `claude plugin install sdlc@agentic-primitives --scope user` | Software Development Lifecycle |
| **workspace** | `claude plugin install workspace@agentic-primitives --scope user` | Observable isolated workspaces |
| **research** | `claude plugin install research@agentic-primitives --scope user` | Information gathering |
| **meta** | `claude plugin install meta@agentic-primitives --scope user` | Primitive generators |
| **docs** | `claude plugin install docs@agentic-primitives --scope user` | Documentation tools |
| **compound-engineering** | `claude plugin install compound-engineering@agentic-primitives --scope user` | Agent-native architecture, swarms, skill creation |

### What's in each plugin

| Plugin | Commands | Skills | Agents | Hooks |
|--------|----------|--------|--------|-------|
| **sdlc** | `git_push`, `git_merge`, `git_merge-cycle`, `git_fetch`, `git_worktree`, `git_set-attributions`, `review`, `validate_security-hooks`, `browser`, `browser_ui-review` | `git`, `commit`, `pre-commit-qa`, `qa-setup`, `testing-expert`, `review`, `prioritize`, `env-management`, `centralized-configuration`, `macos-keychain-secrets`, `browser` | `env-reviewer`, `browser-qa-agent` | PreToolUse security validators, UserPromptSubmit PII detection, git hooks |
| **workspace** | -- | -- | -- | Session lifecycle, tool observability, structured JSONL event emission |
| **research** | `scrape_docs` | -- | -- | -- |
| **meta** | `create-command`, `create-prime`, `create-doc-sync` | `prompt-generator` | -- | -- |
| **docs** | -- | Fumadocs integration | -- | -- |
| **compound-engineering** | -- | `agent-native-architecture`, `orchestrating-swarms`, `create-agent-skills` | -- | -- |

---

## Python Packages

Infrastructure primitives in `lib/python/`, installable via `pip` or `uv`:

| Package | Version | Description |
|---------|---------|-------------|
| [`agentic-isolation`](lib/python/agentic_isolation/) | 0.3.0 | Docker workspace sandboxing for agent execution |
| [`agentic-events`](lib/python/agentic_events/) | 0.1.0 | Zero-dependency JSONL event emission |
| [`agentic-logging`](lib/python/agentic_logging/) | 0.1.0 | Structured logging for agents and humans |

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
│   ├── sdlc/                   #   SDLC plugin
│   │   ├── commands/           #     Explicit user-invocable slash commands
│   │   ├── skills/             #     Agent-invocable workflows
│   │   ├── agents/             #     Named subagents with scoped tools
│   │   └── hooks/              #     Lifecycle event handlers
│   ├── workspace/              #   Workspace observability hooks
│   ├── research/               #   Research tools (firecrawl, doc-scraper)
│   ├── meta/                   #   Primitive generators
│   ├── docs/                   #   Documentation tools
│   └── compound-engineering/   #   Agent-native architecture (from Every, Inc.)
├── lib/python/                 # Infrastructure Primitives
│   ├── agentic_isolation/      #   Docker workspace sandboxing
│   ├── agentic_events/         #   JSONL event emission
│   └── agentic_logging/        #   Structured logging
├── providers/                  # Workspace providers & model data
│   ├── workspaces/claude-cli/  #   Claude CLI Docker workspace
│   ├── models/                 #   Model cards (pricing, context windows)
│   └── agents/                 #   Agent configuration templates
├── scripts/                    # QA runner, benchmark tools
├── tests/                      # Integration & unit tests
├── docs/adrs/                  # Architecture Decision Records (32 ADRs)
├── VERSION                     # Repo version (3.0.1)
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

This project's design decisions are documented in [13 ADRs](docs/adrs/), including:

- [ADR-020: Agentic Prompt Taxonomy](docs/adrs/020-agentic-prompt-taxonomy.md)
- [ADR-025: Just Task Runner](docs/adrs/025-just-task-runner.md)
- [ADR-027: Provider Workspace Images](docs/adrs/027-provider-workspace-images.md)
- [ADR-029: Simplified Event System](docs/adrs/029-simplified-event-system.md)
- [ADR-033: Plugin-Native Workspace Images](docs/adrs/033-plugin-native-workspace-images.md)

---

## License

[MIT](LICENSE)
