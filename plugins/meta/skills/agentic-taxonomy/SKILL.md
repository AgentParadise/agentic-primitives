# Agentic Primitive Taxonomy

The 4-layer architecture for building composable agent systems. Each layer builds on the one below it.

## The 4 Layers

### Layer 1 — Skills (Capability)

Raw capabilities. A skill teaches an agent how to do one thing well.

- **Location:** `plugins/{plugin}/skills/{id}/SKILL.md`
- **Scope:** Single capability (e.g., "commit with conventional messages", "run Playwright tests")
- **Key principle:** Use CLIs, not MCP servers. CLIs are composable and token-efficient. MCPs lock you into opinionated structures.
- **Create:** `/create-skill <description>`

### Layer 2 — Sub-Agents (Scale)

Specialized agents that wrap skills into concrete workflows. This is where you scale through parallelism.

- **Location:** `plugins/{plugin}/agents/{id}.md`
- **Scope:** Single mission wrapping one or more skills (e.g., "Browser QA Agent" that uses Playwright skill to validate user stories)
- **Key principle:** Self-validating. Every sub-agent verifies its own work before returning results.
- **Invocation:** Claude Code Task tool (fire-and-forget) or `claude --print` in containers
- **Create:** `/create-agent <description> [skill-id]`

### Layer 3 — Commands (Orchestration)

Reusable prompts that orchestrate teams of sub-agents. Commands are the human-facing interface.

- **Location:** `plugins/{plugin}/commands/{id}.md` or `.claude/commands/{id}.md`
- **Scope:** Orchestrate multiple agents toward a goal (e.g., `/ui-review` spawns parallel QA agents, collects results, generates summary)
- **Key principle:** Commands decompose work and delegate. They don't do the work themselves.
- **Create:** `/create-command <description>`

### Layer 4 — Workflows / ADWs (Automation)

AI Developer Workflows. Deterministic pipelines with non-deterministic agents at each stage. This is "out of the loop" engineering.

- **Location:** `plugins/{plugin}/workflows/{id}.md`
- **Scope:** End-to-end automation of an engineering process (e.g., "PR Review Pipeline" → lint → test → review → merge)
- **Key principle:** Every stage has a quality gate. No stage passes without validation.
- **Create:** `/create-workflow <description>`

## Layer Interaction

```
Layer 4: Workflows     ← automate entire processes
    ↓ orchestrates
Layer 3: Commands      ← human-facing orchestration
    ↓ spawns
Layer 2: Sub-Agents    ← specialized workers
    ↓ uses
Layer 1: Skills        ← raw capabilities
```

## Two Deployment Targets

All primitives work in both environments:

| | AEF (Orchestration) | Local Dev (Terminal) |
|---|---|---|
| **Runtime** | Container per phase, no human | Claude Code CLI, human in loop |
| **Skills** | Mounted into workspace | `.claude/skills/` in project |
| **Sub-agents** | Task tool inside container | Task tool interactively |
| **Commands** | Injected via prime prompt | `/slash` commands directly |
| **Workflows** | Phase configs in orchestration engine | Sequential command execution |

## Priming Pattern

Instead of running an install script per container (token-wasteful), use the **meta-prime → baked-prime** pattern:

1. **Meta-prime** (`/create-prime`) analyzes a repo and generates a codebase-specific prime
2. **Baked prime** is stored as `AGENTS.md` in the repo root
3. **Container startup** reads `AGENTS.md` automatically — zero extra tokens
4. The prime encodes: architecture, conventions, test patterns, validation expectations, tool access

## Design Rules

1. **Skills are CLIs, not MCPs** — composable, token-efficient, no lock-in
2. **Sub-agents self-validate** — no agent returns results without checking its own work
3. **Commands decompose, they don't execute** — they spawn agents, not run code
4. **Workflows have quality gates** — every stage passes or escalates
5. **Token efficiency everywhere** — progressive disclosure, structured output, smart context loading
