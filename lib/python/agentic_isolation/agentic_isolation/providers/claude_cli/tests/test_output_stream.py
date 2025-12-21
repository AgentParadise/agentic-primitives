"""Tests for SessionOutputStream."""

import pytest
from agentic_isolation.providers.claude_cli.output_stream import (
    SessionOutputStream,
    create_output_stream,
)
from agentic_isolation.providers.claude_cli.types import EventType


class TestSessionOutputStream:
    """Tests for SessionOutputStream."""

    @pytest.fixture
    def sample_lines(self) -> list[str]:
        """Sample Claude CLI JSONL lines."""
        return [
            '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-5"}',
            '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]}}',
            '{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "file1.txt"}]}}',
            '{"type": "result", "is_error": false, "usage": {"input_tokens": 100, "output_tokens": 50}}',
        ]

    async def test_tee_yields_lines_and_events(self, sample_lines: list[str]) -> None:
        """tee() should yield both raw lines and parsed events."""
        stream = await create_output_stream("test-session", sample_lines)

        lines_collected = []
        events_collected = []

        async for line, event in stream.tee():
            lines_collected.append(line)
            if event:
                events_collected.append(event)

        assert len(lines_collected) == 4
        assert len(events_collected) == 4  # All 4 lines produce events

    async def test_events_only(self, sample_lines: list[str]) -> None:
        """events() should yield only parsed events."""
        stream = await create_output_stream("test-session", sample_lines)

        events = []
        async for event in stream.events():
            events.append(event)

        assert len(events) == 4
        assert events[0].event_type == EventType.SESSION_STARTED
        assert events[1].event_type == EventType.TOOL_EXECUTION_STARTED
        assert events[2].event_type == EventType.TOOL_EXECUTION_COMPLETED
        assert events[3].event_type == EventType.SESSION_COMPLETED

    async def test_raw_lines_only(self, sample_lines: list[str]) -> None:
        """raw_lines() should yield only raw lines."""
        stream = await create_output_stream("test-session", sample_lines)

        lines = []
        async for line in stream.raw_lines():
            lines.append(line)

        assert len(lines) == 4
        assert '"type": "system"' in lines[0]

    async def test_summary_after_consumption(self, sample_lines: list[str]) -> None:
        """get_summary() should return summary after consumption."""
        stream = await create_output_stream("test-session", sample_lines)

        # Consume the stream
        async for _ in stream.events():
            pass

        summary = stream.get_summary()

        assert summary.session_id == "test-session"
        assert summary.tool_calls == {"Bash": 1}
        assert summary.total_tool_calls == 1
        assert summary.success is True

    async def test_summary_before_consumption_raises(self, sample_lines: list[str]) -> None:
        """get_summary() should raise if stream not consumed."""
        stream = await create_output_stream("test-session", sample_lines)

        with pytest.raises(RuntimeError, match="must be consumed"):
            stream.get_summary()

    async def test_consume_returns_summary(self, sample_lines: list[str]) -> None:
        """consume() should consume stream and return summary."""
        stream = await create_output_stream("test-session", sample_lines)

        summary = await stream.consume()

        assert summary.session_id == "test-session"
        assert summary.event_count == 4

    async def test_buffers_accessible_after_consumption(self, sample_lines: list[str]) -> None:
        """Buffers should be accessible after consumption."""
        stream = await create_output_stream("test-session", sample_lines)

        await stream.consume()

        assert len(stream.raw_lines_buffer) == 4
        assert len(stream.events_buffer) == 4

    async def test_tool_name_enrichment(self, sample_lines: list[str]) -> None:
        """Tool result should have enriched tool_name."""
        stream = await create_output_stream("test-session", sample_lines)

        events = []
        async for event in stream.events():
            events.append(event)

        # tool_execution_completed should have tool_name from tool_use
        completed_event = events[2]
        assert completed_event.event_type == EventType.TOOL_EXECUTION_COMPLETED
        assert completed_event.tool_name == "Bash"  # Enriched from tool_use
