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

## The Deterministic Backbone: `just`

[just](https://github.com/casey/just) is the task runner that provides the **deterministic glue** between layers. While agents handle ambiguous, non-deterministic work, `just` handles the repeatable parts: build, test, lint, deploy, format.

### Why `just`

- **Deterministic** — same input, same output, every time
- **Composable** — recipes call other recipes
- **Portable** — works on macOS, Linux, CI, containers
- **Agent-friendly** — agents can invoke `just` recipes as reliable building blocks

### How It Fits

```
Agent (non-deterministic)  →  just recipe (deterministic)  →  result
     "figure out what to test"    "just test"                  pass/fail
```

Use `just` for:
- **Build/test/lint/format** — repeatable quality checks
- **Workflow stage execution** — the deterministic skeleton of an ADW
- **Quality gates** — `just qa` as a pass/fail gate between stages
- **Setup/teardown** — container initialization, cleanup

Don't use `just` for:
- Anything requiring judgment or interpretation (that's the agent's job)
- Dynamic decisions about what to do next

### In Workflows (Layer 4)

ADWs combine `just` recipes (deterministic) with agent stages (non-deterministic):

```
just setup → [Agent: analyze] → just test → [Agent: review] → just deploy
```

The `just` steps are the guardrails. The agent steps are the intelligence.

## Layer Interaction

```
Layer 4: Workflows     ← automate entire processes
    ↓ orchestrates
Layer 3: Commands      ← human-facing orchestration
    ↓ spawns
Layer 2: Sub-Agents    ← specialized workers
    ↓ uses
Layer 1: Skills        ← raw capabilities

Cross-cutting: just   ← deterministic glue at every layer
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

## Higher-Order Primitives

A **higher-order primitive** is a prompt that generates other prompts. It operates one level of abstraction above the 4 layers — it's the factory that stamps out skills, agents, commands, and workflows.

### The Hierarchy

```
Higher-order primitives    ← generate other primitives
    ↓ produces
Layer 4: Workflows         ← automate processes
Layer 3: Commands          ← orchestrate agents
Layer 2: Sub-Agents        ← specialize on skills
Layer 1: Skills            ← raw capabilities
```

### Existing Higher-Order Primitives

| Primitive | What It Generates | Layer |
|-----------|-------------------|-------|
| `/create-skill` | Skill definitions | 1 |
| `/create-agent` | Sub-agent definitions | 2 |
| `/create-command` | Command prompts | 3 |
| `/create-workflow` | ADW pipelines | 4 |
| `/create-prime` | Codebase primes (AGENTS.md) | Cross-cutting |

### When to Create a Higher-Order Primitive

Create one when you find yourself repeatedly generating the same *kind* of prompt across repos. The pattern:

1. **Recognize the pattern** — "I keep writing the same type of skill/command"
2. **Extract the template** — what's common across all instances?
3. **Parameterize** — what varies per instance?
4. **Create the generator** — a `/create-X` command that takes parameters and outputs the primitive

### The Meta-Prime Pattern

The most important higher-order primitive is `/create-prime`:

```
/create-prime  →  analyzes repo  →  generates AGENTS.md  →  every agent reads it for free
```

This is **one prompt to rule them all** — it encodes your entire codebase's conventions, architecture, and expectations into a format that any agent (human or AI) can absorb instantly.

## Design Rules

1. **Skills are CLIs, not MCPs** — composable, token-efficient, no lock-in
2. **Sub-agents self-validate** — no agent returns results without checking its own work
3. **Commands decompose, they don't execute** — they spawn agents, not run code
4. **Workflows have quality gates** — every stage passes or escalates
5. **Token efficiency everywhere** — progressive disclosure, structured output, smart context loading
