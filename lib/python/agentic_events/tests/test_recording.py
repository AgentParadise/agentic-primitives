"""Tests for SessionRecorder and SessionPlayer."""

import asyncio
import json
from pathlib import Path

import pytest

from agentic_events import SessionPlayer, SessionRecorder


class TestSessionRecorder:
    """Tests for SessionRecorder."""

    def test_basic_recording(self, tmp_path: Path):
        """Test recording events to a file."""
        output_file = tmp_path / "test.jsonl"

        with SessionRecorder(
            output_path=output_file,
            cli_version="1.0.52",
            model="claude-3-5-sonnet-20241022",
            task="Test recording",
        ) as recorder:
            recorder.record(
                {
                    "event_type": "session_started",
                    "session_id": "test-123",
                }
            )
            recorder.record(
                {
                    "event_type": "tool_execution_started",
                    "session_id": "test-123",
                    "context": {"tool_name": "Bash"},
                }
            )

        assert output_file.exists()
        assert recorder.event_count == 2
        assert recorder.session_id == "test-123"

        # Verify content
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 3  # 1 metadata + 2 events

        # First line is metadata
        meta = json.loads(lines[0])
        assert "_recording" in meta
        assert meta["_recording"]["cli_version"] == "1.0.52"
        assert meta["_recording"]["event_count"] == 2

        # Events have offset
        event1 = json.loads(lines[1])
        assert "_offset_ms" in event1
        assert event1["event_type"] == "session_started"

    def test_timing_offsets(self, tmp_path: Path):
        """Test that timing offsets are recorded."""
        output_file = tmp_path / "timing.jsonl"

        with SessionRecorder(
            output_path=output_file,
            cli_version="1.0.52",
            model="test",
            task="Timing test",
        ) as recorder:
            recorder.record({"event_type": "start", "session_id": "s1"})
            # Small sleep to create offset
            import time

            time.sleep(0.05)  # 50ms
            recorder.record({"event_type": "end", "session_id": "s1"})

        lines = output_file.read_text().strip().split("\n")
        event1 = json.loads(lines[1])
        event2 = json.loads(lines[2])

        # Second event should have larger offset
        assert event2["_offset_ms"] > event1["_offset_ms"]
        assert event2["_offset_ms"] >= 50  # At least 50ms later

    def test_generate_filename(self):
        """Test filename generation."""
        filename = SessionRecorder.generate_filename(
            cli_version="1.0.52",
            model="claude-3-5-sonnet-20241022",
            task_slug="git-status-check",
        )
        assert filename == "v1.0.52_claude-3-5-sonnet-20241022_git-status-check.jsonl"

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Test that parent directories are created."""
        output_file = tmp_path / "nested" / "deep" / "test.jsonl"

        with SessionRecorder(
            output_path=output_file,
            cli_version="1.0.0",
            model="test",
        ) as recorder:
            recorder.record({"event_type": "test", "session_id": "s1"})

        assert output_file.exists()


class TestSessionPlayer:
    """Tests for SessionPlayer."""

    @pytest.fixture
    def sample_recording(self, tmp_path: Path) -> Path:
        """Create a sample recording file."""
        recording_file = tmp_path / "sample.jsonl"

        with SessionRecorder(
            output_path=recording_file,
            cli_version="1.0.52",
            model="claude-3-5-sonnet-20241022",
            task="Sample session",
        ) as recorder:
            recorder.record(
                {
                    "event_type": "session_started",
                    "session_id": "sample-123",
                }
            )
            recorder.record(
                {
                    "event_type": "tool_execution_started",
                    "session_id": "sample-123",
                    "context": {"tool_name": "Bash", "tool_use_id": "toolu_1"},
                }
            )
            recorder.record(
                {
                    "event_type": "tool_execution_completed",
                    "session_id": "sample-123",
                    "context": {"tool_use_id": "toolu_1", "success": True},
                }
            )
            recorder.record(
                {
                    "event_type": "session_completed",
                    "session_id": "sample-123",
                }
            )

        return recording_file

    def test_load_recording(self, sample_recording: Path):
        """Test loading a recording file."""
        player = SessionPlayer(sample_recording)

        assert player.metadata.cli_version == "1.0.52"
        assert player.metadata.model == "claude-3-5-sonnet-20241022"
        assert player.metadata.event_count == 4
        assert player.session_id == "sample-123"
        assert len(player) == 4

    def test_get_events(self, sample_recording: Path):
        """Test getting events without timing."""
        player = SessionPlayer(sample_recording)
        events = player.get_events()

        assert len(events) == 4
        assert events[0]["event_type"] == "session_started"
        assert "_offset_ms" not in events[0]  # Timing stripped

    def test_get_events_with_timing(self, sample_recording: Path):
        """Test getting events with timing preserved."""
        player = SessionPlayer(sample_recording)
        events = player.get_events(strip_timing=False)

        assert len(events) == 4
        assert "_offset_ms" in events[0]

    def test_iterate(self, sample_recording: Path):
        """Test iterating over player."""
        player = SessionPlayer(sample_recording)

        events = list(player)
        assert len(events) == 4
        assert events[0]["event_type"] == "session_started"

    def test_play_sync(self, sample_recording: Path):
        """Test synchronous playback."""
        player = SessionPlayer(sample_recording)
        received = []

        count = player.play_sync(emit_fn=received.append)

        assert count == 4
        assert len(received) == 4
        assert received[0]["event_type"] == "session_started"

    @pytest.mark.asyncio
    async def test_play_async(self, sample_recording: Path):
        """Test async playback with timing."""
        player = SessionPlayer(sample_recording)
        received = []

        async def emit(event):
            received.append(event)

        # Play at very high speed for fast test
        count = await player.play(emit_fn=emit, speed=10000)

        assert count == 4
        assert len(received) == 4
        assert received[0]["event_type"] == "session_started"

    @pytest.mark.asyncio
    async def test_play_speed(self, tmp_path: Path):
        """Test that playback respects speed setting."""
        recording_file = tmp_path / "timed.jsonl"

        # Create recording with known timing
        with SessionRecorder(
            output_path=recording_file,
            cli_version="1.0.0",
            model="test",
        ) as recorder:
            recorder.record({"event_type": "start", "session_id": "t1"})
            import time

            time.sleep(0.1)  # 100ms gap
            recorder.record({"event_type": "end", "session_id": "t1"})

        player = SessionPlayer(recording_file)
        received = []

        async def emit(event):
            received.append((asyncio.get_event_loop().time(), event))

        # Play at 100x speed (100ms -> 1ms)
        start = asyncio.get_event_loop().time()
        await player.play(emit_fn=emit, speed=100)
        duration = asyncio.get_event_loop().time() - start

        # Should take ~1ms instead of 100ms
        assert duration < 0.05  # Allow some slack

    def test_empty_recording_error(self, tmp_path: Path):
        """Test error on empty file."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="Empty recording"):
            SessionPlayer(empty_file)

    def test_file_not_found(self, tmp_path: Path):
        """Test error on missing file."""
        with pytest.raises(FileNotFoundError):
            SessionPlayer(tmp_path / "nonexistent.jsonl")


class TestRoundTrip:
    """Tests for recording and playing back."""

    def test_roundtrip(self, tmp_path: Path):
        """Test recording and playing back produces same events."""
        recording_file = tmp_path / "roundtrip.jsonl"

        original_events = [
            {"event_type": "session_started", "session_id": "rt-123"},
            {
                "event_type": "tool_execution_started",
                "session_id": "rt-123",
                "context": {"tool_name": "Read"},
            },
            {
                "event_type": "tool_execution_completed",
                "session_id": "rt-123",
                "context": {"success": True},
            },
            {"event_type": "session_completed", "session_id": "rt-123"},
        ]

        # Record
        with SessionRecorder(
            output_path=recording_file,
            cli_version="1.0.52",
            model="test-model",
        ) as recorder:
            for event in original_events:
                recorder.record(event)

        # Playback
        player = SessionPlayer(recording_file)
        played_events = player.get_events()

        # Compare (ignoring timestamp differences)
        assert len(played_events) == len(original_events)
        for orig, played in zip(original_events, played_events, strict=True):
            assert played["event_type"] == orig["event_type"]
            assert played["session_id"] == orig["session_id"]


class TestSchemaVersioning:
    """Tests for event schema versioning."""

    def test_recorder_includes_schema_version(self, tmp_path: Path):
        """Recorder includes event_schema_version in metadata."""
        recording_file = tmp_path / "versioned.jsonl"

        with SessionRecorder(
            output_path=recording_file,
            cli_version="1.0.52",
            model="test-model",
        ) as recorder:
            recorder.record({"event_type": "test", "session_id": "s1"})

        # Read raw metadata
        lines = recording_file.read_text().strip().split("\n")
        meta = json.loads(lines[0])

        assert "event_schema_version" in meta["_recording"]
        assert meta["_recording"]["event_schema_version"] == 1

    def test_player_parses_schema_version(self, tmp_path: Path):
        """Player correctly parses event_schema_version."""
        recording_file = tmp_path / "versioned.jsonl"

        with SessionRecorder(
            output_path=recording_file,
            cli_version="1.0.52",
            model="test-model",
        ) as recorder:
            recorder.record({"event_type": "test", "session_id": "s1"})

        player = SessionPlayer(recording_file)

        assert player.metadata.event_schema_version == 1

    def test_player_handles_missing_schema_version(self, tmp_path: Path):
        """Player defaults to 0 for old recordings without schema version."""
        recording_file = tmp_path / "old_format.jsonl"

        # Manually write an old-format recording without event_schema_version
        metadata = {
            "_recording": {
                "version": 1,
                "cli_version": "1.0.0",
                "model": "test",
                "provider": "claude",
                "task": "",
                "recorded_at": "2025-01-01T00:00:00Z",
                "duration_ms": 100,
                "event_count": 1,
                "session_id": "old-123",
                # Note: no event_schema_version
            }
        }

        with open(recording_file, "w") as f:
            f.write(json.dumps(metadata) + "\n")
            f.write(
                json.dumps({"_offset_ms": 0, "event_type": "test", "session_id": "old-123"}) + "\n"
            )

        player = SessionPlayer(recording_file)

        # Should default to 0
        assert player.metadata.event_schema_version == 0

    def test_player_normalizes_old_events(self, tmp_path: Path):
        """Player normalizes events from older schema versions."""
        recording_file = tmp_path / "old_events.jsonl"

        # Create recording with schema v0 (old format)
        metadata = {
            "_recording": {
                "version": 1,
                "event_schema_version": 0,
                "cli_version": "1.0.0",
                "model": "test",
                "provider": "claude",
                "task": "",
                "recorded_at": "2025-01-01T00:00:00Z",
                "duration_ms": 100,
                "event_count": 1,
                "session_id": "old-123",
            }
        }

        with open(recording_file, "w") as f:
            f.write(json.dumps(metadata) + "\n")
            f.write(
                json.dumps({"_offset_ms": 0, "event_type": "test", "session_id": "old-123"}) + "\n"
            )

        player = SessionPlayer(recording_file)
        events = player.get_events()

        # Events should be loaded and normalized
        assert len(events) == 1
        assert events[0]["event_type"] == "test"
