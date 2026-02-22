---
description: Generate a new skill primitive for a specific capability
argument-hint: <description> [category]
model: sonnet
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Create Skill

Generate a new Claude Code skill — a reusable capability that agents can leverage.

## Purpose

Skills are **Layer 1** of the agentic primitive taxonomy: raw capabilities. A skill teaches an agent *how to do one thing well*. Skills are the foundation that sub-agents, commands, and workflows build on.

## Variables

DESCRIPTION: $1    # What capability this skill provides (required)
CATEGORY: $2       # Category: coding, testing, devops, research, security (optional)

## Design Principles

1. **Single capability** — one skill, one thing done well
2. **Self-contained** — all context the agent needs is in the SKILL.md
3. **Token-efficient** — progressive disclosure, not info dumps
4. **Tool-oriented** — prefer CLIs over MCPs (CLIs are composable, MCPs are opinionated)
5. **Validation-ready** — include self-check criteria so the agent can verify its own work

## Workflow

### Phase 1: Analyze Context

```bash
echo "=== Existing Skills ==="
find . -path "*/skills/*/SKILL.md" -exec echo {} \; 2>/dev/null | head -20

echo ""
echo "=== Project Structure ==="
ls -la
```

Read 1-2 existing skills to understand the style and structure conventions.

### Phase 2: Derive Metadata

From the DESCRIPTION, derive:

1. **ID**: Convert to kebab-case (e.g., "browser automation" → `browser-automation`)
2. **Category**: Infer from keywords
   | Keywords | Category |
   |----------|----------|
   | code, refactor, implement, build | `coding` |
   | test, qa, validate, check | `testing` |
   | deploy, ci, docker, infra | `devops` |
   | search, scrape, analyze | `research` |
   | auth, secrets, scan | `security` |

3. **Tools**: What tools does this capability need?
4. **Validation criteria**: How does the agent verify it did the job right?

### Phase 3: Generate Skill

Create the skill in the appropriate plugin location:

```
plugins/{plugin}/skills/{id}/SKILL.md
```

Or for repo-specific skills:

```
.claude/skills/{id}/SKILL.md
```

Use this structure:

```markdown
# {Title} Skill

{One-line description of the capability.}

## When to Use

{Trigger conditions — when should an agent activate this skill?}

## Capability

{What this skill enables. Be specific about inputs and outputs.}

## Tools Required

{List of CLI tools or APIs this skill uses.}

## Technique

{Step-by-step instructions for exercising this capability.}
{Include actual commands, patterns, and examples.}
{Reference real paths and conventions from the repo.}

## Validation

{How to verify the skill was applied correctly.}
{Include self-check criteria — tests to run, output to verify, specs to diff against.}

## Anti-Patterns

{Common mistakes to avoid when using this skill.}
```

### Phase 4: Create File

```bash
mkdir -p {target_dir}/skills/{id}

cat > {target_dir}/skills/{id}/SKILL.md << 'EOF'
{content}
EOF

echo "Created: {target_dir}/skills/{id}/SKILL.md"
```

### Phase 5: Validate

```bash
# Verify structure
head -5 {target_dir}/skills/{id}/SKILL.md
grep -E "^## " {target_dir}/skills/{id}/SKILL.md
```

## Self-Check

- [ ] Skill does ONE thing well
- [ ] Has When to Use triggers
- [ ] Has Validation section with self-check criteria
- [ ] Has Anti-Patterns section
- [ ] References actual tools/CLIs (not abstract concepts)
- [ ] Token-efficient (no filler, progressive disclosure)

## Report

## Skill Generated

**ID:** {id}
**Category:** {category}
**Location:** `{path}/SKILL.md`
**Capability:** {one-line summary}

### Layer Integration

This skill can be used by:
- **Sub-agents** that specialize on this capability
- **Commands** that orchestrate skills together
- **Workflows** that automate multi-step processes
