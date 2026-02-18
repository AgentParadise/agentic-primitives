# Meta Plugin

Primitive generators — tools that create other agentic primitives.

Built on the **4-layer agentic primitive taxonomy**: Skills → Sub-Agents → Commands → Workflows.

## Commands

All generators are **higher-order primitives** — prompts that generate other prompts.

| Command | Layer | Description |
|---------|-------|-------------|
| **create-skill** | 1 - Capability | Generate a new skill primitive (raw capability, CLI-based) |
| **create-agent** | 2 - Scale | Generate a self-validating sub-agent definition |
| **create-command** | 3 - Orchestration | Generate a command that orchestrates agents |
| **create-workflow** | 4 - Automation | Generate an ADW pipeline with quality gates |
| **create-prime** | Cross-cutting | Generate a repo-specific prime (→ AGENTS.md) for agent onboarding |
| **create-doc-sync** | Utility | Create documentation sync configurations |

## Skills

| Skill | Description |
|-------|-------------|
| **agentic-taxonomy** | Reference guide for the 4-layer primitive architecture |
| **prompt-generator** | Meta-skill for generating effective prompts |

## The 4 Layers

```
Layer 4: Workflows     ← automate entire processes (ADWs)
    ↓ orchestrates
Layer 3: Commands      ← human-facing orchestration (/slash)
    ↓ spawns
Layer 2: Sub-Agents    ← specialized workers (Task tool)
    ↓ uses
Layer 1: Skills        ← raw capabilities (CLIs)
```

See `skills/agentic-taxonomy/SKILL.md` for the full taxonomy reference.
