"""Adapter cleanup test (Codex review of PR #202).

`InteractiveTmuxProvider.create()` starts a container with throwaway
claude/codex/gemini credentials mounted, then runs post-start setup
(`docker exec mkdir`, metadata construction). If any of that fails, the
container must be stopped or it leaks running with staged auth material.
This test stubs the driver so `start_workspace` succeeds but the next
`docker exec` fails, and asserts the handle is stopped and the error
re-raised.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agentic_isolation.providers.interactive_tmux as itm
from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider


class _FakeHandle:
    def __init__(self) -> None:
        self.container = "itws-fake"
        self.enabled_agents = ("claude",)
        self.startup_status: dict = {}
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeWorkspace:
    last_handle: _FakeHandle | None = None

    @staticmethod
    def start_workspace(**kwargs) -> _FakeHandle:
        handle = _FakeHandle()
        _FakeWorkspace.last_handle = handle
        return handle


class _FakeDriver:
    DEFAULT_IMAGE = "img:test"
    InteractiveTmuxWorkspace = _FakeWorkspace


def _provider() -> InteractiveTmuxProvider:
    return InteractiveTmuxProvider(
        default_host_auth={"claude": Path("/tmp/nowhere/.claude")},
        default_host_claude_dotjson=Path("/tmp/nowhere/.claude.json"),
        default_claude_plugin_dirs=[],
    )


async def test_create_stops_container_on_post_start_failure(monkeypatch) -> None:
    _FakeWorkspace.last_handle = None
    monkeypatch.setattr(itm, "_get_driver", lambda: _FakeDriver)

    provider = _provider()

    async def _boom(*args, **kwargs):
        raise RuntimeError("docker exec mkdir failed")

    monkeypatch.setattr(provider, "_docker_exec", _boom)

    with pytest.raises(RuntimeError, match="mkdir failed"):
        await provider.create(WorkspaceConfig(provider="interactive-tmux"))

    assert _FakeWorkspace.last_handle is not None
    assert _FakeWorkspace.last_handle.stopped is True, (
        "create() must stop the credential-mounted container when post-start setup fails"
    )
