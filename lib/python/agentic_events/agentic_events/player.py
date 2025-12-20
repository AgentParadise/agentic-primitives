"""Session player for replaying recorded agent events.

Replays recorded sessions at configurable speed for testing.
See ADR-030: Session Recording for Testing.

Usage:
    player = SessionPlayer("fixtures/v1.0.52_claude-3-5-sonnet_task.jsonl")

    # Instant playback for unit tests
    for event in player.get_events():
        await store.insert_one(event)

    # Timed playback at 100x speed for integration tests
    await player.play(emit_fn=store.insert_one, speed=100)

    # Access metadata
    print(f"Recording has {player.metadata.event_count} events")
    print(f"Original duration: {player.metadata.duration_ms}ms")
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass
class RecordingMetadata:
    """Metadata from a recording file."""

    version: int
    cli_version: str
    model: str
    provider: str
    task: str
    recorded_at: datetime
    duration_ms: int
    event_count: int
    session_id: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecordingMetadata":
        """Create from metadata dict."""
        recording = data.get("_recording", data)
        recorded_at = recording.get("recorded_at", "")
        if isinstance(recorded_at, str):
            recorded_at = datetime.fromisoformat(recorded_at)

        return cls(
            version=recording.get("version", 1),
            cli_version=recording.get("cli_version", "unknown"),
            model=recording.get("model", "unknown"),
            provider=recording.get("provider", "claude"),
            task=recording.get("task", ""),
            recorded_at=recorded_at,
            duration_ms=recording.get("duration_ms", 0),
            event_count=recording.get("event_count", 0),
            session_id=recording.get("session_id"),
        )


class SessionPlayer:
    """Replay recorded agent sessions for testing.

    Loads a JSONL recording and provides methods for:
    - Instant playback (get_events) - for unit tests
    - Timed playback (play) - for integration tests
    - Speed control - replay at 10x, 100x, 1000x speed

    Attributes:
        metadata: Recording metadata (version, model, duration, etc).
        session_id: The session ID from the recording.
    """

    def __init__(self, recording_path: str | Path) -> None:
        """Load a recording from file.

        Args:
            recording_path: Path to the JSONL recording file.

        Raises:
            FileNotFoundError: If recording doesn't exist.
            ValueError: If recording format is invalid.
        """
        self._path = Path(recording_path)
        self._events: list[dict[str, Any]] = []
        self._metadata: RecordingMetadata | None = None

        self._load()

    def _load(self) -> None:
        """Load and parse the recording file."""
        with open(self._path) as f:
            lines = f.readlines()

        if not lines:
            raise ValueError(f"Empty recording file: {self._path}")

        # First line should be metadata
        first_line = json.loads(lines[0])
        if "_recording" in first_line:
            self._metadata = RecordingMetadata.from_dict(first_line)
            event_lines = lines[1:]
        else:
            # Old format without metadata header
            self._metadata = RecordingMetadata(
                version=0,
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

        # Parse events
        for line in event_lines:
            line = line.strip()
            if line:
                event = json.loads(line)
                self._events.append(event)

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

    def get_events(self, strip_timing: bool = True) -> list[dict[str, Any]]:
        """Get all events for instant playback.

        Args:
            strip_timing: If True, remove _offset_ms from events.

        Returns:
            List of event dicts.
        """
        if strip_timing:
            return [
                {k: v for k, v in event.items() if k != "_offset_ms"}
                for event in self._events
            ]
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

