# Experimental Primitives Workspace

This directory is a sandbox for testing architectural ideas for future spec versions (v2, v3, etc.).

## Purpose

- **Try new structures** without committing to them
- **Test radical changes** to primitive organization
- **Prototype v2+ ideas** before promotion
- **Iterate quickly** without fear of breaking existing work

## Rules

⚠️ **Everything in this directory is unstable**:
- Can break at any time
- Can be completely reorganized
- Can be deleted without notice
- Should NOT be used in production

✅ **Use experimental primitives for**:
- Testing new metadata schemas
- Trying different directory structures
- Prototyping new primitive types
- Experimenting with provider formats

❌ **Do NOT use experimental primitives for**:
- Production workflows
- Stable reference implementations
- Long-term storage

## Workflow

### 1. Create Experimental Primitive

```bash
# Create in experimental directory
agentic new agent experimental my-experimental-agent --experimental

# Or manually create structure here
mkdir -p experimental/v2-commands/
```

### 2. Test with CLI

```bash
# Validate experimental primitive (more lenient validation)
agentic validate --spec-version experimental experimental/my-primitive

# Build experimental primitive (if compatible)
agentic build --provider claude --spec-version experimental experimental/my-primitive
```

### 3. Iterate Freely

- Try different metadata fields
- Test new directory structures
- Experiment with new primitive types
- Break things without consequences

### 4. Promote When Ready

When an experimental idea is stable and proven:

1. **Create v2 spec**: Copy approach to `/specs/v2/`
2. **Create v2 structure**: Establish `/primitives/v2/`
3. **Migrate primitives**: Move from experimental to v2
4. **Update CLI**: Add v2 validator and transformer
5. **Document**: Update ADRs and guides

## Example: Experimenting with v2 Structure

Let's say you want to try a Claude-specific structure:

```
experimental/v2-claude-native/
  ├── commands/
  │   └── python-scaffold/
  │       └── command.md        # Native Claude command format
  ├── system-prompts/
  │   └── python-pro.md         # Agent as system prompt
  └── skills/
      └── testing-patterns.md   # Skill as context overlay
```

Test it:
```bash
agentic validate --spec-version experimental experimental/v2-claude-native
```

If it works well, promote to v2!

## Current Experiments

(Document your experiments here as you create them)

- None yet - v1 is still being finalized

## Questions?

See `docs/versioning-guide.md` for comprehensive versioning documentation.

