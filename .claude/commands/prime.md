# Agentic Primitives Repository Primer

You are working in the **agentic-primitives** repository - a source-of-truth for reusable, versionable, provider-agnostic primitives for building agentic AI systems.

## 🎯 What This Repo Does

This is a **primitive-to-provider compiler** that transforms generic AI agent components into provider-specific formats (Claude, OpenAI, Cursor, etc.). Think of it as a standard library for AI agents.

**Three types of primitives:**
- **🧠 Prompt Primitives**: Agents, commands, skills, meta-prompts
- **🔧 Tool Primitives**: Logical tool specs with provider implementations
- **🪝 Hook Primitives**: Lifecycle event handlers with middleware

## 📁 Repository Structure

```
agentic-primitives/
├── specs/v1/                    # JSON schemas for validation
├── primitives/v1/               # Source primitives (version v1 active)
│   ├── prompts/
│   │   ├── agents/<category>/<id>/
│   │   ├── commands/<category>/<id>/
│   │   ├── skills/<category>/<id>/
│   │   └── meta-prompts/<category>/<id>/
│   ├── tools/<category>/<id>/
│   └── hooks/<category>/<id>/
├── providers/                   # Provider adapters (claude, openai, cursor)
├── cli/                         # Rust CLI tool
├── hooks/                       # Python hook implementations (uv)
├── docs/                        # Documentation & ADRs
└── Makefile                     # All dev operations use this
```

**Key Pattern**: `/primitives/v1/<type>/<category>/<id>/`
- Example: `primitives/v1/prompts/agents/python/python-pro/`

## 🏗️ Primitive Anatomy

### Prompt Primitives
Each prompt primitive contains:
- `<id>.v1.md`, `<id>.v2.md` - Versioned content files
- `<id>.yaml` - Metadata with version registry, model preferences, tool dependencies

### Tool Primitives
- `<id>.tool.yaml` - Generic tool specification
- `impl.claude.yaml`, `impl.openai.json` - Provider bindings
- `impl.local.{rs|py|ts}` - Local implementations

### Hook Primitives
- `<id>.hook.yaml` - Event config & middleware list
- `impl.python.py` - Orchestrator implementation
- `middleware/` - Safety & observability middleware

## 🚀 Quick Start Commands

### Essential CLI Commands
```bash
# Initialize a new repository
agentic-p init

# Create primitives
agentic-p new prompt agent <category>/<id>
agentic-p new command <category>/<id>
agentic-p new skill <category>/<id>
agentic-p new tool <category>/<id>
agentic-p new hook <category>/<id>

# Validate everything
agentic-p validate

# Inspect a primitive
agentic-p inspect <category>/<id>

# Version management
agentic-p version bump <id> --notes "Added feature X"
agentic-p version list <id>
agentic-p version promote <id> --version 2

# Build & install
agentic-p build --provider claude
agentic-p install --provider claude --global
```

### Makefile Commands (ALWAYS USE THESE)
```bash
make help          # Show all commands
make build         # Build debug CLI
make build-release # Build release CLI
make fmt           # Format Rust + Python
make lint          # Lint all code
make typecheck     # Type check Python
make test          # Run all tests
make qa            # Full QA suite (fmt check, lint, typecheck, test)
make qa-fix        # Auto-fix issues and run QA
make verify        # Clean, check, build everything
```

**IMPORTANT**: Always use `make` commands for consistency. Never run cargo/rustc/pytest directly unless specifically needed.

## 🔄 RIPER-5 Workflow (from AGENTS.md)

This repo follows the RIPER-5 methodology. Always declare your mode:

**[MODE: RESEARCH]** - Information gathering only, no suggestions
**[MODE: INNOVATE]** - Brainstorming approaches, no concrete plans
**[MODE: PLAN]** - Create detailed technical specs in PROJECT-PLAN_YYYYMMDD_<task>.md
**[MODE: EXECUTE]** - Implement the plan exactly, run QA after each milestone
**[MODE: REVIEW]** - Validate implementation against plan

### QA Checkpoint (After Each Milestone)
```bash
make qa-fix   # Auto-fix and run all checks
# Then commit with conventional commits (feat:, fix:, docs:, refactor:, etc.)
```

## ✅ Validation System

Three-layer validation (all must pass):
1. **Structural**: Directory structure, file naming, required files exist
2. **Schema**: YAML/JSON validity, required fields, types
3. **Semantic**: References resolve, no duplicates, hashes match

Run with: `agentic-p validate` or `make test`

## 🔐 Versioning & Immutability

- **System-level**: v1 (active), v2 (future), experimental/
- **Primitive-level**: Each prompt has versions (v1, v2, ...) tracked in `<id>.yaml`
- **Hash validation**: BLAKE3 hashes ensure immutability of active versions
- **Version states**: draft → active → deprecated → archived

**Key**: `default_version` in `<id>.yaml` determines which version is used.

## 📋 Common Tasks

### Adding a New Feature
1. Enter PLAN mode, create PROJECT-PLAN_YYYYMMDD_<feature>.md
2. Document all changes with file paths
3. Consider writing ADR in docs/adrs/ for architecture decisions
4. Enter EXECUTE mode
5. Implement milestone by milestone
6. After each milestone: `make qa-fix` → commit
7. Never commit PROJECT-PLAN files

### Creating a New Primitive
```bash
# Example: Create a Python expert agent
agentic-p new prompt agent python/python-pro

# This creates:
# primitives/v1/prompts/agents/python/python-pro/
#   ├── python-pro.v1.md    # Content
#   └── python-pro.yaml     # Metadata

# Edit the files, then validate
agentic-p validate
```

### Building for a Provider
```bash
# Validate first
agentic-p validate

# Build for Claude
agentic-p build --provider claude
# Output: build/claude/.claude/

# Install globally
agentic-p install --provider claude --global
# Installs to: ~/.claude/

# Or install to project
agentic-p install --provider claude --project
# Installs to: ./.claude/
```

### Making Changes
1. Check current status: `git status`
2. Make changes to primitives
3. Validate: `agentic-p validate`
4. Run QA: `make qa-fix`
5. Review changes: `git diff`
6. Commit with conventional format: `feat:`, `fix:`, `docs:`, `refactor:`, etc.

## 🔍 Important Files to Check

- **README.md** - Full project overview
- **docs/architecture.md** - Complete system architecture
- **docs/versioning-guide.md** - Versioning documentation
- **docs/adrs/** - Architecture Decision Records
- **AGENTS.md** - RIPER-5 workflow (you're following this)
- **Makefile** - All available development commands
- **cli/src/** - CLI source code
- **specs/v1/** - JSON schemas for validation

## 💡 Pro Tips

1. **Always validate**: Run `agentic-p validate` before committing
2. **Use the Makefile**: Never bypass `make` commands
3. **Follow naming**: `<id>.yaml`, `<id>.v1.md`, `<id>.tool.yaml`, `<id>.hook.yaml`
4. **Router structure**: Think of primitives as REST endpoints - type/category/id
5. **Provider-agnostic**: Write generic primitives, compile to specific providers
6. **Version carefully**: Bump versions when content changes materially
7. **Test-driven**: Write tests first (see ADR-008)
8. **Document decisions**: Use ADRs for architectural choices

## 🎓 Learning Path

**First 5 minutes:**
1. Read this primer (you're here!)
2. Check `git status` to see what's changed
3. Run `make help` to see available commands
4. Run `agentic-p list` to see existing primitives

**First task:**
1. Understand the task requirements
2. Grep/read relevant files: `primitives/v1/`, `cli/src/`, `providers/`
3. Enter RESEARCH mode, explore thoroughly
4. Enter PLAN mode if implementation needed
5. Use PROJECT-PLAN for complex changes
6. Execute milestone by milestone with QA checkpoints

**Reference architecture:**
- Provider adapters: `providers/<provider>/`
- Validation logic: `cli/src/validation/`
- Primitive loading: `cli/src/primitives/`
- Commands: `cli/src/commands/`

## 🚨 Critical Rules

1. **Never commit generated files** - Only primitives, not build/ output
2. **Never skip validation** - Always run before committing
3. **Never bypass QA** - Use `make qa-fix` after changes
4. **Follow RIPER-5** - Declare your mode, follow the workflow
5. **Use conventional commits** - Format: `type(scope): description`
6. **Version immutability** - Active versions must not change (bump instead)
7. **Test coverage** - Aim for >80% coverage
8. **ADRs for architecture** - Document significant decisions

---

**You're now primed!** Start by checking `git status` and understanding the current state of the repository.
