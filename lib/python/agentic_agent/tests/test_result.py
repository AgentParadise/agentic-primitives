"""Tests for result types."""

from datetime import datetime, UTC

import pytest

from agentic_agent.result import ToolCall, SessionMetrics, AgentResult


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_basic_creation(self) -> None:
        """Should create a tool call record."""
        tool_call = ToolCall(
            tool_name="Write",
            tool_input={"path": "test.py", "content": "print('hello')"},
        )
        assert tool_call.tool_name == "Write"
        assert tool_call.success is True

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        tool_call = ToolCall(
            tool_name="Bash",
            tool_input={"command": "ls"},
            tool_use_id="toolu_123",
            success=True,
        )
        data = tool_call.to_dict()
        assert data["tool_name"] == "Bash"
        assert data["tool_use_id"] == "toolu_123"
        assert "timestamp" in data

    def test_failed_tool_call(self) -> None:
        """Should record failed tool calls."""
        tool_call = ToolCall(
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            success=False,
            error="Blocked by security policy",
        )
        assert tool_call.success is False
        assert "security" in tool_call.error.lower()


class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_basic_creation(self) -> None:
        """Should create session metrics."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test-123",
            model="claude-sonnet-4-20250514",
            start_time=now,
            end_time=now,
            input_tokens=1000,
            output_tokens=500,
        )
        assert metrics.session_id == "test-123"
        assert metrics.total_tokens == 1500

    def test_total_tokens(self) -> None:
        """Should calculate total tokens."""
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            input_tokens=1000,
            output_tokens=2000,
        )
        assert metrics.total_tokens == 3000

    def test_tokens_per_second(self) -> None:
        """Should calculate token velocity."""
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            input_tokens=1000,
            output_tokens=1000,
            duration_ms=1000,  # 1 second
        )
        assert metrics.tokens_per_second == 2000.0

    def test_tokens_per_second_zero_duration(self) -> None:
        """Should handle zero duration."""
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC),
            duration_ms=0,
        )
        assert metrics.tokens_per_second == 0.0

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test-123",
            model="claude-sonnet-4-20250514",
            start_time=now,
            end_time=now,
            input_tokens=1000,
            output_tokens=500,
            total_cost_usd=0.05,
        )
        data = metrics.to_dict()
        assert data["session_id"] == "test-123"
        assert data["total_tokens"] == 1500
        assert data["total_cost_usd"] == 0.05


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_successful_result(self) -> None:
        """Should create successful result."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=now,
            end_time=now,
        )
        result = AgentResult(
            text="Hello, world!",
            metrics=metrics,
            success=True,
        )
        assert result.success is True
        assert result.text == "Hello, world!"

    def test_failed_result(self) -> None:
        """Should create failed result."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=now,
            end_time=now,
        )
        result = AgentResult(
            text="",
            metrics=metrics,
            success=False,
            error="API error",
        )
        assert result.success is False
        assert result.error == "API error"

    def test_with_tool_calls(self) -> None:
        """Should include tool calls."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=now,
            end_time=now,
        )
        tool_calls = [
            ToolCall(tool_name="Read", tool_input={"path": "file.txt"}),
            ToolCall(tool_name="Write", tool_input={"path": "out.txt", "content": "data"}),
        ]
        result = AgentResult(
            text="Done",
            metrics=metrics,
            tool_calls=tool_calls,
        )
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].tool_name == "Read"

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        now = datetime.now(UTC)
        metrics = SessionMetrics(
            session_id="test",
            model="test",
            start_time=now,
            end_time=now,
        )
        result = AgentResult(
            text="Hello",
            metrics=metrics,
        )
        data = result.to_dict()
        assert data["text"] == "Hello"
        assert data["success"] is True
        assert "metrics" in data
