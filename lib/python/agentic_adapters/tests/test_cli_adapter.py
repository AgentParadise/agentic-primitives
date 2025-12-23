"""Tests for Claude CLI adapter."""

from pathlib import Path

import pytest

from agentic_adapters.claude_cli import (
    ClaudeCLIRunner,
    CLIResult,
    HookTemplate,
    generate_hooks,
    generate_post_tool_use_hook,
    generate_pre_tool_use_hook,
)


class TestHookTemplate:
    """Tests for HookTemplate."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        template = HookTemplate()

        assert template.security_enabled is True
        assert template.observability_enabled is True
        assert template.observability_backend == "events"
        assert template.make_executable is True

    def test_custom_paths(self) -> None:
        """Should support custom paths."""
        template = HookTemplate(
            jsonl_path="/custom/events.jsonl",
        )

        assert template.jsonl_path == "/custom/events.jsonl"


class TestGeneratePreToolUseHook:
    """Tests for generate_pre_tool_use_hook."""

    def test_generates_valid_python(self) -> None:
        """Should generate valid Python code."""
        code = generate_pre_tool_use_hook()

        # Should be valid syntax
        compile(code, "<string>", "exec")

    def test_includes_security_policy(self) -> None:
        """Should include security policy when enabled."""
        template = HookTemplate(security_enabled=True)
        code = generate_pre_tool_use_hook(template)

        assert "SecurityPolicy" in code
        assert "validate" in code

    def test_disabled_security(self) -> None:
        """Should skip security when disabled."""
        template = HookTemplate(security_enabled=False)
        code = generate_pre_tool_use_hook(template)

        assert "SecurityPolicy" not in code
        assert "allow" in code

    def test_includes_main_entry(self) -> None:
        """Should include main entry point."""
        code = generate_pre_tool_use_hook()

        assert "def main()" in code
        assert "__main__" in code


class TestGeneratePostToolUseHook:
    """Tests for generate_post_tool_use_hook."""

    def test_generates_valid_python(self) -> None:
        """Should generate valid Python code."""
        code = generate_post_tool_use_hook()

        # Should be valid syntax
        compile(code, "<string>", "exec")

    def test_jsonl_backend(self) -> None:
        """Should generate JSONL recording code."""
        template = HookTemplate(
            observability_enabled=True,
            observability_backend="jsonl",
        )
        code = generate_post_tool_use_hook(template)

        assert "events.jsonl" in code
        assert "open(" in code

    def test_http_backend(self) -> None:
        """Should generate HTTP recording code."""
        template = HookTemplate(
            observability_enabled=True,
            observability_backend="http",
        )
        code = generate_post_tool_use_hook(template)

        assert "urlopen" in code
        assert "POST" in code

    def test_disabled_observability(self) -> None:
        """Should skip recording when disabled."""
        template = HookTemplate(observability_enabled=False)
        code = generate_post_tool_use_hook(template)

        assert "pass" in code
        assert "Observability disabled" in code

    def test_includes_main_entry(self) -> None:
        """Should include main entry point."""
        code = generate_post_tool_use_hook()

        assert "def main()" in code
        assert "__main__" in code


class TestGenerateHooks:
    """Tests for generate_hooks."""

    def test_creates_files(self, tmp_path: Path) -> None:
        """Should create hook files."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(output_dir)

        assert len(files) == 2
        assert all(f.exists() for f in files)

    def test_makes_executable(self, tmp_path: Path) -> None:
        """Should make files executable by default."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(output_dir)

        for f in files:
            assert f.stat().st_mode & 0o100  # Executable

    def test_no_executable(self, tmp_path: Path) -> None:
        """Should not make files executable when disabled."""
        output_dir = tmp_path / "hooks"
        template = HookTemplate(make_executable=False)

        files = generate_hooks(output_dir, template=template)

        for f in files:
            assert not (f.stat().st_mode & 0o100)

    def test_only_security(self, tmp_path: Path) -> None:
        """Should only generate security hook when observability disabled."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(
            output_dir,
            security_enabled=True,
            observability_enabled=False,
        )

        assert len(files) == 1
        assert files[0].name == "pre_tool_use.py"

    def test_only_observability(self, tmp_path: Path) -> None:
        """Should only generate observability hook when security disabled."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(
            output_dir,
            security_enabled=False,
            observability_enabled=True,
        )

        assert len(files) == 1
        assert files[0].name == "post_tool_use.py"

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Should create output directory if needed."""
        output_dir = tmp_path / "nested" / "hooks"

        files = generate_hooks(output_dir)

        assert output_dir.exists()
        assert len(files) == 2

    def test_events_backend(self, tmp_path: Path) -> None:
        """Should generate agentic_events recording code."""
        output_dir = tmp_path / "hooks"
        template = HookTemplate(
            observability_enabled=True,
            observability_backend="events",
        )

        generate_hooks(output_dir, template=template)

        post_code = (output_dir / "post_tool_use.py").read_text()
        assert "agentic_events" in post_code
        assert "EventEmitter" in post_code


class TestClaudeCLIRunner:
    """Tests for ClaudeCLIRunner."""

    def test_init_default_values(self) -> None:
        """Should have sensible defaults."""
        runner = ClaudeCLIRunner()

        assert runner.cwd == "/workspace"
        assert runner.permission_mode == "bypassPermissions"
        assert runner.claude_command == "claude"

    def test_init_invalid_permission_mode(self) -> None:
        """Should reject invalid permission mode."""
        with pytest.raises(ValueError):
            ClaudeCLIRunner(permission_mode="invalid")

    def test_get_env(self) -> None:
        """Should return environment with extra vars."""
        runner = ClaudeCLIRunner(extra_env={"CUSTOM_VAR": "value"})
        env = runner.get_env()

        assert "CUSTOM_VAR" in env
        assert env["CUSTOM_VAR"] == "value"

    def test_get_command(self) -> None:
        """Should build correct command."""
        runner = ClaudeCLIRunner()
        cmd = runner.get_command("test prompt")

        assert "claude" in cmd
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_get_command_bypass_permissions(self) -> None:
        """Should include bypass permissions flag."""
        runner = ClaudeCLIRunner(permission_mode="bypassPermissions")
        cmd = runner.get_command("test")

        assert "--dangerously-skip-permissions" in cmd

    def test_get_command_allowed_tools(self) -> None:
        """Should include allowed tools."""
        runner = ClaudeCLIRunner(allowed_tools=["Read", "Write"])
        cmd = runner.get_command("test")

        assert "--allowedTools" in cmd
        idx = cmd.index("--allowedTools")
        assert cmd[idx + 1] == "Read,Write"


class TestCLIResult:
    """Tests for CLIResult dataclass."""

    def test_success_result(self) -> None:
        """Should create successful result."""
        result = CLIResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            duration_seconds=1.5,
            events=[{"event_type": "test"}],
        )

        assert result.success is True
        assert result.exit_code == 0
        assert len(result.events) == 1

    def test_failed_result(self) -> None:
        """Should create failed result."""
        result = CLIResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="error",
            duration_seconds=0.5,
        )

        assert result.success is False
        assert result.exit_code == 1
        assert result.events == []
