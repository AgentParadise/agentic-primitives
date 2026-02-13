# Architecture Plugin

Agent-native architecture patterns, swarm orchestration, and skill creation guides for building AI-first systems.

## Install

```bash
claude plugin install architecture@agentic-primitives --scope user
```

Or project-scoped:

```bash
claude plugin install architecture@agentic-primitives --scope project
```

## Skills

### agent-native-architecture

Design systems where AI agents are first-class participants. Covers:

- **Parity principle** — anything users can do via UI, agents can achieve via tools
- **Primitive-first tool design** — composable atomic tools over monolithic ones
- **Agent execution patterns** — loops, retries, context management
- **Self-modification** — agents that improve their own prompts and tools
- **MCP tool design** — building effective Model Context Protocol tools
- **Dynamic context injection** — loading relevant context on demand
- **Shared workspace architecture** — file-based coordination between agents

**Use when:** Designing a new agent system, refactoring an app to be agent-native, building MCP servers, or creating tools for autonomous agents.

**Trigger:** Ask Claude about agent-native architecture, tool design, or building agent-first applications.

### orchestrating-swarms

Patterns for coordinating multiple agents working together. Covers multi-agent communication, task decomposition, and convergence strategies.

**Use when:** Building systems with multiple collaborating agents, or designing how agents hand off work to each other.

**Trigger:** Ask about multi-agent orchestration, swarm patterns, or agent coordination.

### create-agent-skills

Complete guide to building effective agent skills — the reusable prompt packages that give agents domain expertise.

Includes:
- 11 reference docs (best practices, patterns, structure, security)
- 2 templates (simple skill, router skill)
- 9 workflows (`create-new-skill`, `add-reference`, `add-template`, `audit-skill`, etc.)

**Use when:** Creating new skills for Claude Code or any agent that uses the skill/plugin system.

**Trigger:** Ask Claude to create a skill, or use workflows like `create-new-skill`.

## Workflow Commands

These commands were ported alongside the architecture skills and live in `plugins/sdlc/commands/`:

| Command | Description |
|---------|-------------|
| `plan` | Transform feature descriptions into structured project plans |
| `work` | Execute implementation tasks following the plan |
| `compound` | Run compound engineering workflows (plan → implement → review) |
| `compound-review` | Review work done during compound engineering sessions |
| `brainstorm` | Structured brainstorming for features and architecture decisions |

Usage (inside a Claude Code session):

```
/sdlc:plan Add user authentication with OAuth2
/sdlc:work Implement the OAuth2 flow from the plan
/sdlc:compound Build a REST API for user management
/sdlc:brainstorm How should we handle real-time notifications?
```

## Attribution

Architecture skills adapted from [Compound Engineering Plugin](https://github.com/EveryInc/compound-engineering-plugin) by Every, Inc. (MIT License)

## License

MIT License — Copyright 2025 Every, Inc.

See [LICENSE](./LICENSE) for full text.
