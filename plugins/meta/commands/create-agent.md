---
description: Generate a sub-agent definition that specializes on a skill
argument-hint: <description> [skill-id]
model: sonnet
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Create Agent

Generate a sub-agent definition — a specialized agent configuration that wraps one or more skills into a concrete workflow.

## Purpose

Sub-agents are **Layer 2** of the agentic primitive taxonomy: scale through specialization. A sub-agent takes raw skills and wraps them into a purpose-built agent with a clear mission, validation loop, and output format.

Sub-agents are invoked via Claude Code's Task tool (fire-and-forget delegation) or spawned as parallel workers by orchestrating commands.

## Variables

DESCRIPTION: $1    # What this sub-agent specializes in (required)
SKILL_ID: $2       # Existing skill to wrap (optional, can use multiple)

## Design Principles

1. **Single mission** — one agent, one clear job
2. **Self-validating** — agent verifies its own work before returning results
3. **Skill-backed** — wraps existing skills, doesn't reinvent capabilities
4. **Structured output** — returns results in a predictable format
5. **Failure-aware** — knows when to escalate vs retry

## Workflow

### Phase 1: Discover Available Skills

```bash
echo "=== Available Skills ==="
find . -path "*/skills/*/SKILL.md" -exec sh -c 'echo "- $(dirname {} | xargs basename): $(head -1 {})"' \; 2>/dev/null
```

If SKILL_ID is provided, read that skill's SKILL.md to understand the capability.

### Phase 2: Design the Agent

From the DESCRIPTION, determine:

1. **ID**: kebab-case (e.g., "browser QA reviewer" → `browser-qa-reviewer`)
2. **Mission**: One sentence describing what this agent does
3. **Skills used**: Which existing skills it leverages
4. **Input**: What the agent receives (files, specs, URLs, etc.)
5. **Output**: What the agent produces (report, diff, files, etc.)
6. **Validation loop**: How the agent checks its own work
7. **Escalation criteria**: When should it stop and ask for help?

### Phase 3: Generate Agent Definition

Create the agent definition:

```
plugins/{plugin}/agents/{id}.md
```

Or for repo-specific agents:

```
.claude/agents/{id}.md
```

Use this structure:

```markdown
# {Title} Agent

{One-line mission statement.}

## Mission

{Detailed description of what this agent does and when it's invoked.}

## Skills

{List of skills this agent uses, with links to their SKILL.md files.}

| Skill | Purpose in This Agent |
|-------|----------------------|
| {skill-id} | {how this agent uses it} |

## Input

{What this agent receives when invoked.}

- **Required:** {what must be provided}
- **Optional:** {what can be provided for better results}

## Workflow

{Step-by-step execution plan.}

1. **{Phase}** — {what happens}
2. **{Phase}** — {what happens}
3. **Validate** — {self-check before returning}

## Validation

{Self-validation loop. The agent runs these checks before returning results.}

- [ ] {Check 1}
- [ ] {Check 2}
- [ ] {Check 3}

**On failure:** {retry strategy or escalation path}

## Output Format

{Structured output the agent returns to the caller.}

```
## {Agent Name} Results

**Status:** pass | fail | partial
**Summary:** {one-line}

### Findings
{structured results}

### Issues
{any problems encountered}
```

## Invocation

{How to invoke this agent.}

### Via Task Tool (inside Claude Code)
```
Spawn a sub-agent to {mission}. Use the {skill-id} skill.
Input: {description of what to pass}
```

### Via CLI (in AEF containers)
```bash
claude --print --append-system-prompt "You are a {id} agent. {mission}" "{task prompt}"
```

## Escalation

{When this agent should NOT try to handle something.}

- {condition} → escalate to human
- {condition} → retry with different approach
- {condition} → report partial results
```

### Phase 4: Create File

```bash
mkdir -p {target_dir}/agents

cat > {target_dir}/agents/{id}.md << 'EOF'
{content}
EOF

echo "Created: {target_dir}/agents/{id}.md"
```

### Phase 5: Validate

```bash
head -5 {target_dir}/agents/{id}.md
grep -E "^## " {target_dir}/agents/{id}.md
```

## Self-Check

- [ ] Agent has a single clear mission
- [ ] Wraps existing skill(s), not reimplementing capabilities
- [ ] Has self-validation loop with specific checks
- [ ] Has escalation criteria
- [ ] Output format is structured and predictable
- [ ] Includes both Task tool and CLI invocation examples

## Report

## Agent Generated

**ID:** {id}
**Mission:** {one-line mission}
**Skills:** {skill-ids used}
**Location:** `{path}/{id}.md`

### Layer Integration

This agent can be:
- **Invoked by commands** that orchestrate multiple agents
- **Spawned in parallel** by workflow commands
- **Run in AEF containers** via `claude --print`
