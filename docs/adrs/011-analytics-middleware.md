---
title: "ADR-011: Analytics Middleware Architecture"
status: accepted
created: 2025-11-19
updated: 2025-11-19
author: AI Assistant (with user guidance)
supersedes: null
superseded_by: null
tags: [analytics, middleware, hooks, provider-agnostic, architecture]
---

# ADR-011: Analytics Middleware Architecture

## Status

**Accepted**

- Created: 2025-11-19
- Updated: 2025-11-19
- Author(s): AI Assistant (with user guidance)

## Context

The agentic-primitives system needs to capture analytics data from various providers (Claude, OpenAI, Cursor, Gemini) to understand system behavior, usage patterns, and performance metrics. This data is critical for:

1. **Operational Monitoring**: Track tool usage, session patterns, and errors
2. **Performance Analysis**: Measure latency, throughput, and resource usage
3. **User Behavior**: Understand how agents interact with the system
4. **Debugging**: Investigate issues through event replay and correlation

### Challenges

1. **Provider Diversity**: Each provider has different hook event formats
2. **DRY Principle**: Avoid duplicating provider lists across the codebase
3. **Type Safety**: Ensure runtime validation without sacrificing flexibility
4. **Extensibility**: Support new providers without code changes
5. **Decoupling**: Analytics shouldn't depend on provider implementations

### Key Insight

During implementation, we recognized that hardcoding provider names in analytics configuration violates DRY:
- Provider enum in `specs/v1/model-config.schema.json`
- Provider enum in analytics configuration
- Maintenance burden when adding providers

**Question posed**: "Does it make sense to put providers in the analytics config when we have the model config already?"

**Answer**: No! The analytics system should be **truly provider-agnostic**.

## Decision

We will implement an analytics middleware system using the **Port & Adapter pattern** with **provider-agnostic** core logic:

### Core Principles

1. **Provider-Agnostic Core**: No hardcoded provider enums in analytics code
2. **Port & Adapter Pattern**: Input adapters (provider-specific) + Output adapters (backend-specific)
3. **Type Safety with Flexibility**: Use Pydantic for validation, `str` for provider names
4. **Single Source of Truth**: Providers defined only in system configuration
5. **Hook Integration**: Analytics as middleware in existing hook pipeline

### Architecture

```
Provider Hook Events (stdin JSON)
         ↓
  Input Adapters (Provider-Specific)
    - ClaudeAdapter
    - OpenAIAdapter (future)
    - CursorAdapter (future)
         ↓
  Event Normalizer (Provider-Agnostic)
    - Standard event schema
    - Type validation
    - Business logic
         ↓
  Output Adapters (Backend-Specific)
    - FilePublisher (JSONL)
    - APIPublisher (HTTP POST)
    - Future: Redis, Kafka, etc.
         ↓
  Analytics Backend
```

### Provider Field Design

**Before (WET)**:
```python
provider: Literal["claude", "openai", "cursor", "gemini"]
```

**After (DRY)**:
```python
provider: str = Field(
    default="unknown",
    description="Provider name set by hook caller"
)
```

### Technology Stack

- **Language**: Python 3.11+ with uv package manager
- **Validation**: Pydantic v2 with strict mode
- **Configuration**: pydantic-settings for environment variables
- **Type Checking**: mypy with strict mode
- **Testing**: pytest with >80% coverage requirement

## Alternatives Considered

### Alternative 1: Hardcoded Provider Enum

**Description**: Use `Literal["claude", "openai", ...]` throughout analytics code

**Pros**:
- Compile-time validation of provider names
- IDE autocomplete for providers
- Catches typos early

**Cons**:
- Violates DRY (provider list duplicated)
- Maintenance burden (update multiple files for new providers)
- Analytics code depends on provider implementations
- Prevents custom/experimental providers

**Reason for rejection**: Creates WET code and tight coupling. The validation benefit is minimal since provider names come from trusted hook system.

---

### Alternative 2: Dynamic Provider Registry

**Description**: Load provider list from config at runtime, validate against registry

**Pros**:
- Single source of truth
- Runtime validation possible
- Flexible for different deployments

**Cons**:
- Added complexity (registry loading, caching)
- Runtime overhead for validation
- YAGNI - validation not critical for internal system

**Reason for rejection**: Over-engineering. The hook system already knows valid providers, we don't need redundant validation.

---

### Alternative 3: Separate Analytics Service with API

**Description**: Build analytics as standalone microservice with REST API

**Pros**:
- Independent deployment and scaling
- Language-agnostic interface
- Clear boundaries

**Cons**:
- Operational complexity (deployment, monitoring)
- Network latency for each event
- YAGNI for current scale
- Middleware pattern is simpler

**Reason for rejection**: Premature optimization. Start with middleware, evolve to service if needed.

## Consequences

### Positive Consequences

- **DRY Code**: Single source of truth for providers in `primitives.config.yaml`
- **Zero Maintenance**: Adding providers doesn't require analytics changes
- **Future-Proof**: Works with any provider, including custom ones
- **Loose Coupling**: Analytics independent of provider implementations
- **Type Safety**: Full Pydantic validation for data structures (97% coverage)
- **Testability**: Clear boundaries enable comprehensive testing

### Negative Consequences

- **No Compile-Time Provider Validation**: Typos in provider names not caught early
  - **Mitigation**: Hook system validates providers before calling analytics
- **String-Based Identification**: Less type-safe than enums
  - **Mitigation**: Pydantic validates overall structure, provider names are metadata
- **Learning Curve**: Port & adapter pattern requires understanding
  - **Mitigation**: Comprehensive documentation and examples

### Neutral Consequences

- **Provider Discovery**: System discovers providers dynamically
- **Configuration Split**: Runtime config (analytics) vs system config (primitives)
- **Testing Strategy**: Property-based tests for provider agnosticism

## Implementation Notes

### File Structure

```
services/analytics/
├── src/analytics/
│   ├── models/
│   │   ├── hook_input.py      # Provider-specific input models
│   │   ├── events.py           # Normalized event models
│   │   └── config.py           # Configuration (NO provider enum)
│   ├── adapters/
│   │   ├── base.py             # Adapter interface
│   │   ├── claude.py           # Claude-specific logic
│   │   └── openai.py           # OpenAI-specific logic (future)
│   ├── normalizer.py           # Provider-agnostic core
│   └── publishers/
│       ├── base.py             # Publisher interface
│       ├── file.py             # JSONL file publisher
│       └── api.py              # HTTP API publisher
├── middleware/
│   ├── event_normalizer.py    # Entry point for normalization
│   └── event_publisher.py     # Entry point for publishing
└── tests/
    ├── fixtures/
    │   ├── claude_hooks/       # Claude event samples
    │   └── normalized_events/  # Expected outputs
    └── test_*.py               # Comprehensive tests
```

### Migration Path

1. ✅ **Phase 1 (Milestone 1)**: Foundation
   - Pydantic models with provider: str
   - Test fixtures and comprehensive tests
   - JSON schema generation

2. **Phase 2 (Milestone 2-3)**: Implementation
   - Event normalizer with adapters
   - File and API publishers
   - Middleware entry points

3. **Phase 3 (Milestone 4)**: Integration
   - Rust hook system integration
   - Analytics middleware type in hook schema
   - End-to-end testing

4. **Phase 4 (Future)**: Optimization
   - Batching for high-volume scenarios
   - Additional backends (Redis, Kafka)
   - Performance monitoring

### Breaking Changes

None - this is a new system.

### Configuration Example

```bash
# Runtime configuration (environment variables)
export ANALYTICS_PROVIDER=claude           # Set by hook caller
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./events.jsonl

# System configuration (primitives.config.yaml)
providers:
  enabled:
    - claude
    - openai
    - cursor

hooks:
  middleware_types:
    - safety
    - observability  # Analytics is observability middleware
    - analytics      # New type for analytics
```

### Adding New Providers

**No analytics code changes needed!** Just:

1. Add provider to `primitives.config.yaml`
2. Create provider adapter if format differs significantly
3. Hook system passes provider name in events

Example adapter:
```python
# src/analytics/adapters/new_provider.py
from analytics.models import NormalizedEvent

def normalize_new_provider_event(
    hook_input: dict
) -> NormalizedEvent:
    """Map NewProvider format to standard schema"""
    return NormalizedEvent(
        event_type=map_event_type(hook_input["event"]),
        provider="new_provider",  # Just a string!
        # ...
    )
```

## References

- [ADR-006: Middleware Hooks](./006-middleware-hooks.md) - Existing hook system
- [ADR-004: Provider-Scoped Models](./004-provider-scoped-models.md) - Provider naming
- [ADR-008: Test-Driven Development](./008-test-driven-development.md) - Testing approach
- [Port & Adapter Pattern](https://alistair.cockburn.us/hexagonal-architecture/) - Hexagonal Architecture
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/) - Validation framework
- [services/analytics/README.md](../../services/analytics/README.md) - Implementation docs
- [services/analytics/ARCHITECTURE.md](../../services/analytics/ARCHITECTURE.md) - Detailed architecture

### Related Code

- `specs/v1/model-config.schema.json` - Provider enum (source of truth)
- `primitives.config.yaml` - Enabled providers list
- `services/analytics/src/analytics/models/config.py` - Provider: str (not enum!)
- `services/analytics/src/analytics/models/hook_input.py` - Generic wrapper

---

**Status**: Accepted  
**Implementation**: Phase 1 complete (Milestone 1), Phase 2-4 pending  
**Test Coverage**: 97.30% (exceeds 80% requirement)  
**Last Updated**: 2025-11-19

