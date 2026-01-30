# V2 Primitives - Start Here

**⏱️ Read this in 2 minutes**

## What is V2?

V2 is a simplified, flat architecture for agentic primitives that makes it easy to:
- ✅ Create new commands and skills in < 2 minutes
- ✅ Validate primitives against schemas
- ✅ Build provider-specific outputs
- ✅ Maintain and evolve your primitive library

## Key Differences from V1

| Aspect | V1 | V2 |
|--------|-----|-----|
| **Structure** | Nested (`commands/qa/review/review.prompt.v1.md`) | Flat (`commands/qa/review.md`) |
| **Metadata** | Separate `.meta.yaml` files | Frontmatter in markdown |
| **Categories** | Complex hierarchy | Simple category folders |
| **Tool Definitions** | Provider-specific | Standard `tool.yaml` with auto-generated adapters |
| **CLI** | `agentic-p-v1` (maintenance mode) | `agentic-p` (active development) |

## Quick Links

- **[Quick Start Guide](./quick-start.md)** - Create your first primitive in 5 minutes
- **[CLI Reference](./reference/cli.md)** - All CLI commands
- **[Authoring Guides](./authoring/)** - How to create commands, skills, and tools
- **[Migration Guide](./guides/migration.md)** - Migrating from V1 to V2

## Core Concepts

### Primitives

V2 has three types of primitives:

1. **Commands** (`primitives/v2/commands/`) - Reusable prompts for specific tasks
2. **Skills** (`primitives/v2/skills/`) - Expert knowledge and methodologies
3. **Tools** (`primitives/v2/tools/`) - Executable functions with standard interfaces

### Directory Structure

```
primitives/v2/
├── commands/
│   ├── {category}/
│   │   └── {name}.md
├── skills/
│   ├── {category}/
│   │   └── {name}.md
└── tools/
    ├── {category}/
    │   └── {name}/
    │       ├── tool.yaml
    │       ├── impl.py
    │       ├── pyproject.toml
    │       └── README.md
```

## Workflow

```
Create → Validate → Build → Install → Use
   ↓         ↓         ↓        ↓       ↓
agentic-p  validate  build  install  claude
```

### 1. Create
```bash
# Interactive mode (prompts for details)
agentic-p new command qa review

# Non-interactive (all flags)
agentic-p new command qa review \
  --description "Review code for quality and best practices" \
  --model sonnet \
  --allowed-tools "Read, Grep" \
  --non-interactive
```

### 2. Validate
```bash
# Single primitive
agentic-p validate primitives/v2/commands/qa/review.md

# All primitives
agentic-p validate --all
```

### 3. Build
```bash
# Build for Claude
agentic-p build --provider claude --primitives-version v2

# Output: build/claude/
```

### 4. Install
```bash
# Install to user directory (global)
agentic-p install --provider claude --global

# Install to project (local)
agentic-p install --provider claude
```

## CLI Installation

```bash
# Build V2 CLI (recommended)
cd cli/v2
cargo build --release
# Binary: target/release/agentic-p

# Add to PATH (optional)
export PATH="$PATH:$(pwd)/target/release"
```

## Getting Help

- **Quick Start**: [./quick-start.md](./quick-start.md)
- **Authoring Guides**: [./authoring/](./authoring/)
- **CLI Reference**: [./reference/cli.md](./reference/cli.md)
- **Troubleshooting**: Check validation errors, read frontmatter docs
- **ADRs**: See `docs/adrs/` for architectural decisions

## Next Steps

1. **[Create your first primitive](./quick-start.md)** (5 min)
2. **[Learn about frontmatter fields](./reference/frontmatter.md)** (10 min)
3. **[Build and install](./guides/building-installing.md)** (5 min)
4. **[Migrate from V1](./guides/migration.md)** (if applicable)

---

*V2 is designed for speed and simplicity. If something feels complex, it probably is - let us know!*
