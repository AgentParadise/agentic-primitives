"""Tests for Claude CLI event parser."""

from datetime import UTC, datetime, timedelta

from agentic_isolation.providers.claude_cli.event_parser import EventParser
from agentic_isolation.providers.claude_cli.types import EventType


def get_event_by_type(events: list, event_type: EventType):
    """Helper to find first event of a specific type."""
    for event in events:
        if event.event_type == event_type:
            return event
    return None


class TestEventParser:
    """Tests for EventParser."""

    def test_parse_system_event(self) -> None:
        """Should parse system.init as session_started."""
        parser = EventParser(session_id="test-session")

        line = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-5"}'
        events = parser.parse_line(line)

        assert len(events) == 1
        event = events[0]
        assert event.event_type == EventType.SESSION_STARTED
        assert event.session_id == "test-session"

    def test_parse_tool_use_caches_name(self) -> None:
        """Should cache tool_name from tool_use for later enrichment."""
        parser = EventParser(session_id="test-session")

        # Assistant message with tool_use
        line = """{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_123", "name": "Bash", "input": {"command": "ls"}}
        ]}}"""
        events = parser.parse_line(line)

        # Should have tool_execution_started event
        event = get_event_by_type(events, EventType.TOOL_EXECUTION_STARTED)
        assert event is not None
        assert event.tool_name == "Bash"
        assert event.tool_use_id == "toolu_123"

        # Verify cached
        assert parser._tool_names["toolu_123"] == "Bash"

    def test_parse_tool_result_enriches_name(self) -> None:
        """Should enrich tool_result with cached tool_name."""
        parser = EventParser(session_id="test-session")

        # First, parse tool_use to cache the name
        tool_use_line = """{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_abc", "name": "Read", "input": {}}
        ]}}"""
        parser.parse_line(tool_use_line)

        # Then parse tool_result (which doesn't have name)
        tool_result_line = """{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_abc", "content": "file contents"}
        ]}}"""
        events = parser.parse_line(tool_result_line)

        event = get_event_by_type(events, EventType.TOOL_EXECUTION_COMPLETED)
        assert event is not None
        assert event.tool_name == "Read"  # Enriched from cache!
        assert event.tool_use_id == "toolu_abc"
        assert event.success is True

    def test_parse_tool_result_without_cache_returns_unknown(self) -> None:
        """Should return 'unknown' if tool_name not in cache."""
        parser = EventParser(session_id="test-session")

        # Parse tool_result without prior tool_use
        line = """{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_missing", "content": "output"}
        ]}}"""
        events = parser.parse_line(line)

        event = get_event_by_type(events, EventType.TOOL_EXECUTION_COMPLETED)
        assert event is not None
        assert event.tool_name == "unknown"

    def test_parse_tool_result_with_error(self) -> None:
        """Should set success=False when is_error=True."""
        parser = EventParser(session_id="test-session")

        line = """{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_err", "is_error": true}
        ]}}"""
        events = parser.parse_line(line)

        event = get_event_by_type(events, EventType.TOOL_EXECUTION_COMPLETED)
        assert event is not None
        assert event.success is False

    def test_parse_result_event(self) -> None:
        """Should parse result as session_completed."""
        parser = EventParser(session_id="test-session")

        line = """{"type": "result", "is_error": false, "usage": {
            "input_tokens": 100, "output_tokens": 50
        }}"""
        events = parser.parse_line(line)

        assert len(events) == 1
        event = events[0]
        assert event.event_type == EventType.SESSION_COMPLETED
        assert event.success is True

    def test_skip_non_json_lines(self) -> None:
        """Should return empty list for non-JSON lines."""
        parser = EventParser(session_id="test-session")

        events = parser.parse_line("not json at all")
        assert events == []

        events = parser.parse_line("")
        assert events == []

    def test_skip_recording_metadata(self) -> None:
        """Should skip lines with _recording metadata."""
        parser = EventParser(session_id="test-session")

        line = '{"_recording": {"version": 1, "cli_version": "2.0.74"}}'
        events = parser.parse_line(line)

        assert events == []  # Empty list, but base_time should be set

    def test_summary_aggregates_tool_calls(self) -> None:
        """Should aggregate tool calls in summary."""
        parser = EventParser(session_id="test-session")

        # Parse multiple tool_use events
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}
        ]}}""")
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}
        ]}}""")
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t3", "name": "Bash", "input": {}}
        ]}}""")

        summary = parser.get_summary()

        assert summary.tool_calls == {"Bash": 2, "Read": 1}
        assert summary.total_tool_calls == 3

    def test_assistant_with_tool_use_emits_both_token_usage_and_tool_event(self) -> None:
        """Assistant message with tool_use AND usage should emit both event types."""
        parser = EventParser(session_id="test-session")

        # Assistant message with BOTH tool_use content AND usage data
        line = """{"type": "assistant", "message": {
            "content": [{"type": "tool_use", "id": "toolu_xyz", "name": "Bash", "input": {"cmd": "ls"}}],
            "usage": {"input_tokens": 100, "output_tokens": 50}
        }}"""
        events = parser.parse_line(line)

        # Should have BOTH token_usage AND tool_execution_started
        assert len(events) == 2

        token_event = get_event_by_type(events, EventType.TOKEN_USAGE)
        assert token_event is not None
        assert token_event.tokens.input_tokens == 100
        assert token_event.tokens.output_tokens == 50

        tool_event = get_event_by_type(events, EventType.TOOL_EXECUTION_STARTED)
        assert tool_event is not None
        assert tool_event.tool_name == "Bash"


class TestSubagentTracking:
    """Tests for subagent lifecycle tracking."""

    def test_task_tool_emits_subagent_started(self) -> None:
        """Task tool usage should emit SUBAGENT_STARTED event."""
        parser = EventParser(session_id="test-session")

        line = """{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "task_123", "name": "Task", "input": {
                "description": "List all files",
                "prompt": "Run ls -la"
            }}
        ]}}"""
        events = parser.parse_line(line)

        event = get_event_by_type(events, EventType.SUBAGENT_STARTED)
        assert event is not None
        assert event.tool_name == "Task"
        assert event.tool_use_id == "task_123"
        assert event.agent_name == "List all files"
        assert event.subagent_tool_use_id == "task_123"

    def test_task_result_emits_subagent_stopped(self) -> None:
        """Task tool_result should emit SUBAGENT_STOPPED event."""
        parser = EventParser(session_id="test-session")

        # First, start the subagent
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "task_456", "name": "Task", "input": {
                "description": "Check status"
            }}
        ]}}""")

        # Then complete it
        line = """{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "task_456", "content": "done"}
        ]}}"""
        events = parser.parse_line(line)

        event = get_event_by_type(events, EventType.SUBAGENT_STOPPED)
        assert event is not None
        assert event.agent_name == "Check status"
        assert event.subagent_tool_use_id == "task_456"
        assert event.duration_ms is not None
        assert event.duration_ms >= 0

    def test_concurrent_subagents_tracked_independently(self) -> None:
        """Multiple concurrent subagents should be tracked independently."""
        parser = EventParser(session_id="test-session")

        # Start two subagents
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "task_a", "name": "Task", "input": {"description": "Task A"}}
        ]}}""")
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "task_b", "name": "Task", "input": {"description": "Task B"}}
        ]}}""")

        assert parser.get_active_subagent_count() == 2

        # Complete first subagent
        events_a = parser.parse_line("""{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "task_a", "content": "done"}
        ]}}""")

        event_a = get_event_by_type(events_a, EventType.SUBAGENT_STOPPED)
        assert event_a is not None
        assert event_a.agent_name == "Task A"
        assert parser.get_active_subagent_count() == 1

        # Complete second subagent
        events_b = parser.parse_line("""{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "task_b", "content": "done"}
        ]}}""")

        event_b = get_event_by_type(events_b, EventType.SUBAGENT_STOPPED)
        assert event_b is not None
        assert event_b.agent_name == "Task B"
        assert parser.get_active_subagent_count() == 0

    def test_subagent_name_from_prompt_if_no_description(self) -> None:
        """Should extract name from prompt if description not provided."""
        parser = EventParser(session_id="test-session")

        line = """{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "task_789", "name": "Task", "input": {
                "prompt": "List all Python files in the current directory"
            }}
        ]}}"""
        events = parser.parse_line(line)

        event = get_event_by_type(events, EventType.SUBAGENT_STARTED)
        assert event is not None
        assert event.agent_name == "List all Python files in the current directory"

    def test_summary_includes_subagent_metrics(self) -> None:
        """Summary should include subagent count and names."""
        parser = EventParser(session_id="test-session")

        # Start and complete two subagents
        parser.parse_line("""{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Task", "input": {"description": "First task"}}
        ]}}""")
        parser.parse_line("""{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "done"}
        ]}}""")

        parser.parse_line(
            '{"type": "assistant", "message": {"content": ['
            '{"type": "tool_use", "id": "t2", "name": "Task", '
            '"input": {"description": "Second task"}}]}}'
        )
        parser.parse_line("""{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "done"}
        ]}}""")

        summary = parser.get_summary()

        assert summary.subagent_count == 2
        assert "First task" in summary.subagent_names
        assert "Second task" in summary.subagent_names

    def test_subagent_tools_tracked_via_parent_id(self) -> None:
        """Tools used by subagent should be tracked via parent_tool_use_id."""
        parser = EventParser(session_id="test-session")

        # Start subagent
        parser.parse_line(
            '{"type": "assistant", "message": {"content": ['
            '{"type": "tool_use", "id": "task_sub", "name": "Task", '
            '"input": {"description": "Sub task"}}]}}'
        )

        # Subagent uses Bash tool (with parent_tool_use_id)
        parser.parse_line(
            '{"type": "assistant", "parent_tool_use_id": "task_sub", '
            '"message": {"content": [{"type": "tool_use", "id": "bash_1", '
            '"name": "Bash", "input": {"command": "ls"}}]}}'
        )

        # Subagent uses Read tool
        parser.parse_line(
            '{"type": "assistant", "parent_tool_use_id": "task_sub", '
            '"message": {"content": [{"type": "tool_use", "id": "read_1", '
            '"name": "Read", "input": {"file": "test.txt"}}]}}'
        )

        # Complete subagent
        parser.parse_line("""{"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "task_sub", "content": "done"}
        ]}}""")

        summary = parser.get_summary()

        assert "Sub task" in summary.tools_by_subagent
        assert summary.tools_by_subagent["Sub task"] == {"Bash": 1, "Read": 1}


class TestRecordingPlayback:
    """Tests for recording timestamp handling."""

    def test_recording_metadata_sets_base_time(self) -> None:
        """Recording metadata should set base time for offset calculation."""
        parser = EventParser(session_id="test-session")

        # Parse recording metadata
        metadata_line = (
            '{"_recording": {"version": 1, "cli_version": "2.0.76", '
            '"recorded_at": "2026-01-08T10:00:00+00:00"}}'
        )
        events = parser.parse_line(metadata_line)

        assert events == []  # Metadata is skipped
        assert parser._base_time is not None
        assert parser._base_time.year == 2026
        assert parser._base_time.month == 1
        assert parser._base_time.day == 8

    def test_offset_ms_used_for_timestamp(self) -> None:
        """Events with _offset_ms should use base_time + offset."""
        parser = EventParser(session_id="test-session")

        # Set base time
        base = datetime(2026, 1, 8, 10, 0, 0, tzinfo=UTC)
        parser.set_base_time(base)

        # Parse event with offset
        line = '{"type": "system", "subtype": "init", "_offset_ms": 1500}'
        events = parser.parse_line(line)

        assert len(events) == 1
        event = events[0]
        # Timestamp should be base + 1.5 seconds
        expected = base + timedelta(milliseconds=1500)
        assert event.timestamp == expected

    def test_subagent_duration_from_offsets(self) -> None:
        """Subagent duration should be calculated from recording offsets."""
        parser = EventParser(session_id="test-session")

        # Set base time
        base = datetime(2026, 1, 8, 10, 0, 0, tzinfo=UTC)
        parser.set_base_time(base)

        # Start subagent at offset 1000ms
        parser.parse_line(
            '{"type": "assistant", "_offset_ms": 1000, "message": {"content": ['
            '{"type": "tool_use", "id": "task_1", "name": "Task", '
            '"input": {"description": "Test task"}}]}}'
        )

        # Complete subagent at offset 3500ms (2.5 seconds later)
        events = parser.parse_line(
            '{"type": "user", "_offset_ms": 3500, "message": {"content": ['
            '{"type": "tool_result", "tool_use_id": "task_1", "content": "done"}]}}'
        )

        event = get_event_by_type(events, EventType.SUBAGENT_STOPPED)
        assert event is not None
        assert event.duration_ms == 2500  # 3500 - 1000 = 2500ms


class TestCostAndDuration:
    """Tests for cost and duration extraction from result event."""

    def test_result_extracts_cost(self) -> None:
        """Result event should extract total_cost_usd."""
        parser = EventParser(session_id="test-session")

        line = (
            '{"type": "result", "is_error": false, "total_cost_usd": 0.064721, '
            '"duration_ms": 7423, "duration_api_ms": 8135, "num_turns": 3}'
        )
        parser.parse_line(line)

        summary = parser.get_summary()

        assert summary.total_cost_usd == 0.064721
        assert summary.result_duration_ms == 7423
        assert summary.result_duration_api_ms == 8135
        assert summary.num_turns == 3

    def test_summary_duration_prefers_result(self) -> None:
        """Summary duration_ms should prefer result event value."""
        parser = EventParser(session_id="test-session")

        # Parse system init (sets started_at)
        parser.parse_line('{"type": "system", "subtype": "init"}')

        # Parse result with explicit duration
        parser.parse_line('{"type": "result", "is_error": false, "duration_ms": 5000}')

        summary = parser.get_summary()

        # Should use result duration, not calculated
        assert summary.duration_ms == 5000

    def test_summary_to_dict_includes_cost(self) -> None:
        """Summary to_dict should include cost and duration fields."""
        parser = EventParser(session_id="test-session")

        parser.parse_line('{"type": "system", "subtype": "init"}')
        parser.parse_line(
            '{"type": "result", "total_cost_usd": 0.05, '
            '"duration_ms": 3000, "duration_api_ms": 4000, "num_turns": 2}'
        )

        summary = parser.get_summary()
        d = summary.to_dict()

        assert d["total_cost_usd"] == 0.05
        assert d["duration_ms"] == 3000
        assert d["duration_api_ms"] == 4000
        assert d["num_turns"] == 2
