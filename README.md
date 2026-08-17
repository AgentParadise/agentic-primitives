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

Replace `sdlc` with any plugin name from the [Available Plugins](#available-plugins) table in the commands above.

---

## Available Plugins

| Plugin | Install | Description |
|--------|---------|-------------|
| **sdlc** | `claude plugin install sdlc@agentic-primitives --scope user` | Software Development Lifecycle |
| **workspace** | `claude plugin install workspace@agentic-primitives --scope user` | Observable isolated workspaces |
| **research** | `claude plugin install research@agentic-primitives --scope user` | Information gathering |
| **meta** | `claude plugin install meta@agentic-primitives --scope user` | Primitive generators |
| **docs** | `claude plugin install docs@agentic-primitives --scope user` | Documentation tools |
| **notifications** | `claude plugin install notifications@agentic-primitives --scope user` | Push notifications (ntfy, macOS, Pushover) |
| **observability** | `claude plugin install observability@agentic-primitives --scope user` | Full-spectrum JSONL event observability |
| **delegation** | `claude plugin install delegation@agentic-primitives --scope user` | Delegating work — `claude -p`, Codex, and session handoffs |
| **experiments** | `claude plugin install experiments@agentic-primitives --scope user` | Hypothesis-first experiment workflow |

### What's in each plugin

| Plugin | Commands | Skills | Agents | Hooks |
|--------|----------|--------|--------|-------|
| **sdlc** | `git_push`, `git_merge`, `git_merge-cycle`, `git_fetch`, `git_worktree`, `git_set-attributions`, `review`, `validate_security-hooks`, `browser`, `browser_ui-review` | `git`, `git-worktree`, `commit`, `pre-commit-qa`, `qa-setup`, `testing-expert`, `review`, `prioritize`, `env-management`, `centralized-configuration`, `macos-keychain-secrets`, `browser` | `env-reviewer`, `browser-qa-agent` | PreToolUse security validators, UserPromptSubmit PII detection, git hooks |
| **workspace** | -- | -- | -- | Session lifecycle, tool observability, structured JSONL event emission |
| **research** | `scrape_docs` | -- | -- | -- |
| **meta** | `create-command`, `create-prime`, `create-doc-sync` | `prompt-generator` | -- | -- |
| **docs** | -- | `fuma` (Fumadocs integration), `system-infographic` | -- | -- |
| **notifications** | -- | -- | -- | Notification, Stop, TaskCompleted → ntfy/macOS/Pushover with sound themes |
| **observability** | -- | -- | -- | All 14 lifecycle events → structured JSONL via agentic_events |
| **delegation** | -- | `delegating-to-claude-p`, `delegating-to-codex`, `writing-handoffs` | -- | -- |
| **experiments** | -- | `running-experiments` | -- | -- |

---

## Python Packages

Infrastructure primitives in `lib/python/`, installable via `pip` or `uv`:

| Package | Version | Description |
|---------|---------|-------------|
| [`agentic-isolation`](lib/python/agentic_isolation/) | 0.5.1 | Docker workspace sandboxing for agent execution |
| [`agentic-events`](lib/python/agentic_events/) | 0.1.1 | Zero-dependency JSONL event emission |
| [`agentic-logging`](lib/python/agentic_logging/) | 0.1.2 | Structured logging for agents and humans |
| [`agentic-memory`](lib/python/agentic_memory/) | 0.2.0 | Contract and doctor for the `memory` workspace capability |
| [`agentic-session-store`](lib/python/agentic_session_store/) | 0.1.0 | Contract and doctor for the `session-store` workspace capability |

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
│   ├── notifications/          #   Push notifications
│   ├── observability/          #   JSONL event observability
│   ├── delegation/             #   Delegation and handoff skills
│   └── experiments/            #   Hypothesis-first experiment workflow
├── lib/python/                 # Infrastructure Primitives
│   ├── agentic_isolation/      #   Docker workspace sandboxing
│   ├── agentic_events/         #   JSONL event emission
│   ├── agentic_logging/        #   Structured logging
│   ├── agentic_memory/         #   memory capability contract + doctor
│   └── agentic_session_store/  #   session-store capability contract + doctor
├── workspace/                  # Harness-neutral container runtime
│   ├── entrypoint.sh           #   Source of truth for workspace behaviour
│   └── capabilities/           #   Capability modules (memory, session-store)
├── providers/                  # Workspace providers & model data
│   ├── workspaces/             #   Provider images (base, claude-cli,
│   │                           #     interactive-tmux, omni-agent)
│   ├── models/                 #   Model cards (pricing, context windows)
│   └── agents/                 #   Agent configuration templates
├── scripts/                    # QA runner, benchmark tools
├── tests/                      # Integration & unit tests
├── docs/adrs/                  # Architecture Decision Records
├── VERSION                     # Repo version
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

## Workspace

`agentic-primitives` ships the workspace image — the controlled boundary every AI agent runs inside. The workspace has three responsibilities:

1. **Inject** orchestrator-supplied context (`CLAUDE.md`, plugins, subagents) via a bind-mount at `/etc/agentic/workspace/` + three optional env vars (`AGENTIC_WORKSPACE_CONTEXT`, `AGENTIC_WORKSPACE_PLUGINS`, `AGENTIC_WORKSPACE_AGENTS`).
2. **Isolate** the agent's effects (tmpfs home, read-only context mount, network whitelisting, per-task volumes).
3. **Observe** what the agent did (git hooks → JSONL on stderr, `--output-format stream-json` on stdout, output artifacts in `/workspace/artifacts/output/`).

The runtime is harness-neutral and lives at [`workspace/`](workspace/): `entrypoint.sh` plus `capabilities/`. A provider image stages that tree at build time rather than owning a copy of it.

See [`docs/workspace.md`](docs/workspace.md) for the canonical reference, [`docs/adrs/035-workspace-injection-contract.md`](docs/adrs/035-workspace-injection-contract.md) for the design decisions, and [`workspace/entrypoint.sh`](workspace/entrypoint.sh) for the source of truth.

### Capabilities

A capability is a pluggable subsystem the image hosts but does not hard-code (ADR-040). Adapters live at `/opt/agentic/capabilities/<capability>/<provider>/` and run on a three-hook lifecycle: `init.sh` is sourced before the agent starts, `doctor` hard-fails the workspace at preflight, and `finalize.sh` runs after the agent exits.

`AGENTIC_CAPABILITIES` is the registry. `AGENTIC_<CAP>_PROVIDER` selects an adapter, and leaving it unset or setting it to `none` makes that capability a complete no-op, so a listed capability costs nothing until an operator opts in.

Two capabilities ship, and `agentic-workspace-claude-cli` registers both:

| Capability | Provider | What it does |
|---|---|---|
| `memory` | `hindsight` | Persistent agent memory, per ADR-036 |
| `session-store` | `seshmagic` | Uploads agent transcripts to a session store speaking APS-V1-0004 |

See [`docs/workspace-capabilities.md`](docs/workspace-capabilities.md) to author one, [`docs/adrs/040-workspace-capability-modules.md`](docs/adrs/040-workspace-capability-modules.md) for the rationale, and each module's README under [`workspace/capabilities/`](workspace/capabilities/) for its contract.

---

## Published Images

Two workspace images are published to GHCR, multi-arch (`linux/amd64`, `linux/arm64`) and cosign keyless signed:

- `ghcr.io/agentparadise/agentic-workspace-claude-cli`
- `ghcr.io/agentparadise/agentic-workspace-interactive-tmux`

`main` is the development branch and publishes `:edge` and `:<sha>` only. A protected `release` branch is the only thing that moves `:latest` or publishes a version tag.

**Consuming these safely takes two steps.**

**1. Pin a digest, never a tag.** Tags are mutable in OCI by design. `:latest` moves on every release and `:edge` moves on every push to `main`, so neither is a pin:

```bash
IMAGE=ghcr.io/agentparadise/agentic-workspace-claude-cli
DIGEST=$(docker buildx imagetools inspect "${IMAGE}:latest" --format '{{.Manifest.Digest}}')
```

**2. Verify the signature.** Signing is keyless, so the identity is derived from this repository, this workflow file, and the branch that ran it:

```bash
cosign verify "${IMAGE}@${DIGEST}" \
  --certificate-identity-regexp '^https://github\.com/AgentParadise/agentic-primitives/\.github/workflows/build-workspace-images\.yml@refs/heads/(main|release)$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com'
```

Edge images are signed exactly like release images: a signature proves the build's origin, never that the code was reviewed. The channel is carried by the tag and by the `agentic.image.channel` label.

Full tag taxonomy, the release gate, and the cut-a-release procedure are in [`docs/release-process.md`](docs/release-process.md).

---

## Architecture Decision Records

This project's design decisions are documented in [`docs/adrs/`](docs/adrs/), including:

- [ADR-020: Agentic Prompt Taxonomy](docs/adrs/020-agentic-prompt-taxonomy.md)
- [ADR-025: Just Task Runner](docs/adrs/025-just-task-runner.md)
- [ADR-027: Provider Workspace Images](docs/adrs/027-provider-workspace-images.md)
- [ADR-029: Simplified Event System](docs/adrs/029-simplified-event-system.md)
- [ADR-033: Plugin-Native Workspace Images](docs/adrs/033-plugin-native-workspace-images.md)
- [ADR-035: Workspace Injection Contract](docs/adrs/035-workspace-injection-contract.md)
- [ADR-036: Memory Primitive and Doctor](docs/adrs/036-memory-primitive-and-doctor.md)
- [ADR-037: Release Integration Gate](docs/adrs/037-release-integration-gate.md)
- [ADR-040: Workspace Capability Modules](docs/adrs/040-workspace-capability-modules.md)

---

## License

[MIT](LICENSE)
