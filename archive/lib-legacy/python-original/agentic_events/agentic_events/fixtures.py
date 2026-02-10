"""Fixture helpers for working with session recordings.

Provides ergonomic, type-safe functions for finding and loading recordings in tests.
See ADR-030: Session Recording for Testing.

Usage:
    from agentic_events import Recording, load_recording, list_recordings

    # Type-safe loading - MyPy catches typos at build time
    player = load_recording(Recording.LIST_FILES)
    events = player.get_events()

    # With workspace files
    player = load_recording(Recording.ARTIFACT_WORKFLOW)
    if player.has_workspace:
        files = player.get_workspace_files()

    # List all available recordings
    for path in list_recordings():
        print(path.name)

    # Escape hatch for custom recordings (not type-checked)
    player = load_recording_by_path(Path("my-custom-recording.jsonl"))

Environment Variables:
    AGENTIC_RECORDINGS_DIR: Override the recordings directory path.
        Useful when agentic_events is installed as a dependency.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from .player import SessionPlayer


class Recording(str, Enum):
    """Available test recordings.

    Each value corresponds to a recording in fixtures/recordings/.
    Adding a new recording requires adding the enum member here.
    MyPy will enforce that only valid recording names are used.

    Examples:
        >>> player = load_recording(Recording.SIMPLE_BASH)
        >>> events = player.get_events()

        >>> # This fails at build time:
        >>> player = load_recording(Recording.TYPO)  # MyPy error!
    """

    # Existing recordings (legacy .jsonl format)
    FILE_CREATE = "file-create"
    FILE_READ = "file-read"
    GIT_STATUS = "git-status"
    LIST_FILES = "list-files"
    MULTI_TOOL = "multi-tool"
    SIMPLE_BASH = "simple-bash"
    SIMPLE_QUESTION = "simple-question"

    # New recordings with workspace (directory format)
    ARTIFACT_WRITE = "artifact-write"  # Writes to artifacts/output/
    ARTIFACT_READ_WRITE = "artifact-read-write"  # Reads input/, writes output/


def get_recordings_dir() -> Path:
    """Get the canonical recordings directory.

    Returns:
        Path to recordings directory. Uses AGENTIC_RECORDINGS_DIR env var
        if set, otherwise resolves relative to this package.
    """
    # Check for environment variable override
    env_path = os.environ.get("AGENTIC_RECORDINGS_DIR")
    if env_path:
        return Path(env_path)

    # Navigate from agentic_events/fixtures.py to repo root:
    # fixtures.py -> agentic_events -> agentic_events -> python -> lib -> repo_root
    repo_root = Path(__file__).parent.parent.parent.parent.parent
    return repo_root / "providers/workspaces/claude-cli/fixtures/recordings"


def list_recordings(include_directories: bool = True) -> list[Path]:
    """List all available recordings.

    Includes both legacy .jsonl files and directory-format recordings.

    Args:
        include_directories: If True, include directory recordings (default: True)

    Returns:
        List of recording paths, sorted by name.
    """
    recordings_dir = get_recordings_dir()
    if not recordings_dir.exists():
        return []

    results: list[Path] = []

    # Add .jsonl files
    results.extend(recordings_dir.glob("*.jsonl"))

    # Add directories containing events.jsonl
    if include_directories:
        for path in recordings_dir.iterdir():
            if path.is_dir() and (path / "events.jsonl").exists():
                results.append(path)

    return sorted(results, key=lambda p: p.name)


def load_recording(name: Recording | str) -> SessionPlayer:
    """Load a recording by type-safe enum name or string.

    Prefer using Recording enum for type safety - MyPy will catch typos.
    String names are supported for backward compatibility.

    Args:
        name: Recording enum member (e.g., Recording.SIMPLE_BASH) or string

    Returns:
        SessionPlayer loaded with the recording.

    Raises:
        FileNotFoundError: If recording doesn't exist.

    Examples:
        >>> # Type-safe (recommended)
        >>> player = load_recording(Recording.SIMPLE_BASH)
        >>> events = player.get_events()

        >>> # String (backward compatible)
        >>> player = load_recording("simple-bash")

        >>> # With workspace files
        >>> player = load_recording(Recording.ARTIFACT_WORKFLOW)
        >>> if player.has_workspace:
        ...     files = player.get_workspace_files()
    """
    if isinstance(name, Recording):
        return load_recording_by_name(name.value)
    return load_recording_by_name(name)


def load_recording_by_name(name: str) -> SessionPlayer:
    """Load a recording by string name (escape hatch).

    Prefer using load_recording(Recording.NAME) for type safety.
    This function is provided for loading custom recordings not in the enum.

    Args:
        name: Recording name like "list-files" or full name like
              "v2.0.74_claude-sonnet-4-5_list-files"

    Returns:
        SessionPlayer loaded with the recording.

    Raises:
        FileNotFoundError: If recording doesn't exist.
        ValueError: If multiple recordings match the name.

    Examples:
        >>> player = load_recording_by_name("my-custom-recording")
        >>> events = player.get_events()
    """
    recordings_dir = get_recordings_dir()

    # Try as directory first (new format)
    dir_path = recordings_dir / name
    if dir_path.is_dir() and (dir_path / "events.jsonl").exists():
        return SessionPlayer(dir_path)

    # Try exact match with .jsonl extension
    recording_path = recordings_dir / f"{name}.jsonl"
    if recording_path.exists():
        return SessionPlayer(recording_path)

    # Try as a pattern
    matches = list(recordings_dir.glob(f"*{name}*.jsonl"))

    # Also check for directories matching pattern
    dir_matches = [
        d
        for d in recordings_dir.iterdir()
        if d.is_dir() and name in d.name and (d / "events.jsonl").exists()
    ]
    matches.extend(dir_matches)

    if not matches:
        available = [p.name for p in list_recordings()]
        raise FileNotFoundError(f"No recording found matching '{name}'. Available: {available}")

    if len(matches) > 1:
        raise ValueError(f"Multiple recordings match '{name}': {[m.name for m in matches]}")

    return SessionPlayer(matches[0])


def load_recording_by_path(path: Path) -> SessionPlayer:
    """Load a recording from a specific path.

    Use this for recordings outside the fixtures directory.

    Args:
        path: Path to recording file or directory

    Returns:
        SessionPlayer loaded with the recording.

    Raises:
        FileNotFoundError: If recording doesn't exist.

    Examples:
        >>> player = load_recording_by_path(Path("/tmp/my-recording.jsonl"))
        >>> player = load_recording_by_path(Path("/tmp/my-recording/"))  # directory
    """
    if not path.exists():
        raise FileNotFoundError(f"Recording not found: {path}")
    return SessionPlayer(path)
