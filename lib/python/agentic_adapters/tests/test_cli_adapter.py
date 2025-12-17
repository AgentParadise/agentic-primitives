"""Tests for Claude CLI adapter."""

import pytest
from pathlib import Path

from agentic_adapters.claude_cli import (
    generate_hooks,
    generate_pre_tool_use_hook,
    generate_post_tool_use_hook,
    HookTemplate,
)


class TestHookTemplate:
    """Tests for HookTemplate."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        template = HookTemplate()

        assert template.security_enabled is True
        assert template.observability_enabled is True
        assert template.observability_backend == "jsonl"
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
