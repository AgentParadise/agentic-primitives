# ADR-018: Model Registry Architecture

## Status
Accepted

## Date
2025-12-02

## Context

AI model providers (Anthropic, OpenAI, etc.) frequently release new model versions with:
- Versioned API IDs (e.g., `claude-sonnet-4-5-20250929`)
- API aliases that point to latest snapshots (e.g., `claude-sonnet-4-5`)
- Different pricing per model version
- Varying capabilities and performance characteristics

Applications need a way to:
1. Use simple, stable aliases (`sonnet`, `claude-sonnet`) that auto-upgrade
2. Pin to specific API IDs when stability is required
3. Access pricing information tied to specific model versions
4. Know which models are current vs legacy

## Decision

We implement a **three-tier model registry** architecture:

### Tier 1: Simple Aliases (Version-Agnostic)
```
sonnet → (resolves to current model)
claude-sonnet → (resolves to current model)
opus → (resolves to current model)
haiku → (resolves to current model)
```

**Purpose**: Future-proof application code. When Claude 5, 6, etc. are released, these aliases automatically point to the latest recommended model.

**Defined in**: `config.yaml` → `current_models` section

### Tier 2: Model Family IDs
```
claude-4-5-sonnet → claude-sonnet-4-5-20250929
claude-4-5-opus → claude-opus-4-5-20251101
```

**Purpose**: Reference a specific model family while allowing patch updates.

**Defined in**: Individual model YAML files → `id` field

### Tier 3: Versioned API IDs (Immutable)
```
claude-sonnet-4-5-20250929
claude-opus-4-5-20251101
```

**Purpose**: Exact, immutable model reference. Pricing is tied to this level.

**Defined in**: Individual model YAML files → `api_name` field

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Code                              │
│                                                                      │
│   model: "sonnet"  │  model: "claude-sonnet"  │  model: "opus"      │
└────────┬───────────┴────────────┬─────────────┴─────────┬───────────┘
         │                        │                       │
         ▼                        ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    config.yaml (current_models)                      │
│                                                                      │
│   current_models:                                                    │
│     sonnet: claude-4-5-sonnet    ◄── Simple alias → Model ID        │
│     haiku: claude-4-5-haiku                                         │
│     opus: claude-4-5-opus                                           │
└────────┬───────────────────────────────────────────────┬────────────┘
         │                                               │
         ▼                                               ▼
┌────────────────────────────┐        ┌────────────────────────────────┐
│  claude-4-5-sonnet.yaml    │        │     claude-4-5-opus.yaml       │
│                            │        │                                │
│  id: claude-4-5-sonnet     │        │  id: claude-4-5-opus           │
│  api_name: claude-sonnet-  │        │  api_name: claude-opus-4-5-    │
│    4-5-20250929            │        │    20251101                    │
│                            │        │                                │
│  pricing:                  │        │  pricing:                      │
│    input: $3/MTok          │        │    input: $5/MTok              │
│    output: $15/MTok        │        │    output: $25/MTok            │
└────────────────────────────┘        └────────────────────────────────┘
         │                                               │
         ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Anthropic API                                │
│                                                                      │
│   model: "claude-sonnet-4-5-20250929"  (immutable, versioned)       │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Relationships

| Relationship | Source | Target | Notes |
|--------------|--------|--------|-------|
| Simple Alias → Model ID | `config.yaml` | Model YAML `id` | Change this to upgrade |
| Model ID → API Name | Model YAML `id` | Model YAML `api_name` | Fixed per file |
| API Name → Pricing | Model YAML `api_name` | Model YAML `pricing` | Immutable relationship |

## Upgrade Process

When Anthropic releases Claude 5:

1. **Create new model file**: `claude-5-sonnet.yaml`
   ```yaml
   id: claude-5-sonnet
   api_name: claude-sonnet-5-20260315
   pricing:
     input_per_1m_tokens: 3.50  # May change
     output_per_1m_tokens: 17.50
   ```

2. **Update `config.yaml`**:
   ```yaml
   current_models:
     sonnet: claude-5-sonnet  # Changed from claude-4-5-sonnet
   ```

3. **Move old model to legacy**:
   ```yaml
   legacy_status:
     - claude-4-5  # Add to legacy list
   ```

4. **Applications using `sonnet` alias automatically get Claude 5**

## Consequences

### Positive
- Applications use stable aliases (`sonnet`, `opus`) that survive model upgrades
- Pricing stays accurate because it's tied to immutable API IDs
- Clear upgrade path when new models are released
- Supports both "latest" and "pinned" use cases

### Negative
- Additional indirection layer to understand
- Must keep model files updated when providers release new versions
- Applications using aliases may experience behavior changes on upgrade

### Mitigations
- Document the architecture clearly (this ADR)
- Add comments in `config.yaml` explaining the relationship
- Provide tooling to validate model configurations
- Log which actual API ID is being used at runtime

## References

- [Anthropic Models Overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- ADR-004: Provider-Scoped Models
- ADR-009: Versioned Primitives
