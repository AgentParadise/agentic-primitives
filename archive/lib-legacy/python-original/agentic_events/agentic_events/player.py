"""Session player for replaying recorded agent events.

Replays recorded sessions at configurable speed for testing.
See ADR-030: Session Recording for Testing.

Supports two recording formats:
1. Legacy: Single .jsonl file with events
2. Directory: Folder with events.jsonl + workspace/ files

Usage:
    # Load from file or directory
    player = SessionPlayer("fixtures/v1.0.52_claude-3-5-sonnet_task.jsonl")
    player = SessionPlayer("fixtures/artifact-workflow/")  # Directory format

    # Instant playback for unit tests
    for event in player.get_events():
        await store.insert_one(event)

    # Timed playback at 100x speed for integration tests
    await player.play(emit_fn=store.insert_one, speed=100)

    # Access workspace files (directory format only)
    if player.has_workspace:
        files = player.get_workspace_files()
        print(files["artifacts/output/summary.md"])

    # Access metadata
    print(f"Recording has {player.metadata.event_count} events")
    print(f"Original duration: {player.metadata.duration_ms}ms")
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RecordingMetadata:
    """Metadata from a recording file or directory."""

    version: int
    event_schema_version: int
    cli_version: str
    model: str
    provider: str
    task: str
    recorded_at: datetime
    duration_ms: int
    event_count: int
    session_id: str | None
    # New: workspace file info
    has_workspace: bool = False
    workspace_files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordingMetadata:
        """Create from metadata dict."""
        recording = data.get("_recording", data)
        recorded_at = recording.get("recorded_at", "")
        if isinstance(recorded_at, str) and recorded_at:
            recorded_at = datetime.fromisoformat(recorded_at)
        elif not recorded_at:
            recorded_at = datetime.now()

        return cls(
            version=recording.get("version", 1),
            event_schema_version=recording.get("event_schema_version", 0),
            cli_version=recording.get("cli_version", "unknown"),
            model=recording.get("model", "unknown"),
            provider=recording.get("provider", "claude"),
            task=recording.get("task", ""),
            recorded_at=recorded_at,
            duration_ms=recording.get("duration_ms", 0),
            event_count=recording.get("event_count", 0),
            session_id=recording.get("session_id"),
            has_workspace=recording.get("has_workspace", False),
            workspace_files=recording.get("workspace_files", []),
        )


class SessionPlayer:
    """Replay recorded agent sessions for testing.

    Supports two recording formats:
    1. Legacy .jsonl file: Single file with metadata header + events
    2. Directory format: Folder with events.jsonl + workspace/ files

    Provides methods for:
    - Instant playback (get_events) - for unit tests
    - Timed playback (play) - for integration tests
    - Speed control - replay at 10x, 100x, 1000x speed
    - Workspace file access (directory format only)

    Automatically normalizes old event formats to current schema using
    the event_schema_version in recording metadata.

    Attributes:
        metadata: Recording metadata (version, model, duration, etc).
        session_id: The session ID from the recording.
        has_workspace: True if recording includes workspace files.

    Examples:
        Instant playback (unit tests):
        >>> player = SessionPlayer("recording.jsonl")
        >>> events = player.get_events()
        >>> print(f"Recorded {len(events)} events")

        Directory format with workspace:
        >>> player = SessionPlayer("artifact-workflow/")
        >>> if player.has_workspace:
        ...     files = player.get_workspace_files()
        ...     print(files["artifacts/output/summary.md"])

        Timed playback (integration tests):
        >>> async def process_event(event):
        ...     await store.insert(event)
        >>> await player.play(emit_fn=process_event, speed=100)

        Access metadata:
        >>> print(f"CLI version: {player.metadata.cli_version}")
        >>> print(f"Event schema: v{player.metadata.event_schema_version}")
    """

    def __init__(self, recording_path: str | Path) -> None:
        """Load a recording from file or directory.

        Args:
            recording_path: Path to JSONL file or recording directory.
                - File: legacy .jsonl format
                - Directory: must contain events.jsonl, may contain workspace/

        Raises:
            FileNotFoundError: If recording doesn't exist.
            ValueError: If recording format is invalid.
        """
        self._path = Path(recording_path)
        self._events: list[dict[str, Any]] = []
        self._metadata: RecordingMetadata | None = None
        self._workspace_files: dict[str, bytes] = {}
        self._is_directory_format = False

        self._load()

    def _load(self) -> None:
        """Load and parse the recording (file or directory)."""
        if self._path.is_dir():
            self._load_directory()
        else:
            self._load_file()

    def _load_directory(self) -> None:
        """Load recording from directory format."""
        self._is_directory_format = True

        # Load events from events.jsonl
        events_path = self._path / "events.jsonl"
        if not events_path.exists():
            raise ValueError(f"Directory recording missing events.jsonl: {self._path}")

        self._load_events_file(events_path)

        # Load workspace files if present
        workspace_path = self._path / "workspace"
        if workspace_path.exists() and workspace_path.is_dir():
            self._load_workspace(workspace_path)
            # Update metadata with workspace info
            if self._metadata:
                self._metadata.has_workspace = True
                self._metadata.workspace_files = list(self._workspace_files.keys())

    def _load_workspace(self, workspace_path: Path) -> None:
        """Load all files from workspace directory."""
        for file_path in workspace_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(workspace_path)
                self._workspace_files[str(relative_path)] = file_path.read_bytes()

    def _load_file(self) -> None:
        """Load recording from legacy .jsonl file."""
        self._load_events_file(self._path)

    def _load_events_file(self, events_path: Path) -> None:
        """Load events from a JSONL file."""
        with open(events_path) as f:
            lines = f.readlines()

        if not lines:
            raise ValueError(f"Empty recording file: {events_path}")

        # First line should be metadata
        first_line = json.loads(lines[0])
        if "_recording" in first_line:
            self._metadata = RecordingMetadata.from_dict(first_line)
            event_lines = lines[1:]
        else:
            # Old format without metadata header
            self._metadata = RecordingMetadata(
                version=0,
                event_schema_version=0,
                cli_version="unknown",
                model="unknown",
                provider="claude",
                task="",
                recorded_at=datetime.now(),
                duration_ms=0,
                event_count=len(lines),
                session_id=None,
            )
            event_lines = lines

        # Parse events and normalize to current schema
        for line in event_lines:
            line = line.strip()
            if line:
                event = json.loads(line)
                normalized = self._normalize_event(event)
                self._events.append(normalized)

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Normalize old event formats to current schema.

        This allows recordings to work even after schema changes.
        Each schema version migration is handled explicitly.

        Args:
            event: Raw event dict from recording.

        Returns:
            Normalized event dict matching current schema.
        """
        schema_version = self._metadata.event_schema_version if self._metadata else 0

        # Schema v1 (current) - no changes needed
        if schema_version >= 1:
            return event

        # Schema v0 (old format) - migrate if needed
        # Currently no migrations needed, but this is where they would go.
        # Example migration:
        # if "tool_name" in event and "context" not in event:
        #     event = {
        #         "context": {"tool_name": event["tool_name"]},
        #         **{k: v for k, v in event.items() if k != "tool_name"}
        #     }

        return event

    @property
    def metadata(self) -> RecordingMetadata:
        """Recording metadata."""
        if self._metadata is None:
            raise ValueError("Recording not loaded")
        return self._metadata

    @property
    def session_id(self) -> str | None:
        """Session ID from the recording."""
        return self.metadata.session_id

    @property
    def has_workspace(self) -> bool:
        """True if recording includes workspace files.

        Workspace files are only present in directory-format recordings
        that captured the agent's output files after execution.
        """
        return len(self._workspace_files) > 0

    def get_workspace_files(self) -> dict[str, bytes]:
        """Get workspace files captured after agent execution.

        Returns:
            Dict mapping relative path -> file content.
            e.g., {"artifacts/output/summary.md": b"# Summary..."}

        Returns empty dict for legacy .jsonl recordings.

        Examples:
            >>> player = SessionPlayer("artifact-workflow/")
            >>> files = player.get_workspace_files()
            >>> if "artifacts/output/summary.md" in files:
            ...     content = files["artifacts/output/summary.md"].decode()
            ...     print(content)
        """
        return self._workspace_files.copy()

    def get_events(self, strip_timing: bool = True) -> list[dict[str, Any]]:
        """Get all events for instant playback.

        Args:
            strip_timing: If True, remove _offset_ms from events.

        Returns:
            List of event dicts.
        """
        if strip_timing:
            return [{k: v for k, v in event.items() if k != "_offset_ms"} for event in self._events]
        return self._events.copy()

    async def play(
        self,
        emit_fn: Callable[[dict[str, Any]], Awaitable[None]],
        speed: float = 1.0,
    ) -> int:
        """Play events with timing at specified speed.

        Args:
            emit_fn: Async function to call for each event.
            speed: Playback speed multiplier (10 = 10x faster).

        Returns:
            Number of events played.
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")

        last_offset = 0
        count = 0

        for event in self._events:
            offset = event.get("_offset_ms", 0)

            # Calculate delay
            delay_ms = offset - last_offset
            if delay_ms > 0 and speed < float("inf"):
                delay_seconds = (delay_ms / 1000) / speed
                await asyncio.sleep(delay_seconds)

            # Emit event (without timing metadata)
            clean_event = {k: v for k, v in event.items() if k != "_offset_ms"}
            await emit_fn(clean_event)

            last_offset = offset
            count += 1

        return count

    async def play_async(
        self,
        speed: float = 1.0,
    ):
        """Async generator that yields events with timing delays.

        This is used by RecordingEventStreamAdapter for streaming playback.

        Args:
            speed: Playback speed multiplier (10 = 10x faster, inf = instant).

        Yields:
            Tuple of (event_dict, delay_ms) for each event.

        Examples:
            >>> async for event, delay in player.play_async(speed=100):
            ...     print(f"Event after {delay}ms: {event['type']}")
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")

        last_offset = 0

        for event in self._events:
            offset = event.get("_offset_ms", 0)

            # Calculate delay
            delay_ms = offset - last_offset
            if delay_ms > 0 and speed < float("inf"):
                delay_seconds = (delay_ms / 1000) / speed
                await asyncio.sleep(delay_seconds)

            # Yield event (without timing metadata) and the delay
            clean_event = {k: v for k, v in event.items() if k != "_offset_ms"}
            yield clean_event, delay_ms

            last_offset = offset

    def play_sync(
        self,
        emit_fn: Callable[[dict[str, Any]], None],
    ) -> int:
        """Play events synchronously without timing (for sync tests).

        Args:
            emit_fn: Sync function to call for each event.

        Returns:
            Number of events played.
        """
        count = 0
        for event in self.get_events():
            emit_fn(event)
            count += 1
        return count

    def __len__(self) -> int:
        """Number of events in the recording."""
        return len(self._events)

    def __iter__(self):
        """Iterate over events (with timing stripped)."""
        return iter(self.get_events())
