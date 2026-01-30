# Authoring Commands

Commands are reusable prompts for specific tasks. They're the most common type of primitive.

## Command Structure

```markdown
---
description: Brief description (10-200 chars, required)
argument-hint: "[arg1] [arg2] - hint text (optional)"
model: sonnet  # haiku, sonnet, or opus (required)
allowed-tools: Read, Grep, Bash  # comma-separated (optional)
tags:  # optional
  - code-quality
  - review
---

# Command Title

Detailed explanation of what this command does...

## Usage

Examples and usage instructions...
```

## Creating a Command

### Method 1: CLI Generator (Recommended)

```bash
# Interactive
agentic-p new command qa review

# Non-interactive
agentic-p new command qa review \
  --description "Review code for quality" \
  --model sonnet \
  --allowed-tools "Read, Grep" \
  --non-interactive
```

### Method 2: Manual Creation

1. Create file: `primitives/v2/commands/{category}/{name}.md`
2. Add frontmatter (see structure above)
3. Write command content
4. Validate: `agentic-p validate primitives/v2/commands/{category}/{name}.md`

## Frontmatter Fields

### Required Fields

- **`description`**: 10-200 character description of what the command does
- **`model`**: Model to use (`haiku`, `sonnet`, or `opus`)

### Optional Fields

- **`argument-hint`**: Hint for command arguments (e.g., `"[file] [options]"`)
- **`allowed-tools`**: Comma-separated list of tools the command can use
- **`tags`**: Array of tags for categorization

## Best Practices

### 1. Clear, Actionable Descriptions

**Good:**
```yaml
description: Review code for security vulnerabilities and suggest fixes
```

**Bad:**
```yaml
description: Code stuff  # Too vague
description: This command reviews code files in the repository for potential security vulnerabilities, analyzes the code structure, checks for common patterns... # Too long
```

### 2. Choose the Right Model

- **`haiku`**: Fast, simple tasks (formatting, simple transformations)
- **`sonnet`**: Default, balanced (most commands)
- **`opus`**: Complex reasoning (architecture, design patterns)

### 3. Specify Allowed Tools

```yaml
# File operations
allowed-tools: Read, List, Write

# Code analysis
allowed-tools: Read, Grep, Bash

# Full access
allowed-tools: "*"
```

### 4. Use Argument Hints

```yaml
# Command with arguments
argument-hint: "[file_path] - path to file to analyze"

# Command with options
argument-hint: "[directory] [--recursive] - scan directory"

# No arguments
# (omit argument-hint)
```

### 5. Write Clear Instructions

Structure your command content:

```markdown
# Command Name

Brief overview of what this does.

## Purpose

Why use this command? What problem does it solve?

## Usage

\`\`\`bash
command-name [arguments]
\`\`\`

## Process

1. First, do X
2. Then, do Y
3. Finally, do Z

## Output

What the command produces.

## Examples

Concrete examples with expected output.
```

## Common Patterns

### Review/Analysis Commands

```markdown
---
description: Analyze Python code for best practices and suggest improvements
model: sonnet
allowed-tools: Read, Grep
tags:
  - code-quality
  - python
---

# Python Code Review

Analyze Python code for:
- PEP 8 compliance
- Type hints
- Documentation
- Best practices
...
```

### Generation Commands

```markdown
---
description: Generate unit tests for Python functions
model: sonnet
allowed-tools: Read, Write
argument-hint: "[file_path] - path to source file"
---

# Generate Tests

Create comprehensive unit tests...
```

### Refactoring Commands

```markdown
---
description: Refactor code to improve readability and maintainability
model: opus  # Complex reasoning
allowed-tools: Read, Write, Bash
---

# Refactor

Analyze and refactor code while:
- Preserving functionality
- Improving structure
- Adding documentation
...
```

## Categories

Organize commands by category:

- **`qa/`**: Quality assurance, testing, review
- **`devops/`**: DevOps, CI/CD, deployment
- **`docs/`**: Documentation generation
- **`refactor/`**: Code refactoring
- **`data/`**: Data processing, transformation
- **`security/`**: Security analysis, hardening

Create new categories as needed!

## Validation

Always validate before building:

```bash
# Single command
agentic-p validate primitives/v2/commands/{category}/{name}.md

# All commands
agentic-p validate --all
```

### Common Validation Errors

**Error: Description too short**
```
Error: description must be at least 10 characters
```
Fix: Expand your description.

**Error: Invalid model**
```
Error: model must be one of: haiku, sonnet, opus
```
Fix: Use a valid model name.

**Error: Missing frontmatter**
```
Error: No frontmatter found
```
Fix: Ensure file starts with `---` and includes required fields.

## Testing Commands

After creation:

1. **Validate**: `agentic-p validate`
2. **Build**: `agentic-p build --provider claude --primitives-version v2`
3. **Install**: `agentic-p install --provider claude`
4. **Use**: Test in Claude Code

## Examples

### Simple Command

```markdown
---
description: Format Python code with black and isort
model: haiku
allowed-tools: Bash
---

# Format Python

Format Python code using black and isort.

## Usage

\`\`\`bash
format-python [file_or_directory]
\`\`\`

## Process

1. Run `black` for formatting
2. Run `isort` for import sorting
3. Show diff of changes
```

### Complex Command

```markdown
---
description: Design a scalable microservices architecture
model: opus
allowed-tools: Read, Write
argument-hint: "[requirements_file] - path to requirements document"
tags:
  - architecture
  - microservices
---

# Design Microservices

Design a scalable microservices architecture based on requirements.

## Approach

1. Analyze requirements
2. Identify service boundaries
3. Define communication patterns
4. Design data persistence
5. Plan deployment strategy

## Deliverables

- Architecture diagram
- Service specifications
- API contracts
- Deployment guide
```

## Next Steps

- **[Authoring Skills](./skills.md)** - Create expert skills
- **[Authoring Tools](./tools.md)** - Build executable tools
- **[Frontmatter Reference](../reference/frontmatter.md)** - All fields
- **[CLI Reference](../reference/cli.md)** - CLI commands
