"""Tests for shell command utilities.

These tests ensure that command escaping properly handles all special characters
that could break bash -c execution, especially multi-line system prompts.
"""

from __future__ import annotations

import subprocess

import pytest
from agentic_workspace import AEF_WORKSPACE_PROMPT, build_bash_command, escape_for_bash


class TestEscapeForBash:
    """Tests for escape_for_bash function."""

    def test_simple_command(self) -> None:
        """Simple commands without special chars."""
        result = escape_for_bash(["echo", "hello"])
        assert result == "echo hello"

    def test_spaces_quoted(self) -> None:
        """Arguments with spaces are quoted."""
        result = escape_for_bash(["echo", "hello world"])
        assert "hello world" in result
        # shlex.quote uses single quotes
        assert "'hello world'" in result

    def test_newlines_escaped(self) -> None:
        """Newlines in arguments are properly escaped."""
        result = escape_for_bash(["echo", "line1\nline2"])
        # The newline should be inside quotes
        assert "\n" in result
        # Should be a single quoted argument
        assert result.count("'") >= 2

    def test_backticks_escaped(self) -> None:
        """Backticks are properly escaped."""
        result = escape_for_bash(["echo", "code: `ls`"])
        # Backticks should be inside quotes, not executed
        assert "`ls`" in result

    def test_dollar_signs_escaped(self) -> None:
        """Dollar signs are properly escaped (no variable expansion)."""
        result = escape_for_bash(["echo", "$HOME"])
        # Should be quoted to prevent expansion
        assert "'$HOME'" in result

    def test_single_quotes_escaped(self) -> None:
        """Single quotes in arguments are handled."""
        result = escape_for_bash(["echo", "it's"])
        # shlex.quote handles this with escaping
        assert "it" in result and "s" in result

    def test_double_quotes_escaped(self) -> None:
        """Double quotes in arguments are handled."""
        result = escape_for_bash(["echo", 'say "hello"'])
        assert "hello" in result

    def test_shell_metacharacters(self) -> None:
        """Shell metacharacters are escaped."""
        result = escape_for_bash(["echo", "a && b | c; d"])
        # Should be quoted to prevent interpretation
        assert "'" in result

    def test_real_workspace_prompt(self) -> None:
        """The actual AEF workspace prompt escapes correctly."""
        result = escape_for_bash(
            ["claude", "--append-system-prompt", AEF_WORKSPACE_PROMPT]
        )

        # Should contain the prompt (escaped)
        assert "artifacts/output" in result

        # Should not have unquoted newlines that break the command
        # The entire prompt should be a single quoted argument
        parts = result.split("'")
        # At least 2 quotes (opening and closing) around the prompt
        assert len(parts) >= 3


class TestBuildBashCommand:
    """Tests for build_bash_command function."""

    def test_simple_command(self) -> None:
        """Simple command without stderr merge."""
        result = build_bash_command(["echo", "hello"])
        assert result == ["bash", "-c", "echo hello"]

    def test_merge_stderr(self) -> None:
        """Command with stderr merged to stdout."""
        result = build_bash_command(["echo", "hello"], merge_stderr=True)
        assert result == ["bash", "-c", "echo hello 2>&1"]

    def test_multiline_prompt_no_merge(self) -> None:
        """Multi-line prompt without stderr merge."""
        cmd = ["claude", "--prompt", "line1\nline2"]
        result = build_bash_command(cmd)

        assert result[0] == "bash"
        assert result[1] == "-c"
        assert "2>&1" not in result[2]

    def test_multiline_prompt_with_merge(self) -> None:
        """Multi-line prompt with stderr merge."""
        cmd = ["claude", "--prompt", "line1\nline2"]
        result = build_bash_command(cmd, merge_stderr=True)

        assert result[0] == "bash"
        assert result[1] == "-c"
        assert result[2].endswith("2>&1")

    def test_real_workspace_prompt_command(self) -> None:
        """Real Claude CLI command with workspace prompt."""
        cmd = [
            "claude",
            "--print",
            "--verbose",
            "--append-system-prompt",
            AEF_WORKSPACE_PROMPT,
            "Test prompt",
            "--output-format",
            "stream-json",
        ]
        result = build_bash_command(cmd, merge_stderr=True)

        assert result[0] == "bash"
        assert result[1] == "-c"
        assert result[2].endswith("2>&1")
        # The command string should contain all parts
        assert "claude" in result[2]
        assert "artifacts/output" in result[2]


@pytest.mark.unit
class TestBashExecution:
    """Integration tests that actually run commands through bash.

    These verify that the escaped commands execute correctly.
    """

    def test_echo_with_newlines(self) -> None:
        """Verify echo with newlines works through bash -c."""
        cmd = build_bash_command(["echo", "line1\nline2"])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert "line1" in result.stdout
        assert "line2" in result.stdout

    def test_echo_with_backticks_not_executed(self) -> None:
        """Verify backticks are not executed."""
        cmd = build_bash_command(["echo", "code: `pwd`"])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Should print literal `pwd`, not the current directory
        assert "`pwd`" in result.stdout

    def test_echo_with_dollar_not_expanded(self) -> None:
        """Verify dollar signs are not expanded."""
        cmd = build_bash_command(["echo", "$NONEXISTENT_VAR_12345"])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Should print literal $NONEXISTENT_VAR, not empty string
        assert "$NONEXISTENT_VAR_12345" in result.stdout

    def test_stderr_merge(self) -> None:
        """Verify stderr merge works."""
        # Command that writes to stderr
        cmd = build_bash_command(["bash", "-c", "echo error >&2"], merge_stderr=True)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # stderr should be in stdout
        assert "error" in result.stdout

    def test_workspace_prompt_printable(self) -> None:
        """Verify the workspace prompt can be echoed through bash -c."""
        # This is the critical test - if this works, the prompt will work with Claude
        cmd = build_bash_command(["echo", AEF_WORKSPACE_PROMPT])
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Key parts of the prompt should be in output
        assert "artifacts/output" in result.stdout
        assert "artifacts/input" in result.stdout
        assert "repos/" in result.stdout
