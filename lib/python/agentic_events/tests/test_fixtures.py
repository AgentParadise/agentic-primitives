"""Tests for fixture helper functions."""

import pytest

from agentic_events import get_recordings_dir, list_recordings, load_recording

# These tests use the recordings directory, so they're integration tests
pytestmark = pytest.mark.integration


class TestGetRecordingsDir:
    """Tests for get_recordings_dir()."""

    def test_returns_path(self):
        """Returns a Path object."""
        dir_path = get_recordings_dir()
        assert dir_path is not None
        assert hasattr(dir_path, "exists")

    def test_recordings_directory_exists(self):
        """Recordings directory exists and has expected structure."""
        dir_path = get_recordings_dir()
        assert dir_path.is_dir(), f"Recordings directory not found: {dir_path}"
        assert "recordings" in str(dir_path)


class TestListRecordings:
    """Tests for list_recordings()."""

    def test_returns_list(self):
        """Returns a list."""
        recordings = list_recordings()
        assert isinstance(recordings, list)

    def test_all_are_jsonl_files(self):
        """All returned files are JSONL."""
        recordings = list_recordings()
        for path in recordings:
            assert path.suffix == ".jsonl", f"Expected .jsonl: {path}"

    def test_returns_sorted(self):
        """Results are sorted by name."""
        recordings = list_recordings()
        if len(recordings) > 1:
            names = [p.name for p in recordings]
            assert names == sorted(names)


class TestLoadRecording:
    """Tests for load_recording()."""

    @pytest.mark.skipif(
        len(list_recordings()) == 0,
        reason="No recordings available for testing",
    )
    def test_load_by_task_part(self):
        """Can load recording by partial task name."""
        recordings = list_recordings()
        if recordings:
            # Extract task part from first recording
            # e.g., "v2.0.74_claude-sonnet-4-5_list-files.jsonl" -> "list-files"
            first = recordings[0].stem
            task_part = first.split("_")[-1]

            player = load_recording(task_part)
            assert player is not None
            # Recording loaded successfully (may have 0 events if capture failed)
            assert player.metadata is not None

    @pytest.mark.skipif(
        len(list_recordings()) == 0,
        reason="No recordings available for testing",
    )
    def test_load_by_full_name(self):
        """Can load recording by full filename (without extension)."""
        recordings = list_recordings()
        if recordings:
            full_name = recordings[0].stem
            player = load_recording(full_name)
            assert player is not None

    def test_load_nonexistent_raises_error(self):
        """Loading nonexistent recording raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_recording("this-recording-does-not-exist-xyz")
        assert "No recording found matching" in str(exc_info.value)


class TestRecordingFixture:
    """Tests for the @pytest.mark.recording fixture."""

    @pytest.mark.recording("list-files")
    def test_recording_fixture_loads_player(self, recording):
        """Fixture loads SessionPlayer when recording exists."""
        if recording is None:
            pytest.skip("Recording not found")

        assert recording is not None
        assert len(recording) > 0

    @pytest.mark.recording("list-files")
    def test_recording_fixture_has_events(self, recording):
        """Fixture player has events to replay."""
        if recording is None:
            pytest.skip("Recording not found")

        events = recording.get_events()
        assert len(events) > 0
        # Check first event has expected structure
        assert "session_id" in events[0] or "type" in events[0]
