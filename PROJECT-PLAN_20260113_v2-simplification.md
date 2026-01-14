# PROJECT PLAN: V2 Architecture Simplification

**Date**: 2026-01-13
**Branch**: v2-simplification
**Worktree**: ../agentic-primitives_worktrees/v2-simplification/
**Status**: Phase 1 Complete, Phase 2 Pending

> **⚠️ RETROACTIVE UPDATE NOTE**: This plan was created after initial design exploration in the main workspace. Some design documents (ADRs, architecture docs) were created there and should be referenced or committed before full implementation. See "Context Files to Reference" section at bottom.

---

## Executive Summary

Simplify agentic-primitives architecture from complex v1 (provider abstraction, custom metadata, manual adapters) to streamlined v2 (atomic primitives, auto-generated adapters, Claude Code native, version-tracked for evals).

**Core Philosophy**:
- **Standard over Custom**: Follow Claude Code standards
- **Generate over Maintain**: Auto-generate adapters from specs
- **Simple over Clever**: File existence checks for installs, hash-based version tracking for changes
- **Agnostic over Locked**: Multi-framework via generation
- **Version for Evals**: Semver + content hashing for reproducible evaluation

---

## Problem Statement

### Current Pain Points (V1)
1. **Complex structure**: `primitives/v1/<type>/<category>/<id>/`
2. **Custom metadata**: `.meta.yaml` with BLAKE3, version tracking
3. **Manual adapters**: Hand-written for each framework
4. **Non-standard naming**: `<id>.prompt.v1.md`
5. **Build always required**: Can't use plugins directly with Claude

### What We're Building (V2)
- **Atomic primitives**: Flat structure (commands/, skills/, tools/)
- **Simple metadata**: Minimal YAML, no per-file versioning
- **Auto-generated adapters**: FastMCP, LangChain, OpenAI from tool.yaml
- **Claude Code native**: Plugins work with `claude --plugin-dir`
- **Smart install**: File exists = skip, --force = overwrite, --interactive = prompt

---

## Success Criteria

### Must Have
- [ ] V1 build output structure preserved (downstream compatibility)
- [ ] Python imports unchanged (`from agentic_isolation import DockerProvider`)
- [ ] Idempotent installs (skip existing, --force to update)
- [ ] Granular installs (`agentic-p install command review`)
- [ ] Interactive mode (prompt per file)
- [ ] Local install by default (`./.claude/` when in repo)
- [ ] **Version tracking** (semver + content hash for reproducible evals)
- [ ] **Auto-bump detection** (git hooks catch version mismatches)

### Nice to Have
- [ ] Migration tool (v1 → v2 structure conversion)
- [ ] Worktree management primitive command
- [ ] Updated documentation
- [ ] Example primitives in new format
- [ ] Automated version suggestions (analyze diff → suggest patch/minor/major)

---

## Architecture Overview

### V2 Source Structure (Simplified)
```
agentic-primitives/
├── .agentic-versions.json  # ← Version manifest (tracked in git)
├── .git/hooks/
│   └── pre-commit          # ← Version validation hook
│
├── commands/               # ← Flat markdown files (with version frontmatter)
│   ├── review.md
│   ├── commit.md
│   └── doc-scraper.md
│
├── skills/                 # ← Flat markdown files (with version frontmatter)
│   ├── testing-expert.md
│   └── security-expert.md
│
├── tools/                  # ← Code + tool.yaml (with version)
│   ├── firecrawl-scraper/
│   │   ├── tool.yaml       # Standard spec (includes version)
│   │   ├── impl.py         # Pure implementation
│   │   └── pyproject.toml
│   └── docker-isolation/
│       ├── tool.yaml
│       ├── isolation.py
│       └── pyproject.toml
│
├── plugins/                # ← Composition manifests
│   ├── qa-suite.yaml
│   └── devops-tools.yaml
│
├── lib/                    # ← UNCHANGED (stable APIs)
│   └── python/
│       ├── agentic_isolation/
│       ├── agentic_adapters/
│       └── agentic_events/
│
└── cli/                    # ← Enhanced build logic + versioning
    └── src/
        ├── builders/
        │   ├── simple.rs   # File existence checks
        │   └── claude.rs   # V1-compatible output
        ├── generators/
        │   ├── mcp.rs      # FastMCP generator
        │   ├── langchain.rs
        │   └── openai.rs
        └── versioning/     # ← NEW: Version management
            ├── validate.rs # Check version consistency
            ├── bump.rs     # Auto-bump versions
            └── hash.rs     # BLAKE3 content hashing
```

### V1-Compatible Build Output (Preserved)
```
build/claude/              # ← Same as V1!
├── commands/
│   └── review.md
├── skills/
│   └── testing-expert/
│       └── SKILL.md
└── hooks/
    └── hooks.json

.claude/                   # ← Installation target
├── .agentic-p-manifest.json
├── commands/
├── skills/
└── .mcp.json
```

---

## Phase 1: Foundation & Structure

### Milestone 1.1: Clean Up Source Structure ✅ COMPLETE
**Goal**: Flatten primitives/ structure, add version frontmatter

**Tasks**:
- [x] Create new flat directories
  - [x] `primitives/v2/commands/{category}/` (categorized)
  - [x] `primitives/v2/skills/{category}/` (categorized)
  - [x] `primitives/v2/tools/{category}/` (categorized)
- [x] Convert metadata
  - [x] `.meta.yaml` → simple frontmatter (no per-file version tracking - deferred)
  - [x] `tool.yaml` schema (use `tool-spec.v1.json`)
  - [x] Removed "Level X (Workflow)" and "Purpose" sections
- [x] Version manifest (DEFERRED to Phase 2)
  - [ ] `.agentic-versions.json` (deferred - git tags used instead)
  - [ ] Initial population from existing primitives (deferred)
- [x] Test that nothing breaks in lib/python/ (no refactor)

**Example Frontmatter**:
```markdown
---
id: review
version: 1.0.0
last_updated: 2026-01-13

dependencies:
  skills: [testing-expert@1.0.0]

changelog:
  - version: 1.0.0
    date: 2026-01-13
    changes: Migrated from v1 structure
---

# Code Review Command
...
```

**Files Created/Modified**:
- `commands/review.md` (from `primitives/v1/commands/qa/review/review.prompt.v1.md`)
- `commands/commit.md` (from `primitives/v1/commands/devops/commit/`)
- `skills/testing-expert.md` (from `primitives/v1/skills/testing/testing-expert/`)
- `tools/firecrawl-scraper/tool.yaml` (from `primitives/v1/tools/scrape/firecrawl-scraper/`)
- `.agentic-versions.json` (new - version manifest)

**Validation**:
```bash
# Python imports still work
python -c "from agentic_isolation import DockerProvider; print('✓')"
python -c "from agentic_adapters import ClaudeCLIRunner; print('✓')"

# Version manifest valid
agentic-p validate-versions
# Expected: All versions match content hashes
```

---

### Milestone 1.2: Simple Build System ✅ COMPLETE
**Goal**: Implement v2 build and discovery

**Tasks**:
- [x] Update CLI build logic
  - [x] `cli/src/commands/build_v2.rs` - v2 primitives discovery
  - [x] `cli/src/providers/claude_v2.rs` - v2 transformer
  - [x] Add `--primitives-version` flag to build command
  - [x] V2 discovery for commands, skills, tools
- [x] V2 transformer implementation
  - [x] Parse frontmatter from markdown
  - [x] Transform commands with frontmatter
  - [x] Transform skills to Claude Code format
  - [x] Copy tools directory with tool.yaml
- [x] Implement install modes (DEFERRED TO PHASE 2)
  - [ ] Default: skip if file exists (deferred)
  - [ ] `--force`: overwrite all (deferred)
  - [ ] `--interactive`: prompt per file (deferred)
- [x] Add target detection (DEFERRED TO PHASE 2)
  - [ ] Auto-detect project (install to `./.claude/`) (deferred)
  - [ ] `--global` flag (install to `~/.claude/`) (deferred)
  - [ ] `--output` flag (custom path) (deferred)
- [x] Manifest tracking
  - [x] `.agentic-manifest.yaml` generated (needs path fix)

**Files Created/Modified**:
- `cli/src/commands/build_v2.rs` (new - v2 discovery logic)
- `cli/src/providers/claude_v2.rs` (new - v2 transformer)
- `cli/src/commands/build.rs` (updated with --primitives-version flag)
- `cli/src/main.rs` (added --primitives-version argument)
- `cli/src/commands/mod.rs` (added build_v2 module)
- `cli/src/providers/mod.rs` (added claude_v2 export)

**Test Cases**: ✅ PASSING
```bash
# Test 1: V2 build
./cli/target/release/agentic-p build --provider claude --primitives-version v2
# Expected: Build v2 primitives ✅ PASSED
# Result: 4 primitives built (2 commands, 1 skill, 1 tool)

# Test 2: V2 output structure
tree build/claude/
# Expected: commands/{category}/, skills/{name}/, tools/{category}/ ✅ PASSED

# Test 3: V1 build (backward compatibility)
./cli/target/release/agentic-p build --provider claude --primitives-version v1
# Expected: Build v1 primitives ✅ NOT YET TESTED

# Remaining tests (deferred):
# - Install with file-exists logic
# - Interactive mode
# - Granular installs
```

---

### Milestone 1.3: Build Output Compatibility 📋 PENDING
**Goal**: Ensure v1 output structure is preserved

**Tasks**:
- [x] Transform skills (flat → nested)
  - [x] `skills/testing-expert.md` → `build/claude/skills/testing-expert/SKILL.md` ✅
- [x] Transform commands (copy)
  - [x] `commands/review.md` → `build/claude/commands/review.md` ✅
- [ ] Fix manifest path inconsistencies
  - [ ] Standardize to relative paths only
  - [ ] Remove extraneous tool file entries
- [ ] Generate tool adapters (DEFERRED TO PHASE 2)
  - [ ] Read `tools/*/tool.yaml`
  - [ ] Generate FastMCP server → `build/adapters/mcp/*_server.py`
  - [ ] Update `.mcp.json` with server references
- [ ] Test downstream compatibility
  - [ ] Build in this repo ✅ DONE
  - [ ] Use in downstream project (agentic engineering framework)
  - [ ] Verify Python imports work ✅ DONE
  - [ ] Verify .claude/ structure matches v1 ✅ DONE (visual inspection)

**Files Created/Modified**:
- `cli/src/builders/transforms.rs` (new - transformation logic)
- `cli/src/generators/mcp.rs` (modify for tool.yaml)

**Validation Script**:
```bash
#!/bin/bash
# test-downstream-compatibility.sh

set -e

echo "Testing downstream compatibility..."

# Build v2
agentic-p build --target claude

# Check structure matches v1
test -f .claude/commands/review.md || (echo "❌ review.md missing" && exit 1)
test -f .claude/skills/testing-expert/SKILL.md || (echo "❌ SKILL.md missing" && exit 1)
test -f .claude/.mcp.json || (echo "❌ .mcp.json missing" && exit 1)

# Check Python imports
python -c "from agentic_isolation import DockerProvider" || (echo "❌ Import failed" && exit 1)

echo "✓ All compatibility checks passed"
```

---

## Phase 2: Versioning & Enhanced Features

### Milestone 2.1: Version Management System
**Goal**: Auto-detect version changes, poka-yoke version bumps

**Tasks**:
- [ ] Implement version validation
  - [ ] `cli/src/versioning/validate.rs` - Check content hash vs version
  - [ ] `cli/src/versioning/hash.rs` - BLAKE3 content hashing
  - [ ] Compare `.agentic-versions.json` with current file content
- [ ] Implement version bumping
  - [ ] `cli/src/versioning/bump.rs` - Auto-bump version
  - [ ] Interactive: prompt for patch/minor/major
  - [ ] Automated: `--patch`, `--minor`, `--major` flags
  - [ ] Update frontmatter + manifest + create git tag
- [ ] Create git pre-commit hook
  - [ ] Detect version mismatches before commit
  - [ ] Prompt user to fix or skip
  - [ ] Block commit if version inconsistent
- [ ] Add CLI commands
  - [ ] `agentic-p validate-versions` - Check all primitives
  - [ ] `agentic-p bump-version <file>` - Interactive bump
  - [ ] `agentic-p diff <file>` - Show changes since last version
  - [ ] `agentic-p install-hooks` - Install git hooks

**Files Created**:
- `cli/src/versioning/mod.rs`
- `cli/src/versioning/validate.rs`
- `cli/src/versioning/bump.rs`
- `cli/src/versioning/hash.rs`
- `cli/src/commands/validate_versions.rs`
- `cli/src/commands/bump_version.rs`
- `.git/hooks/pre-commit` (installed by CLI)

**Test Cases**:
```bash
# Test 1: Detect mismatch
vim commands/review.md  # Edit content
agentic-p validate-versions
# Expected: ⚠ Version mismatch detected

# Test 2: Interactive bump
agentic-p bump-version commands/review.md
# Expected: Prompt for patch/minor/major
# Updates version, hash, creates tag

# Test 3: Automated bump
agentic-p bump-version commands/review.md --minor
# Expected: Auto-bump 1.0.0 → 1.1.0

# Test 4: Git hook
vim commands/review.md
git add commands/review.md
git commit -m "update review"
# Expected: Hook detects mismatch, prompts to fix
```

---

### Milestone 2.2: Granular Install Commands
**Goal**: Install individual primitives

**Tasks**:
- [ ] Implement `install` subcommands
  - [ ] `agentic-p install command <name>`
  - [ ] `agentic-p install skill <name>`
  - [ ] `agentic-p install tool <name>`
- [ ] Add list operations
  - [ ] `agentic-p list` (available primitives)
  - [ ] `agentic-p list --installed` (what's in .claude/)
  - [ ] `agentic-p status command review` (check specific)
- [ ] Tool-level existence checks
  - [ ] Check `.mcp.json` for tool presence (not just file)
  - [ ] Skip if tool already configured

**Files Modified**:
- `cli/src/commands/install.rs` (new granular subcommands)
- `cli/src/commands/list.rs` (new)
- `cli/src/commands/status.rs` (new)

**Test Cases**:
```bash
# Install single command
agentic-p install command review
test -f .claude/commands/review.md

# Install single tool
agentic-p install tool docker-isolation
grep -q "docker-isolation" .claude/.mcp.json

# List available
agentic-p list commands
# Expected: review, commit, test, doc-scraper

# List installed
agentic-p list --installed
# Expected: Only installed primitives shown
```

---

### Milestone 2.3: Interactive Mode
**Goal**: User control over updates

**Tasks**:
- [ ] Implement interactive prompts
  - [ ] [u] Update (overwrite)
  - [ ] [s] Skip (keep existing)
  - [ ] [d] Diff (show changes with git diff)
  - [ ] [a] Update all remaining
  - [ ] [n] Skip all remaining
- [ ] Add colored output (using `colored` crate)
- [ ] Handle user input gracefully
  - [ ] Invalid choices → re-prompt
  - [ ] Ctrl+C → clean exit

**Files Created/Modified**:
- `cli/src/interactive.rs` (new)
- `cli/Cargo.toml` (add `colored`, `dialoguer` deps)

**Test Scenarios**:
```bash
# Interactive mode
agentic-p build --interactive

# User flow:
# 1. commands/review.md exists → prompt
# 2. User presses 'd' → show diff
# 3. User presses 'u' → update file
# 4. commands/commit.md exists → prompt
# 5. User presses 'a' → update all remaining (no more prompts)
```

---

## Phase 3: Documentation & Migration

### Milestone 3.1: ADR Review & Cleanup
**Goal**: Mark superseded ADRs, update index

**Tasks**:
- [ ] Review all ADRs in `docs/adrs/`
  - [ ] Mark v1-specific ADRs as superseded
  - [ ] Update status fields
  - [ ] Add superseded_by references
- [ ] Update ADR index
  - [ ] Note about removed ADRs (preserve numbers)
  - [ ] Link v1 → v2 migration ADRs
- [ ] Create migration ADR summary

**ADRs to Review**:
- [ ] ADR-001: Staged Bootstrap (keep or supersede?)
- [ ] ADR-002: Strict Validation (simplify for v2)
- [ ] ADR-004: Provider-Scoped Models (supersede - no provider abstraction)
- [ ] ADR-006: Middleware-Based Hooks (keep - still valid)
- [ ] ADR-007: Generated Provider Outputs (keep - now simpler)
- [ ] ADR-009: Versioned Primitives (supersede - git tags only)
- [ ] ADR-010: System-Level Versioning (keep)
- [ ] ADR-019: File Naming Convention (supersede - new conventions)
- [ ] ADR-020: Agentic Prompt Taxonomy (keep - still valid)
- [ ] ADR-021: Primitives Directory Structure (supersede - v2 structure)
- [ ] ADR-031: Tool Primitives (primary reference for v2)

**Files Modified**:
- `docs/adrs/*.md` (update status, add superseded_by)
- `docs/adrs/README.md` or index file (update with notes)

---

### Milestone 3.2: Update Documentation
**Goal**: Reflect v2 architecture

**Tasks**:
- [ ] Update README.md
  - [ ] New directory structure
  - [ ] Updated quick start
  - [ ] CLI command examples
- [ ] Update architecture docs
  - [ ] `docs/architecture.md`
  - [ ] `docs/getting-started.md`
- [ ] Update CLI reference
  - [ ] New commands (install, list, status)
  - [ ] New flags (--interactive, --force)
- [ ] Create migration guide
  - [ ] V1 → V2 guide for users
  - [ ] Breaking changes list
  - [ ] Step-by-step migration

**Files Modified**:
- `README.md`
- `docs/architecture.md`
- `docs/getting-started.md`
- `docs/cli-reference.md`
- `docs/v2-migration-guide.md` (new)

---

### Milestone 3.3: Worktree Management Primitive
**Goal**: Create reusable worktree command

**Tasks**:
- [ ] Create worktree management command
  - [ ] `commands/worktree-create.md`
  - [ ] Template for creating isolated worktrees
  - [ ] Standard path: `../<repo>_worktrees/<branch>/`
- [ ] Document worktree workflow
  - [ ] When to use worktrees
  - [ ] How to sync between worktrees
  - [ ] Cleanup after merge

**Files Created**:
- `commands/worktree-create.md`
- `docs/guides/worktree-workflow.md`

---

## Phase 4: Testing & Validation

### Milestone 4.1: Unit Tests
**Goal**: Test core build logic

**Tasks**:
- [ ] Test file existence logic
  - [ ] Fresh install (all create)
  - [ ] Idempotent (all skip)
  - [ ] Force (all update)
- [ ] Test transformations
  - [ ] Skills (flat → nested)
  - [ ] Commands (copy)
  - [ ] Tools (generate MCP)
- [ ] Test granular installs
  - [ ] Single command
  - [ ] Single skill
  - [ ] Single tool

**Files Created**:
- `cli/tests/test_build_simple.rs`
- `cli/tests/test_transforms.rs`
- `cli/tests/test_install.rs`

---

### Milestone 4.2: Integration Tests
**Goal**: End-to-end workflows

**Tasks**:
- [ ] Test fresh project setup
  ```bash
  mkdir test-project && cd test-project
  git init
  agentic-p build
  claude --plugin-dir .claude
  /review  # Should work
  ```
- [ ] Test update workflow
  ```bash
  # Update source
  cd agentic-primitives
  vim commands/review.md

  # Update in project
  cd ../test-project/agentic-primitives
  git pull
  agentic-p build  # Should skip unchanged
  ```
- [ ] Test downstream compatibility
  ```bash
  # Use in agentic engineering framework
  python -c "from agentic_isolation import DockerProvider"
  ```

**Files Created**:
- `cli/tests/integration/test_workflows.rs`
- `cli/tests/integration/test_downstream.rs`

---

## Phase 5: Polish & Release

### Milestone 5.1: Example Primitives
**Goal**: Show v2 format in action

**Tasks**:
- [ ] Convert 3-5 key primitives to v2
  - [ ] commands/review.md
  - [ ] commands/commit.md
  - [ ] skills/testing-expert.md
  - [ ] tools/firecrawl-scraper/
  - [ ] tools/docker-isolation/
- [ ] Ensure all work with Claude Code
- [ ] Add detailed comments/documentation

---

### Milestone 5.2: Release Preparation
**Goal**: Ready for merge to main

**Tasks**:
- [ ] Run full QA suite
  ```bash
  just qa
  just test
  ```
- [ ] Update CHANGELOG.md
  - [ ] V2.0.0 breaking changes
  - [ ] Migration guide link
- [ ] Tag release
  ```bash
  git tag v2.0.0
  git push --tags
  ```
- [ ] Create release notes

---

## Key Decisions

### Decision 1: Simple Versioning with Poka-Yoke
**Why**: Semver in frontmatter + content hash for change detection. Git hooks prevent version drift.
**How**: `.agentic-versions.json` tracks hash, CLI detects mismatches, pre-commit hook enforces
**Benefit**: Reproducible evals (version + hash), mistake-proofing, no manual hash management

### Decision 2: File Existence = Skip (for Installs)
**Why**: Simple, fast, predictable. User controls updates explicitly.
**Alternative**: Hash-based incremental updates (can add later if needed)

### Decision 3: Preserve V1 Build Output
**Why**: Downstream dependencies (agentic engineering framework) must keep working.
**Alternative**: Break downstream (unacceptable)

### Decision 4: Claude Code as Standard
**Why**: They defined standards early (skills, commands, agents).
**Alternative**: Invent our own (NIH syndrome)

### Decision 5: Version Manifest in Git
**Why**: `.agentic-versions.json` committed to repo (not gitignored). Enables CI validation, team coordination.
**Alternative**: Each developer tracks locally (inconsistent)

### Decision 6: Eval Results NOT in Primitives Repo
**Why**: Clean separation - primitives track versions, eval framework tracks results
**Alternative**: Store eval results in primitives (coupling, noise)

---

## Risk Mitigation

### Risk 1: Breaking Downstream Projects
**Mitigation**:
- Test build output structure matches v1
- Test Python imports unchanged
- Validation script in CI

### Risk 2: User Confusion (V1 → V2)
**Mitigation**:
- Clear migration guide
- Side-by-side support (v1 + v2)
- Examples and documentation

### Risk 3: Interactive Mode Complexity
**Mitigation**:
- Start with simple [u/s] only
- Add [d/a/n] later if needed
- Good error handling

---

## Success Metrics

- [ ] All tests passing
- [ ] V1 output structure preserved
- [ ] Python imports unchanged
- [ ] Idempotent installs working
- [ ] Interactive mode functional
- [ ] **Version tracking working** (auto-detect changes)
- [ ] **Git hooks installed** (prevent version drift)
- [ ] **Version manifest valid** (all hashes match)
- [ ] Documentation updated
- [ ] ADRs reviewed and updated
- [ ] Example primitives converted
- [ ] Downstream project tested (agentic engineering framework)
- [ ] **Eval framework can reference versions** (commands/review@2.1.0 + hash)

---

## Timeline Estimate

- **Phase 1**: 3-5 days (Foundation + simple versioning)
- **Phase 2**: 3-4 days (Version management + enhanced features)
- **Phase 3**: 2-3 days (Documentation)
- **Phase 4**: 2-3 days (Testing)
- **Phase 5**: 1-2 days (Polish)

**Total**: 11-17 days (~2-3 weeks)

**Note**: Versioning adds ~1 day but provides significant value for eval system.

---

## Notes

- **NEVER commit PROJECT-PLAN files** (per AGENTS.md)
- Use RIPER-5 mode transitions explicitly
- After each milestone: QA checkpoint (lint, format, test, review, commit)
- Follow conventional commits
- Test-driven development (tests first, then implement)

---

## Context Files to Reference

> **⚠️ IMPORTANT**: Some design documents were created in the main workspace during initial exploration. These need to be either:
> 1. Committed to main and pulled into worktree, OR
> 2. Referenced directly from main workspace at `/Users/codedev/Code/ai/agentic-primitives/`

### Design Documents (Created in Main Workspace)
**Location**: `/Users/codedev/Code/ai/agentic-primitives/`

- `docs/v2-architecture-design.md` - Complete v2 design (NOT YET IN WORKTREE)
- `docs/adrs/031-tool-primitives-auto-generated-adapters.md` - Core ADR (NOT YET IN WORKTREE)
- `V2-DESIGN-COMPLETE.md` - Quick reference (NOT YET IN WORKTREE)
- `docs/v2-implementation-status.md` - Status tracker (NOT YET IN WORKTREE)
- `docs/deps/unknown/claude-code@latest-20260113.md` - Claude plugin format (NOT YET IN WORKTREE)
- `docs/deps/python/fastmcp@latest-20260113.md` - FastMCP patterns (NOT YET IN WORKTREE)
- `schemas/tool-spec.v1.json` - Tool specification schema (NOT YET IN WORKTREE)

**To access these**: Either view from main workspace or commit them:
```bash
# In main workspace
cd /Users/codedev/Code/ai/agentic-primitives
git add docs/v2-architecture-design.md docs/adrs/031-* V2-DESIGN-COMPLETE.md docs/v2-implementation-status.md docs/deps/ schemas/
git commit -m "docs: add v2 design and planning documentation"

# In worktree
cd /Users/codedev/Code/ai/agentic-primitives_worktrees/v2-simplification
git pull origin main
```

### Current Structure (V1) - Available in Worktree
- `/primitives/v1/` - Current primitive structure
- `/lib/python/` - Python libraries (DO NOT REFACTOR)
- `/cli/` - Current CLI implementation
- `/.claude/` - Current build output example

### Workflow Standards - Available in Worktree
- `/AGENTS.md` - RIPER-5 protocol ✅
- `/justfile` - QA commands ✅

### Files Created in This Worktree
- `PROJECT-PLAN_20260113_v2-simplification.md` - This file ✅
- `V2-WORKTREE-README.md` - Quick start guide ✅
- `.context-docs/README.md` - Context reference ✅

---

## Version Tracking Implementation Details

### .agentic-versions.json Format
```json
{
  "schema_version": "1.0.0",
  "primitives": {
    "commands/review.md": {
      "version": "2.2.0",
      "content_hash": "blake3:def456...",
      "last_updated": "2026-01-14T10:30:00Z"
    }
  }
}
```

### Primitive Frontmatter Format
```markdown
---
id: review
version: 2.2.0
last_updated: 2026-01-14

dependencies:
  skills: [testing-expert@1.5.0]

changelog:
  - version: 2.2.0
    date: 2026-01-14
    changes: |
      - Added security checks
      - Improved formatting
---
```

### CLI Commands for Versioning
```bash
# Check version consistency
agentic-p validate-versions

# Bump version (interactive)
agentic-p bump-version commands/review.md

# Bump version (automated)
agentic-p bump-version commands/review.md --minor

# Show what changed
agentic-p diff commands/review.md

# Install git hooks
agentic-p install-hooks
```

---

**Ready for EXECUTE mode once approved.**
