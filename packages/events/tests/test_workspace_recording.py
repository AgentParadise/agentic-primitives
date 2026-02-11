"""Tests for workspace file capture in recordings.

Tests the directory-based recording format that includes workspace files
alongside events, enabling complete artifact flow testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_events.player import SessionPlayer
from agentic_events.recorder import SessionRecorder

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
WORKSPACE_RECORDING = FIXTURES_DIR / "test-workspace-recording"
LEGACY_RECORDING = FIXTURES_DIR / "test-workspace-recording" / "events.jsonl"


class TestDirectoryFormatLoading:
    """Test loading recordings from directory format."""

    def test_loads_from_directory(self) -> None:
        """SessionPlayer can load from directory path."""
        player = SessionPlayer(WORKSPACE_RECORDING)
        assert player is not None
        assert len(player) == 3

    def test_directory_has_workspace(self) -> None:
        """Directory recording has workspace files."""
        player = SessionPlayer(WORKSPACE_RECORDING)
        assert player.has_workspace is True

    def test_get_workspace_files(self) -> None:
        """Can retrieve workspace files from directory recording."""
        player = SessionPlayer(WORKSPACE_RECORDING)
        files = player.get_workspace_files()

        assert len(files) == 1
        assert "artifacts/output/summary.md" in files

    def test_workspace_file_content(self) -> None:
        """Workspace file content is correct."""
        player = SessionPlayer(WORKSPACE_RECORDING)
        files = player.get_workspace_files()

        content = files["artifacts/output/summary.md"].decode("utf-8")
        assert "# Summary" in content
        assert "Success!" in content

    def test_metadata_includes_workspace_info(self) -> None:
        """Metadata includes workspace information."""
        player = SessionPlayer(WORKSPACE_RECORDING)

        assert player.metadata.has_workspace is True
        assert "artifacts/output/summary.md" in player.metadata.workspace_files

    def test_events_still_accessible(self) -> None:
        """Events are still accessible in directory format."""
        player = SessionPlayer(WORKSPACE_RECORDING)
        events = player.get_events()

        assert len(events) == 3
        assert events[0]["type"] == "session_started"
        assert events[2]["type"] == "session_completed"


class TestLegacyFormatCompatibility:
    """Test backward compatibility with legacy .jsonl files."""

    def test_loads_from_jsonl_file(self) -> None:
        """SessionPlayer can still load from .jsonl file directly."""
        player = SessionPlayer(LEGACY_RECORDING)
        assert player is not None
        assert len(player) == 3

    def test_jsonl_has_no_workspace(self) -> None:
        """Legacy .jsonl recording has no workspace files."""
        player = SessionPlayer(LEGACY_RECORDING)
        # When loading from file directly (not directory), no workspace
        assert player.has_workspace is False

    def test_get_workspace_files_returns_empty(self) -> None:
        """get_workspace_files returns empty dict for legacy format."""
        player = SessionPlayer(LEGACY_RECORDING)
        files = player.get_workspace_files()
        assert files == {}


class TestWorkspaceFilesImmutable:
    """Test that workspace files are returned as copies."""

    def test_workspace_files_is_copy(self) -> None:
        """Modifying returned dict doesn't affect player."""
        player = SessionPlayer(WORKSPACE_RECORDING)

        files1 = player.get_workspace_files()
        files1["new_file.txt"] = b"malicious"

        files2 = player.get_workspace_files()
        assert "new_file.txt" not in files2


class TestNestedWorkspaceFiles:
    """Test handling of nested directory structures in workspace."""

    @pytest.fixture
    def nested_recording(self, tmp_path: Path) -> Path:
        """Create a recording with nested workspace structure."""
        recording_dir = tmp_path / "nested-recording"
        recording_dir.mkdir()

        # Create events
        events_file = recording_dir / "events.jsonl"
        events_file.write_text(
            '{"_recording": {"version": 1, "event_schema_version": 1}}\n{"type": "test"}\n'
        )

        # Create nested workspace
        workspace = recording_dir / "workspace"
        (workspace / "artifacts" / "output" / "reports").mkdir(parents=True)
        (workspace / "artifacts" / "output" / "data").mkdir(parents=True)

        (workspace / "artifacts" / "output" / "summary.md").write_text("# Summary")
        (workspace / "artifacts" / "output" / "reports" / "report.md").write_text("# Report")
        (workspace / "artifacts" / "output" / "data" / "results.json").write_text(
            '{"status": "ok"}'
        )

        return recording_dir

    def test_loads_nested_files(self, nested_recording: Path) -> None:
        """Loads all nested files from workspace."""
        player = SessionPlayer(nested_recording)
        files = player.get_workspace_files()

        assert len(files) == 3
        assert "artifacts/output/summary.md" in files
        assert "artifacts/output/reports/report.md" in files
        assert "artifacts/output/data/results.json" in files

    def test_nested_file_content(self, nested_recording: Path) -> None:
        """Nested files have correct content."""
        player = SessionPlayer(nested_recording)
        files = player.get_workspace_files()

        assert files["artifacts/output/reports/report.md"] == b"# Report"
        assert b'"status": "ok"' in files["artifacts/output/data/results.json"]


# =============================================================================
# RECORDER TESTS - Capturing workspace files
# =============================================================================


class TestRecorderWithoutWorkspace:
    """Test recorder creates legacy format when no workspace files."""

    def test_creates_jsonl_file(self, tmp_path: Path) -> None:
        """Recorder creates .jsonl file when no workspace files."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})

        assert output.exists()
        assert output.is_file()

    def test_has_workspace_false(self, tmp_path: Path) -> None:
        """has_workspace is False when no files set."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            assert rec.has_workspace is False


class TestRecorderWithWorkspace:
    """Test recorder creates directory format with workspace files."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Recorder creates directory when workspace files are set."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            rec.set_workspace_files({"artifacts/output/test.md": b"# Test"})

        # Should create directory (without .jsonl extension)
        dir_path = tmp_path / "test"
        assert dir_path.exists()
        assert dir_path.is_dir()

    def test_has_workspace_true(self, tmp_path: Path) -> None:
        """has_workspace is True when files are set."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.set_workspace_files({"test.md": b"test"})
            assert rec.has_workspace is True

    def test_events_in_directory(self, tmp_path: Path) -> None:
        """Events are written to events.jsonl in directory."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test_event"})
            rec.set_workspace_files({"test.md": b"test"})

        events_path = tmp_path / "test" / "events.jsonl"
        assert events_path.exists()

        content = events_path.read_text()
        assert "test_event" in content

    def test_workspace_files_in_directory(self, tmp_path: Path) -> None:
        """Workspace files are written to workspace/ subdirectory."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            rec.set_workspace_files(
                {
                    "artifacts/output/summary.md": b"# Summary",
                    "artifacts/output/data/results.json": b'{"ok": true}',
                }
            )

        workspace_path = tmp_path / "test" / "workspace"
        assert workspace_path.exists()
        assert (workspace_path / "artifacts/output/summary.md").exists()
        assert (workspace_path / "artifacts/output/data/results.json").exists()

    def test_workspace_file_content(self, tmp_path: Path) -> None:
        """Workspace files have correct content."""
        output = tmp_path / "test.jsonl"
        content = b"# Test Content\n\nWith multiple lines."

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            rec.set_workspace_files({"output.md": content})

        file_path = tmp_path / "test" / "workspace" / "output.md"
        assert file_path.read_bytes() == content

    def test_add_workspace_file(self, tmp_path: Path) -> None:
        """Can add workspace files one at a time."""
        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            rec.add_workspace_file("file1.md", b"First")
            rec.add_workspace_file("file2.md", b"Second")

        workspace = tmp_path / "test" / "workspace"
        assert (workspace / "file1.md").read_bytes() == b"First"
        assert (workspace / "file2.md").read_bytes() == b"Second"

    def test_metadata_includes_workspace_info(self, tmp_path: Path) -> None:
        """Metadata includes workspace file list."""
        import json

        output = tmp_path / "test.jsonl"

        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "test"})
            rec.set_workspace_files(
                {
                    "a.md": b"a",
                    "b.md": b"b",
                }
            )

        events_path = tmp_path / "test" / "events.jsonl"
        first_line = events_path.read_text().split("\n")[0]
        metadata = json.loads(first_line)

        assert metadata["_recording"]["has_workspace"] is True
        assert "a.md" in metadata["_recording"]["workspace_files"]
        assert "b.md" in metadata["_recording"]["workspace_files"]


class TestRecorderPlayerRoundTrip:
    """Test that recorded workspace files can be loaded by player."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        """Files recorded can be loaded by player."""
        output = tmp_path / "roundtrip.jsonl"
        files = {
            "artifacts/output/summary.md": b"# Summary\n\nTest content.",
            "artifacts/output/data.json": b'{"status": "ok"}',
        }

        # Record
        with SessionRecorder(output, cli_version="1.0", model="test") as rec:
            rec.record({"type": "session_started", "session_id": "test-123"})
            rec.record({"type": "session_completed"})
            rec.set_workspace_files(files)

        # Load
        player = SessionPlayer(tmp_path / "roundtrip")

        # Verify events
        events = player.get_events()
        assert len(events) == 2
        assert events[0]["type"] == "session_started"

        # Verify workspace files
        assert player.has_workspace
        loaded_files = player.get_workspace_files()
        assert loaded_files == files
