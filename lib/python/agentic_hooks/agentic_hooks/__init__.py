"""agentic-hooks: High-performance async hook client for agent swarms.

.. deprecated:: 0.2.0
    This package is deprecated in favor of `agentic_otel` which uses
    OpenTelemetry for event emission. The custom JSONL/HTTP backends
    are replaced by OTLP export to OTel Collector.

    Migration:
        # OLD (deprecated)
        from agentic_hooks import HookClient, HookEvent
        async with HookClient(backend=JSONLBackend()) as client:
            await client.emit(HookEvent(...))

        # NEW (recommended)
        from agentic_otel import OTelConfig, HookOTelEmitter
        config = OTelConfig(endpoint="http://collector:4317")
        emitter = HookOTelEmitter(config)
        with emitter.start_tool_span("Bash", tool_use_id, tool_input) as span:
            ...

    See ADR-026: OTel-First Observability for details.

This library provides a lightweight, batched event emission system that
scales to 1000+ concurrent agents without subprocess overhead.

Quick Start:
    from agentic_hooks import HookClient, HookEvent, EventType

    async with HookClient(backend_url="http://localhost:8080") as client:
        await client.emit(HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
        ))

Features:
    - Zero runtime dependencies (core client)
    - Async batching for high throughput
    - Pluggable backends (JSONL, HTTP)
    - Fail-safe: never blocks agent execution
"""

import warnings

warnings.warn(
    "agentic_hooks is deprecated. Use agentic_otel for OTel-first observability. "
    "See ADR-026 for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

from agentic_hooks.client import HookClient
from agentic_hooks.events import EventType, HookEvent

__all__ = [
    "HookClient",
    "HookEvent",
    "EventType",
]

__version__ = "0.1.0"
