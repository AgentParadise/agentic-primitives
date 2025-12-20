"""Fixture helpers for working with session recordings.

Provides ergonomic functions for finding and loading recordings in tests.
See ADR-030: Session Recording for Testing.

Usage:
    from agentic_events import load_recording, list_recordings

    # Quick load by task name
    player = load_recording("list-files")
    events = player.get_events()

    # List all available recordings
    for path in list_recordings():
        print(path.name)

Environment Variables:
    AGENTIC_RECORDINGS_DIR: Override the recordings directory path.
        Useful when agentic_events is installed as a dependency.
"""

from __future__ import annotations

import os
from pathlib import Path

from .player import SessionPlayer


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


def list_recordings(pattern: str = "*.jsonl") -> list[Path]:
    """List all available recordings.

    Args:
        pattern: Glob pattern for recordings (default: *.jsonl)

    Returns:
        List of recording file paths, sorted by name.
    """
    recordings_dir = get_recordings_dir()
    if not recordings_dir.exists():
        return []
    return sorted(recordings_dir.glob(pattern))


def load_recording(name: str) -> SessionPlayer:
    """Load a recording by short name (without path/extension).

    Args:
        name: Recording name like "list-files" or full name like
              "v2.0.74_claude-sonnet-4-5_list-files"

    Returns:
        SessionPlayer loaded with the recording.

    Raises:
        FileNotFoundError: If recording doesn't exist.
        ValueError: If multiple recordings match the name.

    Examples:
        >>> player = load_recording("list-files")
        >>> events = player.get_events()
    """
    recordings_dir = get_recordings_dir()

    # Try exact match first
    recording_path = recordings_dir / f"{name}.jsonl"
    if recording_path.exists():
        return SessionPlayer(recording_path)

    # Try as a pattern
    matches = list(recordings_dir.glob(f"*{name}*.jsonl"))
    if not matches:
        available = [p.name for p in list_recordings()]
        raise FileNotFoundError(f"No recording found matching '{name}'. Available: {available}")

    if len(matches) > 1:
        raise ValueError(f"Multiple recordings match '{name}': {[m.name for m in matches]}")

    return SessionPlayer(matches[0])
