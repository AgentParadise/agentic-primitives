# Specification v1

This directory contains the JSON Schema definitions for the v1 specification of agentic primitives.

## Schemas

- **prompt-meta.schema.json**: Defines metadata for prompt primitives (agents, commands, skills, meta-prompts)
- **tool-meta.schema.json**: Defines metadata for tool primitives
- **hook-meta.schema.json**: Defines metadata for hook primitives with middleware pipeline
- **model-config.schema.json**: Defines provider-scoped model configurations
- **provider-impl.schema.json**: Defines provider-specific implementation bindings

## Version Information

**Spec Version**: v1  
**Status**: Active  
**Created**: 2025-11-13  

## Structure Expectations

All primitives using the v1 spec must follow this structure:

```
primitives/v1/<type>/<category>/<id>/
  ├── meta.yaml              # Must include: spec_version: "v1"
  ├── prompt.v1.md           # For prompts (versioned content)
  ├── prompt.v2.md           # Optional additional versions
  └── ...
```

## Validation

Primitives are validated against these schemas using the CLI:

```bash
# Validate all v1 primitives
agentic-p validate --spec-version v1

# Validate specific primitive
agentic-p validate primitives/v1/prompts/agents/python/python-pro
```

## Future Evolution

When v2 is created, it will live in `/specs/v2/` with potentially different schemas. v1 primitives will continue to work unchanged.

