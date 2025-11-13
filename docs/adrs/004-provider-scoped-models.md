# ADR-004: Provider-Scoped Model Configuration

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

Primitives reference AI models in their metadata (e.g., `preferred_models`). We need a system for:
- Defining model configurations (capabilities, pricing, context windows)
- Referencing models from primitives
- Supporting multiple providers (Claude, OpenAI, Cursor, Gemini)

### The Organization Question

Where should model configurations live?

**Option A: Flat models/ directory**
```
models/
├── claude-sonnet.yaml
├── claude-opus.yaml
├── gpt-4-turbo.yaml
├── gpt-4o.yaml
```

**Option B: Provider-scoped**
```
providers/
├── claude/models/
│   ├── sonnet.yaml
│   └── opus.yaml
├── openai/models/
│   ├── gpt-codex.yaml
│   └── gpt-large.yaml
```

### Reference Syntax

How should primitives reference models?

- **Generic aliases**: `sonnet`, `gpt-large` (ambiguous)
- **Qualified names**: `claude/sonnet`, `openai/gpt-codex` (explicit)
- **Full identifiers**: `claude-3-5-sonnet-20241022` (verbose)

## Decision

We will organize models **under provider directories** and reference them using **qualified names**:

1. **Directory Structure**
   ```
   providers/<provider>/models/<model-id>.yaml
   ```
   - Example: `providers/claude/models/sonnet.yaml`
   - Example: `providers/openai/models/gpt-codex.yaml`

2. **Reference Syntax**
   ```
   provider/model-id
   ```
   - Example: `claude/sonnet`
   - Example: `openai/gpt-codex`
   - Example: `cursor/gpt-4`

3. **Model Config Schema**
   ```yaml
   id: sonnet
   full_name: "Claude 3.5 Sonnet"
   api_name: "claude-3-5-sonnet-20241022"
   version: "20241022"
   provider: claude
   
   capabilities:
     max_tokens: 200000
     context_window: 200000
     supports_vision: true
     supports_function_calling: true
     supports_streaming: true
   
   performance:
     speed: "fast"
     quality: "high"
   
   pricing:
     input_per_1m_tokens: 3.00
     output_per_1m_tokens: 15.00
     currency: "USD"
   
   strengths:
     - "Code generation"
     - "Long context reasoning"
     - "Instruction following"
   
   recommended_for:
     - "agents"
     - "commands"
     - "complex reasoning"
   
   notes: "Balanced model for most agentic tasks"
   ```

## Rationale

### Why Provider-Scoped?

✅ **Encapsulation**: Each provider is self-contained

✅ **Clarity**: Obvious which models belong to which provider

✅ **No Naming Conflicts**: Multiple providers can have similarly-named models

✅ **Independent Versioning**: Each provider manages their own model lifecycle

✅ **Easy Provider Addition**: Just add a new `providers/<new>` directory

✅ **Explicit References**: `claude/sonnet` is unambiguous

### Why Not Generic Aliases?

❌ **Ambiguity**: What is "sonnet"? Claude's Sonnet or something else?

❌ **Maintenance Burden**: Need to maintain mapping from alias → actual models

❌ **Provider Coupling**: Aliases might not map cleanly across providers

❌ **Hidden Dependencies**: Not clear which provider is being used

### Why Not Start with Generic Aliases?

Some suggested starting simple with generic aliases like `sonnet-large`, `gpt-large` and mapping them to specific providers later. However:

- **YAGNI violation**: We don't actually need provider-agnostic aliases
- **Premature abstraction**: Adds complexity without proven benefit
- **False flexibility**: Models across providers aren't truly interchangeable
- **Better explicit**: `claude/sonnet` is clearer than `sonnet-large`

## Consequences

### Positive

✅ **Clear Ownership**: Each model explicitly belongs to a provider

✅ **Scalable**: Easy to add new providers and models

✅ **No Ambiguity**: References are always explicit

✅ **Self-Documenting**: Reading `claude/sonnet` immediately tells you the provider

✅ **Flexible**: Can have provider-specific model features

✅ **Simple Resolution**: Parse `provider/model` → load `providers/{provider}/models/{model}.yaml`

### Negative

⚠️ **Verbosity**: Must write `claude/sonnet` instead of just `sonnet`

⚠️ **No Cross-Provider Abstraction**: Can't easily swap providers

⚠️ **Repetition**: Might reference same model in many primitives

### Mitigations

1. **Short IDs**: Use `sonnet` not `claude-3-5-sonnet-20241022`
2. **Defaults**: Primitives can omit models, use provider defaults
3. **Templates**: Common model refs in primitive templates
4. **Future**: Could add aliases later if truly needed

## Implementation

### Model File Location

```
providers/claude/models/
├── sonnet.yaml       (claude-3-5-sonnet-20241022)
├── opus.yaml         (claude-3-opus-20240229)
└── haiku.yaml        (claude-3-haiku-20240307)

providers/openai/models/
├── gpt-codex.yaml    (gpt-4-turbo-2024-11-20)
├── gpt-large.yaml    (gpt-4.5-preview)
└── o1.yaml           (o1-preview)

providers/cursor/models/
├── gpt-4.yaml        (whatever Cursor uses)
└── claude.yaml       (whatever Cursor uses)
```

### Resolution Logic

```rust
// Parse "claude/sonnet"
let model_ref = ModelRef::parse("claude/sonnet")?;
// model_ref.provider = "claude"
// model_ref.model = "sonnet"

// Load config
let config = model_ref.resolve()?;
// Reads: providers/claude/models/sonnet.yaml
// Returns: ModelConfig { full_name: "Claude 3.5 Sonnet", ... }
```

### Usage in Primitives

```yaml
# prompts/agents/python/python-pro.meta.yaml
defaults:
  preferred_models:
    - claude/sonnet      # Primary choice
    - openai/gpt-codex   # Fallback
    - cursor/gpt-4       # Fallback
```

### Provider Configuration

```yaml
# primitives.config.yaml
providers:
  default: "claude"
  
  claude:
    default_model: "claude/sonnet"
  
  openai:
    default_model: "openai/gpt-codex"
```

## Success Criteria

This decision is successful when:

1. ✅ All model configs live in `providers/<provider>/models/`
2. ✅ All model references use `provider/model` format
3. ✅ Model resolution works reliably
4. ✅ Adding a new provider is straightforward
5. ✅ No ambiguity in which model is being used
6. ✅ Validation can verify model references exist

## Related Decisions

- **ADR-007: Generated Provider Outputs** - Uses model configs for transformation
- **ADR-002: Strict Validation** - Validates model references resolve

## References

- [Qualified Namespacing](https://en.wikipedia.org/wiki/Namespace)
- Docker image naming: `registry/image:tag`
- Python module imports: `package.module`

## Notes

**No Generic Aliases**

We explicitly reject "smart defaults" or generic model aliases because:
- They add complexity without clear benefit (YAGNI)
- They hide which provider is actually being used
- Models aren't truly interchangeable across providers
- Explicit is better than implicit (Zen of Python)

**Future Flexibility**

If we ever need cross-provider abstractions, we can add them later without breaking existing primitives:

```yaml
# Could add model aliases (but we're not)
model_aliases:
  fast-cheap: "claude/haiku"
  balanced: "claude/sonnet"
  powerful: "claude/opus"
```

But for now: **YAGNI** (You Aren't Gonna Need It).

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

