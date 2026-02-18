---
description: Generate an AI Developer Workflow (ADW) that orchestrates agents
argument-hint: <description>
model: opus
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Create Workflow

Generate an AI Developer Workflow (ADW) — a multi-agent orchestration pattern that combines deterministic code with non-deterministic agents to automate an entire class of engineering work.

## Purpose

Workflows are **Layer 4** of the agentic primitive taxonomy: full automation. An ADW composes skills, sub-agents, and commands into a deterministic pipeline where agents execute autonomously. This is "out of the loop" engineering — the workflow runs without human intervention.

## Variables

DESCRIPTION: $1    # What engineering work this workflow automates (required)

## Design Principles

1. **Deterministic skeleton, non-deterministic agents** — the workflow structure is fixed; agents handle the ambiguity
2. **Composable** — built from existing skills, agents, and commands
3. **Observable** — emits structured events at each stage for monitoring
4. **Resumable** — can recover from failures without restarting from scratch
5. **Self-validating** — each stage has quality gates before progressing

## Workflow

### Phase 1: Discover Available Primitives

```bash
echo "=== Available Skills ==="
find . -path "*/skills/*/SKILL.md" -exec sh -c 'echo "  $(dirname {} | xargs basename)"' \; 2>/dev/null

echo ""
echo "=== Available Agents ==="
find . -path "*/agents/*.md" -exec sh -c 'echo "  $(basename {} .md)"' \; 2>/dev/null

echo ""
echo "=== Available Commands ==="
find . -path "*/commands/*.md" ! -name "create-*" -exec sh -c 'echo "  $(basename {} .md)"' \; 2>/dev/null
```

### Phase 2: Design the Workflow

From the DESCRIPTION, determine:

1. **ID**: kebab-case (e.g., "PR review pipeline" → `pr-review-pipeline`)
2. **Trigger**: What starts this workflow? (commit, PR, schedule, manual)
3. **Stages**: Ordered list of stages, each with:
   - Agent(s) responsible
   - Input from previous stage
   - Quality gate (pass/fail criteria)
   - Output to next stage
4. **Parallelism**: Which stages can run concurrently?
5. **Recovery**: What happens when a stage fails?

### Phase 3: Map the Pipeline

Design the stage graph:

```
[Trigger] → [Stage 1: Agent A] → [Gate 1] → [Stage 2: Agent B + C (parallel)] → [Gate 2] → [Stage 3: Agent D] → [Output]
```

For each stage:
- **Agent**: Which sub-agent runs this?
- **Isolation**: Does it need its own container/sandbox?
- **Timeout**: Maximum time before escalation
- **Retry**: How many retries on failure?

### Phase 4: Generate Workflow Definition

Create the workflow:

```
plugins/{plugin}/workflows/{id}.md
```

Or for repo-specific workflows:

```
.claude/workflows/{id}.md
```

Use this structure:

```markdown
# {Title} Workflow

{One-line description of what engineering work this automates.}

## Overview

**Trigger:** {what starts this workflow}
**Agents:** {list of sub-agents used}
**Estimated time:** {typical duration}
**Human involvement:** None (out of the loop) | Review at gate N | Approval at end

## Pipeline

```
{ASCII diagram of the stage flow}
```

## Stages

### Stage 1: {Name}

| Property | Value |
|----------|-------|
| **Agent** | {agent-id} |
| **Input** | {what it receives} |
| **Output** | {what it produces} |
| **Timeout** | {max duration} |
| **Retries** | {count} |
| **Isolation** | container / shared / none |

**Quality Gate:**
- [ ] {pass criterion 1}
- [ ] {pass criterion 2}

**On failure:** {retry | skip | abort | escalate}

### Stage 2: {Name}
{repeat structure}

## Execution

### Local (Terminal, Human in Loop)
```bash
# Run the workflow as a command
/{id}
```

### AEF (Container Orchestration)
```yaml
workflow: {id}
phases:
  - name: {stage-1-name}
    agent: {agent-id}
    image: {workspace-image}
    timeout: {duration}
  - name: {stage-2-name}
    agent: {agent-id}
    depends_on: [{stage-1-name}]
    parallel: true
```

## Events

{Structured events emitted at each stage for observability.}

| Event | Stage | Data |
|-------|-------|------|
| `workflow.started` | — | workflow_id, trigger |
| `stage.started` | {name} | stage_id, agent_id |
| `stage.completed` | {name} | stage_id, status, duration |
| `gate.evaluated` | {name} | gate_id, pass/fail, criteria |
| `workflow.completed` | — | workflow_id, status, duration |

## Recovery

{What happens when things go wrong.}

| Failure | Recovery |
|---------|----------|
| Agent timeout | {action} |
| Quality gate fail | {action} |
| Infra error | {action} |
| All retries exhausted | {action} |

## Customization

{How to adapt this workflow for different repos or use cases.}
```

### Phase 5: Create File

```bash
mkdir -p {target_dir}/workflows

cat > {target_dir}/workflows/{id}.md << 'EOF'
{content}
EOF

echo "Created: {target_dir}/workflows/{id}.md"
```

### Phase 6: Validate

```bash
head -5 {target_dir}/workflows/{id}.md
grep -E "^### Stage" {target_dir}/workflows/{id}.md
```

## Self-Check

- [ ] Every stage has a named agent responsible
- [ ] Every stage has a quality gate with specific pass criteria
- [ ] Parallelism is identified where possible
- [ ] Recovery strategy defined for each failure mode
- [ ] Both local and AEF execution paths documented
- [ ] Events defined for observability
- [ ] Workflow composes existing primitives (skills, agents, commands)

## Report

## Workflow Generated

**ID:** {id}
**Stages:** {count}
**Agents used:** {agent-ids}
**Location:** `{path}/{id}.md`

### Pipeline Summary
```
{ASCII diagram}
```

### Deployment Targets
- **Local:** `/{id}` command
- **AEF:** Phase config ready for orchestration engine
