"""Phase 4 tests: agent-agnostic `TmuxSession` + adapter-registry dispatch.

Covers the session/agent split from issue #225 phase 4:

  * `TmuxSession` (send_keys/send_literal/capture_pane/get_incremental_output/
    is_alive/start/stop) is agent-agnostic and routes through the injected
    `CommandExecutor` (via the module-level `_tmux_*`/`_docker_exec` seams,
    so monkeypatching those still works whether callers go through
    `TmuxSession` or the free functions directly).
  * `InteractiveTmuxWorkspace` builds one `TmuxSession` per enabled agent in
    `__post_init__` and delegates `capture_response`/`await_completion`'s
    polling/the startup wait to it — a pure refactor, not a behavior change
    (those call paths are also covered by the pre-existing reliability/
    pane-tail test files).
  * `start_workspace` enables agents by iterating the `_ADAPTERS` registry
    (not the closed `AGENTS` literal tuple), so a 4th agent becomes
    enable-able by registering an adapter object.

No real docker daemon or tmux required.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
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


@dataclass
class _FakeExecutor:
    """Records every `exec()` call; returns a configurable canned result."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def exec(self, command, *, timeout_s=None, stdin=None):
        self.calls.append((tuple(command), {"timeout_s": timeout_s, "stdin": stdin}))
        return driver.ExecResult(exit_code=self.exit_code, stdout=self.stdout, stderr=self.stderr)


class TestTmuxSessionIsAgentAgnostic:
    def test_no_agent_name_referenced_in_class_source(self) -> None:
        """`TmuxSession` must know nothing about claude/codex/gemini — only
        generic pane/window operations, matching the phase-4 spec."""
        import inspect

        src = inspect.getsource(driver.TmuxSession)
        for name in ("claude", "codex", "gemini"):
            assert name not in src.lower(), f"TmuxSession source unexpectedly mentions {name!r}"

    def test_send_keys_delegates_to_module_tmux_send_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            driver,
            "_tmux_send_keys",
            lambda container, window, *keys, **kw: calls.append((container, window, keys, kw)),
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        session.send_keys("Enter", timeout_s=9.0)
        assert calls == [("c1", "win1", ("Enter",), {"executor": fake, "timeout_s": 9.0})]

    def test_send_literal_delegates_to_module_tmux_send_literal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            driver,
            "_tmux_send_literal",
            lambda container, window, text, **kw: calls.append((container, window, text, kw)),
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        session.send_literal("hello world")
        assert calls == [
            (
                "c1",
                "win1",
                "hello world",
                {"executor": fake, "timeout_s": driver.DEFAULT_EXEC_TIMEOUT_S},
            )
        ]

    def test_capture_pane_delegates_to_module_tmux_capture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            driver,
            "_tmux_capture",
            lambda container, window, **kw: f"{container}:{window}:{kw.get('timeout_s')}",
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        assert session.capture_pane(timeout_s=4.0) == "c1:win1:4.0"

    def test_is_alive_true_when_has_session_succeeds(self) -> None:
        fake = _FakeExecutor(exit_code=0)
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        assert session.is_alive() is True
        assert fake.calls[0][0] == ("tmux", "has-session", "-t", driver.TMUX_SESSION)

    def test_is_alive_false_when_has_session_fails(self) -> None:
        fake = _FakeExecutor(exit_code=1)
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        assert session.is_alive() is False

    def test_start_new_session_for_first_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = []
        monkeypatch.setattr(
            driver,
            "_docker_exec",
            lambda container, *args, **kw: calls.append((container, args, kw)),
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="claude", executor=fake)
        session.start(200, 50)
        container, args, kw = calls[0]
        assert container == "c1"
        assert args == (
            "tmux",
            "new-session",
            "-d",
            "-s",
            driver.TMUX_SESSION,
            "-n",
            "claude",
            "-x",
            "200",
            "-y",
            "50",
        )
        assert kw["executor"] is fake

    def test_start_new_window_for_subsequent_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = []
        monkeypatch.setattr(
            driver,
            "_docker_exec",
            lambda container, *args, **kw: calls.append((container, args, kw)),
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="codex", executor=fake)
        session.start(200, 50, as_new_window=True)
        container, args, kw = calls[0]
        assert args == ("tmux", "new-window", "-t", driver.TMUX_SESSION, "-n", "codex")

    def test_get_incremental_output_diffs_against_previous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(driver, "_tmux_capture", lambda container, window, **kw: "abcXYZ")
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        new_text, full = session.get_incremental_output("abc")
        assert new_text == "XYZ"
        assert full == "abcXYZ"

    def test_get_incremental_output_falls_back_to_full_capture_when_no_common_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            driver, "_tmux_capture", lambda container, window, **kw: "fresh pane contents"
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        new_text, full = session.get_incremental_output("unrelated prior text")
        assert new_text == "fresh pane contents"
        assert full == "fresh pane contents"

    def test_get_incremental_output_with_no_previous_returns_full_capture_as_new(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            driver, "_tmux_capture", lambda container, window, **kw: "first capture"
        )
        fake = _FakeExecutor()
        session = driver.TmuxSession(target="c1", window="win1", executor=fake)
        new_text, full = session.get_incremental_output(None)
        assert new_text == "first capture"
        assert full == "first capture"


class TestWorkspaceBuildsSessionsPerAgent:
    def test_post_init_builds_one_session_per_enabled_agent(self) -> None:
        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude", "codex"),
        )
        assert set(ws._sessions) == {"claude", "codex"}
        assert ws._sessions["claude"].target == "test-container"
        assert ws._sessions["claude"].window == "claude"
        assert ws._sessions["claude"].executor is ws.executor

    def test_capture_response_delegates_to_the_agent_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            driver,
            "_tmux_capture",
            lambda container, window, **kw: calls.append((container, window, kw)) or "pane text",
        )
        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )
        result = ws.capture_response("claude", timeout_s=6.0)
        assert result == "pane text"
        assert calls == [("test-container", "claude", {"executor": ws.executor, "timeout_s": 6.0})]


class TestAdapterRegistryDrivesEnablement:
    def test_start_workspace_iterates_adapter_registry_not_closed_agents_tuple(self) -> None:
        """A 4th agent becomes enable-able by registering it in `_ADAPTERS`
        alone — `start_workspace`'s enablement loop must not be hardcoded
        to the `AGENTS` literal tuple."""
        import inspect

        src = inspect.getsource(driver.InteractiveTmuxWorkspace.start_workspace.__func__)
        assert "for agent in _ADAPTERS" in src
