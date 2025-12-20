"""Tests for EventEmitter."""

import io
import json

from agentic_events import EventEmitter, EventType, SecurityDecision


class TestEventEmitter:
    """Tests for EventEmitter class."""

    def test_init(self):
        """Test emitter initialization."""
        emitter = EventEmitter(session_id="test-123", provider="claude")
        assert emitter.session_id == "test-123"
        assert emitter.provider == "claude"

    def test_emit_basic(self):
        """Test basic event emission."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.emit(EventType.SESSION_STARTED, {"source": "startup"})

        assert event["event_type"] == "session_started"
        assert event["session_id"] == "test-123"
        assert event["context"]["source"] == "startup"
        assert "timestamp" in event

        # Verify JSONL output
        output.seek(0)
        line = output.readline()
        parsed = json.loads(line)
        assert parsed["event_type"] == "session_started"

    def test_tool_started(self):
        """Test tool started event."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.tool_started("Bash", "toolu_abc", "git status")

        assert event["event_type"] == "tool_execution_started"
        assert event["context"]["tool_name"] == "Bash"
        assert event["context"]["tool_use_id"] == "toolu_abc"
        assert event["context"]["input_preview"] == "git status"

    def test_tool_completed(self):
        """Test tool completed event."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.tool_completed(
            "Bash",
            "toolu_abc",
            success=True,
            duration_ms=150,
            output_preview="On branch main",
        )

        assert event["event_type"] == "tool_execution_completed"
        assert event["context"]["tool_name"] == "Bash"
        assert event["context"]["success"] is True
        assert event["context"]["duration_ms"] == 150
        assert event["context"]["output_preview"] == "On branch main"

    def test_tool_duration_auto_calculated(self):
        """Test that duration is auto-calculated when tool_started was called."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        emitter.tool_started("Bash", "toolu_abc", "sleep 0.01")
        # Small sleep to ensure measurable duration
        import time

        time.sleep(0.01)
        event = emitter.tool_completed("Bash", "toolu_abc", success=True)

        assert "duration_ms" in event["context"]
        assert event["context"]["duration_ms"] >= 10  # At least 10ms

    def test_security_decision_block(self):
        """Test security decision block event."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.security_decision(
            "Bash",
            SecurityDecision.BLOCK,
            reason="Dangerous command: rm -rf /",
            validators=["bash_validator"],
        )

        assert event["event_type"] == "security_decision"
        assert event["context"]["tool_name"] == "Bash"
        assert event["context"]["decision"] == "block"
        assert event["context"]["reason"] == "Dangerous command: rm -rf /"
        assert event["context"]["validators"] == ["bash_validator"]

    def test_session_completed(self):
        """Test session completed event."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.session_completed(reason="normal", duration_ms=5000)

        assert event["event_type"] == "session_completed"
        assert event["context"]["reason"] == "normal"
        assert event["context"]["duration_ms"] == 5000

    def test_context_compacted(self):
        """Test context compacted event."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        event = emitter.context_compacted(before_tokens=10000, after_tokens=3000)

        assert event["event_type"] == "context_compacted"
        assert event["context"]["before_tokens"] == 10000
        assert event["context"]["after_tokens"] == 3000
        assert event["context"]["reduction_percent"] == 70.0

    def test_input_preview_truncated(self):
        """Test that long input previews are truncated."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        long_input = "x" * 1000
        event = emitter.tool_started("Bash", "toolu_abc", long_input, max_preview_length=100)

        assert len(event["context"]["input_preview"]) == 100

    def test_multiple_events_jsonl(self):
        """Test that multiple events produce valid JSONL."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-123", output=output)

        emitter.session_started()
        emitter.tool_started("Bash", "toolu_1", "echo hello")
        emitter.tool_completed("Bash", "toolu_1", success=True, duration_ms=10)
        emitter.session_completed()

        output.seek(0)
        lines = output.readlines()
        assert len(lines) == 4

        # All lines should be valid JSON
        for line in lines:
            event = json.loads(line)
            assert "event_type" in event
            assert "timestamp" in event
            assert "session_id" in event
