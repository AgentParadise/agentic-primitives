---
title: "ADR-020: Agentic Prompt Taxonomy"
status: accepted
created: 2025-12-06
updated: 2025-12-06
author: Neural
---

# ADR-020: Agentic Prompt Taxonomy

## Status

**Accepted**

- Created: 2025-12-06
- Updated: 2025-12-06
- Author(s): Neural

## Context

The agentic-primitives framework supports multiple types of reusable prompts, but the relationship between **prompt complexity levels** and **primitive types** has not been formally documented. This leads to confusion about:

1. When to use each primitive type (agent, command, skill, tool, hook, workflow)
2. How to structure prompts at different complexity levels
3. How prompts can reference and compose each other
4. Best practices for variables with default values

The TAC Engineering framework defines **7 levels of agentic prompts** based on capability/complexity, while our primitive types define **how** prompts are invoked and used. These are orthogonal concepts that need clear documentation.

## Decision

We establish a two-dimensional taxonomy for agentic prompts:

### Dimension 1: Primitive Types (Invocation Method)

| Type | Invocation | Description | Source |
|------|------------|-------------|--------|
| **Agent** | `@agent-name` | Persistent persona with model, context, tools, and prompt | Our framework |
| **Command** | `/command-name` | User-invoked action | Claude SDK |
| **Skill** | Referenced by other prompts | Reusable capability | Claude SDK |
| **Tool** | MCP server / function call | External system integration | Common pattern |
| **Hook** | Automatic on lifecycle events | Event handler | Our framework |
| **Workflow** | `/workflow/name` | Multi-step orchestrated process | Our framework |

### Dimension 2: Prompt Levels (Capability/Complexity)

From the TAC Engineering framework, prompts are categorized by their structural complexity. **Levels stack** - higher levels include all sections from lower levels.

| Level | Name | Key Capability | Sections Added |
|-------|------|----------------|----------------|
| 1 | **High-Level** | Simple reusable task | Title, Purpose, Task |
| 2 | **Workflow** | Sequential steps | + Variables, Workflow, Report |
| 3 | **Control Flow** | Conditionals, loops | + If/else, loops, early returns |
| 4 | **Delegation** | Sub-agent orchestration | + Agent spawning, parallel work |
| 5 | **Higher-Order** | Prompts accepting prompts | + Dynamic plan/prompt input |
| 6 | **Template Meta** | Prompt generation | + Template section, format spec |
| 7 | **Self-Improving** | Dynamic expertise | + Expertise section, self-update |

### Composable Sections by Tier

Based on usage patterns, sections are ranked by utility:

**S-Tier (Most Useful)**
- **Workflow** - Step-by-step execution plan
- **Delegation** - Sub-agent coordination

**A-Tier (Very Useful)**
- **Variables** - Static and dynamic inputs with defaults
- **Examples** - Expected behavior/output demonstrations
- **Template** - Structured output format
- **Purpose** - Direct statement of intent

**B-Tier (Useful)**
- **Report** - Output format specification
- **Instructions** - Auxiliary guidance for workflow
- **Task** - Simple high-level description

**C-Tier (Situational)**
- **Metadata** - Model, tools, description (in frontmatter)
- **Codebase Structure** - Context map of files
- **Relevant Files** - Quick reference to key files

### Variables with Defaults Pattern

Variables support positional arguments with fallback defaults:

```markdown
## Variables

TARGET_BRANCH: $1 || "develop"     # First arg, defaults to "develop"
MAX_RETRIES: $2 || 3               # Second arg, defaults to 3
AUTO_FIX: true                     # Static default (not from args)
RUNNER: auto                       # Computed at runtime
```

This pattern enables:
- Sensible defaults for common cases
- Override capability for specific needs
- Clear documentation of expected inputs

### Type + Level Combinations

Any primitive type can be implemented at any complexity level:

| Primitive Type | Common Levels | Example |
|----------------|---------------|---------|
| Command | 2-3 | `/commit` (Level 2), `/push` (Level 3 with CI wait loop) |
| Skill | 1-2 | `/prioritize` (Level 2 workflow) |
| Workflow | 3-5 | `/merge-cycle` (Level 3 with multiple loops) |
| Agent | 4-7 | `@devops-engineer` (Level 4 with delegation) |
| Meta-prompt | 6-7 | `/prompt-generator` (Level 6 template) |

## Alternatives Considered

### Alternative 1: Single-Dimension Type System

**Description**: Combine levels and types into a single classification.

**Pros**:
- Simpler mental model
- Fewer concepts to learn

**Cons**:
- Loses expressiveness
- Can't distinguish "what it does" from "how it's invoked"
- Doesn't capture complexity progression

**Reason for rejection**: The two dimensions capture genuinely different aspects of prompt design.

### Alternative 2: Flat Section List

**Description**: Don't tier sections, just list all available sections equally.

**Pros**:
- No implied hierarchy
- Simpler documentation

**Cons**:
- No guidance on which sections to prioritize
- New users don't know where to start

**Reason for rejection**: Tiering helps users make better design decisions.

## Consequences

### Positive Consequences

- **Clear mental model**: Developers understand both what a prompt does and how to invoke it
- **Guided complexity**: Levels provide a progression path from simple to advanced prompts
- **Consistent patterns**: Variables with defaults become a standard pattern
- **Better composition**: Understanding types enables proper prompt composition

### Negative Consequences

- **Learning curve**: Two dimensions require more initial learning
- **Potential over-engineering**: Users might add complexity unnecessarily to reach higher levels

### Neutral Consequences

- Existing prompts may need level annotations in their documentation
- The prompt-generator meta-prompt already implements this taxonomy

## Implementation Notes

### File Naming

Per ADR-019, primitives use the `{id}.{type}.{ext}` pattern:
- `commit.meta.yaml` - Metadata
- `commit.prompt.v1.md` - Prompt content

### Directory Structure

```
primitives/v1/prompts/
├── agents/           # Agent primitives (any level)
├── commands/         # Command primitives
│   ├── devops/       # DevOps commands
│   ├── qa/           # QA commands
│   ├── review/       # Review commands
│   └── workflow/     # Workflow orchestrators
├── meta-prompts/     # Level 6-7 meta-prompts
└── skills/           # Skill primitives
```

### Documenting Prompt Level

Include level in the prompt's Purpose or metadata:

```markdown
## Purpose

*Level 3 (Control Flow)*

Push changes to remote and monitor CI status with retry logic.
```

### Validation

The CLI's `validate` command should eventually check:
- Required sections for declared level
- Variables follow the defaults pattern
- Proper frontmatter for primitive type

## References

- `primitives/v1/prompts/meta-prompts/prompt-generator/prompt-generator.prompt.v1.md` - Source of 7 levels
- ADR-019: File Naming Convention
- Claude Agent SDK documentation (commands, skills)
- [TAC Engineering Course](https://tacengineering.com) - Original 7 levels framework
