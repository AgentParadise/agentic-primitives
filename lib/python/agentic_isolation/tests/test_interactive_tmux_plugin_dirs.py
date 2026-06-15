"""Unit tests for `ITMUX_CLAUDE_PLUGIN_DIRS` / `claude_plugin_dirs`.

Covers the workflow-skills bridge finding (Syntropic137 repo,
`feat/workflow-skills`, `docs/plans/workflow-skills.md` §9): injecting
plugins via `~/.claude.json` `installedPlugins` is silently ignored by
the tmux-driven `claude` TUI; only the `--plugin-dir` CLI flag actually
loads plugins. The driver builds one `--plugin-dir <path>` flag per
entry. These tests assert the constructed launch command contains the
flags verbatim, including a tmux-send-keys integration test that
captures the actual argv handed to `_tmux_send_literal`.

No container is spawned.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest


def _load_driver_module():
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = (
            ancestor
            / "providers"
            / "workspaces"
            / "interactive-tmux"
            / "driver"
            / "interactive_tmux.py"
        )
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interactive_tmux", candidate)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("interactive_tmux", module)
            spec.loader.exec_module(module)
            return module
    pytest.skip("interactive_tmux driver not found in repo layout")


driver = _load_driver_module()


@pytest.fixture
def clean_plugin_env() -> Iterator[None]:
    saved = os.environ.pop("ITMUX_CLAUDE_PLUGIN_DIRS", None)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("ITMUX_CLAUDE_PLUGIN_DIRS", None)
        else:
            os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = saved


class TestDefaultClaudePluginDirsFromEnv:
    """`_default_claude_plugin_dirs_from_env` parses `:`-separated paths."""

    def test_unset_yields_empty_list(self, clean_plugin_env: None) -> None:
        assert driver._default_claude_plugin_dirs_from_env() == []

    def test_empty_string_yields_empty_list(self, clean_plugin_env: None) -> None:
        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = ""
        assert driver._default_claude_plugin_dirs_from_env() == []

    def test_single_path(self, clean_plugin_env: None) -> None:
        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = "/opt/skills"
        assert driver._default_claude_plugin_dirs_from_env() == [Path("/opt/skills")]

    def test_multiple_paths_in_path_order(self, clean_plugin_env: None) -> None:
        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = "/opt/a:/opt/b:/opt/c"
        assert driver._default_claude_plugin_dirs_from_env() == [
            Path("/opt/a"),
            Path("/opt/b"),
            Path("/opt/c"),
        ]

    def test_empty_entries_dropped(self, clean_plugin_env: None) -> None:
        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = "/opt/a::/opt/b:"
        assert driver._default_claude_plugin_dirs_from_env() == [
            Path("/opt/a"),
            Path("/opt/b"),
        ]


class TestBuildLaunchCommand:
    """`_ClaudeAdapter.build_launch_command` returns the exact shell string."""

    def test_no_plugin_dirs_yields_bare_claude(self) -> None:
        assert driver._ClaudeAdapter.build_launch_command() == "claude"
        assert driver._ClaudeAdapter.build_launch_command([]) == "claude"

    def test_single_plugin_dir(self) -> None:
        cmd = driver._ClaudeAdapter.build_launch_command([Path("/opt/skills")])
        assert cmd == "claude --plugin-dir /opt/skills"

    def test_multiple_plugin_dirs_emit_one_flag_per_path(self) -> None:
        cmd = driver._ClaudeAdapter.build_launch_command(
            [Path("/opt/skills"), Path("/opt/observability"), Path("/opt/notifications")]
        )
        # One `--plugin-dir` flag per entry, in input order.
        assert cmd.count("--plugin-dir") == 3
        assert cmd == (
            "claude "
            "--plugin-dir /opt/skills "
            "--plugin-dir /opt/observability "
            "--plugin-dir /opt/notifications"
        )

    def test_paths_with_spaces_get_shell_quoted(self) -> None:
        cmd = driver._ClaudeAdapter.build_launch_command(
            [Path("/opt/skills"), Path("/opt/with space/here")]
        )
        # shlex.quote produces single-quoted strings for paths with spaces.
        assert "'/opt/with space/here'" in cmd
        # The plain path is not quoted (only chars that need it are).
        assert " /opt/skills " in cmd

    def test_paths_with_single_quote_safely_escaped(self) -> None:
        # Defensive: directory names with embedded ' get the shlex-style
        # close-escape-reopen treatment so the resulting command is still
        # shell-safe when echoed.
        cmd = driver._ClaudeAdapter.build_launch_command([Path("/opt/it's mine")])
        # shlex.quote("/opt/it's mine") = "'/opt/it'\"'\"'s mine'"
        assert "'/opt/it'\"'\"'s mine'" in cmd


class TestLaunchInWindowSendsFlags:
    """`_ClaudeAdapter.launch_in_window` actually passes the flags to tmux."""

    def test_no_plugin_dirs_preserves_keystroke_sequence(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # When no plugin dirs are configured, the launch is byte-equal to
        # the pre-plugins behaviour: `claude` then `Enter` via send-keys
        # (not send-literal). This matters because smoke fixtures expect
        # this exact keystroke shape.
        calls: list[tuple[str, str, tuple[str, ...]]] = []

        def fake_send_keys(container: str, window: str, *keys: str) -> None:
            calls.append((container, window, keys))

        def fake_send_literal(container: str, window: str, text: str) -> None:  # noqa: ARG001
            pytest.fail("send_literal should not be called without plugin_dirs")

        monkeypatch.setattr(driver, "_tmux_send_keys", fake_send_keys)
        monkeypatch.setattr(driver, "_tmux_send_literal", fake_send_literal)

        driver._ClaudeAdapter.launch_in_window("c", "/workspace", plugin_dirs=None)

        assert calls == [("c", "claude", ("claude", "Enter"))]

    def test_with_plugin_dirs_sends_literal_then_enter(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        send_keys_calls: list[tuple[str, str, tuple[str, ...]]] = []
        send_literal_calls: list[tuple[str, str, str]] = []

        def fake_send_keys(container: str, window: str, *keys: str) -> None:
            send_keys_calls.append((container, window, keys))

        def fake_send_literal(container: str, window: str, text: str) -> None:
            send_literal_calls.append((container, window, text))

        monkeypatch.setattr(driver, "_tmux_send_keys", fake_send_keys)
        monkeypatch.setattr(driver, "_tmux_send_literal", fake_send_literal)

        driver._ClaudeAdapter.launch_in_window(
            "c",
            "/workspace",
            plugin_dirs=[Path("/opt/skills"), Path("/opt/observability")],
        )

        # 1) send_literal got the full command with both flags.
        assert send_literal_calls == [
            ("c", "claude", "claude --plugin-dir /opt/skills --plugin-dir /opt/observability"),
        ]
        # 2) send_keys then dispatched Enter.
        assert send_keys_calls == [("c", "claude", ("Enter",))]


class TestProviderAdapterPicksUpPluginDirs:
    """`InteractiveTmuxProvider` reads `ITMUX_CLAUDE_PLUGIN_DIRS` by default."""

    def test_constructor_picks_up_env_var_default(
        self,
        clean_plugin_env: None,
    ) -> None:
        from agentic_isolation.providers.interactive_tmux import (
            InteractiveTmuxProvider,
        )

        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = "/opt/p1:/opt/p2"

        provider = InteractiveTmuxProvider()

        assert provider._default_claude_plugin_dirs == [Path("/opt/p1"), Path("/opt/p2")]

    def test_explicit_kwarg_overrides_env(
        self,
        clean_plugin_env: None,
    ) -> None:
        from agentic_isolation.providers.interactive_tmux import (
            InteractiveTmuxProvider,
        )

        os.environ["ITMUX_CLAUDE_PLUGIN_DIRS"] = "/opt/from-env"
        explicit = [Path("/opt/explicit-only")]

        provider = InteractiveTmuxProvider(default_claude_plugin_dirs=explicit)

        assert provider._default_claude_plugin_dirs == explicit
