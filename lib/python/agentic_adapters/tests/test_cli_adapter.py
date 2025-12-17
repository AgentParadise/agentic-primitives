"""Tests for Claude CLI adapter."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
        assert template.observability_backend == "otel"  # Changed from jsonl
        assert template.make_executable is True
        assert template.otel_service_name == "agentic-hooks"

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
            observability_endpoint="http://test:8080/events",
        )
        code = generate_post_tool_use_hook(template)

        assert "http://test:8080/events" in code
        assert "urllib" in code

    def test_disabled_observability(self) -> None:
        """Should skip observability when disabled."""
        template = HookTemplate(observability_enabled=False)
        code = generate_post_tool_use_hook(template)

        assert "pass" in code  # No-op

    def test_includes_main_entry(self) -> None:
        """Should include main entry point."""
        code = generate_post_tool_use_hook()

        assert "def main()" in code
        assert "__main__" in code


class TestGenerateHooks:
    """Tests for generate_hooks."""

    def test_creates_both_files(self, tmp_path: Path) -> None:
        """Should create pre and post hook files."""
        output_dir = tmp_path / ".claude" / "hooks"

        files = generate_hooks(output_dir)

        assert len(files) == 2
        assert (output_dir / "pre_tool_use.py").exists()
        assert (output_dir / "post_tool_use.py").exists()

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Should create output directory if missing."""
        output_dir = tmp_path / "nested" / "deep" / "hooks"

        generate_hooks(output_dir)

        assert output_dir.exists()

    def test_security_only(self, tmp_path: Path) -> None:
        """Should create only pre hook when observability disabled."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(
            output_dir,
            security_enabled=True,
            observability_enabled=False,
        )

        assert len(files) == 1
        assert (output_dir / "pre_tool_use.py").exists()
        assert not (output_dir / "post_tool_use.py").exists()

    def test_observability_only(self, tmp_path: Path) -> None:
        """Should create only post hook when security disabled."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(
            output_dir,
            security_enabled=False,
            observability_enabled=True,
        )

        assert len(files) == 1
        assert (output_dir / "post_tool_use.py").exists()
        assert not (output_dir / "pre_tool_use.py").exists()

    def test_makes_executable(self, tmp_path: Path) -> None:
        """Should make files executable."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(output_dir)

        for f in files:
            mode = f.stat().st_mode
            assert mode & 0o100  # Owner executable bit

    def test_non_executable(self, tmp_path: Path) -> None:
        """Should respect make_executable=False."""
        output_dir = tmp_path / "hooks"
        template = HookTemplate(make_executable=False)

        files = generate_hooks(output_dir, template=template)

        for f in files:
            mode = f.stat().st_mode
            assert not (mode & 0o100)  # No owner executable bit

    def test_custom_template(self, tmp_path: Path) -> None:
        """Should use custom template."""
        output_dir = tmp_path / "hooks"
        template = HookTemplate(
            blocked_paths=["/custom/blocked"],
            observability_backend="http",
            observability_endpoint="http://custom:9000",
        )

        generate_hooks(output_dir, template=template)

        pre_content = (output_dir / "pre_tool_use.py").read_text()
        post_content = (output_dir / "post_tool_use.py").read_text()

        assert "/custom/blocked" in pre_content
        assert "http://custom:9000" in post_content

    def test_generated_code_is_valid(self, tmp_path: Path) -> None:
        """Should generate syntactically valid Python."""
        output_dir = tmp_path / "hooks"

        generate_hooks(output_dir)

        pre_code = (output_dir / "pre_tool_use.py").read_text()
        post_code = (output_dir / "post_tool_use.py").read_text()

        # Both should compile without syntax errors
        compile(pre_code, "pre_tool_use.py", "exec")
        compile(post_code, "post_tool_use.py", "exec")

    def test_returns_file_paths(self, tmp_path: Path) -> None:
        """Should return list of created file paths."""
        output_dir = tmp_path / "hooks"

        files = generate_hooks(output_dir)

        assert all(isinstance(f, Path) for f in files)
        assert all(f.exists() for f in files)

    def test_otel_backend(self, tmp_path: Path) -> None:
        """Should generate OTel recording code."""
        output_dir = tmp_path / "hooks"
        template = HookTemplate(
            observability_enabled=True,
            observability_backend="otel",
            observability_endpoint="http://collector:4317",
        )

        generate_hooks(output_dir, template=template)

        post_code = (output_dir / "post_tool_use.py").read_text()
        assert "agentic_otel" in post_code
        assert "OTelConfig" in post_code
        assert "HookOTelEmitter" in post_code


class TestClaudeCLIRunner:
    """Tests for ClaudeCLIRunner."""

    @pytest.fixture
    def mock_otel_config(self) -> MagicMock:
        """Create a mock OTelConfig."""
        config = MagicMock()
        config.to_env.return_value = {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://test:4317",
        }
        return config

    def test_init_default_values(self, mock_otel_config: MagicMock) -> None:
        """Should have sensible defaults."""
        runner = ClaudeCLIRunner(otel_config=mock_otel_config)

        assert runner.cwd == "/workspace"
        assert runner.permission_mode == "bypassPermissions"
        assert runner.claude_command == "claude"

    def test_init_invalid_permission_mode(self, mock_otel_config: MagicMock) -> None:
        """Should reject invalid permission modes."""
        with pytest.raises(ValueError, match="Invalid permission_mode"):
            ClaudeCLIRunner(
                otel_config=mock_otel_config,
                permission_mode="invalid",
            )

    def test_get_env_includes_otel(self, mock_otel_config: MagicMock) -> None:
        """Should include OTel config in environment."""
        runner = ClaudeCLIRunner(otel_config=mock_otel_config)

        env = runner.get_env()

        assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
        assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://test:4317"

    def test_get_env_includes_extra(self, mock_otel_config: MagicMock) -> None:
        """Should include extra env vars."""
        runner = ClaudeCLIRunner(
            otel_config=mock_otel_config,
            extra_env={"CUSTOM_VAR": "value"},
        )

        env = runner.get_env()

        assert env["CUSTOM_VAR"] == "value"

    def test_get_command_basic(self, mock_otel_config: MagicMock) -> None:
        """Should build basic command."""
        runner = ClaudeCLIRunner(
            otel_config=mock_otel_config,
            permission_mode="default",
        )

        cmd = runner.get_command("Hello")

        assert cmd == ["claude", "--print", "Hello"]

    def test_get_command_bypass_permissions(self, mock_otel_config: MagicMock) -> None:
        """Should add skip permissions flag."""
        runner = ClaudeCLIRunner(
            otel_config=mock_otel_config,
            permission_mode="bypassPermissions",
        )

        cmd = runner.get_command("Hello")

        assert "--dangerously-skip-permissions" in cmd

    def test_get_command_plan_mode(self, mock_otel_config: MagicMock) -> None:
        """Should configure plan mode."""
        runner = ClaudeCLIRunner(
            otel_config=mock_otel_config,
            permission_mode="plan",
        )

        cmd = runner.get_command("Hello")

        assert "--allowedTools" in cmd

    @pytest.mark.asyncio
    async def test_run_not_found(self, mock_otel_config: MagicMock) -> None:
        """Should raise FileNotFoundError if claude not found."""
        runner = ClaudeCLIRunner(
            otel_config=mock_otel_config,
            claude_command="nonexistent-claude-command",
        )

        with pytest.raises(FileNotFoundError, match="Claude CLI not found"):
            await runner.run("Hello")

    @pytest.mark.asyncio
    async def test_run_success(self, mock_otel_config: MagicMock) -> None:
        """Should return CLIResult on success."""
        runner = ClaudeCLIRunner(otel_config=mock_otel_config)

        # Mock subprocess
        with patch.object(runner, "_find_claude", return_value=True):
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_process = MagicMock()
                mock_process.returncode = 0
                mock_process.communicate = MagicMock(return_value=(b"output", b""))
                mock_exec.return_value = mock_process

                # Make communicate awaitable
                async def mock_communicate() -> tuple[bytes, bytes]:
                    return (b"output", b"")

                mock_process.communicate = mock_communicate

                result = await runner.run("Hello")

                assert isinstance(result, CLIResult)
                assert result.success is True
                assert result.exit_code == 0
                assert result.stdout == "output"
