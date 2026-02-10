"""Tests for Claude SDK adapter."""

from dataclasses import dataclass
from typing import Any

from agentic_adapters.claude_sdk import (
    HookConfig,
    create_agent_options,
    create_observability_hooks,
    create_security_hooks,
)


# Mock SecurityPolicy for testing
@dataclass
class MockSecurityPolicy:
    """Mock security policy."""

    blocked_tools: list[str] | None = None

    def validate(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """Mock validation."""

        @dataclass
        class Result:
            safe: bool
            reason: str | None = None

        if self.blocked_tools and tool_name in self.blocked_tools:
            return Result(safe=False, reason=f"Tool {tool_name} is blocked")
        return Result(safe=True)


class TestCreateSecurityHooks:
    """Tests for create_security_hooks."""

    def test_allows_safe_tools(self) -> None:
        """Should allow safe tool calls."""
        policy = MockSecurityPolicy()
        pre_hook, _ = create_security_hooks(policy)

        result = pre_hook("Write", {"path": "/tmp/test.txt"})
        assert result is None  # None means allow unchanged

    def test_blocks_dangerous_tools(self) -> None:
        """Should block dangerous tool calls."""
        policy = MockSecurityPolicy(blocked_tools=["Bash"])
        pre_hook, _ = create_security_hooks(policy, block_on_violation=True)

        result = pre_hook("Bash", {"command": "rm -rf /"})

        assert result is not None
        assert result.get("__blocked__") is True
        assert "blocked" in result.get("__reason__", "").lower()

    def test_block_includes_original_input(self) -> None:
        """Should preserve original input in blocked response."""
        policy = MockSecurityPolicy(blocked_tools=["Bash"])
        pre_hook, _ = create_security_hooks(policy)

        original_input = {"command": "dangerous"}
        result = pre_hook("Bash", original_input)

        assert result["__original_input__"] == original_input


class TestCreateObservabilityHooks:
    """Tests for create_observability_hooks."""

    def test_creates_pre_and_post_hooks(self) -> None:
        """Should create both hooks."""
        pre_hook, post_hook = create_observability_hooks()

        assert callable(pre_hook)
        assert callable(post_hook)

    def test_pre_hook_adds_tool_id(self) -> None:
        """Should add tool_id to input."""
        pre_hook, _ = create_observability_hooks()

        result = pre_hook("Write", {"path": "/test"})

        assert result is not None
        assert "__tool_id__" in result
        assert result["path"] == "/test"

    def test_post_hook_accepts_result(self) -> None:
        """Should accept tool result without error."""
        _, post_hook = create_observability_hooks()

        # Should not raise
        post_hook("Write", {"path": "/test"}, "success", duration_ms=100)

    def test_hooks_with_client(self) -> None:
        """Should work with mock hook client."""
        events: list[dict] = []

        class MockClient:
            def emit_sync(self, event: dict) -> None:
                events.append(event)

        client = MockClient()
        pre_hook, post_hook = create_observability_hooks(hook_client=client)

        # Call hooks
        result = pre_hook("Write", {"path": "/test"})
        post_hook("Write", result, "success", duration_ms=50)

        assert len(events) == 2
        assert events[0]["type"] == "tool_started"
        assert events[1]["type"] == "tool_completed"


class TestHookConfig:
    """Tests for HookConfig."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        config = HookConfig()

        assert config.security_policy is None
        assert config.block_on_violation is True
        assert config.observability_enabled is True
        assert config.custom_pre_tool_use == []
        assert config.custom_post_tool_use == []


class TestCreateAgentOptions:
    """Tests for create_agent_options."""

    def test_empty_options(self) -> None:
        """Should create options without hooks when nothing enabled."""
        config = HookConfig(
            security_policy=None,
            observability_enabled=False,
        )
        options = create_agent_options(config)

        assert "pre_tool_use" not in options
        assert "post_tool_use" not in options

    def test_security_only(self) -> None:
        """Should create options with security only."""
        policy = MockSecurityPolicy()
        options = create_agent_options(
            security_policy=policy,
            observability_enabled=False,
        )

        assert "pre_tool_use" in options
        # No post hook for security-only
        assert "post_tool_use" not in options

    def test_observability_only(self) -> None:
        """Should create options with observability only."""
        options = create_agent_options(
            security_policy=None,
            observability_enabled=True,
        )

        assert "pre_tool_use" in options  # For tool_id tracking
        assert "post_tool_use" in options

    def test_both_enabled(self) -> None:
        """Should create options with both security and observability."""
        policy = MockSecurityPolicy()
        options = create_agent_options(
            security_policy=policy,
            observability_enabled=True,
        )

        assert "pre_tool_use" in options
        assert "post_tool_use" in options

    def test_passes_extra_options(self) -> None:
        """Should pass through extra options."""
        options = create_agent_options(
            observability_enabled=False,
            model="claude-sonnet-4-20250514",
            max_turns=50,
        )

        assert options["model"] == "claude-sonnet-4-20250514"
        assert options["max_turns"] == 50

    def test_combined_hooks_run_in_order(self) -> None:
        """Should run security before observability."""
        policy = MockSecurityPolicy(blocked_tools=["DangerousTool"])
        options = create_agent_options(
            security_policy=policy,
            observability_enabled=True,
        )

        pre_hook = options["pre_tool_use"]

        # Safe tool should pass through
        safe_result = pre_hook("Write", {"path": "/test"})
        assert safe_result is None or "__blocked__" not in safe_result

        # Dangerous tool should be blocked
        blocked_result = pre_hook("DangerousTool", {"action": "bad"})
        assert blocked_result is not None
        assert blocked_result.get("__blocked__") is True

    def test_custom_hooks(self) -> None:
        """Should include custom hooks."""
        custom_pre_called = []
        custom_post_called = []

        def custom_pre(tool_name: str, tool_input: dict) -> dict | None:
            custom_pre_called.append(tool_name)
            return None

        def custom_post(
            tool_name: str, tool_input: dict, result: Any, duration: float | None
        ) -> None:
            custom_post_called.append(tool_name)

        config = HookConfig(
            observability_enabled=False,
            custom_pre_tool_use=[custom_pre],
            custom_post_tool_use=[custom_post],
        )
        options = create_agent_options(config)

        # Call hooks
        options["pre_tool_use"]("Write", {})
        options["post_tool_use"]("Write", {}, "result", 100)

        assert "Write" in custom_pre_called
        assert "Write" in custom_post_called
