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
    >>> from agentic_events import Recording, load_recording
    >>>
    >>> # Type-safe loading - MyPy catches typos
    >>> player = load_recording(Recording.SIMPLE_BASH)
    >>> for event in player.get_events():
    ...     await store.insert_one(event)
    >>>
    >>> # With workspace files (directory format)
    >>> player = load_recording(Recording.ARTIFACT_WORKFLOW)
    >>> if player.has_workspace:
    ...     files = player.get_workspace_files()
"""

from agentic_events.buffer import BatchBuffer, enrich_event, parse_jsonl_line
from agentic_events.emitter import EventEmitter
from agentic_events.fixtures import (
    Recording,
    get_recordings_dir,
    list_recordings,
    load_recording,
    load_recording_by_name,
    load_recording_by_path,
)
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
    # Fixture helpers (ADR-030) - type-safe
    "Recording",  # Enum for type-safe recording names
    "load_recording",  # Type-safe loading
    "load_recording_by_name",  # String-based escape hatch
    "load_recording_by_path",  # Path-based escape hatch
    "get_recordings_dir",
    "list_recordings",
]

__version__ = "0.1.0"
