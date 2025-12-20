"""Tests for capture_recording.py script."""

import io
import json
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from capture_recording import (
    capture_from_stream,
    generate_filename,
    is_jsonl_event,
    parse_event,
)


class TestIsJsonlEvent:
    """Tests for is_jsonl_event function."""

    def test_valid_event(self):
        """Valid event line returns True."""
        line = '{"event_type": "session_started", "session_id": "abc"}'
        assert is_jsonl_event(line) is True

    def test_event_without_event_type(self):
        """JSON without event_type returns False."""
        line = '{"session_id": "abc", "data": {}}'
        assert is_jsonl_event(line) is False

    def test_non_json(self):
        """Non-JSON line returns False."""
        assert is_jsonl_event("Hello world") is False
        assert is_jsonl_event("Starting agent...") is False

    def test_empty_line(self):
        """Empty line returns False."""
        assert is_jsonl_event("") is False
        assert is_jsonl_event("   ") is False

    def test_invalid_json(self):
        """Invalid JSON returns False."""
        assert is_jsonl_event("{invalid json}") is False


class TestParseEvent:
    """Tests for parse_event function."""

    def test_valid_json(self):
        """Valid JSON is parsed."""
        line = '{"event_type": "test", "value": 42}'
        result = parse_event(line)
        assert result == {"event_type": "test", "value": 42}

    def test_invalid_json(self):
        """Invalid JSON returns None."""
        assert parse_event("not json") is None

    def test_with_whitespace(self):
        """Whitespace is stripped."""
        line = '  {"event_type": "test"}  \n'
        result = parse_event(line)
        assert result == {"event_type": "test"}


class TestGenerateFilename:
    """Tests for generate_filename function."""

    def test_basic(self):
        """Basic filename generation."""
        result = generate_filename("1.0.52", "claude-3-5-sonnet", "git-status")
        assert result == "v1.0.52_claude-3-5-sonnet_git-status.jsonl"

    def test_special_chars_removed(self):
        """Special characters are replaced with dashes."""
        result = generate_filename("1.0", "model/v1:latest", "my task!")
        assert "/" not in result
        assert ":" not in result
        assert "!" not in result


class TestCaptureFromStream:
    """Tests for capture_from_stream function."""

    def test_captures_events(self, tmp_path: Path):
        """Events are captured from stream."""
        output_file = tmp_path / "test.jsonl"

        # Simulate input stream with events
        input_data = """Starting agent...
{"event_type": "session_started", "session_id": "test-123"}
Processing...
{"event_type": "tool_execution_started", "session_id": "test-123", "context": {"tool_name": "Bash"}}
{"event_type": "tool_execution_completed", "session_id": "test-123", "context": {"success": true}}
Done.
{"event_type": "session_completed", "session_id": "test-123"}
"""
        input_stream = io.StringIO(input_data)

        count = capture_from_stream(
            input_stream=input_stream,
            output_path=output_file,
            cli_version="1.0.52",
            model="test-model",
            task="Test capture",
        )

        assert count == 4
        assert output_file.exists()

        # Verify recording format
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 5  # 1 metadata + 4 events

        # Check metadata
        meta = json.loads(lines[0])
        assert "_recording" in meta
        assert meta["_recording"]["cli_version"] == "1.0.52"
        assert meta["_recording"]["event_count"] == 4
        assert meta["_recording"]["capture_method"] == "container_logs"

        # Check events have timing
        event1 = json.loads(lines[1])
        assert "_offset_ms" in event1
        assert event1["event_type"] == "session_started"

    def test_filters_non_events(self, tmp_path: Path):
        """Non-event lines are filtered out."""
        output_file = tmp_path / "test.jsonl"

        input_data = """Log line 1
Log line 2
{"event_type": "test_event", "session_id": "s1"}
Another log
"""
        input_stream = io.StringIO(input_data)

        count = capture_from_stream(
            input_stream=input_stream,
            output_path=output_file,
        )

        assert count == 1

        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 2  # 1 metadata + 1 event

    def test_empty_stream(self, tmp_path: Path):
        """Empty stream produces empty recording."""
        output_file = tmp_path / "test.jsonl"
        input_stream = io.StringIO("")

        count = capture_from_stream(
            input_stream=input_stream,
            output_path=output_file,
        )

        assert count == 0
        assert output_file.exists()

        # Still has metadata
        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 1
        meta = json.loads(lines[0])
        assert meta["_recording"]["event_count"] == 0

    def test_timing_offsets_increase(self, tmp_path: Path):
        """Timing offsets increase monotonically."""
        output_file = tmp_path / "test.jsonl"

        # Multiple events
        events = [
            '{"event_type": "e1", "session_id": "s1"}',
            '{"event_type": "e2", "session_id": "s1"}',
            '{"event_type": "e3", "session_id": "s1"}',
        ]
        input_stream = io.StringIO("\n".join(events))

        capture_from_stream(
            input_stream=input_stream,
            output_path=output_file,
        )

        lines = output_file.read_text().strip().split("\n")[1:]  # Skip metadata
        offsets = [json.loads(line)["_offset_ms"] for line in lines]

        # Offsets should be monotonically increasing
        for i in range(1, len(offsets)):
            assert offsets[i] >= offsets[i - 1]

    def test_captures_session_id(self, tmp_path: Path):
        """Session ID is captured in metadata."""
        output_file = tmp_path / "test.jsonl"

        input_data = '{"event_type": "start", "session_id": "my-session-id"}'
        input_stream = io.StringIO(input_data)

        capture_from_stream(
            input_stream=input_stream,
            output_path=output_file,
        )

        lines = output_file.read_text().strip().split("\n")
        meta = json.loads(lines[0])
        assert meta["_recording"]["session_id"] == "my-session-id"
