# V2 Simplification Worktree

**Location**: `/Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification/`
**Branch**: `v2-simplification`
**Status**: Ready for implementation

---

## 🎯 Start Here

1. **Read the PROJECT-PLAN**: `PROJECT-PLAN_20260113_v2-simplification.md`
   - Complete implementation plan with milestones
   - All tasks with checkboxes
   - File paths and validation criteria

2. **Open in New Cursor Window**:
   ```bash
   cursor /Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification
   ```

3. **Follow RIPER-5 Protocol** (from `AGENTS.md`):
   - Start in PLAN mode (review plan)
   - Transition to EXECUTE for each milestone
   - QA checkpoint after each milestone
   - Conventional commits

---

## 📚 Context Available in This Worktree

### Planning & Architecture
- ✅ `PROJECT-PLAN_20260113_v2-simplification.md` - **Main plan document**
- ✅ `AGENTS.md` - RIPER-5 workflow protocol
- ✅ `.context-docs/README.md` - Quick reference

### Reference from Main Repo
To access design docs created in the main workspace session:
```bash
# From main repo workspace:
cd /Users/codedev/Code/ai/agentic-primitives

# View these docs:
cat docs/v2-architecture-design.md
cat docs/adrs/031-tool-primitives-auto-generated-adapters.md
cat V2-DESIGN-COMPLETE.md
cat docs/v2-implementation-status.md
cat docs/deps/unknown/claude-code@latest-20260113.md
cat docs/deps/python/fastmcp@latest-20260113.md
cat schemas/tool-spec.v1.json
```

Or commit them to main and pull into worktree:
```bash
# In main workspace
cd /Users/codedev/Code/ai/agentic-primitives
git add docs/v2-architecture-design.md docs/adrs/031-tool-primitives-auto-generated-adapters.md V2-DESIGN-COMPLETE.md docs/v2-implementation-status.md
git commit -m "docs: add v2 architecture design and planning docs"

# In worktree
cd /Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification
git pull origin main
```

---

## 🚀 Quick Start

### Phase 1: Foundation (Start Here)

```bash
# Navigate to worktree
cd /Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification

# Review the plan
cat PROJECT-PLAN_20260113_v2-simplification.md

# Start with Milestone 1.1: Clean Up Source Structure
# See PROJECT-PLAN for detailed tasks
```

### Key Files to Work On

**Phase 1 (Foundation)**:
- `commands/` (new directory structure)
- `skills/` (new directory structure)
- `tools/` (new directory structure)
- `cli/src/builders/simple.rs` (file existence logic)
- `cli/src/builders/claude.rs` (v1-compatible output)

**Critical Constraint**:
- `lib/python/` - **DO NOT REFACTOR** (must preserve imports)
- Build output must match v1 structure

---

## ✅ Success Criteria

Before merge to main:
- [ ] V1 build output structure preserved
- [ ] Python imports unchanged (`from agentic_isolation import DockerProvider`)
- [ ] Idempotent installs (skip existing, --force = update)
- [ ] Granular installs (`agentic-p install command review`)
- [ ] Interactive mode (prompt per file)
- [ ] Local install by default (`./.claude/` when in repo)
- [ ] All tests passing
- [ ] Documentation updated
- [ ] ADRs reviewed

---

## 📋 Key Decisions from Planning Session

1. **No Per-Primitive Versioning** - Git tags for repo version only
2. **File Exists = Skip** - Simple, fast, predictable
3. **Preserve V1 Build Output** - Downstream compatibility critical
4. **Claude Code as Standard** - Follow their conventions
5. **FastMCP for Python Tools** - Auto-generate MCP servers

---

## 🔧 Development Commands

```bash
# QA checks
just qa           # Full QA suite
just qa-fix       # Auto-fix issues
just fmt          # Format code
just test         # Run tests

# Build CLI
just build        # Debug build
just build-release  # Release build

# Test build output
agentic-p build --provider claude
agentic-p build --dry-run
agentic-p build --force
```

---

## 📝 Commit Guidelines

Use conventional commits:
- `feat:` - New features
- `fix:` - Bug fixes
- `refactor:` - Code restructuring
- `docs:` - Documentation
- `test:` - Tests
- `chore:` - Maintenance

**DO NOT commit**:
- PROJECT-PLAN files
- Temporary files
- Build artifacts

---

## 🔄 Worktree Management

### Sync with Main
```bash
# Update from main
git fetch origin
git merge origin/main

# Or rebase
git rebase origin/main
```

### When Done
```bash
# Merge back to main
git checkout main
git merge v2-simplification

# Remove worktree
git worktree remove v2-simplification
```

---

## 🆘 Need Help?

1. **Review PROJECT-PLAN** - Has detailed tasks and validation
2. **Check AGENTS.md** - RIPER-5 workflow protocol
3. **Refer to ADR-031** - Core architectural decisions
4. **Test incrementally** - Run tests after each milestone

---

**Ready to start Phase 1 implementation!**

Open in new Cursor window:
```bash
cursor /Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification
```
