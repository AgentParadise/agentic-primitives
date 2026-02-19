# Agentic Primitives

> Atomic building blocks for AI agent systems

[![Version](https://img.shields.io/badge/version-3.1.2-purple.svg)](VERSION)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

---

## What Are Agentic Primitives?

Atomic building blocks for AI agent systems — packaged as Claude Code plugins and Python libraries.

---

## The Primitives

Four Claude Code primitives, each with a distinct responsibility:

### Skills
Reusable multi-step workflows invoked as slash commands (`/sdlc:commit`) or auto-detected by Claude when a task matches the skill's description. A skill defines the workflow, the tools allowed, and can delegate to agents.

→ Lives in: `plugins/<plugin>/skills/<name>/SKILL.md`

### Agents
Named specialist subagents with a focused system prompt, scoped tool access, and optional persistent memory. Delegated to via the `Task` tool — Claude routes work to the right specialist automatically based on the task description.

→ Lives in: `plugins/<plugin>/agents/<name>/agent.md`

### Hooks
Event-driven automation that fires on Claude Code lifecycle events (`PreToolUse`, `PostToolUse`, `SubagentStop`, `SessionStart`, etc.). Can observe, modify, or block — enforcing policies, emitting telemetry, running validators.

→ Lives in: `plugins/<plugin>/hooks/hooks.json` + handlers

### Lib
Python packages that power agent runtimes — isolation, events, logging, security. Used by the [Agentic Engineering Framework (AEF)](https://github.com/AgentParadise/agentic-engineering-framework) as its foundation.

→ Lives in: `lib/python/`

---

### How They Compose

```
User invokes /sdlc:commit (Skill)
       │
       ├─► Skill runs QA checks
       │         │
       │         └─► PreToolUse Hook validates Bash commands
       │
       ├─► Skill delegates to review Agent (Task tool)
       │         │
       │         ├─► Agent has read-only tools + security-checklist skill preloaded
       │         └─► SubagentStop Hook records telemetry (Lib: agentic-events)
       │
       └─► Skill creates commit with conventional format
```

**The pattern:**
- **Skills** orchestrate — they define the workflow and call the right tools or agents
- **Agents** specialize — scoped to a domain, can't accidentally do things outside their remit
- **Hooks** automate — enforce policies and observability without touching the workflow code
- **Lib** provides the runtime substrate — isolation, events, structured logging

This composition means you can add observability without touching skills, tighten security without touching agents, and extend workflows without changing hooks. Each primitive is independently replaceable.

---

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

### What's in each plugin

| Plugin | Skills | Agents | Hooks |
|--------|--------|--------|-------|
| **sdlc** | `commit`, `pre-commit-qa`, `qa-setup`, `review`, `prioritize`, `testing-expert`, `env-management`, `centralized-configuration`, `macos-keychain-secrets`, `git_push`, `git_merge`, `git_merge-cycle`, `git_fetch`, `git_worktree`, `git_set-attributions`, `validate_security-hooks` | `env-reviewer` | PreToolUse security validators, UserPromptSubmit PII detection, git hooks |
| **workspace** | -- | -- | Session lifecycle, tool observability, structured JSONL event emission |
| **research** | `doc-scraper` | -- | -- |
| **meta** | `prompt-generator`, `create-prime`, `create-doc-sync` | -- | -- |
| **docs** | Fumadocs integration | -- | -- |

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
├── plugins/                     # Claude Code plugins
│   └── <plugin>/
│       ├── .claude-plugin/      #   Plugin metadata (plugin.json)
│       ├── skills/              #   Skills — reusable slash command workflows
│       │   └── <name>/SKILL.md
│       ├── agents/              #   Agents — named specialist subagents
│       │   └── <name>/agent.md
│       ├── hooks/               #   Hooks — lifecycle event automation
│       │   ├── hooks.json
│       │   └── handlers/
│       └── commands/            #   Legacy commands (migrating → skills)
├── lib/python/                  # Python infrastructure packages
│   ├── agentic_isolation/       #   Docker workspace sandboxing
│   ├── agentic_events/          #   JSONL event emission
│   └── agentic_logging/         #   Structured logging
├── providers/                   # Workspace images & model data
│   ├── workspaces/claude-cli/   #   Claude CLI Docker workspace
│   └── models/                  #   Model cards (pricing, context windows)
├── docs/adrs/                   # Architecture Decision Records
├── VERSION                      # Repo version
└── justfile                     # Task runner (just --list)
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
