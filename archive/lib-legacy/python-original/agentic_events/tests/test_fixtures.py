"""Tests for fixture helper functions."""

import pytest

from agentic_events import (
    Recording,
    get_recordings_dir,
    list_recordings,
    load_recording,
    load_recording_by_name,
    load_recording_by_path,
)

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

    def test_includes_jsonl_files(self):
        """Includes .jsonl files."""
        recordings = list_recordings()
        jsonl_files = [p for p in recordings if p.suffix == ".jsonl"]
        assert len(jsonl_files) > 0, "Expected at least one .jsonl file"

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


class TestRecordingEnum:
    """Tests for the Recording enum."""

    def test_enum_has_expected_values(self):
        """Recording enum has expected members."""
        assert hasattr(Recording, "SIMPLE_BASH")
        assert hasattr(Recording, "LIST_FILES")
        assert hasattr(Recording, "FILE_CREATE")

    def test_enum_values_are_strings(self):
        """Recording enum values are kebab-case strings."""
        assert Recording.SIMPLE_BASH.value == "simple-bash"
        assert Recording.LIST_FILES.value == "list-files"

    def test_load_with_enum(self):
        """Can load recording using enum."""
        player = load_recording(Recording.SIMPLE_BASH)
        assert player is not None
        assert player.metadata is not None

    def test_load_with_string(self):
        """Can load recording using string (backward compatible)."""
        player = load_recording("simple-bash")
        assert player is not None
        assert player.metadata is not None

    def test_enum_and_string_return_same(self):
        """Enum and string load the same recording."""
        player_enum = load_recording(Recording.SIMPLE_BASH)
        player_str = load_recording("simple-bash")

        assert player_enum.metadata.task == player_str.metadata.task
        assert len(player_enum) == len(player_str)


class TestLoadRecordingByPath:
    """Tests for load_recording_by_path()."""

    def test_load_by_path(self):
        """Can load recording by explicit path."""
        recordings = list_recordings()
        if recordings:
            player = load_recording_by_path(recordings[0])
            assert player is not None

    def test_nonexistent_path_raises(self, tmp_path):
        """Loading nonexistent path raises FileNotFoundError."""
        fake_path = tmp_path / "nonexistent.jsonl"
        with pytest.raises(FileNotFoundError):
            load_recording_by_path(fake_path)


class TestLoadRecordingByName:
    """Tests for load_recording_by_name()."""

    def test_load_by_name(self):
        """Can load recording by string name."""
        player = load_recording_by_name("simple-bash")
        assert player is not None

    def test_nonexistent_name_raises(self):
        """Loading nonexistent name raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_recording_by_name("this-does-not-exist-xyz")


class TestArtifactWriteRecording:
    """Tests for the artifact-write recording with workspace files."""

    def test_load_artifact_write(self):
        """Can load artifact-write recording via enum."""
        player = load_recording(Recording.ARTIFACT_WRITE)
        assert player is not None
        assert len(player) > 0

    def test_has_workspace(self):
        """Artifact-write recording has workspace files."""
        player = load_recording(Recording.ARTIFACT_WRITE)
        assert player.has_workspace is True

    def test_workspace_contains_summary(self):
        """Workspace contains artifacts/output/summary.md."""
        player = load_recording(Recording.ARTIFACT_WRITE)
        files = player.get_workspace_files()
        assert "artifacts/output/summary.md" in files

    def test_summary_content(self):
        """Summary file has expected content."""
        player = load_recording(Recording.ARTIFACT_WRITE)
        files = player.get_workspace_files()
        content = files["artifacts/output/summary.md"].decode()
        assert "Cat" in content or "cat" in content


class TestArtifactReadWriteRecording:
    """Tests for the artifact-read-write recording (full input→output flow)."""

    def test_load_artifact_read_write(self):
        """Can load artifact-read-write recording via enum."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        assert player is not None
        assert len(player) > 0

    def test_has_workspace(self):
        """Recording has workspace files."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        assert player.has_workspace is True

    def test_has_input_artifact(self):
        """Workspace contains input artifact (from Phase 1)."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        files = player.get_workspace_files()
        assert "artifacts/input/phase1-summary.md" in files

    def test_has_output_artifact(self):
        """Workspace contains output artifact (Phase 2 response)."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        files = player.get_workspace_files()
        assert "artifacts/output/phase2-response.md" in files

    def test_output_references_input(self):
        """Phase 2 output references Phase 1 input content."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        files = player.get_workspace_files()

        # Phase 1 mentioned Item A, B, C
        input_content = files["artifacts/input/phase1-summary.md"].decode()
        assert "Item A" in input_content

        # Phase 2 should reference the same items
        output_content = files["artifacts/output/phase2-response.md"].decode()
        assert "Item A" in output_content or "Phase 1" in output_content

    def test_full_artifact_flow(self):
        """Validates the complete input→output artifact flow."""
        player = load_recording(Recording.ARTIFACT_READ_WRITE)
        files = player.get_workspace_files()

        # Both input and output exist
        input_files = [f for f in files if f.startswith("artifacts/input/")]
        output_files = [f for f in files if f.startswith("artifacts/output/")]

        assert len(input_files) >= 1, "Should have at least one input artifact"
        assert len(output_files) >= 1, "Should have at least one output artifact"

        # Output is non-empty
        for path in output_files:
            assert len(files[path]) > 0, f"Output {path} should not be empty"
