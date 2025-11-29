"""Agentic Analytics - Event schemas and emission for AI agent systems.

This library provides:
- Canonical event schemas (SessionStarted, TokensUsed, ToolCalled, SessionEnded)
- Event emitter for writing to JSONL files
- Hook decision logging for safety/observability hooks
- Validation utilities for analyzing event streams

Quick Start - Event Emission:
    from agentic_analytics import EventEmitter, SessionStarted, ToolCalled

    emitter = EventEmitter()

    # Using context manager (recommended)
    with emitter.session(model="claude-sonnet-4-5-20250929", provider="anthropic") as session:
        session.tokens_used(input_tokens=100, output_tokens=50)
        session.tool_called("Write", {"file_path": "app.py"})

    # Or emit events directly
    emitter.emit(SessionStarted(
        session_id="sess-123",
        model="claude-sonnet-4-5-20250929",
        provider="anthropic",
    ))

Quick Start - Hook Decisions:
    from agentic_analytics import AnalyticsClient, HookDecision

    analytics = AnalyticsClient()
    analytics.log(HookDecision(
        hook_id="bash-validator",
        event_type="PreToolUse",
        decision="block",
        session_id="abc123",
        reason="Dangerous command",
    ))

Configuration:
    # Default output: .agentic/analytics/events.jsonl
    emitter = EventEmitter()

    # Custom file path
    emitter = EventEmitter(output_path="./custom/events.jsonl")

    # Via environment variable
    # AGENTIC_EVENTS_PATH=./custom/events.jsonl
    emitter = EventEmitter()
"""

from agentic_analytics.client import AnalyticsClient
from agentic_analytics.emitter import EventEmitter, SessionContext, emit, emit_raw
from agentic_analytics.events import (
    AgentEvent,
    AuditContext,
    SessionEnded,
    SessionStarted,
    TokensUsed,
    ToolCalled,
)
from agentic_analytics.models import HookDecision
from agentic_analytics.validation import (
    EventStats,
    ValidationResult,
    analyze_events,
    format_summary,
    load_events,
    validate,
)

__version__ = "0.1.0"

__all__ = [
    # Event schemas (canonical)
    "SessionStarted",
    "TokensUsed",
    "ToolCalled",
    "SessionEnded",
    "AuditContext",
    "AgentEvent",
    # Emitter
    "EventEmitter",
    "SessionContext",
    "emit",
    "emit_raw",
    # Legacy client (for hook decisions)
    "AnalyticsClient",
    "HookDecision",
    # Validation
    "EventStats",
    "ValidationResult",
    "load_events",
    "analyze_events",
    "validate",
    "format_summary",
]
