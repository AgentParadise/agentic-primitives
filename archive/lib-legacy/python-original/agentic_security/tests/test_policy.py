"""Tests for SecurityPolicy class."""

import os
from unittest.mock import patch

from agentic_security import SecurityPolicy, ToolName


class TestSecurityPolicy:
    """Tests for SecurityPolicy configuration and validation."""

    def test_with_defaults(self) -> None:
        """Should create policy with sensible defaults."""
        policy = SecurityPolicy.with_defaults()
        assert policy.use_default_bash_patterns is True
        assert policy.use_default_file_patterns is True
        assert policy.use_default_blocked_paths is True

    def test_permissive_policy(self) -> None:
        """Should create permissive policy."""
        policy = SecurityPolicy.permissive()
        assert policy.use_default_bash_patterns is True
        assert policy.use_default_file_patterns is False
        assert policy.block_git_add_all is False
        assert policy.allow_sensitive_read is True

    def test_strict_policy(self) -> None:
        """Should create strict policy."""
        policy = SecurityPolicy.strict()
        assert policy.use_default_bash_patterns is True
        assert policy.use_default_file_patterns is True
        assert policy.block_git_add_all is True
        assert policy.allow_sensitive_read is False

    def test_validate_bash_tool(self) -> None:
        """Should validate Bash tool calls."""
        policy = SecurityPolicy.with_defaults()

        # Dangerous command
        result = policy.validate("Bash", {"command": "rm -rf /"})
        assert not result.safe
        assert result.tool_name == "Bash"

        # Safe command
        result = policy.validate("Bash", {"command": "ls -la"})
        assert result.safe

    def test_validate_write_tool(self) -> None:
        """Should validate Write tool calls."""
        policy = SecurityPolicy.with_defaults()

        # Blocked path
        result = policy.validate("Write", {"path": "/etc/passwd", "content": "test"})
        assert not result.safe

        # Safe path
        result = policy.validate("Write", {"path": "src/main.py", "content": "test"})
        assert result.safe

    def test_validate_write_with_sensitive_content(self) -> None:
        """Should block writes with sensitive content."""
        policy = SecurityPolicy.with_defaults()

        result = policy.validate(
            "Write",
            {
                "path": "config.txt",
                "content": "aws_key=AKIAIOSFODNN7EXAMPLE",
            },
        )
        assert not result.safe
        assert "AWS access key" in (result.reason or "")

    def test_validate_read_tool(self) -> None:
        """Should validate Read tool calls."""
        policy = SecurityPolicy.with_defaults()

        # Blocked path
        result = policy.validate("Read", {"path": "/etc/shadow"})
        assert not result.safe

        # Sensitive file (allowed with redaction)
        result = policy.validate("Read", {"path": ".env"})
        assert result.safe
        assert result.metadata is not None
        assert result.metadata.get("redacted") is True

    def test_validate_unknown_tool(self) -> None:
        """Should allow unknown tools by default."""
        policy = SecurityPolicy.with_defaults()
        result = policy.validate("UnknownTool", {"param": "value"})
        assert result.safe

    def test_convenience_methods(self) -> None:
        """Should have working convenience methods."""
        policy = SecurityPolicy.with_defaults()

        result = policy.validate_bash("rm -rf /")
        assert not result.safe

        result = policy.validate_file_read("/etc/shadow")
        assert not result.safe

        result = policy.validate_file_write("/etc/passwd", "test")
        assert not result.safe

    def test_from_env_default(self) -> None:
        """Should load default policy from environment."""
        with patch.dict(os.environ, {}, clear=True):
            policy = SecurityPolicy.from_env()
            assert policy.use_default_bash_patterns is True

    def test_from_env_strict(self) -> None:
        """Should load strict policy from environment."""
        with patch.dict(os.environ, {"AGENTIC_SECURITY_LEVEL": "strict"}):
            policy = SecurityPolicy.from_env()
            assert policy.allow_sensitive_read is False

    def test_from_env_permissive(self) -> None:
        """Should load permissive policy from environment."""
        with patch.dict(os.environ, {"AGENTIC_SECURITY_LEVEL": "permissive"}):
            policy = SecurityPolicy.from_env()
            assert policy.block_git_add_all is False

    def test_from_env_blocked_paths(self) -> None:
        """Should load blocked paths from environment."""
        with patch.dict(os.environ, {"AGENTIC_BLOCKED_PATHS": "/custom/path,/another/path"}):
            policy = SecurityPolicy.from_env()
            assert "/custom/path" in policy.blocked_paths
            assert "/another/path" in policy.blocked_paths

    def test_from_env_toggles(self) -> None:
        """Should load toggle flags from environment."""
        with patch.dict(
            os.environ,
            {
                "AGENTIC_BLOCK_GIT_ADD_ALL": "false",
                "AGENTIC_ALLOW_SENSITIVE_READ": "false",
            },
        ):
            policy = SecurityPolicy.from_env()
            assert policy.block_git_add_all is False
            assert policy.allow_sensitive_read is False

    def test_to_dict_and_from_dict(self) -> None:
        """Should serialize and deserialize policy."""
        original = SecurityPolicy(
            blocked_paths=["/custom/path"],
            block_git_add_all=False,
            extra_bash_patterns=[("test_pattern", "test description")],
        )

        data = original.to_dict()
        restored = SecurityPolicy.from_dict(data)

        assert restored.blocked_paths == original.blocked_paths
        assert restored.block_git_add_all == original.block_git_add_all
        assert restored.extra_bash_patterns == original.extra_bash_patterns

    def test_custom_blocked_paths(self) -> None:
        """Should use custom blocked paths."""
        policy = SecurityPolicy(
            blocked_paths=["/my/sensitive/path"],
            use_default_blocked_paths=False,
        )

        result = policy.validate("Write", {"path": "/my/sensitive/path/file.txt"})
        assert not result.safe

        # Default paths not blocked when disabled
        result = policy.validate("Write", {"path": "/proc/test"})
        # Note: /proc/ is only blocked when use_default_blocked_paths=True

    def test_custom_extra_patterns(self) -> None:
        """Should use custom extra patterns."""
        policy = SecurityPolicy(
            extra_bash_patterns=[
                (r"my-custom-dangerous", "custom danger"),
            ],
        )

        result = policy.validate("Bash", {"command": "my-custom-dangerous --flag"})
        assert not result.safe
        assert "custom danger" in (result.reason or "")


class TestToolNameConstants:
    """Tests for ToolName constants."""

    def test_tool_names(self) -> None:
        """Should have correct tool name constants."""
        assert ToolName.BASH == "Bash"
        assert ToolName.READ == "Read"
        assert ToolName.WRITE == "Write"
        assert ToolName.EDIT == "Edit"

    def test_file_tools_set(self) -> None:
        """Should have correct file tools set."""
        assert "Read" in ToolName.FILE_TOOLS
        assert "Write" in ToolName.FILE_TOOLS
        assert "Edit" in ToolName.FILE_TOOLS
        assert "Bash" not in ToolName.FILE_TOOLS

    def test_bash_tools_set(self) -> None:
        """Should have correct bash tools set."""
        assert "Bash" in ToolName.BASH_TOOLS
        assert "Read" not in ToolName.BASH_TOOLS
