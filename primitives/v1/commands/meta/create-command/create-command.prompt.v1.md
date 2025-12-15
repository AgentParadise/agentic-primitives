---
description: Generate a new command - auto-detects library vs repo context
argument-hint: <description> [category] [id]
model: opus
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Create Command

Generate a new command primitive with proper structure. Auto-detects whether to create a library primitive or a repo-specific command.

## Purpose

Create a spec-compliant command that either:
- **Library Mode**: Adds to `primitives/v1/commands/` (when in agentic-primitives repo)
- **Consumer Mode**: Creates `.claude/commands/` file (when in any other repo)

## Variables

DESCRIPTION: $1    # What the command should do (required)
CATEGORY: $2       # Category: qa, devops, docs, meta, review, workflow (optional)
ID: $3             # Command ID in kebab-case (optional, derived from description)

## Command Complexity Reference

Commands vary in complexity. Choose the simplest structure that accomplishes the goal:

| Type | Structure | When to Use |
|------|-----------|-------------|
| **Simple** | Purpose + Task | One-off reusable tasks |
| **Workflow** | + Variables, Workflow, Report | Sequential multi-step operations |
| **Conditional** | + Control flow (if/else, loops) | Domain-specific with branching |
| **Orchestrator** | + Delegation to sub-agents | Complex parallel operations |

**Most commands should be Workflow type.** Start simple, add complexity only when needed.

## Required Sections

Every command MUST have:

| Section | Purpose |
|---------|---------|
| **Purpose** | Direct statement of what this accomplishes |
| **Workflow** | Sequential steps to execute |
| **Report** | Output format specification |

## Token Efficiency Guidelines

Commands should be **token-efficient**:

1. **Be concise** - Use direct language, avoid filler words
2. **Progressive disclosure** - Start with summary, expand when needed
3. **Structured output** - Use tables and lists over paragraphs
4. **Smart context loading** - Only read files when necessary
5. **Summarize large outputs** - Truncate or summarize verbose results

Example of progressive summarization:
```
Phase 1: Quick scan → summary only
Phase 2: If issues found → load detailed context
Phase 3: If complex → read specific files
```

## Phase 0: Context Detection

First, detect which mode to use:

```bash
echo "=== Context Detection ==="

# Check for library structure
if [ -d "primitives/v1" ] && [ -f "primitives.config.yaml" ]; then
  echo "MODE: library"
  echo "  → Detected agentic-primitives repository"
  echo "  → Output: primitives/v1/commands/{category}/{id}/"
elif [ -d "primitives/v1" ]; then
  echo "MODE: library"
  echo "  → Detected primitives structure"
  echo "  → Output: primitives/v1/commands/{category}/{id}/"
else
  echo "MODE: consumer"
  echo "  → Detected consumer repository"
  echo "  → Output: .claude/commands/{id}.md"
fi
```

## Phase 1: Analyze Existing Commands

Learn from existing commands for style consistency.

### If Library Mode

```bash
echo ""
echo "=== Analyzing Existing Library Commands ==="

# List existing categories
echo "Categories:"
ls -d primitives/v1/commands/*/ 2>/dev/null | xargs -n1 basename

# Find example commands to learn from
echo ""
echo "Example commands:"
find primitives/v1/commands -name "*.prompt.v1.md" | head -5
```

Read 1-2 existing commands to match their style:
- Look at section ordering
- Note the verbosity level
- Observe workflow step format
- Check report structure

### If Consumer Mode

```bash
echo ""
echo "=== Analyzing Repo Context ==="

# Check for existing commands
if [ -d ".claude/commands" ]; then
  echo "Existing commands:"
  ls .claude/commands/
else
  echo "No existing .claude/commands/ directory"
fi

# Understand the project
echo ""
echo "Project structure:"
ls -la

# Check for key files
echo ""
echo "Key files:"
ls README.md AGENTS.md CLAUDE.md pyproject.toml package.json Cargo.toml justfile 2>/dev/null
```

## Phase 2: Derive Metadata

From the DESCRIPTION, derive:

1. **ID**: Convert to kebab-case
   - "run QA checks" → `run-qa-checks`
   - "review PR changes" → `review-pr-changes`

2. **Category**: Infer from keywords
   | Keywords | Category |
   |----------|----------|
   | qa, test, lint, check, validate | `qa` |
   | commit, push, merge, deploy, ci | `devops` |
   | doc, readme, changelog | `docs` |
   | review, pr, feedback | `review` |
   | workflow, pipeline, process | `workflow` |
   | meta, generate, create, template | `meta` |

3. **Tools**: Infer needed tools
   | Task Type | Tools |
   |-----------|-------|
   | File operations | Read, Write |
   | Shell commands | Bash |
   | Code search | Grep, Glob |

4. **Title**: Title Case from ID

## Phase 3: Generate Command

### Library Mode Output

Create TWO files in `primitives/v1/commands/{category}/{id}/`:

**File 1: `{id}.yaml`**

```yaml
id: {id}
kind: command
category: {category}
domain: {domain}
summary: "{one-line summary}"
tags:
  - {category}

defaults:
  preferred_models:
    - claude/sonnet

context_usage:
  as_user: true

tools:
  - {Tool1}
  - {Tool2}

versions:
  - version: 1
    file: {id}.prompt.v1.md
    hash: "blake3:{calculated}"
    status: active
    created: "{YYYY-MM-DD}"
    notes: "Initial version"

default_version: 1
```

**File 2: `{id}.prompt.v1.md`**

```markdown
---
description: {short description}
argument-hint: [{args}]
model: sonnet
allowed-tools: {tools}
---

# {Title}

{One sentence explaining what this command does.}

## Purpose

{Direct statement. Be specific and actionable.}

## Variables

{VAR}: $ARGUMENTS    # Description

## Workflow

### Phase 1: {Name}

{Brief description}

```bash
# Commands
```

### Phase 2: {Name}

1. **{Step}** - {Action}
2. **{Step}** - {Action}

## Report

## {Title} Results

**Status:** ✅ Complete / ❌ Issues Found

### Summary
{Key outcomes}

### Next Steps
{What to do next}

## Examples

### Basic usage
```
/{id}
```
```

### Consumer Mode Output

Create ONE file: `.claude/commands/{id}.md`

This file should be **repo-specific** - reference actual paths and patterns from THIS repository.

```markdown
---
description: {description for this repo}
argument-hint: [{args}]
model: sonnet
allowed-tools: {tools}
---

# {Title}

{Intro specific to this repository.}

## Purpose

{What this does FOR THIS SPECIFIC REPO.}

## Variables

{VAR}: $ARGUMENTS

## Workflow

1. **{Step}** - {With actual repo paths}
2. **{Step}** - {Reference actual files}
3. **{Step}** - {Use repo conventions}

## Report

{Output format for this repo}
```

## Phase 4: Create Files

### Library Mode

```bash
mkdir -p primitives/v1/commands/{category}/{id}

# Write files
cat > primitives/v1/commands/{category}/{id}/{id}.yaml << 'EOF'
{yaml content}
EOF

cat > primitives/v1/commands/{category}/{id}/{id}.prompt.v1.md << 'EOF'
{prompt content}
EOF

echo "Created:"
ls -la primitives/v1/commands/{category}/{id}/
```

### Consumer Mode

```bash
mkdir -p .claude/commands

cat > .claude/commands/{id}.md << 'EOF'
{content}
EOF

echo "Created: .claude/commands/{id}.md"
```

## Phase 5: Validation

### Library Mode

```bash
if command -v agentic-p &> /dev/null; then
  agentic-p validate primitives/v1/commands/{category}/{id}/
else
  echo "Manual validation required"
fi
```

### Consumer Mode

```bash
head -10 .claude/commands/{id}.md
grep -E "^## (Purpose|Workflow|Report)" .claude/commands/{id}.md
```

## Self-Check

Before finalizing:

- [ ] ID is kebab-case
- [ ] ID matches folder/filename
- [ ] Has Purpose, Workflow, Report sections
- [ ] Tools in metadata match frontmatter
- [ ] Workflow has actionable steps
- [ ] Content is token-efficient (no filler)

## Report

## Command Generated

**Mode:** {library | consumer}
**ID:** {id}
**Category:** {category}
**Location:** {path}

| File | Purpose |
|------|---------|
| {path1} | {desc} |

### Next Steps

1. Review generated content
2. Customize workflow for your needs
3. Test: `/{id}`
