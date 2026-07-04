"""Regression tests for the async follow-up on issue #225 (phase 3).

`InteractiveTmuxProvider.create()`/`.destroy()` used to call the blocking
driver (`start_workspace`/`stop`, both `subprocess.run`-backed) directly on
the caller's event loop, freezing every other task on that loop for the
full container startup/teardown window. They now offload the blocking
call via `asyncio.to_thread`.

An earlier revision also serialized every offloaded call through a single
`asyncio.Lock`, but that made N concurrent `create()` calls run strictly
sequentially and a `destroy()` block behind an in-flight `create()` --
defeating the multi-agent concurrency this provider exists to enable. The
lock is gone; only the `self._workspaces` registry dict is guarded.

These tests prove two things:

  1. `create()`/`destroy()` no longer block the event loop: a concurrently
     scheduled `asyncio.sleep()` task completes *during* the call, not
     only after it returns.
  2. Concurrent `create()` calls are NOT serialized: with a driver stub
     whose `start_workspace` blocks, multiple creates overlap in time
     (observed concurrency > 1) instead of running one at a time.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

import agentic_isolation.providers.interactive_tmux as itm
from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider


def _provider() -> InteractiveTmuxProvider:
    return InteractiveTmuxProvider(
        default_host_auth={"claude": Path("/tmp/nowhere/.claude")},
        default_host_claude_dotjson=Path("/tmp/nowhere/.claude.json"),
        default_claude_plugin_dirs=[],
    )


class _FakeHandle:
    def __init__(self, sleep_s: float = 0.0) -> None:
        self.container = "itws-fake"
        self.enabled_agents = ("claude",)
        self.startup_status: dict = {}
        self.stopped = False
        self._sleep_s = sleep_s

    def stop(self) -> None:
        time.sleep(self._sleep_s)
        self.stopped = True


class _SlowStartWorkspace:
    """Driver stand-in whose `start_workspace` blocks synchronously."""

    sleep_s = 0.3
    last_handle: _FakeHandle | None = None

    @classmethod
    def start_workspace(cls, **kwargs) -> _FakeHandle:
        time.sleep(cls.sleep_s)
        handle = _FakeHandle()
        cls.last_handle = handle
        return handle


class _SlowStartDriver:
    DEFAULT_IMAGE = "img:test"
    InteractiveTmuxWorkspace = _SlowStartWorkspace


async def _noop_docker_exec(provider: InteractiveTmuxProvider) -> None:
    async def _ok(*args, **kwargs):
        return None

    provider._docker_exec = _ok  # type: ignore[method-assign]


async def test_create_sets_workspace_dir_metadata(monkeypatch) -> None:
    """#225 spec: metadata must carry a `workspace_dir` key so downstream
    artifact collection knows where to copy files from. For this exec-based
    provider it is the container workdir (no host bind-mount)."""
    monkeypatch.setattr(itm, "_get_driver", lambda: _SlowStartDriver)
    _SlowStartWorkspace.sleep_s = 0.0
    provider = _provider()
    await _noop_docker_exec(provider)

    config = WorkspaceConfig(provider="interactive-tmux", working_dir="/workspace")
    workspace = await provider.create(config)

    assert "workspace_dir" in workspace.metadata
    assert workspace.metadata["workspace_dir"] == "/workspace"
    # For this provider it mirrors the container workdir.
    assert workspace.metadata["workspace_dir"] == workspace.metadata["workdir"]


async def test_create_does_not_block_event_loop(monkeypatch) -> None:
    monkeypatch.setattr(itm, "_get_driver", lambda: _SlowStartDriver)
    _SlowStartWorkspace.sleep_s = 0.3
    provider = _provider()
    await _noop_docker_exec(provider)

    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    ticker_task = asyncio.ensure_future(_ticker())
    try:
        await provider.create(WorkspaceConfig(provider="interactive-tmux"))
    finally:
        ticker_task.cancel()

    # `start_workspace` slept synchronously for 0.3s. If `create()` had
    # blocked the event loop for that whole window, the ticker (0.05s
    # cadence) would not have gotten a chance to run at all. Offloaded via
    # `asyncio.to_thread`, the loop stays free to service it several times.
    assert ticks >= 3, (
        f"expected the event loop to keep servicing other tasks while "
        f"create() ran, but only {ticks} ticks completed"
    )


async def test_destroy_does_not_block_event_loop() -> None:
    provider = _provider()
    workspace = await _make_workspace(provider, sleep_s=0.3)

    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    ticker_task = asyncio.ensure_future(_ticker())
    try:
        await provider.destroy(workspace)
    finally:
        ticker_task.cancel()

    assert ticks >= 3, (
        f"expected the event loop to keep servicing other tasks while "
        f"destroy() ran, but only {ticks} ticks completed"
    )
    assert workspace._handle.stopped is True


async def _make_workspace(provider: InteractiveTmuxProvider, *, sleep_s: float):
    """Build a `Workspace` with a fake handle without going through
    `create()` (keeps these tests independent of the driver stub above)."""
    from datetime import UTC, datetime

    from agentic_isolation.providers.base import Workspace

    handle = _FakeHandle(sleep_s=sleep_s)
    workspace = Workspace(
        id="itws-fake",
        provider=provider.name,
        path=Path("/workspace"),
        config=WorkspaceConfig(provider="interactive-tmux"),
        created_at=datetime.now(UTC),
        metadata={"container": handle.container, "workdir": "/workspace"},
        _handle=handle,
    )
    provider._workspaces[workspace.id] = workspace
    return workspace


class _ConcurrencyDriver:
    """Driver stand-in that records how many `start_workspace` calls are
    executing at the same time.

    Each call bumps a shared counter, sleeps (holding the overlap window
    open), then decrements. If the provider serialized offloaded calls
    (the old behavior), `max_observed_concurrency` would stay at 1. With
    the cross-workspace lock removed, concurrent creates overlap and the
    counter climbs above 1.
    """

    DEFAULT_IMAGE = "img:test"
    max_observed_concurrency = 0
    current_concurrency = 0
    _guard = threading.Lock()

    class InteractiveTmuxWorkspace:
        @classmethod
        def start_workspace(cls, **kwargs) -> _FakeHandle:
            return _ConcurrencyDriver._enter_blocking_section()

    @classmethod
    def _enter_blocking_section(cls) -> _FakeHandle:
        with cls._guard:
            cls.current_concurrency += 1
            cls.max_observed_concurrency = max(
                cls.max_observed_concurrency, cls.current_concurrency
            )
        try:
            # Hold the overlap window open long enough that sibling creates,
            # now that they are not serialized, reliably run at the same time.
            time.sleep(0.1)
        finally:
            with cls._guard:
                cls.current_concurrency -= 1
        return _FakeHandle()


async def test_concurrent_creates_are_not_serialized(monkeypatch) -> None:
    monkeypatch.setattr(itm, "_get_driver", lambda: _ConcurrencyDriver)
    _ConcurrencyDriver.max_observed_concurrency = 0
    _ConcurrencyDriver.current_concurrency = 0

    provider = _provider()
    await _noop_docker_exec(provider)

    await asyncio.gather(
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
    )

    assert _ConcurrencyDriver.max_observed_concurrency > 1, (
        "concurrent create() calls did not overlap -- provisioning is still "
        "serialized across workspaces, defeating multi-agent concurrency"
    )


async def test_cancelled_create_stops_late_started_workspace(monkeypatch) -> None:
    monkeypatch.setattr(itm, "_get_driver", lambda: _SlowStartDriver)
    _SlowStartWorkspace.sleep_s = 0.2
    _SlowStartWorkspace.last_handle = None
    provider = _provider()
    await _noop_docker_exec(provider)

    task = asyncio.create_task(provider.create(WorkspaceConfig(provider="interactive-tmux")))
    await asyncio.sleep(0.05)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    for _ in range(20):
        handle = _SlowStartWorkspace.last_handle
        if handle is not None and handle.stopped:
            break
        await asyncio.sleep(0.05)

    assert _SlowStartWorkspace.last_handle is not None
    assert _SlowStartWorkspace.last_handle.stopped is True


class _StopSleepWorkspace:
    """Driver whose `start_workspace` succeeds fast but whose handle's
    `stop()` blocks briefly, giving a window to cancel `create()` *while
    the cleanup stop() is in flight*."""

    last_handle: _FakeHandle | None = None

    @classmethod
    def start_workspace(cls, **kwargs) -> _FakeHandle:
        handle = _FakeHandle(sleep_s=0.2)
        cls.last_handle = handle
        return handle


class _StopSleepDriver:
    DEFAULT_IMAGE = "img:test"
    InteractiveTmuxWorkspace = _StopSleepWorkspace


async def test_cleanup_stop_runs_when_cancelled_during_teardown(monkeypatch) -> None:
    """Finding 3: post-start setup fails (entering create()'s teardown),
    then a SECOND cancellation lands while the cleanup `stop()` is awaiting.
    The shielded stop() must still run to completion so the
    credential-seeded container is never leaked."""
    monkeypatch.setattr(itm, "_get_driver", lambda: _StopSleepDriver)
    _StopSleepWorkspace.last_handle = None
    provider = _provider()

    async def _boom(*args, **kwargs):
        raise RuntimeError("post-start setup failed")

    provider._docker_exec = _boom  # type: ignore[method-assign]

    task = asyncio.create_task(provider.create(WorkspaceConfig(provider="interactive-tmux")))
    # Let create() start, fail setup, and enter the shielded cleanup stop().
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises((asyncio.CancelledError, RuntimeError)):
        await task

    for _ in range(40):
        handle = _StopSleepWorkspace.last_handle
        if handle is not None and handle.stopped:
            break
        await asyncio.sleep(0.05)

    assert _StopSleepWorkspace.last_handle is not None
    assert _StopSleepWorkspace.last_handle.stopped is True, (
        "cleanup stop() was skipped when create() was cancelled during "
        "teardown -- the credential-seeded container leaked"
    )
