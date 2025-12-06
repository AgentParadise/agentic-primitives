# ADR-019: Primitive File Naming Convention

```yaml
---
status: accepted
created: 2025-12-06
updated: 2025-12-06
deciders: System Architect
consulted: Development Team
informed: All Stakeholders
---
```

## Context

Agentic primitives consist of multiple files per primitive: metadata, prompt content, provider bindings, and implementations. We need a consistent file naming convention that:

1. **Enables alphabetical sorting** - Files for the same primitive group together
2. **Clarifies file purpose** - File type obvious from name without opening
3. **Supports tooling** - CLI can discover files predictably
4. **Scales across types** - Works for prompts, tools, hooks, and future primitives

### Problems with Previous Conventions

**Inconsistent naming**:
```
# Some primitives used
meta.yaml
tool.meta.yaml
impl.claude.yaml

# Others used
review.yaml
firecrawl-scraper.tool.yaml
```

**Poor sorting**:
```
# Files sorted alphabetically:
impl.claude.yaml
impl.local.py
meta.yaml
prompt.v1.md

# vs. ID-first (all related files together):
review.meta.yaml
review.prompt.v1.md
review.claude.yaml
```

**Ambiguous types**:
```
# What type of file is this?
review.yaml          # Could be config, metadata, or data
meta.yaml            # Generic, doesn't indicate primitive type
```

## Decision

Adopt `{id}.{type}.{ext}` naming convention for all primitive files:

### File Naming Patterns

| Primitive Type | Metadata File | Content File | Provider Config |
|---------------|---------------|--------------|-----------------|
| **Commands** | `{id}.meta.yaml` | `{id}.prompt.v{n}.md` | (inline in meta) |
| **Agents** | `{id}.meta.yaml` | `{id}.prompt.v{n}.md` | (inline in meta) |
| **Skills** | `{id}.meta.yaml` | `{id}.prompt.v{n}.md` | (inline in meta) |
| **Meta-prompts** | `{id}.meta.yaml` | `{id}.prompt.v{n}.md` | (inline in meta) |
| **Tools** | `{id}.tool.yaml` | N/A | `{id}.claude.yaml` (optional) |
| **Hooks** | `{id}.hook.yaml` | N/A | `{id}.claude.yaml` (optional) |

### Type Suffixes

| Suffix | Purpose | Example |
|--------|---------|---------|
| `.meta.yaml` | Prompt primitive metadata | `review.meta.yaml` |
| `.tool.yaml` | Tool primitive metadata | `firecrawl-scraper.tool.yaml` |
| `.hook.yaml` | Hook primitive metadata | `bash-validator.hook.yaml` |
| `.prompt.v{n}.md` | Versioned prompt content | `review.prompt.v1.md` |
| `.claude.yaml` | Claude provider config | `run-tests.claude.yaml` |
| `.openai.json` | OpenAI provider config | `run-tests.openai.json` |
| `.local.py` | Python implementation | `scraper.local.py` |
| `.local.ts` | TypeScript implementation | `scraper.local.ts` |
| `.local.rs` | Rust implementation | `scraper.local.rs` |

### Directory Structure Examples

**Command Primitive**:
```
primitives/v1/prompts/commands/qa/review/
├── review.meta.yaml         # Metadata
└── review.prompt.v1.md      # Prompt content
```

**Tool Primitive**:
```
primitives/v1/tools/scrape/firecrawl-scraper/
├── firecrawl-scraper.tool.yaml   # Metadata + inline providers
├── firecrawl_scraper.py          # Implementation (snake_case for Python)
└── firecrawl-scraper.local.ts    # Alternative implementation
```

**Hook Primitive**:
```
primitives/v1/hooks/safety/bash-validator/
├── bash-validator.hook.yaml      # Configuration
├── bash_validator.py             # Python orchestrator
└── handlers/                     # Handler modules
    ├── block_dangerous.py
    └── log_commands.py
```

### The `{id}` Component

The `{id}` **MUST** match the directory name:

```
primitives/v1/prompts/commands/devops/manage-security-patches/
                                      └─────────────┬─────────┘
                                                    │
├── manage-security-patches.meta.yaml    ← {id} = directory name
└── manage-security-patches.prompt.v1.md
```

## Rationale

### Why ID-First?

**Better file explorer experience**:
```
# All files for "review" sort together
review.meta.yaml
review.prompt.v1.md
review.claude.yaml

# vs. type-first (files scattered)
impl.claude.yaml
meta.yaml
prompt.v1.md
```

**Faster visual scanning**: When browsing directories, immediately see which primitive the file belongs to.

**Tab-completion friendly**: Type `review.<TAB>` to see all files for that primitive.

### Why Separate Type Suffixes?

**Disambiguates file purpose**:
```
# Clear what each file contains
review.meta.yaml      ← Primitive metadata
review.prompt.v1.md   ← Prompt template
review.claude.yaml    ← Claude-specific config

# vs. ambiguous
review.yaml           ← Could be anything
```

**Enables type-specific schema validation**: CLI can validate `*.meta.yaml` against prompt schema, `*.tool.yaml` against tool schema.

**Supports glob patterns**:
```bash
# Find all prompt metadata
find . -name "*.meta.yaml"

# Find all tool implementations
find . -name "*.local.py"
```

### Why Not Generic Names?

`meta.yaml` and `impl.claude.yaml` were:
- **Not unique**: Multiple files with same name in different directories
- **Hard to identify**: When viewing file in isolation, unclear which primitive
- **Poor searchability**: Can't grep for specific primitive's files

## Consequences

### Positive

✅ **Consistent convention** across all primitive types

✅ **Better IDE experience** - Files sort logically, easier to navigate

✅ **Clearer file purpose** - No ambiguity about what a file contains

✅ **Tooling friendly** - CLI can discover files via predictable patterns

✅ **Searchable** - Can find all files for a primitive by ID

### Negative

⚠️ **Migration required** - Existing files need renaming

⚠️ **Longer filenames** - `review.meta.yaml` vs `meta.yaml`

⚠️ **Redundancy** - Directory name repeated in filename

### Migration Strategy

1. **CLI supports both patterns** during transition:
   - New: `{id}.meta.yaml` (preferred)
   - Legacy: `{id}.yaml`, `meta.yaml` (fallback)

2. **Gradual migration**:
   - New primitives use new convention
   - Existing primitives migrated over time

3. **Validation warnings**:
   - CLI warns about legacy naming, doesn't fail

## Implementation

### CLI Discovery Logic

```rust
fn find_metadata_file(path: &Path) -> Option<PathBuf> {
    let dir_name = path.file_name()?.to_str()?;

    // Try conventions in order of preference
    let candidates = [
        format!("{dir_name}.meta.yaml"),  // Prompts (new)
        format!("{dir_name}.tool.yaml"),  // Tools
        format!("{dir_name}.hook.yaml"),  // Hooks
        format!("{dir_name}.yaml"),       // Legacy prompt
        "meta.yaml".to_string(),          // Legacy generic
    ];

    candidates.iter()
        .map(|name| path.join(name))
        .find(|p| p.exists())
}
```

### Schema Validation

```yaml
# prompt-meta.schema.json expects files matching:
# - {id}.meta.yaml (commands, agents, skills, meta-prompts)

# tool.schema.json expects files matching:
# - {id}.tool.yaml

# hook.schema.json expects files matching:
# - {id}.hook.yaml
```

## Related Decisions

- **ADR-005: Polyglot Implementations** - Updated to use new naming
- **ADR-009: Versioned Primitives** - `.prompt.v{n}.md` pattern

## References

- [Naming Conventions Best Practices](https://en.wikipedia.org/wiki/Naming_convention_(programming))
- [Unix File Naming](https://www.gnu.org/software/coreutils/manual/html_node/File-permissions.html)

---

**Status**: Accepted
**Last Updated**: 2025-12-06
