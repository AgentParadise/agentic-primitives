---
description: Generate a new command for the current repo
argument-hint: <description> [category] [id]
model: opus
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Create Command

Generate a new Claude Code command with proper structure for the current repository.

## Purpose

Create a spec-compliant command in `.claude/commands/` that is specific to the current repo's conventions, paths, and tooling.

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

## Workflow

### Phase 1: Analyze Repo Context

```bash
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

Read 1-2 existing commands (if any) to match their style.

### Phase 2: Derive Metadata

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

### Phase 3: Generate Command

Create `.claude/commands/{id}.md` — the command should be **repo-specific**, referencing actual paths and patterns from the current repository.

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

{What this does for this specific repo.}

## Variables

{VAR}: $ARGUMENTS

## Workflow

1. **{Step}** - {With actual repo paths}
2. **{Step}** - {Reference actual files}
3. **{Step}** - {Use repo conventions}

## Report

{Output format for this repo}
```

### Phase 4: Create File

```bash
mkdir -p .claude/commands

cat > .claude/commands/{id}.md << 'EOF'
{content}
EOF

echo "Created: .claude/commands/{id}.md"
```

### Phase 5: Validation

```bash
head -10 .claude/commands/{id}.md
grep -E "^## (Purpose|Workflow|Report)" .claude/commands/{id}.md
```

## Self-Check

Before finalizing:

- [ ] ID is kebab-case
- [ ] ID matches filename
- [ ] Has Purpose, Workflow, Report sections
- [ ] Tools in metadata match frontmatter
- [ ] Workflow has actionable steps
- [ ] Content references actual repo paths/conventions
- [ ] Content is token-efficient (no filler)

## Report

## Command Generated

**ID:** {id}
**Category:** {category}
**Location:** `.claude/commands/{id}.md`

### Next Steps

1. Review generated content
2. Customize workflow for your needs
3. Test: `/{id}`
