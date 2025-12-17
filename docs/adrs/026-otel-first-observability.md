---
title: "ADR-026: OTel-First Observability Architecture"
status: accepted
created: 2025-12-17
updated: 2025-12-17
author: Neural
supersedes: ADR-011
---

# ADR-026: OTel-First Observability Architecture

## Status

**Accepted**

- Created: 2025-12-17
- Updated: 2025-12-17
- Author(s): Neural
- Supersedes: ADR-011 (Analytics Middleware)

## Context

The agentic-primitives library previously used a custom observability stack:

1. **`agentic_analytics`** - Custom event schemas, JSONL storage
2. **`agentic_hooks`** - Custom hook client with HTTP/JSONL backends
3. **`agentic_observability`** - Custom `ObservabilityPort` protocol

This approach had several problems:

1. **Duplication**: Every platform (AEF, custom apps) rebuilt observability pipelines
2. **Non-standard**: Custom schemas require custom dashboards/alerting
3. **Limited ecosystem**: No integration with existing APM tools
4. **Agent runtime mismatch**: Claude CLI has native OTel support we weren't leveraging

The Claude Code CLI exports telemetry via OpenTelemetry (OTel) when configured with:
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

This native OTel support means:
- Token usage metrics are already instrumented
- Tool executions emit spans
- All standard OTel tooling works (Jaeger, Prometheus, Grafana)

## Decision

We will adopt an **OTel-first observability architecture**:

1. **New `agentic_otel` package** with:
   - `OTelConfig`: Configuration dataclass with `to_env()` for CLI injection
   - `HookOTelEmitter`: Emit OTel spans/events from hook scripts
   - `AgentSemanticConventions`: Standard attribute names for agent telemetry

2. **Updated `agentic_adapters`** with:
   - `ClaudeCLIRunner`: Execute Claude CLI with OTel environment injection
   - OTel backend option in `generate_hooks()`

3. **Deprecated packages** (emit warnings, to be removed):
   - `agentic_observability` - Removed entirely
   - `agentic_analytics` - Removed entirely
   - `agentic_hooks` - Deprecated, use OTel emitter
   - `agentic_agent` - Deprecated, use `ClaudeCLIRunner`

4. **Hook handlers emit OTel** instead of JSONL:
   - `pre-tool-use.py` → OTel span with security decision
   - `post-tool-use.py` → OTel span with tool result

## Alternatives Considered

### Alternative 1: Enhance Custom Analytics

**Description**: Keep `agentic_analytics` and add more backends (PostgreSQL, ClickHouse)

**Pros**:
- No breaking changes
- Full control over schema

**Cons**:
- Continues duplication across platforms
- No ecosystem integration
- Must maintain custom dashboards

**Reason for rejection**: Claude CLI already emits OTel; fighting the platform.

### Alternative 2: Dual Output (OTel + JSONL)

**Description**: Emit both OTel and legacy JSONL formats

**Pros**:
- Backward compatible
- Gradual migration

**Cons**:
- Double the complexity
- Confusion about which is canonical
- Performance overhead

**Reason for rejection**: Alpha stage - clean break is acceptable.

## Consequences

### Positive Consequences

- **Standard tooling**: Use Jaeger, Prometheus, Grafana out of the box
- **Reduced code**: No custom analytics pipeline to maintain
- **Better correlation**: OTel trace context propagates across services
- **Future-proof**: OpenTelemetry is the industry standard

### Negative Consequences

- **Breaking change**: Legacy backends no longer work
- **Learning curve**: Teams must learn OTel concepts
- **Infrastructure**: Requires OTel Collector deployment

### Neutral Consequences

- Package structure changes significantly
- Hook handlers rewritten for OTel

## Implementation Notes

### Package Structure

```
lib/python/
├── agentic_otel/           # NEW
│   ├── config.py           # OTelConfig dataclass
│   ├── emitter.py          # HookOTelEmitter
│   └── conventions.py      # AgentSemanticConventions
├── agentic_adapters/
│   └── claude_cli/
│       └── runner.py       # ClaudeCLIRunner with OTel
└── [DEPRECATED]
    ├── agentic_observability/
    ├── agentic_analytics/
    └── agentic_hooks/
```

### OTelConfig Usage

```python
from agentic_otel import OTelConfig

config = OTelConfig(
    endpoint="http://localhost:4317",
    service_name="my-agent",
    resource_attributes={"agent.task": "code-review"},
)

# Inject into Claude CLI environment
env = config.to_env()
# Returns: {"OTEL_EXPORTER_OTLP_ENDPOINT": "...", ...}
```

### HookOTelEmitter Usage

```python
from agentic_otel import HookOTelEmitter

emitter = HookOTelEmitter.from_env()
emitter.emit_tool_decision(
    tool_name="Bash",
    allowed=False,
    reason="Blocked by security policy",
)
```

### Migration Path

1. Deploy OTel Collector in infrastructure
2. Update hook handlers to use `HookOTelEmitter`
3. Configure agents with `OTEL_EXPORTER_OTLP_ENDPOINT`
4. Remove JSONL file collection
5. Point dashboards at OTel backends (Prometheus, Jaeger)

## References

- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)
- [Claude CLI Headless Mode](https://code.claude.com/docs/en/headless)
- ADR-011: Analytics Middleware (superseded)
- ADR-017: Hook Client Library
- ADR-025: Universal Agent Integration Layer
