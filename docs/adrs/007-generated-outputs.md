# ADR-007: Generated Provider Outputs

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team
informed: All Stakeholders
---
```

## Context

Primitives are **provider-agnostic** by design. They describe intent, not implementation:
- What an agent should do (not how Claude/OpenAI executes it)
- What a tool provides (not how to call it)
- When a hook runs (not provider-specific syntax)

However, each LLM provider has different formats:
- **Claude Agent SDK**: `.claude/commands/*.md`, `settings.json` for hooks
- **OpenAI API**: System messages, function calling JSON
- **Cursor**: Custom integration format

We must decide: **Should provider-specific files be committed to the repository or generated on demand?**

### Alternative Approaches

1. **Commit Provider Files**
   - Source: primitives + provider files both in repo
   - Pros: Everything visible, no build step
   - Cons: Duplication, drift, merge conflicts

2. **Generate and Commit**
   - Source: primitives only
   - Build: Generate provider files
   - Commit: Both source and generated files
   - Pros: Visible outputs
   - Cons: Still duplication, unclear which is source of truth

3. **Generate On Demand** (CHOSEN)
   - Source: primitives only (committed)
   - Build: Generate provider files (not committed)
   - Install: Copy generated files to target
   - Pros: Single source of truth, no drift
   - Cons: Extra build step

## Decision

We will **generate provider-specific outputs on demand** and **not commit them**:

1. **Primitives are Source**
   - Only primitives are committed
   - Provider files are build artifacts
   - `.gitignore` excludes build/ and provider directories

2. **Build Command Generates**
   ```bash
   agentic build --provider claude
   # Output: build/claude/.claude/
   ```
   - Transforms primitives to provider format
   - Uses provider-specific transformers
   - Applies Handlebars templates
   - Writes to build/ directory

3. **Install Command Deploys**
   ```bash
   agentic install --provider claude --global
   # Copies: build/claude/.claude/ → ~/.claude/
   ```
   - Installs generated files to target
   - Global: `~/.claude/`, `~/.openai/`, etc.
   - Project: `./.claude/`, `./.openai/`, etc.

4. **Provider Transformers**
   - Each provider has `transformer/` directory with Rust code
   - Transforms primitives to provider-specific formats
   - Uses templates from `providers/<provider>/templates/`

## Rationale

### Why Generate?

✅ **Single Source of Truth**: Primitives are the only canonical representation

✅ **No Duplication**: Provider files don't need to be maintained separately

✅ **No Drift**: Can't have primitives and provider files out of sync

✅ **Easy Updates**: Change primitive once, regenerate for all providers

✅ **Clean Git History**: No noise from generated file changes

✅ **Multiple Providers**: Generate for Claude + OpenAI + Cursor from one source

✅ **Versioning**: Provider files match primitive versions automatically

### Why Not Commit Generated Files?

❌ **Duplication**: Same information in two places

❌ **Drift Risk**: Primitives and provider files can get out of sync

❌ **Merge Conflicts**: Generated files cause unnecessary conflicts

❌ **Git Noise**: Large diffs from generated file updates

❌ **Source Confusion**: Which is canonical - primitive or provider file?

### Why Not Skip Primitives?

❌ **Provider Lock-in**: Can't switch providers easily

❌ **No Validation**: Provider formats vary in validation strictness

❌ **No Versioning**: Provider formats may not support versioning

❌ **No Cross-Provider**: Can't reuse across Claude/OpenAI/Cursor

❌ **No Meta-Generation**: Can't use meta-prompts to generate primitives

## Consequences

### Positive

✅ **Clean Repository**: Only source files committed

✅ **Flexible**: Generate for any provider anytime

✅ **Reliable**: Generated files always match source

✅ **Maintainable**: Update transformers, regenerate everything

✅ **Testable**: Can test transformations systematically

✅ **Multi-Provider**: Support multiple providers from one source

### Negative

⚠️ **Build Step Required**: Must run `agentic build` before installing

⚠️ **Invisible Outputs**: Generated files not visible in repo

⚠️ **Transformer Complexity**: Each provider needs transformer implementation

⚠️ **Testing**: Must test transformers produce correct outputs

### Mitigations

1. **Fast Build**: Optimize transformers for speed (<1s for 100 primitives)

2. **Cache**: Cache generated outputs, rebuild only on changes

3. **CI/CD**: Automate build + install in deployment pipelines

4. **Preview**: `agentic build --dry-run` shows what would be generated

5. **Validation**: Validate generated files before installing

6. **Documentation**: Clear workflow examples

## Implementation

### Transformation Flow

```
Primitives (source)
        ↓
[agentic build --provider claude]
        ↓
Load primitives + metadata
        ↓
Provider-specific transformer
  - prompts/agents/ → system prompts
  - prompts/commands/ → .claude/commands/
  - prompts/skills/ → .claude/skills/
  - tools/ → tool configurations
  - hooks/ → settings.json hooks
        ↓
Apply Handlebars templates
        ↓
Write to build/claude/.claude/
        ↓
[agentic install --provider claude]
        ↓
Copy build/claude/.claude/ → ~/.claude/
```

### Provider Transformer (Rust)

```rust
// providers/claude/transformer/prompts.rs
pub struct ClaudePromptsTransformer;

impl PromptsTransformer for ClaudePromptsTransformer {
    fn transform_agent(&self, agent: &PromptPrimitive) -> Result<ClaudeSystemPrompt> {
        // Agents become system-level prompts
        // Maybe written to a special CLAUDE.md file
        let template = load_template("system.md.hbs")?;
        let rendered = template.render(agent)?;
        
        Ok(ClaudeSystemPrompt {
            content: rendered,
            path: ".claude/SYSTEM.md"
        })
    }
    
    fn transform_command(&self, command: &PromptPrimitive) -> Result<ClaudeCommand> {
        // Commands become .claude/commands/<id>.md
        let template = load_template("command.md.hbs")?;
        let rendered = template.render(command)?;
        
        Ok(ClaudeCommand {
            id: command.id.clone(),
            content: rendered,
            path: format!(".claude/commands/{}.md", command.id)
        })
    }
    
    fn transform_skill(&self, skill: &PromptPrimitive) -> Result<ClaudeSkill> {
        // Skills become .claude/skills/<id>.md
        let template = load_template("skill.md.hbs")?;
        let rendered = template.render(skill)?;
        
        Ok(ClaudeSkill {
            id: skill.id.clone(),
            content: rendered,
            path: format!(".claude/skills/{}.md", skill.id)
        })
    }
}
```

### Handlebars Templates

```handlebars
{{! providers/claude/templates/command.md.hbs }}
---
name: {{id}}
description: {{summary}}
{{#if tools}}
allowed-tools:
{{#each tools}}
  - {{this}}
{{/each}}
{{/if}}
---

# {{summary}}

{{content}}

{{#if inputs}}
## Expected Inputs

{{#each inputs}}
- **{{name}}** ({{type}}{{#if required}}, required{{/if}}): {{description}}
{{/each}}
{{/if}}
```

### Hook Transformation

```rust
// providers/claude/transformer/hooks.rs
pub fn transform_hook(hook: &HookPrimitive) -> Result<ClaudeHookConfig> {
    // Transform to Claude settings.json format
    let hook_entry = json!({
        "matcher": hook.meta.get("matcher").unwrap_or("*"),
        "hooks": [{
            "type": "command",
            "command": format!("uv run {}/impl.python.py", hook.path),
            "timeout": hook.meta.get("timeout").unwrap_or(60)
        }]
    });
    
    Ok(ClaudeHookConfig {
        event: hook.meta.event.clone(),
        entry: hook_entry
    })
}
```

### Build Output Structure

```
build/
├── claude/
│   └── .claude/
│       ├── commands/
│       │   ├── code-review.md
│       │   └── test-generator.md
│       ├── skills/
│       │   └── pytest-patterns.md
│       ├── hooks/
│       │   └── pre-tool-use/
│       │       ├── impl.python.py
│       │       └── middleware/
│       └── settings.json
│
├── openai/
│   └── .openai/
│       ├── system.txt
│       └── functions.json
│
└── cursor/
    └── .cursor/
        └── ...
```

### .gitignore

```gitignore
# Generated provider outputs
build/
.claude/
.openai/
.cursor/
.gemini/
```

## Success Criteria

Generated outputs are successful when:

1. ✅ Primitives are the only committed source
2. ✅ `agentic build` generates valid provider files
3. ✅ Generated files match provider specifications
4. ✅ Build is fast (<5s for 100 primitives)
5. ✅ Install correctly deploys generated files
6. ✅ Regenerating produces identical output (deterministic)
7. ✅ Multiple providers can be built from same primitives

## Related Decisions

- **ADR-004: Provider-Scoped Models** - Models referenced in transformers
- **ADR-006: Middleware-Based Hooks** - Hooks transformed to provider format
- **ADR-002: Strict Validation** - Generated files must be valid

## References

- [Generate, don't accumulate](https://blog.codinghorror.com/creating-software-from-data/)
- [Build artifacts in .gitignore](https://git-scm.com/docs/gitignore)
- [The Twelve-Factor App: Build, release, run](https://12factor.net/build-release-run)

## Notes

**Why "Build" vs "Compile"?**

We use `build` because:
- More familiar to developers
- Matches `make build`, `npm run build`, `cargo build`
- "Compile" implies low-level transformation

**Caching Strategy**:
- Hash primitives to detect changes
- Only rebuild changed primitives
- Store build cache in `.agentic-cache/`

**Preview Before Install**:
```bash
agentic build --provider claude --output ./preview
# Review generated files in ./preview
agentic install --provider claude --source ./preview
```

**Testing Transformers**:
- Unit tests: Transform sample primitives, check output
- Integration tests: Build full repository, validate all files
- Snapshot tests: Compare generated files to known-good outputs

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

