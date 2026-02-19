"""Tests for new event types: SUBAGENT_STARTED, TOOL_EXECUTION_FAILED, TEAMMATE_IDLE, TASK_COMPLETED."""

import io
import json

import pytest

from agentic_events import EventEmitter, EventType

pytestmark = pytest.mark.unit


class TestNewEventTypes:
    """Verify new event types exist and have correct values."""

    def test_subagent_started_type(self):
        assert EventType.SUBAGENT_STARTED == "subagent_started"

    def test_tool_failed_type(self):
        assert EventType.TOOL_EXECUTION_FAILED == "tool_execution_failed"

    def test_teammate_idle_type(self):
        assert EventType.TEAMMATE_IDLE == "teammate_idle"

    def test_task_completed_type(self):
        assert EventType.TASK_COMPLETED == "task_completed"


class TestSubagentStartedEmitter:
    """Tests for subagent_started emitter method."""

    def test_basic(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-sa", output=output)

        event = emitter.subagent_started(subagent_id="sub-001")

        assert event["event_type"] == "subagent_started"
        assert event["context"]["subagent_id"] == "sub-001"
        assert event["context"]["agent_type"] == "subagent"

    def test_custom_agent_type(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-sa", output=output)

        event = emitter.subagent_started(subagent_id="tm-001", agent_type="teammate")

        assert event["context"]["agent_type"] == "teammate"

    def test_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-sa", output=output)

        emitter.subagent_started(subagent_id="sub-002")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "subagent_started"
        assert parsed["session_id"] == "test-sa"


class TestToolFailedEmitter:
    """Tests for tool_failed emitter method."""

    def test_basic(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-tf", output=output)

        event = emitter.tool_failed("Bash", "toolu_fail_1", error="command not found")

        assert event["event_type"] == "tool_execution_failed"
        assert event["context"]["tool_name"] == "Bash"
        assert event["context"]["tool_use_id"] == "toolu_fail_1"
        assert event["context"]["error"] == "command not found"

    def test_empty_error(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-tf", output=output)

        event = emitter.tool_failed("Write", "toolu_fail_2")

        assert event["context"]["error"] == ""

    def test_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-tf", output=output)

        emitter.tool_failed("Bash", "toolu_fail_3", error="timeout")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "tool_execution_failed"


class TestTeammateIdleEmitter:
    """Tests for teammate_idle emitter method."""

    def test_basic(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-ti", output=output)

        event = emitter.teammate_idle(teammate_id="agent-alpha")

        assert event["event_type"] == "teammate_idle"
        assert event["context"]["teammate_id"] == "agent-alpha"

    def test_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-ti", output=output)

        emitter.teammate_idle(teammate_id="agent-beta")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "teammate_idle"
        assert parsed["session_id"] == "test-ti"


class TestTaskCompletedEmitter:
    """Tests for task_completed emitter method."""

    def test_basic(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-tc", output=output)

        event = emitter.task_completed(task_id="task-42")

        assert event["event_type"] == "task_completed"
        assert event["context"]["task_id"] == "task-42"

    def test_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-tc", output=output)

        emitter.task_completed(task_id="task-99")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "task_completed"


class TestNewEventsIntegration:
    """Integration: new event types mixed with existing events produce valid JSONL."""

    def test_mixed_session(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-mixed", output=output)

        emitter.session_started()
        emitter.subagent_started(subagent_id="sub-1")
        emitter.tool_started("Bash", "toolu_1", "echo hi")
        emitter.tool_failed("Bash", "toolu_1", error="exit code 1")
        emitter.teammate_idle(teammate_id="peer-1")
        emitter.task_completed(task_id="task-1")
        emitter.session_completed()

        output.seek(0)
        lines = output.readlines()
        assert len(lines) == 7

        types = []
        for line in lines:
            event = json.loads(line)
            assert "event_type" in event
            assert "timestamp" in event
            assert event["session_id"] == "test-mixed"
            types.append(event["event_type"])

        assert "subagent_started" in types
        assert "tool_execution_failed" in types
        assert "teammate_idle" in types
        assert "task_completed" in types
        assert "session_started" in types
        assert "session_completed" in types
