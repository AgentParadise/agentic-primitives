# Analytics Service Architecture

## Design Principles

### 1. **Provider Agnostic**

The analytics service is **truly provider-agnostic** and does not hardcode provider names. This follows the DRY principle and keeps the codebase maintainable.

#### Why No Provider Enum?

**Problem**: Originally, we had:
```python
provider: Literal["claude", "openai", "cursor", "gemini"]
```

This creates **WET code** (Write Everything Twice):
- Provider list in `specs/v1/model-config.schema.json`
- Provider list in `analytics/models/config.py`
- Provider list in `analytics/models/hook_input.py`

**Solution**: Provider-agnostic string field:
```python
provider: str = Field(
    default="unknown",
    description="Provider name set by hook caller"
)
```

**Benefits**:
1. ✅ **Single Source of Truth**: Providers defined only in `primitives.config.yaml` and `specs/v1/model-config.schema.json`
2. ✅ **No Maintenance Burden**: Adding new providers doesn't require analytics changes
3. ✅ **Future-Proof**: System works with any provider, including custom ones
4. ✅ **Loose Coupling**: Analytics doesn't depend on provider implementations

#### Provider Determination Flow

```
1. Hook System (Rust) knows which provider triggered the hook
   ↓
2. Hook System passes provider name in stdin JSON
   ↓
3. Analytics validates JSON structure (not provider enum)
   ↓
4. Analytics normalizes event with provider metadata
   ↓
5. Backend stores event with provider tag
```

### 2. **Port & Adapter Pattern**

The analytics system uses ports and adapters for extensibility:

```
┌─────────────────────────────────────┐
│   INPUT ADAPTERS (Provider-Specific) │
│   - Claude Adapter                   │
│   - OpenAI Adapter (future)          │
│   - Cursor Adapter (future)          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      CORE DOMAIN (Provider-Agnostic)│
│      - Event Normalizer              │
│      - Business Logic                │
│      - Type Validation (Pydantic)    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   OUTPUT ADAPTERS (Backend-Specific) │
│   - File Publisher (JSONL)           │
│   - API Publisher (HTTP POST)        │
│   - Future: Redis, Kafka, etc.       │
└─────────────────────────────────────┘
```

**Key Points**:
- Input adapters **know** about provider-specific formats
- Core domain is **completely provider-agnostic**
- Output adapters **don't care** about providers

### 3. **Type Safety**

All models use **Pydantic v2** with strict validation:

```python
# Hook input validation
hook_input = ClaudePreToolUseInput.model_validate(stdin_data)

# Normalized event validation
normalized = NormalizedEvent(
    event_type="tool_execution_started",
    provider=hook_input.session_id.split("-")[0],  # Example
    # ...
)
```

**Guarantees**:
- ✅ Runtime validation of all data
- ✅ Type-safe transformations
- ✅ Automatic JSON schema generation
- ✅ IDE autocomplete and type hints

### 4. **Configuration Strategy**

Configuration uses environment variables for flexibility:

```bash
# Runtime configuration (can vary per deployment)
export ANALYTICS_PROVIDER=claude           # Set by hook caller
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./events.jsonl

# System configuration (defined in repo)
# See: primitives.config.yaml
providers:
  enabled:
    - claude
    - openai
    - cursor
```

**Separation of Concerns**:
- **Analytics Config**: Runtime behavior (where to write, timeout, etc.)
- **Primitives Config**: System structure (which providers exist)
- **Provider Discovery**: Dynamic (scan `providers/` directory)

## Architecture Decisions

### ADR: Provider-Agnostic Analytics

**Status**: Implemented  
**Date**: 2025-11-19

**Context**:
The analytics system needs to work with multiple providers (Claude, OpenAI, Cursor, Gemini) without creating coupling or duplication.

**Decision**:
Use string-based provider identification instead of enum validation in analytics models.

**Consequences**:
- ✅ No hardcoded provider lists in analytics code
- ✅ System automatically works with new providers
- ✅ Single source of truth for provider configuration
- ⚠️ Provider names not validated by analytics (validated by hook system)

**Alternatives Considered**:
1. **Enum validation**: Rejected - creates WET code
2. **Dynamic enum from config**: Rejected - complex, unnecessary
3. **Provider registry pattern**: Rejected - over-engineering (YAGNI)

## Data Flow

### Hook Event → Normalized Event

```python
# 1. Hook input (provider-specific)
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "Write",
  "tool_input": {...},
  "provider": "claude"  # Set by hook caller
}

# 2. Validation (input adapter)
hook_input = ClaudePreToolUseInput.model_validate(data)

# 3. Normalization (core domain)
normalized = normalize_claude_event(hook_input)

# 4. Normalized event (provider-agnostic)
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56Z",
  "session_id": "abc123",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {...}
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    ...
  }
}

# 5. Publishing (output adapter)
write_jsonl(normalized)  # or post_to_api(normalized)
```

## Extension Points

### Adding a New Provider

No analytics code changes needed! Just:

1. Create provider adapter (if format differs)
2. Add provider to `primitives.config.yaml`
3. Hook system passes provider name in events

Example:
```python
# services/analytics/src/analytics/adapters/new_provider.py
def normalize_new_provider_event(data: dict) -> NormalizedEvent:
    """Normalize NewProvider events to standard format"""
    # Map NewProvider format → NormalizedEvent
    pass
```

### Adding a New Backend

Implement the publisher interface:

```python
# services/analytics/src/analytics/publishers/custom.py
from analytics.models import NormalizedEvent

async def publish_to_custom_backend(event: NormalizedEvent) -> None:
    """Publish event to custom backend"""
    # Your implementation
    pass
```

## Testing Strategy

1. **Model Tests**: Validate Pydantic models (97% coverage)
2. **Adapter Tests**: Test provider-specific transformations
3. **Integration Tests**: End-to-end flow with fixtures
4. **Property Tests**: Verify invariants hold for all providers

## Performance Considerations

- **Async I/O**: All publishers use async for non-blocking writes
- **Batching**: Future enhancement for high-volume scenarios
- **Validation Caching**: Pydantic models compile schemas once
- **Memory Efficiency**: Stream processing, no buffering

## Security

- **Input Validation**: All data validated before processing
- **No Secrets in Events**: Filter sensitive data in adapters
- **Configurable Backends**: Choose where data is stored
- **Audit Trail**: Metadata tracks event provenance

## Related Documentation

- [README.md](./README.md) - Usage and getting started
- [../../primitives.config.yaml](../../primitives.config.yaml) - Provider configuration
- [../../specs/v1/model-config.schema.json](../../specs/v1/model-config.schema.json) - Provider schema
- [../../docs/adrs/004-provider-scoped-models.md](../../docs/adrs/004-provider-scoped-models.md) - Provider naming

