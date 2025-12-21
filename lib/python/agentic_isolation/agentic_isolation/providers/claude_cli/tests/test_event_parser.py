"""Tests for Claude CLI event parser."""

import pytest
from agentic_isolation.providers.claude_cli.event_parser import EventParser
from agentic_isolation.providers.claude_cli.types import EventType


class TestEventParser:
    """Tests for EventParser."""

    def test_parse_system_event(self) -> None:
        """Should parse system.init as session_started."""
        parser = EventParser(session_id="test-session")

        line = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-5"}'
        event = parser.parse_line(line)

        assert event is not None
        assert event.event_type == EventType.SESSION_STARTED
        assert event.session_id == "test-session"

    def test_parse_tool_use_caches_name(self) -> None:
        """Should cache tool_name from tool_use for later enrichment."""
        parser = EventParser(session_id="test-session")

        # Assistant message with tool_use
        line = '''{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_123", "name": "Bash", "input": {"command": "ls"}}
        ]}}'''
        event = parser.parse_line(line)

        assert event is not None
        assert event.event_type == EventType.TOOL_EXECUTION_STARTED
        assert event.tool_name == "Bash"
        assert event.tool_use_id == "toolu_123"

        # Verify cached
        assert parser._tool_names["toolu_123"] == "Bash"

    def test_parse_tool_result_enriches_name(self) -> None:
        """Should enrich tool_result with cached tool_name."""
        parser = EventParser(session_id="test-session")

        # First, parse tool_use to cache the name
        tool_use_line = '''{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_abc", "name": "Read", "input": {}}
        ]}}'''
        parser.parse_line(tool_use_line)

        # Then parse tool_result (which doesn't have name)
        tool_result_line = '''{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_abc", "content": "file contents"}
        ]}}'''
        event = parser.parse_line(tool_result_line)

        assert event is not None
        assert event.event_type == EventType.TOOL_EXECUTION_COMPLETED
        assert event.tool_name == "Read"  # Enriched from cache!
        assert event.tool_use_id == "toolu_abc"
        assert event.success is True

    def test_parse_tool_result_without_cache_returns_unknown(self) -> None:
        """Should return 'unknown' if tool_name not in cache."""
        parser = EventParser(session_id="test-session")

        # Parse tool_result without prior tool_use
        line = '''{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_missing", "content": "output"}
        ]}}'''
        event = parser.parse_line(line)

        assert event is not None
        assert event.tool_name == "unknown"

    def test_parse_tool_result_with_error(self) -> None:
        """Should set success=False when is_error=True."""
        parser = EventParser(session_id="test-session")

        line = '''{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_err", "is_error": true}
        ]}}'''
        event = parser.parse_line(line)

        assert event is not None
        assert event.success is False

    def test_parse_result_event(self) -> None:
        """Should parse result as session_completed."""
        parser = EventParser(session_id="test-session")

        line = '''{"type": "result", "is_error": false, "usage": {
            "input_tokens": 100, "output_tokens": 50
        }}'''
        event = parser.parse_line(line)

        assert event is not None
        assert event.event_type == EventType.SESSION_COMPLETED
        assert event.success is True

    def test_skip_non_json_lines(self) -> None:
        """Should return None for non-JSON lines."""
        parser = EventParser(session_id="test-session")

        event = parser.parse_line("not json at all")
        assert event is None

        event = parser.parse_line("")
        assert event is None

    def test_skip_recording_metadata(self) -> None:
        """Should skip lines with _recording metadata."""
        parser = EventParser(session_id="test-session")

        line = '{"_recording": {"version": 1, "cli_version": "2.0.74"}}'
        event = parser.parse_line(line)

        assert event is None

    def test_summary_aggregates_tool_calls(self) -> None:
        """Should aggregate tool calls in summary."""
        parser = EventParser(session_id="test-session")

        # Parse multiple tool_use events
        parser.parse_line('''{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}
        ]}}''')
        parser.parse_line('''{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}
        ]}}''')
        parser.parse_line('''{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {}}
        ]}}''')

        summary = parser.get_summary()

        assert summary.tool_calls == {"Bash": 2, "Read": 1}
        assert summary.total_tool_calls == 3
