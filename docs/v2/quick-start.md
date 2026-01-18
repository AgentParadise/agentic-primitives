# V2 Quick Start Guide

**⏱️ Complete in 5 minutes**

This guide walks you through creating, validating, building, and using your first V2 primitive.

## Prerequisites

- Rust 1.83+ (for CLI)
- Python 3.11+ (for tools, optional)

## Step 1: Build the CLI (1 min)

```bash
cd cli/v2
cargo build --release

# Add to PATH (optional)
export PATH="$PATH:$(pwd)/target/release"

# Verify installation
agentic-p --version
```

## Step 2: Create a Command (1 min)

### Interactive Mode (Recommended)

```bash
agentic-p new command qa code-review
```

Follow the prompts:
- **Description**: "Review code for quality and best practices"
- **Model**: sonnet (default)
- **Argument hint**: (press Enter to skip)
- **Allowed tools**: "Read, Grep, Bash"

### Non-Interactive Mode

```bash
agentic-p new command qa code-review \
  --description "Review code for quality and best practices" \
  --model sonnet \
  --allowed-tools "Read, Grep, Bash" \
  --non-interactive
```

**Result**: `primitives/v2/commands/qa/code-review.md` created and validated!

## Step 3: Inspect the Generated File (30 sec)

```bash
cat primitives/v2/commands/qa/code-review.md
```

You'll see:
```markdown
---
description: Review code for quality and best practices
model: sonnet
allowed-tools: Read, Grep, Bash
---

# Code Review

Review code for quality and best practices

## Usage

\`\`\`bash
# Example usage of this command
code-review
\`\`\`

## Details

<!-- Add implementation details here -->
...
```

**Action**: Edit the file to add your custom prompt logic!

## Step 4: Validate (30 sec)

```bash
# Validate single file
agentic-p validate primitives/v2/commands/qa/code-review.md

# Output:
# ✓ Command frontmatter is valid
# ✓ Primitive is valid!
```

```bash
# Validate all v2 primitives
agentic-p validate --all

# Output:
# Total:  4
# Passed: 4 ✓
# Failed: 0 ✓
```

## Step 5: Build (1 min)

```bash
agentic-p build --provider claude --primitives-version v2
```

**Result**: Builds all V2 primitives to `build/claude/`

```
build/claude/
├── commands/
│   └── qa/
│       └── code-review.md
└── .agentic-manifest.yaml
```

## Step 6: Install (1 min)

```bash
# Install to user directory (global)
agentic-p install --provider claude --global

# Output: Installed to ~/.claude/commands/qa/
```

Or install locally to project:

```bash
# Install to project
agentic-p install --provider claude

# Output: Installed to ./.claude/commands/qa/
```

## Step 7: Use with Claude (30 sec)

Your command is now available in Claude Code:

```bash
# In Claude Code chat
/code-review
```

Or use the Claude CLI:

```bash
claude code-review path/to/file.py
```

## What You've Learned

- ✅ Created a command primitive
- ✅ Validated it against schemas
- ✅ Built it for Claude
- ✅ Installed it for use
- ✅ Used it in Claude Code

## Next Steps

### Create More Primitives

**Create a Skill:**
```bash
agentic-p new skill testing test-expert \
  --description "Expert knowledge in testing best practices" \
  --model sonnet \
  --expertise "TDD, BDD, Coverage Analysis" \
  --non-interactive
```

**Create a Tool:**
```bash
agentic-p new tool data json-validator \
  --description "Validate JSON against schemas" \
  --model sonnet \
  --non-interactive
```

### Learn More

- **[Authoring Commands](./authoring/commands.md)** - Deep dive into command creation
- **[Authoring Skills](./authoring/skills.md)** - Create expert skills
- **[Authoring Tools](./authoring/tools.md)** - Build executable tools
- **[Frontmatter Reference](./reference/frontmatter.md)** - All available fields
- **[CLI Reference](./reference/cli.md)** - Complete CLI documentation

### Advanced Topics

- **[Testing Primitives](./guides/testing.md)** - Write tests for your primitives
- **[Building & Installing](./guides/building-installing.md)** - Advanced build options
- **[Migration from V1](./guides/migration.md)** - Migrate existing primitives

## Troubleshooting

### Validation Errors

If you see validation errors, check:
1. **Description length**: Must be 10-200 characters
2. **Model**: Must be one of `haiku`, `sonnet`, `opus`
3. **Frontmatter format**: Must be valid YAML between `---` delimiters

### Build Errors

If build fails:
1. **Run validation first**: `agentic-p validate --all`
2. **Check file paths**: Ensure files are in correct category structure
3. **Verbose output**: Add `--verbose` flag to see details

### Command Not Found

If `agentic-p` command not found:
1. **Check PATH**: Ensure `cli/v2/target/release` is in PATH
2. **Rebuild**: `cd cli/v2 && cargo build --release`
3. **Use full path**: `./cli/v2/target/release/agentic-p`

## Get Help

- **Docs**: See other guides in `docs/v2/`
- **Issues**: Check GitHub issues
- **ADRs**: See `docs/adrs/` for design decisions

---

*Ready to build? Start creating primitives!*
