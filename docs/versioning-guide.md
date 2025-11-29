# Versioning Guide

This guide explains the complete versioning strategy for agentic primitives, covering both **system-level** and **prompt-level** versioning.

## Table of Contents

1. [Overview](#overview)
2. [System-Level Versioning](#system-level-versioning)
3. [Prompt-Level Versioning](#prompt-level-versioning)
4. [How They Work Together](#how-they-work-together)
5. [CLI Commands](#cli-commands)
6. [Workflows](#workflows)
7. [Best Practices](#best-practices)
8. [FAQ](#faq)

---

## Overview

The agentic primitives repository uses **two independent versioning systems**:

| Layer | Scope | Purpose | Example |
|-------|-------|---------|---------|
| **System-Level** | Entire architecture | Structural evolution | v1 (generic) → v2 (Claude-specific) |
| **Prompt-Level** | Individual primitive content | Content refinement | `prompt.v1.md` → `prompt.v2.md` |

### Why Two Layers?

- **System-level versioning**: Allows us to change *how primitives are organized* without breaking existing work
- **Prompt-level versioning**: Allows us to refine *individual primitive content* with hash-verified immutability

Both are necessary for a system that evolves gracefully over time.

---

## System-Level Versioning

### What Is It?

System-level versioning represents **architectural changes** to the primitive system itself. When the fundamental structure needs to change, we create a new version.

### When to Use

Create a new system version when you need to:

- Change the directory structure of primitives
- Modify metadata schema significantly
- Pivot to a provider-specific format (e.g., Claude Code commands)
- Introduce new primitive types with different organization
- Make any change that would require refactoring existing primitives

### Directory Structure

```
/specs/
  v1/                          # v1 schemas
    prompt-meta.schema.json
    tool-meta.schema.json
    ...
  v2/                          # Future: v2 schemas
    ...

/primitives/
  v1/                          # v1 primitives
    prompts/...
    tools/...
    hooks/...
  v2/                          # Future: v2 primitives
    ...
  experimental/                # Sandbox for testing
    ...
```

### Current Version: v1

**Status**: Active  
**Structure**: Generic provider-agnostic primitives  
**Directory**: `/primitives/v1/`  
**Schemas**: `/specs/v1/`  

**Characteristics**:
- Organized by type (`prompts`, `tools`, `hooks`)
- Then by category (user-defined, e.g., `python`, `review`)
- Then by ID (`python-pro`, `code-reviewer`)
- Generic metadata format in `meta.yaml`
- Provider adapters transform to specific formats

### Future: v2 (Example)

**Status**: Not yet defined  
**Potential Structure**: Claude Code-specific  
**Directory**: `/primitives/v2/` (when created)  

**Potential Characteristics**:
- Organized by Claude conventions (`commands/`, `system-prompts/`)
- Native `.claude/` format
- Different metadata schema
- Optimized for Claude's workflow

### Experimental Workspace

**Location**: `/primitives/experimental/`  
**Purpose**: Sandbox for testing v2+ architectural ideas  
**Rules**:
- Can break at any time
- No stability guarantees
- Free-form structure
- Promote to v2 when ready

See `/primitives/experimental/README.md` for detailed workflow.

### CLI Usage

```bash
# Validate v1 primitive (default)
agentic-p validate primitives/v1/prompts/agents/python/python-pro

# Explicit v1
agentic-p validate --spec-version v1 primitives/v1/prompts/...

# Validate experimental
agentic-p validate --spec-version experimental primitives/experimental/my-test

# Future: v2
agentic-p validate --spec-version v2 primitives/v2/...
```

### Declaring System Version

Every primitive's `meta.yaml` declares its system version:

```yaml
id: python-pro
kind: agent
spec_version: "v1"    # System-level version
category: python
# ... rest of metadata
```

---

## Prompt-Level Versioning

### What Is It?

Prompt-level versioning tracks **content iterations** of individual primitives. Each version is a refinement of the prompt text, with BLAKE3 hash verification for immutability.

### When to Use

Bump the prompt version when you:

- Improve the prompt wording
- Add new instructions or examples
- Fix issues with prompt output
- Refine the persona or style
- Want to A/B test different approaches

**Do NOT bump** when:
- Changing metadata (tags, domain, etc.) - just edit `meta.yaml`
- Fixing typos in metadata
- Updating documentation

### File Structure

```
primitives/v1/prompts/agents/python/python-pro/
  ├── prompt.v1.md       # Version 1 content (immutable)
  ├── prompt.v2.md       # Version 2 content (immutable)
  ├── prompt.v3.md       # Version 3 content (immutable)
  └── meta.yaml          # Metadata with versions array
```

### Metadata Structure

```yaml
id: python-pro
kind: agent
spec_version: "v1"
category: python
domain: python
summary: "Expert Python engineer..."

# Versions array (prompt-level)
versions:
  - version: 1
    status: deprecated
    hash: "blake3:abc123..."
    created: "2025-11-01"
  - version: 2
    status: active
    hash: "blake3:def456..."
    created: "2025-11-10"
  - version: 3
    status: draft
    hash: "blake3:ghi789..."
    created: "2025-11-13"
```

### Version Status

| Status | Meaning | Usage |
|--------|---------|-------|
| `draft` | Work in progress | Can be edited, not for production |
| `active` | Production-ready | Immutable, used by default |
| `deprecated` | Superseded | Still works, but not recommended |

**Rules**:
- At least one `active` version must exist
- Multiple `active` versions allowed (for A/B testing)
- Hash must match file content (enforced by validation)

### Immutability via BLAKE3

Each version file is hashed with BLAKE3 for:
- **Fast verification**: BLAKE3 is extremely fast
- **Content integrity**: Detect any tampering
- **Reproducibility**: Same content = same hash
- **Benchmarking**: Compare exact versions over time

The CLI verifies hashes during validation:
```bash
agentic-p validate primitives/v1/prompts/agents/python/python-pro
# ✅ Version 1 hash verified: blake3:abc123...
# ✅ Version 2 hash verified: blake3:def456...
```

### CLI Usage

#### List Versions

```bash
agentic-p version list primitives/v1/prompts/agents/python/python-pro
```

Output:
```
Versions for python-pro:
  v1  deprecated  blake3:abc123...  2025-11-01
  v2  active      blake3:def456...  2025-11-10
  v3  draft       blake3:ghi789...  2025-11-13
```

#### Bump Version

```bash
agentic-p version bump primitives/v1/prompts/agents/python/python-pro
```

This:
1. Finds highest version (e.g., v3)
2. Creates `prompt.v4.md` (copy of v3 as starting point)
3. Adds v4 entry to `meta.yaml` (status: draft)
4. Calculates BLAKE3 hash
5. Opens editor for you to modify content

#### Promote Version

```bash
agentic-p version promote primitives/v1/prompts/agents/python/python-pro 3
```

This:
1. Verifies v3 hash matches file
2. Changes status: `draft` → `active`
3. Optionally deprecates previous active version

#### Deprecate Version

```bash
agentic-p version deprecate primitives/v1/prompts/agents/python/python-pro 1
```

This:
1. Changes status: `active` → `deprecated`
2. Ensures at least one `active` version remains

---

## How They Work Together

### Example: Evolution of a Python Agent

#### Step 1: Initial Creation (v1 system, v1 prompt)

```
primitives/v1/prompts/agents/python/python-pro/
  ├── prompt.v1.md       # System v1, Prompt v1
  └── meta.yaml          # spec_version: "v1", versions: [1:active]
```

#### Step 2: Improve Prompt Content (v1 system, v2 prompt)

```bash
agentic-p version bump primitives/v1/prompts/agents/python/python-pro
# Edit prompt.v2.md
agentic-p version promote primitives/v1/prompts/agents/python/python-pro 2
```

```
primitives/v1/prompts/agents/python/python-pro/
  ├── prompt.v1.md       # Deprecated
  ├── prompt.v2.md       # Active
  └── meta.yaml          # spec_version: "v1", versions: [1:deprecated, 2:active]
```

**Same system version (v1), new prompt version (v2).**

#### Step 3: Architectural Shift (v2 system, v1 prompt)

Decide v1 generic structure isn't ideal for Claude. Create v2:

```
primitives/v2/commands/python-scaffold/
  ├── command.v1.md      # System v2, Prompt v1 (first version in new system)
  └── meta.yaml          # spec_version: "v2"
```

**New system version (v2), starts at prompt version 1 again.**

### Key Insight

The two versioning systems are **independent**:
- You can bump prompt versions within v1 system
- You can migrate to v2 system and start prompt versions fresh
- v1 primitives keep their prompt versions intact

---

## CLI Commands

### System-Level Commands

```bash
# Validate with specific system version
agentic-p validate --spec-version v1 <path>
agentic-p validate --spec-version experimental <path>

# Build for provider (uses system version)
agentic-p build --provider claude --spec-version v1

# Create new primitive (outputs to version directory)
agentic-p new agent python python-pro --spec-version v1
```

### Prompt-Level Commands

```bash
# List prompt versions
agentic-p version list <primitive-path>

# Bump to new prompt version
agentic-p version bump <primitive-path>

# Promote draft to active
agentic-p version promote <primitive-path> <version>

# Deprecate old version
agentic-p version deprecate <primitive-path> <version>

# Validate hash integrity
agentic-p validate <primitive-path>  # Checks hashes
```

### Per-Project Configuration

Consumer projects can pin specific versions using `agentic.yaml`:

```bash
# Generate config template (all options commented like tsconfig)
agentic-p config init

# Show current configuration
agentic-p config show

# List available primitives for pinning
agentic-p config list
```

Example `agentic.yaml` (only specify overrides):

```yaml
version: "1.0"

# Override versions like npm resolutions
primitives:
  qa/review: 1              # Pin to v1
  qa/pre-commit-qa: latest  # Always use default_version
  core/prompt-generator:
    enabled: false          # Exclude from build

exclude:
  - meta-prompts/*          # Exclude entire category
```

### Migration Commands (Future)

```bash
# Migrate primitive from v1 to v2 system
agentic-p migrate spec v1 v2 <primitive-path>
```

---

## Workflows

### Workflow 1: Refining a Prompt

**Goal**: Improve an existing primitive's content.

```bash
# 1. Bump version
agentic-p version bump primitives/v1/prompts/agents/python/python-pro

# 2. Edit the new version file
vim primitives/v1/prompts/agents/python/python-pro/prompt.v3.md

# 3. Test the new version
agentic-p build --provider claude primitives/v1/prompts/agents/python/python-pro
# Use the built output to test

# 4. If good, promote
agentic-p version promote primitives/v1/prompts/agents/python/python-pro 3

# 5. Validate
agentic-p validate primitives/v1/prompts/agents/python/python-pro
```

### Workflow 2: Experimenting with v2 Architecture

**Goal**: Test a radical new structure without risk.

```bash
# 1. Create experimental primitive
mkdir -p primitives/experimental/v2-claude-commands/python-scaffold
cat > primitives/experimental/v2-claude-commands/python-scaffold/command.md <<EOF
# Python Scaffold Command
... new format ...
EOF

# 2. Test with experimental flag
agentic-p validate --spec-version experimental primitives/experimental/v2-claude-commands

# 3. Iterate freely (can break, change, delete)
# ... make changes ...

# 4. When stable, promote to v2
# - Create /specs/v2/
# - Create /primitives/v2/
# - Move experimental primitives to v2
# - Implement v2 validators
```

### Workflow 3: Migrating from v1 to v2

**Goal**: Move a primitive to new system version.

```bash
# Future command (not yet implemented)
agentic-p migrate spec v1 v2 primitives/v1/prompts/agents/python/python-pro

# This would:
# 1. Read v1 primitive
# 2. Transform to v2 structure
# 3. Write to primitives/v2/
# 4. Preserve prompt version history
```

### Workflow 4: A/B Testing Two Prompt Versions

**Goal**: Compare performance of two prompt versions.

```bash
# 1. Create version 3 as alternative approach
agentic-p version bump primitives/v1/prompts/agents/python/python-pro
vim primitives/v1/prompts/agents/python/python-pro/prompt.v3.md

# 2. Promote both v2 and v3 to active
agentic-p version promote primitives/v1/prompts/agents/python/python-pro 3

# 3. Both versions are now active
# Build and test each
agentic-p build --provider claude primitives/v1/prompts/agents/python/python-pro --version 2
agentic-p build --provider claude primitives/v1/prompts/agents/python/python-pro --version 3

# 4. After testing, deprecate the losing version
agentic-p version deprecate primitives/v1/prompts/agents/python/python-pro 2
```

### Workflow 5: Creating a New Primitive

**Goal**: Add a new primitive from scratch.

```bash
# 1. Create new primitive in v1
agentic-p new agent rust rust-expert --spec-version v1

# This creates:
# primitives/v1/prompts/agents/rust/rust-expert/
#   ├── prompt.v1.md
#   └── meta.yaml (with spec_version: "v1")

# 2. Edit the content
vim primitives/v1/prompts/agents/rust/rust-expert/prompt.v1.md

# 3. Validate
agentic-p validate primitives/v1/prompts/agents/rust/rust-expert

# 4. Promote to active
agentic-p version promote primitives/v1/prompts/agents/rust/rust-expert 1

# 5. Build for provider
agentic-p build --provider claude primitives/v1/prompts/agents/rust/rust-expert
```

---

## Best Practices

### System-Level Versioning

1. **Don't create v2 prematurely** - Experiment first in `/primitives/experimental/`
2. **Document architectural decisions** - Write ADRs for version changes
3. **Support multiple versions** - v1 and v2 should coexist during transition
4. **Avoid version churn** - System versions are heavyweight, use sparingly
5. **Clear migration paths** - Document how to move from v1 to v2
6. **Backwards compatibility** - Ensure v1 primitives keep working

### Prompt-Level Versioning

1. **Bump versions for meaningful changes** - Not for typos in metadata
2. **Always hash verify** - Run `agentic-p validate` before promoting
3. **Keep at least one active** - Never deprecate all versions
4. **Use draft liberally** - Iterate in draft, promote when ready
5. **Document changes** - Add comments in prompt explaining version differences
6. **Test before promoting** - Build and test draft versions thoroughly

### Combined Strategy

1. **Most changes = prompt-level** - Default to refining content, not restructuring
2. **System-level = rare** - Only when architecture fundamentally needs to change
3. **Experiment first** - Test radical ideas in `/experimental/` before committing to v2
4. **Gradual migration** - Don't force immediate v1 → v2 migration, let them coexist
5. **Version independence** - Remember system and prompt versions are separate concerns

### Metadata Management

1. **Declare spec_version explicitly** - Every `meta.yaml` must have `spec_version: "v1"`
2. **Keep versions array updated** - CLI manages this, but review regularly
3. **Meaningful version notes** - Add notes explaining what changed in each version
4. **Consistent categorization** - Keep category names consistent across versions
5. **Tag appropriately** - Use tags to help discover related primitives

---

## FAQ

### Q: When should I create a new system version (v2)?

**A**: Only when the current structure (v1) fundamentally doesn't work anymore. Examples:
- "Generic prompts don't map well to Claude Code commands"
- "Tool organization needs complete overhaul"
- "Metadata schema needs breaking changes"

If you're just improving a prompt, that's prompt-level versioning (v1 → v2 within same system).

### Q: Can I have both v1 and v2 primitives at the same time?

**A**: Yes! That's the whole point. During transition:
- Some primitives stay in v1
- Some primitives move to v2
- Both work fine
- CLI routes based on `--spec-version`

### Q: What happens to prompt versions when I migrate to v2?

**A**: Ideally, they migrate with the primitive:
```
v1: python-pro with prompt.v1.md, prompt.v2.md, prompt.v3.md
↓
v2: python-pro with prompt.v1.md, prompt.v2.md, prompt.v3.md
```

But this is up to the migration tool. You might start fresh at v1 in the new system.

### Q: Do I need to hash prompt files myself?

**A**: No, the CLI does it automatically:
```bash
agentic-p version bump <path>   # Calculates hash
agentic-p version promote <path> <version>  # Verifies hash
```

### Q: Can I edit an `active` prompt version?

**A**: No, `active` versions are immutable (enforced by hash check). To change:
1. Bump to new version
2. Edit the new version
3. Promote the new version
4. Optionally deprecate the old version

### Q: What's in `/primitives/experimental/`?

**A**: Whatever you want! It's a free-form sandbox. Common uses:
- Testing v2 architectural ideas
- Prototyping new primitive types
- Experimenting with metadata formats
- Trying provider-specific structures

See `/primitives/experimental/README.md`.

### Q: How does validation differ for experimental?

**A**: More lenient:
```bash
agentic-p validate --spec-version v1 <path>
# ✅ Structural, schema, semantic validation

agentic-p validate --spec-version experimental <path>
# ✅ Structural validation only
# ⚠️  Schema and semantic skipped
```

### Q: What if I want to go back to an old prompt version?

**A**: Just promote it again:
```bash
agentic-p version promote <path> 1  # Reactivate version 1
```

Multiple versions can be `active` simultaneously for A/B testing.

### Q: How do I know which system version a primitive uses?

**A**: Check the `meta.yaml` file:
```yaml
spec_version: "v1"  # This primitive uses v1 structure
```

Or look at the directory path:
```
primitives/v1/...    # v1 primitive
primitives/v2/...    # v2 primitive
```

### Q: Can I mix v1 and v2 primitives in the same project?

**A**: Yes! The CLI handles routing:
```bash
# Build both v1 and v2 primitives
agentic-p build --provider claude primitives/v1/prompts/agents/python/python-pro
agentic-p build --provider claude primitives/v2/commands/rust-expert
```

### Q: What happens if I don't specify --spec-version?

**A**: The CLI defaults to v1:
```bash
agentic-p validate primitives/v1/prompts/...
# Same as: agentic-p validate --spec-version v1 primitives/v1/prompts/...
```

### Q: Should I version tools and hooks?

**A**: It depends:
- **Agents, commands, meta-prompts**: Versioning required (Tier 1)
- **Skills, tools, hooks**: Versioning optional (Tier 2)

For Tier 2, you can use versioning if you want to track iterations, but it's not mandatory.

### Q: How do providers handle different system versions?

**A**: Each provider has transformers for each system version:
```
providers/claude/
  v1-transformer/    # Transforms v1 primitives
  v2-transformer/    # Transforms v2 primitives (future)
```

The CLI routes to the appropriate transformer based on `spec_version`.

### Q: What's the difference between `deprecated` and `archived` status?

**A**: 
- **deprecated**: Still works, but not recommended (e.g., old version superseded)
- **archived**: No longer maintained or supported (e.g., removed feature)

Use `deprecated` for normal version lifecycle, `archived` for discontinued primitives.

### Q: Can I delete old prompt versions?

**A**: Technically yes, but not recommended:
- Old versions provide history
- Useful for debugging regressions
- Enable rollback if new version has issues
- Disk space is cheap

Only delete if absolutely necessary (e.g., contained sensitive data).

---

## References

- **ADR 010**: System-Level Versioning
- **ADR 009**: Versioned Primitives (Prompt-Level)
- `primitives.config.yaml`: Configuration file with `spec_version`
- `/primitives/experimental/README.md`: Experimental workflow details
- `docs/architecture.md`: Overall system architecture

---

## Appendix: Version Lifecycle

### System Version Lifecycle

```
[Planning] → [Experimental] → [Stable] → [Legacy] → [Archived]
     ↓             ↓             ↓           ↓          ↓
  Discussing   Testing in   Active use   Superseded  Removed
  ideas        /experimental             by v2
```

### Prompt Version Lifecycle

```
[Draft] → [Active] → [Deprecated] → [Archived]
   ↓         ↓            ↓              ↓
Creating  Production  Superseded    Discontinued
```

### Timeline Example

```
2025-11:  v1 created (active)
          python-pro prompt.v1 (active)

2025-12:  python-pro prompt.v2 (active, v1 deprecated)

2026-01:  v2 experimental testing begins

2026-03:  v2 stabilized, becomes active
          v1 remains active (legacy support)

2026-06:  New primitives use v2
          v1 primitives optionally migrate

2027-01:  v1 archived (no new primitives)
          Existing v1 primitives still work
```

---

**Last Updated**: 2025-11-13  
**Applies To**: v1 primitives and future versions

