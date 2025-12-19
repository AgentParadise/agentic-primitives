"""Simple JSONL event emission for AI agents.

This package provides a lightweight event system for AI agent observability.
Zero external dependencies - uses only Python stdlib.

Example:
    >>> from agentic_events import EventEmitter, EventType
    >>>
    >>> emitter = EventEmitter(session_id="session-123")
    >>> emitter.tool_started("Bash", "toolu_abc", "git status")
    >>> emitter.tool_completed("Bash", "toolu_abc", success=True, duration_ms=150)
"""

from agentic_events.buffer import BatchBuffer, enrich_event, parse_jsonl_line
from agentic_events.emitter import EventEmitter
from agentic_events.types import EventType, SecurityDecision, SessionSource

__all__ = [
    # Core
    "EventEmitter",
    "EventType",
    # Types
    "SecurityDecision",
    "SessionSource",
    # Buffer utilities (for AEF)
    "BatchBuffer",
    "parse_jsonl_line",
    "enrich_event",
]

__version__ = "0.1.0"
