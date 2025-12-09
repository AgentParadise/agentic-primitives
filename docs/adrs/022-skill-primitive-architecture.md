# ADR-022: Skill Primitive Architecture

## Status
Accepted

## Date
2024-12-09

## Context
The agentic primitives framework needed a way to define reusable skills that can be:
1. Validated at build time for structural correctness
2. Transformed to Claude Code's `.claude/skills/{category}/{name}/SKILL.md` format
3. Include optional bundled tools that are packaged with the skill
4. Support both legacy tool references (simple strings) and new structured references

Previous prompt types (agent, command, meta-prompt) were not designed for the skill-specific
features required by Claude Code's skill system.

## Decision
We will implement a dedicated `skill` primitive type with:

### 1. Metadata Schema (`specs/v1/skill-meta.schema.json`)
```yaml
id: prioritize
kind: skill
category: review
domain: code-review
summary: Prioritize review comments by severity
claude:
  name: prioritize
  description: Use when triaging code review feedback
  allowed_tools: [Read, Grep]
resources:
  - path: resources/severity-guide.md
    description: Severity classification guide
tools:
  - path: tools/comment-parser
    description: Parse review comments
versions:
  - version: 1
    file: prioritize.skill.v1.md
    status: active
    hash: "blake3:..."
    created: "2024-12-09"
```

### 2. File Structure
```
primitives/v1/skills/{category}/{id}/
├── {id}.skill.yaml      # Metadata with claude config
├── {id}.skill.v1.md     # Version 1 content
├── resources/           # Optional bundled resources
│   └── guide.md
└── tools/               # Optional bundled tools
    └── my-tool/
        ├── my-tool.tool.yaml
        ├── my_tool.py
        ├── pyproject.toml
        ├── tests/
        └── README.md
```

### 3. Build Output (Claude Code format)
```
.claude/skills/{category}/{name}/SKILL.md
```

With frontmatter:
```yaml
---
name: skill-id
description: Summary
allowed_tools:
  - Read
  - Grep
---
[skill content]
```

### 4. Flexible Tool References
Support both legacy and new formats:
```yaml
# Legacy (simple string array)
tools:
  - Read
  - Grep

# New (structured references)
tools:
  - path: tools/comment-parser
    description: Parse review comments
```

## Consequences

### Positive
- Skills are first-class primitives with full validation
- Claude Code integration via standard `.claude/skills/` directory
- Tools can be bundled with skills for self-contained packages
- Backward compatible with existing tool reference formats

### Negative
- More complex validation logic in `structural.rs`
- Two different tool reference formats to maintain

### Neutral
- Skills use the same versioning system as other prompts
- Build output includes both `SKILL.md` and `skills.json` manifest

## Implementation
- `cli/src/primitives/skill.rs`: Rust data structures
- `cli/src/validators/v1/structural.rs`: Validation logic
- `cli/src/providers/claude.rs`: `transform_skill()` function
- `specs/v1/skill-meta.schema.json`: JSON Schema

## Related
- ADR-019: File Naming Convention
- ADR-020: Agentic Prompt Taxonomy
- ADR-021: Primitives Directory Structure
