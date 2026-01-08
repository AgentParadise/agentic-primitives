"""Tests for package exports - ensures clean public API for downstream consumers."""


class TestPackageExports:
    """Verify all public types are importable from the main package."""

    def test_main_api_exports(self) -> None:
        """Main workspace API should be importable."""
        from agentic_isolation import (
            AgenticWorkspace,
            register_provider,
        )

        # Verify they're the correct types
        assert AgenticWorkspace is not None
        assert callable(register_provider)

    def test_observability_exports(self) -> None:
        """Observability types should be importable from main package."""
        from agentic_isolation import (
            EventType,
        )

        # Verify EventType has expected members
        assert hasattr(EventType, "SESSION_STARTED")
        assert hasattr(EventType, "SESSION_COMPLETED")
        assert hasattr(EventType, "TOOL_EXECUTION_STARTED")
        assert hasattr(EventType, "TOOL_EXECUTION_COMPLETED")
        assert hasattr(EventType, "SUBAGENT_STARTED")
        assert hasattr(EventType, "SUBAGENT_STOPPED")
        assert hasattr(EventType, "TOKEN_USAGE")
        assert hasattr(EventType, "ERROR")

    def test_event_type_values(self) -> None:
        """EventType enum values should be stable strings."""
        from agentic_isolation import EventType

        # These string values are part of the public API
        # Changing them would break downstream consumers
        assert EventType.SESSION_STARTED == "session_started"
        assert EventType.SESSION_COMPLETED == "session_completed"
        assert EventType.SUBAGENT_STARTED == "subagent_started"
        assert EventType.SUBAGENT_STOPPED == "subagent_stopped"

    def test_session_summary_has_cost_fields(self) -> None:
        """SessionSummary should have cost and duration fields."""
        from datetime import UTC, datetime

        from agentic_isolation import SessionSummary

        summary = SessionSummary(
            session_id="test",
            started_at=datetime.now(UTC),
            total_cost_usd=0.05,
            result_duration_ms=5000,
            result_duration_api_ms=6000,
            num_turns=3,
        )

        assert summary.total_cost_usd == 0.05
        assert summary.duration_ms == 5000  # Prefers result_duration_ms
        assert summary.result_duration_api_ms == 6000
        assert summary.num_turns == 3

    def test_session_summary_to_dict_complete(self) -> None:
        """SessionSummary.to_dict() should include all fields."""
        from datetime import UTC, datetime

        from agentic_isolation import SessionSummary

        summary = SessionSummary(
            session_id="test",
            started_at=datetime.now(UTC),
            total_cost_usd=0.05,
            result_duration_ms=5000,
            subagent_count=2,
            subagent_names=["task1", "task2"],
            tools_by_subagent={"task1": {"Bash": 1}},
        )

        d = summary.to_dict()

        # Verify all key fields are present
        assert "session_id" in d
        assert "total_cost_usd" in d
        assert "duration_ms" in d
        assert "subagent_count" in d
        assert "subagent_names" in d
        assert "tools_by_subagent" in d

    def test_observability_event_has_subagent_fields(self) -> None:
        """ObservabilityEvent should have subagent-related fields."""
        from datetime import UTC, datetime

        from agentic_isolation import EventType, ObservabilityEvent

        event = ObservabilityEvent(
            event_type=EventType.SUBAGENT_STARTED,
            session_id="test",
            timestamp=datetime.now(UTC),
            raw_event={},
            agent_name="My Subagent",
            parent_tool_use_id="toolu_parent",
            subagent_tool_use_id="toolu_task",
        )

        assert event.agent_name == "My Subagent"
        assert event.parent_tool_use_id == "toolu_parent"
        assert event.subagent_tool_use_id == "toolu_task"

        # to_dict should include these
        d = event.to_dict()
        assert d["agent_name"] == "My Subagent"
        assert d["parent_tool_use_id"] == "toolu_parent"
