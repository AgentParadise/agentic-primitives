---
title: "ADR-021: Primitives Directory Structure"
status: accepted
created: 2025-12-06
updated: 2025-12-06
author: Neural
---

# ADR-021: Primitives Directory Structure

## Status

**Accepted**

- Created: 2025-12-06
- Updated: 2025-12-06
- Author(s): Neural

## Context

The agentic-primitives framework defines reusable AI agent components (commands, tools, hooks, skills, agents). The current directory structure includes an unnecessary `prompts/` intermediate layer:

```
primitives/v1/
├── hooks/
├── prompts/           # ← Extra nesting with no value
│   ├── agents/
│   ├── commands/
│   ├── meta-prompts/
│   └── skills/
└── tools/
```

### Problems with Current Structure

1. **Unnecessary nesting**: The `prompts/` directory adds cognitive overhead without providing value
2. **Inconsistent with industry standards**: Claude Code's `.claude/` directory uses flat structure
3. **Build output mismatch**: Source structure doesn't map cleanly to output structure
4. **Meta-prompts are special-cased**: `meta-prompts/` is a sibling to `commands/` but meta-prompts are logically a type of command

### Industry Context

Claude Code's `.claude/` directory has emerged as the de facto standard for AI agent configuration (similar to how OpenAI's API became the standard for LLM APIs). We should align our source structure with this convention:

```
.claude/
├── commands/          # Direct, no intermediate layers
├── hooks/
├── tools/
├── settings.json
└── mcp.json
```

## Decision

Restructure `primitives/v1/` to match Claude Code's `.claude/` directory structure, removing the `prompts/` intermediate layer.

### New Directory Structure

```
primitives/v1/
├── commands/              # User-invoked commands (/command-name)
│   ├── devops/
│   │   ├── commit/
│   │   ├── merge/
│   │   └── push/
│   ├── docs/
│   │   └── doc-scraper/
│   ├── meta/              # Meta-prompts (prompt generators)
│   │   ├── create-doc-sync/
│   │   ├── create-prime/
│   │   └── prompt-generator/
│   ├── qa/
│   │   ├── pre-commit-qa/
│   │   ├── qa-setup/
│   │   └── review/
│   ├── review/
│   │   └── fetch/
│   └── workflow/
│       └── merge-cycle/
├── skills/                # Reusable capabilities (referenced in prompts)
│   └── review/
│       └── prioritize/
├── agents/                # Persistent personas (@agent-name)
│   └── (future use)
├── hooks/                 # Lifecycle event handlers (unchanged)
│   ├── handlers/
│   └── validators/
└── tools/                 # MCP tool integrations (unchanged)
    └── scrape/
        └── firecrawl-scraper/
```

### Key Changes

| Current Path | New Path |
|--------------|----------|
| `v1/prompts/commands/{cat}/{id}/` | `v1/commands/{cat}/{id}/` |
| `v1/prompts/meta-prompts/{id}/` | `v1/commands/meta/{id}/` |
| `v1/prompts/skills/{cat}/{id}/` | `v1/skills/{cat}/{id}/` |
| `v1/prompts/agents/{cat}/{id}/` | `v1/agents/{cat}/{id}/` |
| `v1/hooks/` | `v1/hooks/` (unchanged) |
| `v1/tools/` | `v1/tools/` (unchanged) |

### Build Output Mapping

| Primitive Type | Source Location | Build Output |
|----------------|-----------------|--------------|
| commands | `v1/commands/{cat}/{id}/` | `.claude/commands/{cat}/{id}.md` |
| meta-prompts | `v1/commands/meta/{id}/` | `.claude/commands/meta/{id}.md` |
| skills | `v1/skills/{cat}/{id}/` | `.claude/skills.json` + content |
| agents | `v1/agents/{cat}/{id}/` | `.claude/custom_prompts/{cat}/{id}.md` |
| hooks | `v1/hooks/{cat}/{id}/` | `.claude/hooks/{cat}/{id}/` + `settings.json` |
| tools | `v1/tools/{cat}/{id}/` | `.claude/tools/{cat}/{id}/` + `mcp.json` |

## Alternatives Considered

### Alternative 1: Keep `prompts/` as Type Container

**Description**: Keep the `prompts/` directory but rename it to something more meaningful like `prompt-primitives/`.

**Pros**:
- Less migration effort
- Keeps prompt types grouped

**Cons**:
- Still adds unnecessary nesting
- Doesn't align with Claude Code conventions
- Doesn't solve the meta-prompts categorization issue

**Reason for rejection**: The nesting provides no value and diverges from industry standards.

### Alternative 2: Flat Structure with Type Suffixes

**Description**: All primitives at `v1/` root with type in directory name: `v1/command-commit/`, `v1/tool-firecrawl/`.

**Pros**:
- Maximum flatness
- No nesting at all

**Cons**:
- Poor organization for many primitives
- Hard to browse by type
- Doesn't match `.claude/` output structure

**Reason for rejection**: Too flat; loses useful categorization without type directories.

### Alternative 3: Keep Meta-prompts as Separate Type

**Description**: Keep `v1/meta-prompts/` as a sibling to `v1/commands/` instead of moving under `v1/commands/meta/`.

**Pros**:
- Meta-prompts are conceptually different
- Less change to existing validation

**Cons**:
- Meta-prompts are invoked like commands (`/meta/prompt-generator`)
- Creates inconsistency in invocation model
- Requires special-case handling in CLI

**Reason for rejection**: Meta-prompts are functionally commands that generate prompts; keeping them under `commands/meta/` reflects this relationship.

## Consequences

### Positive Consequences

- **Industry alignment**: Structure mirrors Claude Code's `.claude/` conventions
- **Cleaner mental model**: Type directories directly under `v1/`
- **1:1 source-to-output mapping**: Easy to understand what gets built where
- **Meta-prompts properly categorized**: As a category of commands, not a separate type
- **Future-ready**: Structure supports upcoming primitives (contexts, memories)

### Negative Consequences

- **Migration required**: All primitives must be moved
- **CLI code updates**: Path detection logic needs updating
- **Test fixture updates**: Test data must be restructured
- **Breaking change**: Anyone referencing old paths will need updates

### Neutral Consequences

- ADRs need path example updates
- Documentation needs structure diagram updates
- Build output structure remains unchanged

## Implementation Notes

### CLI Changes Required

1. **validate.rs**: Update `detect_type()` to identify types from new paths
2. **build.rs**: Update `discover_primitives()` to walk new structure
3. **new.rs**: Update scaffolding to create in new locations
4. **structural.rs**: Update path validation patterns

### Path Detection Logic

```rust
// Old: primitives/v1/prompts/commands/{category}/{id}
// New: primitives/v1/commands/{category}/{id}

fn detect_type(path: &Path) -> Result<String> {
    let components: Vec<_> = path.components().collect();
    for (i, c) in components.iter().enumerate() {
        match c.as_os_str().to_str() {
            Some("commands") => return Ok("command".to_string()),
            Some("skills") => return Ok("skill".to_string()),
            Some("agents") => return Ok("agent".to_string()),
            Some("tools") => return Ok("tool".to_string()),
            Some("hooks") => return Ok("hook".to_string()),
            _ => continue,
        }
    }
    Err(anyhow!("Unknown primitive type"))
}
```

### Migration Steps

1. Create new directory structure
2. Move primitives using `git mv` for history preservation
3. Update meta.yaml files if `kind` field references old structure
4. Update CLI path detection
5. Update test fixtures
6. Rebuild and verify

### Backward Compatibility

For one release cycle, the CLI should:
- Support both old and new paths during detection
- Emit deprecation warnings for old structure
- Document migration path for external users

## References

- [Claude Code Agent SDK](https://docs.anthropic.com/en/docs/claude-code) - `.claude/` structure reference
- ADR-019: File Naming Convention - File naming within directories
- ADR-020: Agentic Prompt Taxonomy - Primitive types and levels
- [OpenAI API](https://platform.openai.com/docs/api-reference) - Example of API standardization

---

**Status**: Accepted
**Last Updated**: 2025-12-06
