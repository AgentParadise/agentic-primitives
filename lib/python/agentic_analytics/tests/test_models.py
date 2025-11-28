"""Tests for analytics models."""

import pytest

from agentic_analytics.models import HookDecision


class TestHookDecision:
    """Tests for HookDecision dataclass."""

    def test_create_minimal_decision(self) -> None:
        """Test creating a decision with minimal required fields."""
        decision = HookDecision(
            hook_id="test-hook",
            event_type="PreToolUse",
            decision="allow",
            session_id="sess-123",
        )

        assert decision.hook_id == "test-hook"
        assert decision.event_type == "PreToolUse"
        assert decision.decision == "allow"
        assert decision.session_id == "sess-123"
        assert decision.provider == "claude"  # Default
        assert decision.tool_name is None
        assert decision.reason is None
        assert decision.metadata == {}

    def test_create_full_decision(self) -> None:
        """Test creating a decision with all fields."""
        decision = HookDecision(
            hook_id="bash-validator",
            event_type="PreToolUse",
            decision="block",
            session_id="sess-456",
            provider="openai",
            tool_name="Bash",
            reason="Dangerous command detected",
            metadata={"command": "rm -rf /", "pattern": "rm -rf"},
        )

        assert decision.hook_id == "bash-validator"
        assert decision.provider == "openai"
        assert decision.tool_name == "Bash"
        assert decision.reason == "Dangerous command detected"
        assert decision.metadata["command"] == "rm -rf /"

    def test_to_dict(self) -> None:
        """Test converting decision to dictionary."""
        decision = HookDecision(
            hook_id="file-security",
            event_type="PreToolUse",
            decision="warn",
            session_id="sess-789",
            tool_name="Read",
            reason="Sensitive file access",
            metadata={"file_path": ".env"},
        )

        d = decision.to_dict()

        assert d["hook_id"] == "file-security"
        assert d["event_type"] == "PreToolUse"
        assert d["decision"] == "warn"
        assert d["session_id"] == "sess-789"
        assert d["provider"] == "claude"
        assert d["tool_name"] == "Read"
        assert d["reason"] == "Sensitive file access"
        assert d["metadata"]["file_path"] == ".env"

    def test_to_dict_minimal(self) -> None:
        """Test to_dict with minimal fields."""
        decision = HookDecision(
            hook_id="test",
            event_type="SessionStart",
            decision="allow",
            session_id="sess",
        )

        d = decision.to_dict()

        assert d["tool_name"] is None
        assert d["reason"] is None
        assert d["metadata"] == {}

    @pytest.mark.parametrize(
        "decision_type",
        ["allow", "block", "warn"],
    )
    def test_decision_types(self, decision_type: str) -> None:
        """Test all valid decision types."""
        decision = HookDecision(
            hook_id="test",
            event_type="PreToolUse",
            decision=decision_type,  # type: ignore[arg-type]
            session_id="sess",
        )

        assert decision.decision == decision_type
