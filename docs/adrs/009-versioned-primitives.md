---
title: "ADR-009: Versioned Primitives with Hash Validation"
status: accepted
created: 2025-11-13
updated: 2025-11-13
author: Neural
---

# ADR-009: Versioned Primitives with Hash Validation

## Status

**Accepted**

- Created: 2025-11-13
- Updated: 2025-11-13
- Author(s): Neural

## Context

As the agentic-primitives repository evolves, primitives (agents, commands, meta-prompts) will need updates for various reasons:

- **Behavior improvements**: Better prompting techniques discovered
- **Output format changes**: Structured JSON instead of plain text
- **Interface changes**: New inputs, different outputs
- **Performance optimizations**: More efficient token usage
- **Personality adjustments**: Different interaction styles

### Problems with In-Place Updates

Without versioning, updating a primitive in place causes issues:

1. **Breaking changes**: Users depending on specific behavior get unexpected results
2. **Lost history**: No way to compare old vs new approaches
3. **No rollback**: Can't revert to known-good version
4. **Silent breakage**: Edits without intent to change behavior
5. **No benchmarking**: Can't compare efficiency/quality across iterations

### The Benchmarking Use Case

A critical requirement is **comparing primitive versions**:

- Run same task with v1, v2, v3 of an agent
- Measure: token usage, execution time, output quality, success rate
- Prove: "v2 is 30% more efficient than v1"
- Choose: Best version for specific use cases

This requires **immutable versions** with clear history.

## Decision

We will implement a **versioning system** for primitives with three tiers:

### Tier 1: Required Versioning (Strict Immutability)
- **Agents**: User-facing personas with specific behaviors
- **Commands**: Task workflows with defined inputs/outputs
- **Meta-prompts**: Generators that create other primitives

These MUST use versioned files with hash validation.

### Tier 2: Optional Versioning (Flexible)
- **Skills**: Knowledge overlays (can version if they evolve significantly)
- **Tools**: Capability primitives (version on breaking interface changes)
- **Hooks**: Lifecycle events (version on breaking behavior changes)

These MAY use versioned files or single-file format.

### File Structure

```
prompts/agents/python-pro/
├── python-pro.prompt.v1.md    # Version 1 content (immutable)
├── python-pro.prompt.v2.md    # Version 2 content (immutable)
├── python-pro.prompt.v3.md    # Version 3 content (can edit if draft)
└── python-pro.meta.yaml       # Version registry + shared metadata

prompts/skills/async-patterns/
├── async-patterns.prompt.md   # Unversioned (implicit v1)
└── async-patterns.meta.yaml   # OR use versioning if needed
```

### Meta.yaml Version Registry

```yaml
id: python-pro
kind: agent
domain: python
summary: "Expert Python engineer for architecture and debugging"

# Version registry (REQUIRED for Tier 1 primitives)
versions:
  - version: 1
    file: python-pro.prompt.v1.md
    status: deprecated
    hash: blake3:abc123def456...
    created: 2025-01-15
    deprecated: 2025-06-01
    notes: "Original version. Verbose responses, good for learning."
    
  - version: 2
    file: python-pro.prompt.v2.md
    status: active
    hash: blake3:789ghi012jkl...
    created: 2025-06-01
    notes: "Concise responses, better examples. 30% fewer tokens."
    
  - version: 3
    file: python-pro.prompt.v3.md
    status: draft
    hash: blake3:345mno678pqr...
    created: 2025-11-01
    notes: "Testing Socratic teaching style for juniors."

# Default version (latest 'active' status)
default_version: 2

# Shared metadata (applies to all versions unless overridden)
tags: [python, backend, architecture]
defaults:
  preferred_models: [claude/sonnet, openai/gpt-codex]
context_usage:
  as_system: true
tools: [run-tests, search-code]
```

### Hash Validation

Use **BLAKE3** for content hashing:
- Fast (faster than SHA256, comparable to xxHash)
- Cryptographically secure (unlike xxHash)
- Trusted dependency (used by many Rust projects)
- 256-bit output (same security as SHA256)

**Validation flow**:
1. CLI calculates BLAKE3 hash of `.prompt.vN.md` content
2. Compares to stored `hash` in meta.yaml
3. If mismatch and status is `active` or `deprecated`:
   - **ERROR**: "Content modified but version not bumped. Create new version with 'agentic version bump'."
4. If mismatch and status is `draft`:
   - **AUTO-UPDATE**: Update hash in meta.yaml (drafts can be edited)
5. If match:
   - **PASS**: Content is immutable

### Version Status Lifecycle

```
draft → active → deprecated → archived
  ↓       ↓
  └───────┴──→ Can create new draft at any time
```

**Status meanings**:
- `draft`: Work in progress, hash can change, not for production
- `active`: Stable, recommended, **immutable** (hash enforced)
- `deprecated`: Still works, but not recommended, **immutable**
- `archived`: No longer maintained, use at own risk, **immutable**

### Version Selection

**Default behavior** (no version specified):
- Use latest `active` version
- If no active, use latest `draft` (with warning)

**Explicit version selection** (using `@vN` syntax):
```bash
# Build with specific version
agentic build --provider claude --agent python-pro@v1

# Inspect specific version
agentic inspect python-pro@v2

# Benchmark multiple versions
agentic benchmark python-pro@v1 python-pro@v2 python-pro@v3

# In meta.yaml references
dependencies:
  agents:
    - python-pro@v1  # Pin to specific version
    - code-reviewer  # Use default (latest active)
```

### Migration Strategy

Existing primitives without versions automatically become v1:

```bash
# Before migration
prompts/agents/python-pro/
├── prompt.md
└── meta.yaml

# After migration (automatic)
prompts/agents/python-pro/
├── python-pro.prompt.v1.md  # Renamed from prompt.md
└── python-pro.meta.yaml     # Updated with version registry
```

CLI command: `agentic migrate --add-versions`

## Alternatives Considered

### Alternative 1: Git-Based Versioning Only

**Description**: Rely purely on git tags/commits for versions, no file-level versioning

**Pros**:
- Simple, uses existing tooling
- No duplicate files
- Full git history available

**Cons**:
- Hard to use multiple versions simultaneously
- Benchmarking requires git checkouts
- No easy way to mark status (active/deprecated)
- Provider builds can't include multiple versions

**Reason for rejection**: Benchmarking use case requires multiple versions available simultaneously in one repo

### Alternative 2: Semantic Versioning in Meta.yaml Only

**Description**: Keep single `prompt.md` file, track versions in meta.yaml with git references

```yaml
versions:
  - version: 1.0.0
    git_commit: abc123
    status: deprecated
  - version: 2.0.0
    git_commit: def456
    status: active
```

**Pros**:
- No file duplication
- Standard semver format
- Git provides content

**Cons**:
- Still requires git operations to access old versions
- Can't easily diff versions side-by-side
- Provider builds complicated
- No hash validation without git

**Reason for rejection**: Makes versioned access too complex, defeats benchmarking purpose

### Alternative 3: Separate Version Branches

**Description**: Create git branches for each major version (`v1`, `v2`, `v3`)

**Pros**:
- Clear separation
- Git tooling handles it
- Can maintain old versions

**Cons**:
- Branch management overhead
- Hard to compare versions
- Can't build multiple versions at once
- Merging improvements across versions is painful

**Reason for rejection**: Too heavyweight, makes simultaneous version access impossible

### Alternative 4: SHA256 for Hashing

**Description**: Use SHA256 instead of BLAKE3

**Pros**:
- More widely known
- Built into many systems
- Cryptographically proven

**Cons**:
- Slower than BLAKE3 (matters for large repos)
- No real security advantage for our use case

**Reason for rejection**: BLAKE3 is faster with same security, better developer experience

## Consequences

### Positive Consequences

1. **Immutability**: Once a version is active, it never changes unexpectedly
2. **Benchmarking**: Easy to compare efficiency and quality across versions
3. **Rollback**: Always can revert to known-good version
4. **History**: Clear evolution of primitive behavior over time
5. **Selective upgrades**: Users choose when to adopt new versions
6. **Parallel testing**: Run multiple versions side-by-side
7. **Fast validation**: BLAKE3 hashing is very fast
8. **Trusted hashing**: BLAKE3 is cryptographically secure

### Negative Consequences

1. **File duplication**: Multiple `.prompt.vN.md` files in same directory
2. **Storage overhead**: Repository size grows with versions (mitigated by git compression)
3. **Complexity**: Users must understand versioning system
4. **Breaking changes**: Creating new version is more ceremony than editing in place
5. **Coordination**: Teams must agree on when to bump versions

### Neutral Consequences

1. **More files**: Directory listings are longer (can be mitigated with tooling)
2. **Meta.yaml size**: Version registry adds lines (but under 500 line ADR limit)
3. **CLI surface area**: New commands needed (`version bump`, `version list`, etc.)

## Implementation Notes

### Rust Dependencies

Add to `cli/Cargo.toml`:
```toml
blake3 = "1.5"  # Fast, secure hashing
```

### CLI Commands

**New version management commands**:

```bash
# Create new version (auto-increments)
agentic version bump <primitive-path> \
  --notes "Improved efficiency by 30%" \
  --status draft

# List versions
agentic version list <primitive-id>
# Output:
# v1: deprecated (2025-01-15 → 2025-06-01) "Original version"
# v2: active (2025-06-01 → present) ← default "Concise responses"
# v3: draft (2025-11-01 → present) "Socratic style"

# Promote draft to active
agentic version promote <primitive-id> --version 3

# Deprecate old version
agentic version deprecate <primitive-id> --version 1

# Validate all hashes
agentic validate --check-hashes
# Errors if any active/deprecated version has hash mismatch

# Migrate existing primitives to versioned format
agentic migrate --add-versions

# Benchmark versions
agentic benchmark <primitive-id> --versions v1,v2,v3 \
  --task "Implement binary search" \
  --metrics tokens,time,quality
```

### File Operations

**Creating new version**:
1. Find highest version number in meta.yaml
2. Create `<name>.prompt.v{N+1}.md` with template or copy of latest
3. Add entry to meta.yaml versions array with status: draft
4. Calculate BLAKE3 hash, store in meta.yaml
5. Set as default_version if promoting to active

**Editing version**:
1. Check status in meta.yaml
2. If `draft`: Allow edit, auto-update hash on save
3. If `active` or `deprecated` or `archived`: Block edit, suggest `version bump`

**Validation**:
1. For each version entry in meta.yaml:
2. Read corresponding `.prompt.vN.md` file
3. Calculate BLAKE3 hash
4. Compare to stored hash
5. If mismatch and not draft: ERROR
6. If mismatch and draft: UPDATE hash in meta.yaml

### Validation Rules

**Structural validation** must check:
- Tier 1 primitives (agents, commands, meta-prompts) MUST have `versions` array
- Each version entry MUST have: version, file, status, hash, created, notes
- Each versioned file MUST exist
- Folder name MUST equal primitive ID
- At most one version can have status: active (or none if all deprecated)
- default_version MUST point to an active version (or latest draft if no active)

**Hash validation**:
- Run with `--check-hashes` flag
- For all non-draft versions, verify hash matches file content
- Fail if any mismatch

### Migration Implementation

```rust
// In cli/src/commands/migrate.rs
pub fn migrate_to_versioned(primitive_path: &Path) -> Result<()> {
    // 1. Read existing meta.yaml
    // 2. Check if already versioned (has 'versions' array)
    // 3. If not versioned:
    //    a. Rename prompt.md → <name>.prompt.v1.md
    //    b. Calculate hash
    //    c. Add versions array to meta.yaml with v1 entry
    //    d. Set default_version: 1
    //    e. Write updated meta.yaml
}
```

### Version Selection in Provider Builds

```rust
// When building for provider
pub fn resolve_version(primitive_id: &str) -> Result<u32> {
    let (id, version) = parse_version_ref(primitive_id)?;
    // "python-pro@v2" → ("python-pro", Some(2))
    // "python-pro" → ("python-pro", None)
    
    if let Some(v) = version {
        return Ok(v);
    }
    
    // Use default_version from meta.yaml
    let meta = load_meta(&id)?;
    Ok(meta.default_version)
}
```

## References

- [BLAKE3 Official Site](https://github.com/BLAKE3-team/BLAKE3) - Fast, secure hashing algorithm
- [Semantic Versioning](https://semver.org/) - Versioning inspiration (though we use simple integers)
- [Git Tags](https://git-scm.com/book/en/v2/Git-Basics-Tagging) - Alternative approach we rejected
- ADR-000: ADR Template - Standardized structure and length guidelines
- ADR-002: Strict Validation - Hash validation fits our strict validation philosophy
- ADR-008: Test-Driven Development - Versioning enables benchmarking and testing

---

**Implementation Priority**: High (Milestone 5-6)
**Estimated Effort**: 2-3 milestones
**Breaking Change**: No (new feature, backward compatible via migration)

