"""Tests for HookEvent and EventType."""

from datetime import UTC, datetime

from agentic_hooks.events import EventType, HookEvent


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self) -> None:
        """Test that all event types have correct values."""
        assert EventType.SESSION_STARTED.value == "session_started"
        assert EventType.SESSION_COMPLETED.value == "session_completed"
        assert EventType.TOOL_EXECUTION_STARTED.value == "tool_execution_started"
        assert EventType.TOOL_EXECUTION_COMPLETED.value == "tool_execution_completed"
        assert EventType.TOOL_BLOCKED.value == "tool_blocked"
        assert EventType.AGENT_REQUEST_STARTED.value == "agent_request_started"
        assert EventType.AGENT_REQUEST_COMPLETED.value == "agent_request_completed"
        assert EventType.USER_PROMPT_SUBMITTED.value == "user_prompt_submitted"
        assert EventType.HOOK_DECISION.value == "hook_decision"
        assert EventType.CUSTOM.value == "custom"

    def test_event_type_is_string_enum(self) -> None:
        """Test that EventType is a string enum."""
        assert isinstance(EventType.SESSION_STARTED, str)
        assert EventType.SESSION_STARTED == "session_started"


class TestHookEvent:
    """Tests for HookEvent dataclass."""

    def test_create_event_with_enum(self) -> None:
        """Test creating event with EventType enum."""
        event = HookEvent(
            event_type=EventType.SESSION_STARTED,
            session_id="session-123",
        )

        assert event.event_type == EventType.SESSION_STARTED
        assert event.session_id == "session-123"
        assert event.workflow_id is None
        assert event.data == {}
        assert isinstance(event.event_id, str)
        assert len(event.event_id) == 36  # UUID format
        assert isinstance(event.timestamp, datetime)

    def test_create_event_with_string(self) -> None:
        """Test creating event with custom string type."""
        event = HookEvent(
            event_type="custom_event_type",
            session_id="session-123",
        )

        assert event.event_type == "custom_event_type"

    def test_create_event_with_all_fields(self) -> None:
        """Test creating event with all optional fields."""
        timestamp = datetime.now(UTC)
        event = HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
            workflow_id="workflow-456",
            phase_id="phase-1",
            milestone_id="milestone-1",
            data={"tool_name": "Write", "file_path": "app.py"},
            event_id="custom-event-id",
            timestamp=timestamp,
        )

        assert event.event_type == EventType.TOOL_EXECUTION_STARTED
        assert event.session_id == "session-123"
        assert event.workflow_id == "workflow-456"
        assert event.phase_id == "phase-1"
        assert event.milestone_id == "milestone-1"
        assert event.data == {"tool_name": "Write", "file_path": "app.py"}
        assert event.event_id == "custom-event-id"
        assert event.timestamp == timestamp

    def test_to_dict_with_enum(self) -> None:
        """Test to_dict serializes enum value correctly."""
        event = HookEvent(
            event_type=EventType.SESSION_STARTED,
            session_id="session-123",
        )

        result = event.to_dict()

        assert result["event_type"] == "session_started"
        assert result["session_id"] == "session-123"
        assert result["workflow_id"] is None
        assert result["data"] == {}
        assert "event_id" in result
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)

    def test_to_dict_with_string(self) -> None:
        """Test to_dict with custom string event type."""
        event = HookEvent(
            event_type="custom_type",
            session_id="session-123",
        )

        result = event.to_dict()

        assert result["event_type"] == "custom_type"

    def test_to_dict_includes_all_fields(self) -> None:
        """Test to_dict includes all fields."""
        event = HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
            workflow_id="workflow-456",
            phase_id="phase-1",
            milestone_id="milestone-1",
            data={"key": "value"},
        )

        result = event.to_dict()

        assert result["workflow_id"] == "workflow-456"
        assert result["phase_id"] == "phase-1"
        assert result["milestone_id"] == "milestone-1"
        assert result["data"] == {"key": "value"}

    def test_from_dict_with_enum_value(self) -> None:
        """Test from_dict creates event from dict with enum value."""
        data = {
            "event_type": "session_started",
            "session_id": "session-123",
            "workflow_id": "workflow-456",
            "data": {"key": "value"},
        }

        event = HookEvent.from_dict(data)

        assert event.event_type == EventType.SESSION_STARTED
        assert event.session_id == "session-123"
        assert event.workflow_id == "workflow-456"
        assert event.data == {"key": "value"}

    def test_from_dict_with_custom_type(self) -> None:
        """Test from_dict with custom string event type."""
        data = {
            "event_type": "my_custom_type",
            "session_id": "session-123",
        }

        event = HookEvent.from_dict(data)

        assert event.event_type == "my_custom_type"

    def test_from_dict_with_timestamp_string(self) -> None:
        """Test from_dict parses timestamp string."""
        timestamp_str = "2025-12-01T10:30:00+00:00"
        data = {
            "event_type": "session_started",
            "session_id": "session-123",
            "timestamp": timestamp_str,
        }

        event = HookEvent.from_dict(data)

        assert isinstance(event.timestamp, datetime)
        assert event.timestamp.year == 2025
        assert event.timestamp.month == 12
        assert event.timestamp.day == 1

    def test_from_dict_with_timestamp_datetime(self) -> None:
        """Test from_dict accepts datetime object."""
        timestamp = datetime.now(UTC)
        data = {
            "event_type": "session_started",
            "session_id": "session-123",
            "timestamp": timestamp,
        }

        event = HookEvent.from_dict(data)

        assert event.timestamp == timestamp

    def test_from_dict_missing_fields(self) -> None:
        """Test from_dict handles missing optional fields."""
        data = {
            "event_type": "session_started",
        }

        event = HookEvent.from_dict(data)

        assert event.session_id == ""
        assert event.workflow_id is None
        assert event.data == {}
        assert isinstance(event.event_id, str)
        assert isinstance(event.timestamp, datetime)

    def test_roundtrip_to_dict_from_dict(self) -> None:
        """Test roundtrip conversion to_dict -> from_dict."""
        original = HookEvent(
            event_type=EventType.TOOL_EXECUTION_COMPLETED,
            session_id="session-123",
            workflow_id="workflow-456",
            phase_id="phase-1",
            milestone_id="milestone-1",
            data={"result": "success", "count": 42},
        )

        data = original.to_dict()
        restored = HookEvent.from_dict(data)

        assert restored.event_type == EventType.TOOL_EXECUTION_COMPLETED
        assert restored.session_id == original.session_id
        assert restored.workflow_id == original.workflow_id
        assert restored.phase_id == original.phase_id
        assert restored.milestone_id == original.milestone_id
        assert restored.data == original.data
        assert restored.event_id == original.event_id


class TestHookEventDefaults:
    """Tests for HookEvent default values."""

    def test_auto_generated_event_id_is_unique(self) -> None:
        """Test that auto-generated event IDs are unique."""
        events = [
            HookEvent(event_type=EventType.SESSION_STARTED, session_id="s1") for _ in range(100)
        ]

        event_ids = [e.event_id for e in events]
        assert len(set(event_ids)) == 100  # All unique

    def test_auto_generated_timestamp_is_recent(self) -> None:
        """Test that auto-generated timestamp is recent."""
        before = datetime.now(UTC)
        event = HookEvent(event_type=EventType.SESSION_STARTED, session_id="s1")
        after = datetime.now(UTC)

        assert before <= event.timestamp <= after

    def test_default_data_is_empty_dict(self) -> None:
        """Test that default data is an empty dict, not shared."""
        event1 = HookEvent(event_type=EventType.SESSION_STARTED, session_id="s1")
        event2 = HookEvent(event_type=EventType.SESSION_STARTED, session_id="s2")

        # Modify one event's data
        event1.data["key"] = "value"

        # Other event's data should be unaffected
        assert event2.data == {}
