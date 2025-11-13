---
id: 010
title: System-Level Versioning
status: accepted
created: 2025-11-13
updated: 2025-11-13
---

# ADR 010: System-Level Versioning

## Context

The agentic primitives repository needs to evolve its architecture over time without breaking existing primitives. We already have prompt-level versioning (ADR 009) for content iterations, but we lack a mechanism for architectural/structural evolution.

### Problem

Currently, if we need to make fundamental changes to how primitives are organized:
- Moving from generic prompts to provider-specific structures (e.g., Claude Code commands)
- Changing tool or hook organization
- Restructuring metadata schemas

...we would need to refactor the entire repository, potentially breaking all existing primitives and requiring 1-2 weeks of work.

### Analysis Paralysis

This architectural rigidity creates fear of making the "wrong" choice early, leading to analysis paralysis. We need a way to make architectural decisions that are **revisable** without catastrophic refactoring.

## Decision

We implement **system-level versioning** with explicit version directories:

```
/specs/
  v1/                          # v1 schema specifications
    prompt-meta.schema.json
    tool-meta.schema.json
    ...
  v2/                          # Future: v2 specifications
    ...

/primitives/
  v1/                          # v1 primitive structure
    prompts/
    tools/
    hooks/
  v2/                          # Future: v2 structure (may be completely different)
    commands/                  # Maybe Claude-specific
    ...
  experimental/                # Sandbox for testing v2+ ideas
    ...
```

### Key Principles

1. **Explicit Versioning**: Version directories are explicit (`v1`, `v2`), not implicit
2. **Immutable Versions**: v1 structure never changes; new architecture = new version
3. **Independent Evolution**: v1 and v2 coexist; no forced migration
4. **Experimental Sandbox**: `/primitives/experimental/` for testing radical ideas
5. **Version Routing**: CLI routes operations based on `--spec-version` flag

## Two Layers of Versioning

This creates a **two-layer versioning system**:

### System-Level Versioning (This ADR)
- **What**: Architectural/structural versions (v1, v2, v3)
- **When**: Fundamental organizational changes
- **Scope**: Entire primitive system structure
- **Examples**:
  - v1: Generic provider-agnostic primitives
  - v2: Claude Code-specific command structure
  - v3: OpenAI-native function calling structure

### Prompt-Level Versioning (ADR 009)
- **What**: Content iterations within a structure
- **When**: Refining/improving individual primitives
- **Scope**: Single primitive's content
- **Examples**:
  - `prompt.v1.md`: Initial version
  - `prompt.v2.md`: Improved version
  - `prompt.v3.md`: Further refinement

**Both coexist**: A v1 primitive can have multiple prompt versions (v1, v2, v3 of content).

## Rationale

### Benefits

1. **Architectural Freedom**: Try v2 ideas in experimental without touching v1
2. **Backwards Compatibility**: v1 keeps working forever, no forced migrations
3. **Reduced Fear**: Bad architectural decisions become "v1 experiments", not permanent mistakes
4. **Clear Evolution**: v1 -> v2 migration path is explicit and documented
5. **Parallel Development**: v1 and v2 can coexist during transition
6. **Fast Iteration**: Experimental workspace allows rapid testing

### Tradeoffs

1. **More Directories**: Additional nesting (`/primitives/v1/prompts/...`)
2. **Version Management**: CLI must route based on version
3. **Multiple Truths**: During v2 transition, two structures exist
4. **Migration Work**: Eventually need tooling to migrate v1 -> v2

We accept these tradeoffs because they're **far cheaper** than the alternative (being stuck with wrong architecture or massive refactoring).

## Implementation

### Directory Structure

```
/specs/v1/                     # v1 contracts
  prompt-meta.schema.json
  tool-meta.schema.json
  hook-meta.schema.json
  model-config.schema.json
  provider-impl.schema.json
  README.md

/primitives/v1/                # v1 primitives
  prompts/
    agents/<category>/<id>/
      prompt.v1.md             # Prompt-level versioning
      prompt.v2.md
      meta.yaml                # Includes: spec_version: "v1"
    commands/...
    skills/...
    meta-prompts/...
  tools/...
  hooks/...

/primitives/experimental/      # v2+ testing ground
  README.md
  # Arbitrary structure for experimentation
```

### Configuration

`primitives.config.yaml` includes:
```yaml
spec_version: "v1"
paths:
  specs: "specs/v1"
  primitives: "primitives/v1"
  experimental: "primitives/experimental"
```

### CLI Integration

```bash
# Default to v1
agentic validate primitives/v1/prompts/agents/python/python-pro

# Explicit version
agentic validate --spec-version v1 ...

# Experimental
agentic validate --spec-version experimental primitives/experimental/my-test

# Future: v2
agentic validate --spec-version v2 primitives/v2/commands/...
```

### Experimental Workflow

1. **Create** experimental primitive with new structure
2. **Test** with `--spec-version experimental`
3. **Iterate** freely (can break, change, delete)
4. **Promote** to v2 when stable:
   - Create `/specs/v2/`
   - Create `/primitives/v2/`
   - Implement v2 validators
   - Migrate primitives

## Consequences

### Positive

- ✅ Can try v2 architecture without risk
- ✅ v1 primitives never break
- ✅ Analysis paralysis eliminated
- ✅ Clear evolution story
- ✅ Future-proof architecture

### Negative

- ❌ More complex directory structure
- ❌ CLI must handle multiple versions
- ❌ Documentation must explain two versioning layers
- ❌ Migration tooling needed eventually

### Neutral

- Developers must understand two versioning concepts
- Version in `meta.yaml` (`spec_version: "v1"`) required
- Primitives explicitly declare their spec version

## Examples

### Example 1: Current State (v1)

A generic Python agent using v1 structure:

```
primitives/v1/prompts/agents/python/python-pro/
  ├── prompt.v1.md        # Prompt-level version 1
  ├── prompt.v2.md        # Prompt-level version 2
  └── meta.yaml           # spec_version: "v1"
```

### Example 2: Future v2 (Claude-Specific)

When we decide Claude-specific structure is better:

```
primitives/v2/commands/python-scaffold/
  └── command.md          # Native Claude command format

specs/v2/command-meta.schema.json  # New schema for v2
```

Both v1 and v2 coexist. Users choose which to use.

### Example 3: Experimental Testing

Testing a radical new idea:

```
primitives/experimental/v3-draft/
  ├── tasks/              # New primitive type
  └── workflows/          # Another new type
```

Test with `--spec-version experimental`, promote to v3 if it works.

## Migration Path

When v2 is ready:

1. **Stabilize v2 in experimental**
2. **Create `/specs/v2/`** with new schemas
3. **Create `/primitives/v2/`** directory
4. **Implement v2 validators** in CLI
5. **Add v2 transformers** for providers
6. **Migrate primitives** (or leave in v1)
7. **Document v2** architecture
8. **Support both** v1 and v2 indefinitely

Optional:
```bash
agentic migrate spec v1 v2 primitives/v1/prompts/agents/python/python-pro
```

## Related

- **ADR 009**: Versioned Primitives (prompt-level versioning)
- **ADR 004**: Provider-Scoped Models (providers separate from primitives)
- **ADR 007**: Generated Outputs (primitives are source of truth)

## References

- "API versioning" patterns from REST API design
- Semantic versioning principles (adapted for directory structure)
- Compiler version support (GCC, LLVM support multiple language versions)

---

**Status**: ✅ Accepted  
**Implemented**: Wave 4  
**Next Review**: When v2 design begins

