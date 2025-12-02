"""agentic-hooks: High-performance async hook client for agent swarms.

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

from agentic_hooks.client import HookClient
from agentic_hooks.events import EventType, HookEvent

__all__ = [
    "HookClient",
    "HookEvent",
    "EventType",
]

__version__ = "0.1.0"
