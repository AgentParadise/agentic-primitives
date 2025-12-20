"""Session recorder for capturing agent events with timing.

Records events during a real agent session for later playback in tests.
See ADR-030: Session Recording for Testing.

Usage:
    recorder = SessionRecorder(
        output_path="fixtures/v1.0.52_claude-3-5-sonnet_task.jsonl",
        cli_version="1.0.52",
        model="claude-3-5-sonnet-20241022",
        task="Description of what the agent did"
    )

    # Record events as they happen
    recorder.record({"event_type": "session_started", ...})
    recorder.record({"event_type": "tool_execution_started", ...})

    # Finalize the recording
    recorder.close()
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any


class SessionRecorder:
    """Record agent session events with timing for test playback.

    Events are written as JSONL with timing offsets from session start.
    The first line contains recording metadata (cli version, model, etc).

    Attributes:
        session_id: The session ID being recorded (set on first event).
        event_count: Number of events recorded.

    Examples:
        Basic usage:
        >>> with SessionRecorder("recording.jsonl", cli_version="1.0.52", model="claude-3-5-sonnet") as rec:
        ...     rec.record({"event_type": "started", "session_id": "abc"})
        ...     rec.record({"event_type": "completed"})

        Generate filename:
        >>> filename = SessionRecorder.generate_filename(
        ...     cli_version="1.0.52",
        ...     model="claude-3-5-sonnet",
        ...     task_slug="list-files"
        ... )
        >>> print(filename)
        v1.0.52_claude-3-5-sonnet_list-files.jsonl
    """

    RECORDING_VERSION = 1
    EVENT_SCHEMA_VERSION = 1  # Increment when event format changes

    def __init__(
        self,
        output_path: str | Path,
        cli_version: str,
        model: str,
        task: str = "",
        provider: str = "claude",
    ) -> None:
        """Initialize the recorder.

        Args:
            output_path: Path to write the JSONL recording.
            cli_version: Version of the CLI being recorded (e.g., "1.0.52").
            model: Model being used (e.g., "claude-3-5-sonnet-20241022").
            task: Human-readable description of what the session does.
            provider: Provider name (default: "claude").
        """
        self._output_path = Path(output_path)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output: IO[str] = open(self._output_path, "w")

        self._cli_version = cli_version
        self._model = model
        self._task = task
        self._provider = provider

        self._start_time = time.monotonic()
        self._start_datetime = datetime.now(UTC)
        self._event_count = 0
        self._closed = False

        self.session_id: str | None = None

    @property
    def event_count(self) -> int:
        """Number of events recorded so far."""
        return self._event_count

    def record(self, event: dict[str, Any]) -> dict[str, Any]:
        """Record an event with timing offset.

        Args:
            event: The event dict to record.

        Returns:
            The event with _offset_ms added.

        Raises:
            RuntimeError: If the recorder has been closed.
        """
        if self._closed:
            raise RuntimeError("Cannot record to a closed recorder")

        # Calculate offset from start
        offset_ms = int((time.monotonic() - self._start_time) * 1000)

        # Add timing metadata
        recorded_event = {"_offset_ms": offset_ms, **event}

        # Capture session_id from first event that has it
        if self.session_id is None and "session_id" in event:
            self.session_id = event["session_id"]

        # Write as JSONL
        self._output.write(json.dumps(recorded_event, default=str) + "\n")
        self._output.flush()

        self._event_count += 1
        return recorded_event

    def close(self) -> Path:
        """Finalize the recording and write metadata header.

        The metadata is written by rewriting the file with header first.
        This ensures we have accurate duration and event count.

        Returns:
            Path to the recording file.
        """
        if self._closed:
            return self._output_path

        self._closed = True
        duration_ms = int((time.monotonic() - self._start_time) * 1000)

        # Close current file
        self._output.close()

        # Read existing events
        with open(self._output_path) as f:
            events = f.readlines()

        # Write metadata header + events
        metadata = {
            "_recording": {
                "version": self.RECORDING_VERSION,
                "event_schema_version": self.EVENT_SCHEMA_VERSION,
                "cli_version": self._cli_version,
                "model": self._model,
                "provider": self._provider,
                "task": self._task,
                "recorded_at": self._start_datetime.isoformat(),
                "duration_ms": duration_ms,
                "event_count": self._event_count,
                "session_id": self.session_id,
            }
        }

        with open(self._output_path, "w") as f:
            f.write(json.dumps(metadata) + "\n")
            f.writelines(events)

        return self._output_path

    def __enter__(self) -> "SessionRecorder":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - closes the recorder."""
        self.close()

    @classmethod
    def generate_filename(
        cls,
        cli_version: str,
        model: str,
        task_slug: str,
    ) -> str:
        """Generate a filename following the naming convention.

        Format: v{cli_version}_{model}_{task-slug}.jsonl

        Args:
            cli_version: CLI version (e.g., "1.0.52")
            model: Model name (e.g., "claude-3-5-sonnet-20241022")
            task_slug: Kebab-case task description (e.g., "git-status-check")

        Returns:
            Formatted filename.
        """
        # Normalize model name (remove special chars)
        model_slug = model.replace("/", "-").replace(":", "-")
        return f"v{cli_version}_{model_slug}_{task_slug}.jsonl"

