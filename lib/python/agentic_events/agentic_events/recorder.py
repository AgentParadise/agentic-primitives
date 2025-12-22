"""Session recorder for capturing agent events with timing.

Records events during a real agent session for later playback in tests.
See ADR-030: Session Recording for Testing.

Supports two output formats:
1. Legacy: Single .jsonl file (default when no workspace files)
2. Directory: Folder with events.jsonl + workspace/ files

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

    # Optionally capture workspace files (creates directory format)
    recorder.set_workspace_files({
        "artifacts/output/summary.md": b"# Summary..."
    })

    # Finalize the recording
    recorder.close()
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any


class SessionRecorder:
    """Record agent session events with timing for test playback.

    Events are written as JSONL with timing offsets from session start.
    The first line contains recording metadata (cli version, model, etc).

    Supports two output formats:
    1. Legacy .jsonl file (default): Single file with metadata + events
    2. Directory format: When workspace files are captured

    Attributes:
        session_id: The session ID being recorded (set on first event).
        event_count: Number of events recorded.
        has_workspace: True if workspace files have been set.

    Examples:
        Basic usage (creates .jsonl file):
        >>> with SessionRecorder(
        ...     "recording.jsonl", cli_version="1.0.52", model="claude-3-5-sonnet"
        ... ) as rec:
        ...     rec.record({"event_type": "started", "session_id": "abc"})
        ...     rec.record({"event_type": "completed"})

        With workspace files (creates directory):
        >>> with SessionRecorder(
        ...     "recording.jsonl", cli_version="1.0.52", model="claude-3-5-sonnet"
        ... ) as rec:
        ...     rec.record({"event_type": "started"})
        ...     rec.set_workspace_files({
        ...         "artifacts/output/summary.md": b"# Summary..."
        ...     })
        >>> # Creates: recording/ directory with events.jsonl + workspace/

        Generate filename:
        >>> filename = SessionRecorder.generate_filename(
        ...     cli_version="1.0.52",
        ...     model="claude-3-5-sonnet",
        ...     task_slug="list-files"
        ... )
        >>> print(filename)
        v1.0.52_claude-3-5-sonnet_list-files.jsonl
    """

    RECORDING_VERSION = 2  # Bumped for workspace support
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
            output_path: Path to write the JSONL recording (or directory base).
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
        self._workspace_files: dict[str, bytes] = {}

        self.session_id: str | None = None

    @property
    def has_workspace(self) -> bool:
        """True if workspace files have been set."""
        return len(self._workspace_files) > 0

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

    def set_workspace_files(self, files: dict[str, bytes]) -> None:
        """Set workspace files to include in the recording.

        When workspace files are set, close() will create a directory-format
        recording instead of a single .jsonl file.

        Args:
            files: Dict mapping relative path -> file content.
                   Paths should be relative to /workspace/
                   e.g., {"artifacts/output/summary.md": b"# Summary..."}

        Raises:
            RuntimeError: If the recorder has been closed.

        Examples:
            >>> recorder.set_workspace_files({
            ...     "artifacts/output/summary.md": b"# Summary\\n...",
            ...     "artifacts/output/data.json": b'{"key": "value"}',
            ... })
        """
        if self._closed:
            raise RuntimeError("Cannot set workspace files on a closed recorder")

        self._workspace_files = files.copy()

    def add_workspace_file(self, path: str, content: bytes) -> None:
        """Add a single workspace file to the recording.

        Args:
            path: Relative path (e.g., "artifacts/output/summary.md")
            content: File content as bytes

        Raises:
            RuntimeError: If the recorder has been closed.
        """
        if self._closed:
            raise RuntimeError("Cannot add workspace file to a closed recorder")

        self._workspace_files[path] = content

    def close(self) -> Path:
        """Finalize the recording and write metadata header.

        If workspace files were set, creates a directory-format recording.
        Otherwise, creates a single .jsonl file (legacy format).

        Returns:
            Path to the recording file or directory.
        """
        if self._closed:
            return self._final_path if hasattr(self, "_final_path") else self._output_path

        self._closed = True
        duration_ms = int((time.monotonic() - self._start_time) * 1000)

        # Close current file
        self._output.close()

        # Read existing events
        with open(self._output_path) as f:
            events = f.readlines()

        # Build metadata
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
                "has_workspace": self.has_workspace,
                "workspace_files": list(self._workspace_files.keys()),
            }
        }

        if self.has_workspace:
            # Directory format: convert .jsonl to directory
            self._final_path = self._write_directory_format(events, metadata)
        else:
            # Legacy format: single .jsonl file
            self._final_path = self._write_jsonl_format(events, metadata)

        return self._final_path

    def _write_jsonl_format(self, events: list[str], metadata: dict[str, Any]) -> Path:
        """Write legacy single-file format."""
        with open(self._output_path, "w") as f:
            f.write(json.dumps(metadata) + "\n")
            f.writelines(events)
        return self._output_path

    def _write_directory_format(self, events: list[str], metadata: dict[str, Any]) -> Path:
        """Write directory format with events + workspace files."""
        # Determine directory path (remove .jsonl extension if present)
        if self._output_path.suffix == ".jsonl":
            dir_path = self._output_path.with_suffix("")
        else:
            dir_path = self._output_path

        # Remove existing file/directory
        if self._output_path.exists():
            self._output_path.unlink()
        if dir_path.exists():
            shutil.rmtree(dir_path)

        # Create directory structure
        dir_path.mkdir(parents=True, exist_ok=True)

        # Write events.jsonl
        events_path = dir_path / "events.jsonl"
        with open(events_path, "w") as f:
            f.write(json.dumps(metadata) + "\n")
            f.writelines(events)

        # Write workspace files
        workspace_path = dir_path / "workspace"
        for rel_path, content in self._workspace_files.items():
            file_path = workspace_path / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        return dir_path

    def __enter__(self) -> SessionRecorder:
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

    @classmethod
    def create(
        cls,
        task_slug: str,
        cli_version: str = "2.0.74",
        model: str = "claude-sonnet-4-5",
        task: str = "",
        output_dir: str | Path | None = None,
    ) -> SessionRecorder:
        """Create a recorder with auto-generated standardized filename.

        This is the recommended way to create recordings - it enforces
        the naming convention and puts files in the correct directory.

        Args:
            task_slug: Kebab-case task name (e.g., "simple-bash", "file-create")
            cli_version: CLI version (default: "2.0.74")
            model: Model name (default: "claude-sonnet-4-5")
            task: Human-readable task description
            output_dir: Override output directory (default: standard fixtures dir)

        Returns:
            SessionRecorder ready to record events.

        Examples:
            >>> recorder = SessionRecorder.create("simple-bash")
            >>> # Creates: .../fixtures/recordings/v2.0.74_claude-sonnet-4-5_simple-bash.jsonl

            >>> recorder = SessionRecorder.create(
            ...     "git-status",
            ...     task="Run git status and explain"
            ... )
        """
        filename = cls.generate_filename(cli_version, model, task_slug)

        if output_dir is None:
            # Use standard fixtures directory
            output_dir = (
                Path(__file__).parent.parent.parent.parent
                / "providers/workspaces/claude-cli/fixtures/recordings"
            )
        else:
            output_dir = Path(output_dir)

        output_path = output_dir / filename

        return cls(
            output_path=output_path,
            cli_version=cli_version,
            model=model,
            task=task or task_slug.replace("-", " ").title(),
        )
