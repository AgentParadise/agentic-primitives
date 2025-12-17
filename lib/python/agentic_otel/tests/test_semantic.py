"""Tests for AgentSemanticConventions."""

from agentic_otel.semantic import AgentSemanticConventions as Sem


class TestAgentSemanticConventions:
    """Tests for semantic conventions."""

    def test_session_attributes_exist(self) -> None:
        """Test that session attributes are defined."""
        assert Sem.AGENT_SESSION_ID == "agent.session.id"

    def test_tool_attributes_exist(self) -> None:
        """Test that tool attributes are defined."""
        assert Sem.TOOL_NAME == "tool.name"
        assert Sem.TOOL_USE_ID == "tool.use_id"
        assert Sem.TOOL_INPUT == "tool.input"
        assert Sem.TOOL_OUTPUT_PREVIEW == "tool.output.preview"
        assert Sem.TOOL_SUCCESS == "tool.success"
        assert Sem.TOOL_DURATION_MS == "tool.duration_ms"
        assert Sem.TOOL_ERROR == "tool.error"

    def test_hook_attributes_exist(self) -> None:
        """Test that hook/security attributes are defined."""
        assert Sem.HOOK_TYPE == "hook.type"
        assert Sem.HOOK_DECISION == "hook.decision"
        assert Sem.HOOK_REASON == "hook.reason"
        assert Sem.HOOK_VALIDATORS == "hook.validators_run"

    def test_token_attributes_exist(self) -> None:
        """Test that token attributes are defined."""
        assert Sem.TOKEN_TYPE == "token.type"
        assert Sem.TOKEN_COUNT == "token.count"
        assert Sem.TOKEN_MODEL == "token.model"

    def test_event_names_exist(self) -> None:
        """Test that event names are defined."""
        assert Sem.EVENT_SECURITY_DECISION == "security.decision"
        assert Sem.EVENT_TOOL_STARTED == "tool.started"
        assert Sem.EVENT_TOOL_COMPLETED == "tool.completed"
        assert Sem.EVENT_TOOL_BLOCKED == "tool.blocked"

    def test_attributes_follow_naming_convention(self) -> None:
        """Test that all attributes follow OTel naming convention."""
        # Get all public attributes
        attrs = [
            getattr(Sem, name)
            for name in dir(Sem)
            if not name.startswith("_") and isinstance(getattr(Sem, name), str)
        ]

        for attr in attrs:
            # Should be lowercase
            assert attr == attr.lower(), f"{attr} should be lowercase"
            # Should use dots for namespacing
            assert "." in attr, f"{attr} should use dots for namespacing"
            # Should not have spaces
            assert " " not in attr, f"{attr} should not have spaces"
