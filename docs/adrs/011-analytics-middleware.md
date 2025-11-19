# ADR-011: Analytics Middleware for Hook System

```yaml
---
status: accepted
created: 2025-11-19
updated: 2025-11-19
deciders: System Architect
consulted: Development Team, Analytics Team
informed: All Stakeholders
---
```

## Context

The agentic-primitives system supports multiple AI providers (Claude, OpenAI, Cursor, Gemini) through a flexible hook system. Each provider emits lifecycle events (SessionStart, PreToolUse, PostToolUse, etc.) that currently serve safety and observability purposes.

We need to add **analytics capabilities** to understand:
- How agents use tools across providers
- Session patterns and duration
- User interaction frequency
- Permission request patterns
- Error rates and failure modes

### Current State

The hook system (ADR-006) supports two middleware types:
- **Safety**: Block dangerous operations (sequential, fail-fast)
- **Observability**: Log and emit metrics (parallel, non-blocking)

However, observability middleware is focused on real-time monitoring, not long-term analytics aggregation.

### Requirements

1. **Provider-Agnostic**: Work with any provider without hardcoding names
2. **Type-Safe**: Validate all data with strong typing
3. **Extensible**: Easy to add new providers and backends
4. **Non-Blocking**: Analytics failures shouldn't affect agent execution
5. **Normalized Schema**: Consistent event format regardless of provider
6. **Multiple Backends**: Support file (JSONL), API, and future backends (Redis, Kafka)

### Constraints

- Must integrate with existing hook system
- Python implementation for data transformations (better than Rust for this use case)
- No breaking changes to existing hooks
- <10ms overhead per event
- TDD with >80% test coverage (>90% for core logic)

## Decision

We will implement a **provider-agnostic analytics system** using the port & adapter pattern with two-stage middleware:

### Architecture

```
Provider Hook Event (JSON stdin)
        ↓
┌─────────────────────────────────────┐
│   Stage 1: Event Normalizer         │
│   (Input Adapter)                   │
│   - Validate provider-specific JSON │
│   - Map to normalized schema        │
│   - Extract analytics context       │
│   - Output: NormalizedEvent         │
└────────────┬────────────────────────┘
             │ stdout (JSON)
             ▼
┌─────────────────────────────────────┐
│   Stage 2: Event Publisher           │
│   (Output Adapter)                   │
│   - Validate normalized event        │
│   - Publish to backend(s)            │
│   - Handle retries/errors            │
│   - Backend: file, API, etc.         │
└─────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Provider Agnostic

**No hardcoded provider enums** in analytics code:

```python
# ❌ BAD: Creates coupling
provider: Literal["claude", "openai", "cursor", "gemini"]

# ✅ GOOD: Provider-agnostic
provider: str = Field(
    default="unknown",
    description="Provider name set by hook caller"
)
```

Provider names are determined by the hook system, not validated by analytics. This means:
- Single source of truth for providers (`primitives.config.yaml`, `specs/v1/model-config.schema.json`)
- Adding new providers doesn't require analytics changes
- System automatically works with custom providers

#### 2. Port & Adapter Pattern

```
Input Adapters (Provider-Specific)
- ClaudeAdapter: Claude hook format → NormalizedEvent
- OpenAIAdapter: OpenAI hook format → NormalizedEvent
- Future: CursorAdapter, GeminiAdapter, etc.

Core Domain (Provider-Agnostic)
- Pydantic models for type safety
- Event normalization logic
- Business rules

Output Adapters (Backend-Specific)
- FilePublisher: Write to JSONL
- APIPublisher: HTTP POST to API
- Future: RedisPublisher, KafkaPublisher, etc.
```

#### 3. Two-Stage Middleware

**Why two stages instead of one?**

- **Separation of Concerns**: Normalization and publishing are distinct responsibilities
- **Testability**: Each stage can be tested independently
- **Flexibility**: Swap backends without changing normalization
- **Pipeline Composition**: Can insert additional stages (filtering, enrichment, etc.)
- **Debugging**: Inspect normalized events between stages

#### 4. Pydantic for Type Safety

All data validated with Pydantic v2:

```python
# Hook input validation
hook_input = HookInput.model_validate(stdin_data)

# Normalized event validation
normalized = NormalizedEvent(
    event_type="tool_execution_started",
    timestamp=datetime.now(),
    session_id=hook_input.data["session_id"],
    provider=hook_input.provider,
    context=ToolExecutionContext(
        tool_name=hook_input.data["tool_name"],
        tool_input=hook_input.data["tool_input"],
    ),
    metadata=EventMetadata(
        hook_event_name=hook_input.event,
        transcript_path=hook_input.data.get("transcript_path"),
    ),
)
```

Benefits:
- Runtime validation catches errors early
- Auto-generate JSON schemas
- IDE autocomplete and type hints
- Clear error messages for invalid data

#### 5. Analytics as MiddlewareType

Extend the Rust hook system with a new middleware type:

```rust
pub enum MiddlewareType {
    Safety,       // Blocking, fail-fast
    Observability, // Non-blocking, best-effort
    Analytics,     // Non-blocking, best-effort (new)
}
```

Analytics middleware behaves like observability:
- Runs in parallel with other middleware
- Errors don't block agent execution
- Results logged but don't affect decisions

### Event Schema

Normalized events follow a consistent structure:

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:34:56.789Z",
  "session_id": "abc123-def456",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {
      "file_path": "src/main.py",
      "contents": "print('Hello, World!')"
    },
    "tool_use_id": "toolu_01ABC123"
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/path/to/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/Users/dev/project"
}
```

### Event Type Mapping

| Hook Event         | Analytics Event Type      | Context Data                  |
|--------------------|---------------------------|-------------------------------|
| SessionStart       | session_started           | source (startup/resume)       |
| SessionEnd         | session_completed         | reason, duration              |
| UserPromptSubmit   | user_prompt_submitted     | prompt, prompt_length         |
| PreToolUse         | tool_execution_started    | tool_name, tool_input         |
| PostToolUse        | tool_execution_completed  | tool_name, tool_response      |
| PermissionRequest  | permission_requested      | tool_name, decision           |
| Stop               | agent_stopped             | stop_hook_active              |
| SubagentStop       | subagent_stopped          | stop_hook_active              |
| Notification       | system_notification       | notification_type, message    |
| PreCompact         | context_compacted         | trigger (manual/auto)         |

## Alternatives Considered

### Alternative 1: Direct Provider Integration

**Description**: Implement analytics directly in provider transformers (Claude, OpenAI, etc.)

**Pros**:
- No separate middleware needed
- Direct access to provider internals
- Potentially lower latency

**Cons**:
- **Tight coupling**: Each provider needs analytics code
- **Duplication**: Same logic repeated per provider
- **Maintenance burden**: Changes require updating all providers
- **Not extensible**: Hard to add new backends

**Reason for rejection**: Violates DRY principle and creates maintenance burden

### Alternative 2: Message Queue Architecture

**Description**: Publish events to message queue (Redis Streams, Kafka), separate consumer processes events

**Pros**:
- Truly decoupled
- Scalable for high volume
- Async processing
- Multiple consumers possible

**Cons**:
- **Over-engineering**: Too complex for v1
- **Infrastructure dependency**: Requires Redis/Kafka
- **Operational overhead**: More services to manage
- **Latency**: Additional network hop

**Reason for rejection**: YAGNI (You Aren't Gonna Need It) - start simple, add message queue later if needed

### Alternative 3: Embedded Rust Analytics

**Description**: Implement analytics in Rust, embedded in CLI

**Pros**:
- Single-language codebase
- Potentially faster
- No Python dependency

**Cons**:
- **Less flexible**: Rust harder for data transformations
- **Steeper learning curve**: More developers know Python
- **Integration challenges**: Provider-specific logic in Rust more complex
- **Pydantic benefits lost**: No auto schema generation

**Reason for rejection**: Python better suited for data transformation and has richer ecosystem for analytics

### Alternative 4: Dynamic Provider Enum

**Description**: Load provider names from config at runtime, validate in analytics

**Pros**:
- Some validation of provider names
- Still somewhat extensible

**Cons**:
- **Complexity**: Runtime enum generation is complex
- **Not truly provider-agnostic**: Still coupled to provider list
- **Unnecessary**: Hook system already validates providers

**Reason for rejection**: Adds complexity without meaningful benefits

## Consequences

### Positive Consequences

✅ **Provider Agnostic**: Adding new providers requires zero analytics code changes

✅ **Type Safe**: Pydantic catches data errors at runtime with clear messages

✅ **Testable**: Each component (adapters, normalizer, publishers) tested independently

✅ **Extensible**: Easy to add new backends (Redis, Kafka, etc.)

✅ **Non-Blocking**: Analytics failures don't affect agent execution

✅ **Normalized Schema**: Consistent format enables cross-provider analytics

✅ **Future-Proof**: Port & adapter pattern accommodates future requirements

✅ **Developer Friendly**: Python better than Rust for data transformations

✅ **Auto-Documentation**: Pydantic generates JSON schema automatically

### Negative Consequences

⚠️ **Additional Complexity**: Two-stage middleware more complex than single stage

⚠️ **Python Dependency**: Requires Python 3.11+ and uv

⚠️ **Performance Overhead**: Pydantic validation adds ~1-2ms per event

⚠️ **Multi-Language**: Rust + Python increases cognitive load

⚠️ **No Provider Validation**: Analytics doesn't validate provider names

### Neutral Consequences

ℹ️ **Two Middleware Stages**: Some hooks will have normalizer + publisher

ℹ️ **Environment Variables**: Configuration via ANALYTICS_* env vars

ℹ️ **JSONL Format**: File backend uses line-delimited JSON

### Mitigations

1. **Complexity**: Comprehensive documentation and examples (this ADR, integration guide)
2. **Python Dependency**: Use uv for fast, reproducible Python environments
3. **Performance**: Benchmark and optimize hot paths, use `model_validate()` only at boundaries
4. **Multi-Language**: Clear separation of concerns, Python only for analytics
5. **Provider Validation**: Hook system validates providers before analytics sees events

## Implementation Notes

### Directory Structure

```
services/analytics/
├── pyproject.toml              # uv project config
├── uv.lock                     # Locked dependencies
├── src/analytics/
│   ├── models/
│   │   ├── hook_input.py       # Provider-specific input models
│   │   ├── events.py           # Normalized event models
│   │   └── config.py           # Configuration models
│   ├── adapters/
│   │   ├── base.py             # Abstract adapter interface
│   │   ├── claude.py           # Claude adapter
│   │   └── openai.py           # OpenAI adapter (future)
│   ├── normalizer.py           # Event normalization logic
│   └── publishers/
│       ├── base.py             # Abstract publisher interface
│       ├── file.py             # File backend (JSONL)
│       └── api.py              # API backend (HTTP POST)
├── middleware/
│   ├── event_normalizer.py     # Stage 1: Normalize events
│   └── event_publisher.py      # Stage 2: Publish events
└── tests/
    ├── fixtures/               # Test data
    ├── test_models.py          # Pydantic model tests
    ├── test_adapters.py        # Adapter tests
    ├── test_normalizer.py      # Normalizer tests
    └── test_publishers.py      # Publisher tests
```

### Rust Integration

```rust
// cli/src/primitives/hook.rs
pub enum MiddlewareType {
    Safety,
    Observability,
    Analytics,  // Add this
}
```

```json
// specs/v1/hook-meta.schema.json
{
  "middleware": {
    "type": {
      "enum": ["safety", "observability", "analytics"]
    }
  }
}
```

### Hook Configuration Example

```yaml
# primitives/v1/hooks/analytics/analytics-collector/hook.meta.yaml
version: 1
id: analytics-collector
name: "Analytics Event Collector"
description: "Collects and normalizes hook events for analytics"
events:
  - PreToolUse
  - PostToolUse
  - SessionStart
  - SessionEnd
  - UserPromptSubmit
  - PermissionRequest
  - Stop
  - SubagentStop
  - Notification
  - PreCompact

middleware:
  - name: "analytics-normalizer"
    type: analytics
    impl: python
    path: "../../services/analytics/middleware/event_normalizer.py"
    env:
      ANALYTICS_PROVIDER: "claude"
  
  - name: "analytics-publisher"
    type: analytics
    impl: python
    path: "../../services/analytics/middleware/event_publisher.py"
    env:
      ANALYTICS_PUBLISHER_BACKEND: "file"
      ANALYTICS_OUTPUT_PATH: "./analytics/events.jsonl"

execution: pipeline
```

### Environment Variables

```bash
# Normalizer stage
export ANALYTICS_PROVIDER=claude          # Set by hook system

# Publisher stage
export ANALYTICS_PUBLISHER_BACKEND=file   # or "api"
export ANALYTICS_OUTPUT_PATH=./events.jsonl
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3
export ANALYTICS_DEBUG=false
```

### Migration Path

1. **Phase 1**: Foundation (Pydantic models, JSON schema) ✅ COMPLETE
2. **Phase 2**: Core Logic (normalizer, adapters, publishers)
3. **Phase 3**: Rust Integration (middleware type, schemas)
4. **Phase 4**: System-Level Hook (analytics-collector primitive)
5. **Phase 5**: Provider Transformers (include analytics in build)

No breaking changes to existing hooks. Analytics is additive.

## Success Criteria

Analytics middleware is successful when:

1. ✅ Works with any provider without code changes
2. ✅ >90% test coverage for normalization logic
3. ✅ >80% test coverage for publishers
4. ✅ <10ms performance overhead per event
5. ✅ Fails gracefully without blocking agent execution
6. ✅ Normalized schema consistent across all providers
7. ✅ Easy to add new backends (file, API, Redis, Kafka)
8. ✅ Comprehensive documentation with examples

## Related Decisions

- **ADR-004: Provider-Scoped Models** - Provider naming and discovery
- **ADR-005: Polyglot Implementations** - Python for analytics (type: python)
- **ADR-006: Middleware-Based Hooks** - Foundation for analytics middleware
- **ADR-008: Test-Driven Development** - TDD approach used for analytics

## References

- [Ports and Adapters Pattern](https://alistair.cockburn.us/hexagonal-architecture/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [Claude Hooks Reference](https://code.claude.com/docs/en/hooks)
- [OpenTelemetry for inspiration](https://opentelemetry.io/)

## Notes

### Why Not OpenTelemetry?

OpenTelemetry is designed for distributed tracing and metrics, not for capturing detailed business events from AI agents. We need:
- Rich, provider-specific context (tool inputs, prompts, etc.)
- Normalized schema across providers
- Simple file-based storage for v1
- Lightweight integration without OTLP overhead

OpenTelemetry might be useful later for infrastructure metrics, but not for analytics events.

### Provider Agnostic Philosophy

This decision embodies a core principle: **analytics should not know about providers**.

The hook system knows which provider triggered an event. The hook system passes this information to analytics. Analytics treats it as an opaque string tag.

This inverts the dependency: providers depend on hook system, hook system depends on nothing, analytics depends on hook system. Analytics never depends on providers.

### Future Enhancements

Possible future additions without breaking changes:
- Event filtering (sample rates, allowlists)
- Event enrichment (user info, project metadata)
- Batching for high-volume scenarios
- Compression for file backend
- Event replay for debugging
- Real-time streaming to dashboard

All can be added through new adapters or configuration without changing core architecture.

---

**Status**: Accepted  
**Last Updated**: 2025-11-19
