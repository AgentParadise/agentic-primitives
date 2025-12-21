"""Simple JSONL event emission for AI agents.

This package provides a lightweight event system for AI agent observability.
Zero external dependencies - uses only Python stdlib.

Example:
    >>> from agentic_events import EventEmitter, EventType
    >>>
    >>> emitter = EventEmitter(session_id="session-123")
    >>> emitter.tool_started("Bash", "toolu_abc", "git status")
    >>> emitter.tool_completed("Bash", "toolu_abc", success=True, duration_ms=150)

Recording and playback for testing (ADR-030):
    >>> from agentic_events import SessionRecorder, SessionPlayer
    >>>
    >>> # Record a session
    >>> with SessionRecorder(
    ...     "recording.jsonl", cli_version="1.0.52", model="claude-3-5-sonnet"
    ... ) as rec:
    ...     rec.record({"event_type": "session_started", ...})
    >>>
    >>> # Play back for tests
    >>> player = SessionPlayer("recording.jsonl")
    >>> for event in player.get_events():
    ...     await store.insert_one(event)
"""

from agentic_events.buffer import BatchBuffer, enrich_event, parse_jsonl_line
from agentic_events.emitter import EventEmitter
from agentic_events.fixtures import get_recordings_dir, list_recordings, load_recording
from agentic_events.player import RecordingMetadata, SessionPlayer
from agentic_events.recorder import SessionRecorder
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
    # Recording/playback (ADR-030)
    "SessionRecorder",
    "SessionPlayer",
    "RecordingMetadata",
    # Fixture helpers (ADR-030)
    "get_recordings_dir",
    "list_recordings",
    "load_recording",
]

__version__ = "0.1.0"
