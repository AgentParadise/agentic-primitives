"""Regression tests for the async follow-up on issue #225 (phase 3).

`InteractiveTmuxProvider.create()`/`.destroy()` used to call the blocking
driver (`start_workspace`/`stop`, both `subprocess.run`-backed) directly on
the caller's event loop, freezing every other task on that loop for the
full container startup/teardown window. They now offload the blocking
call via `asyncio.to_thread`, serialized through a dedicated
`asyncio.Lock` (`self._blocking_call_lock`) so no two such offloaded calls
ever run concurrently in different threads (the documented concern was a
race between an executor thread's `subprocess.run` and asyncio's child
watcher).

These tests prove two things:

  1. `create()`/`destroy()` no longer block the event loop: a concurrently
     scheduled `asyncio.sleep()` task completes *during* the call, not
     only after it returns.
  2. The serialization lock actually serializes: two concurrent `create()`
     calls with a driver stub that detects re-entrancy (a shared
     "currently inside a blocking call" flag) never overlap.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

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


async def test_create_does_not_block_event_loop(monkeypatch) -> None:
    monkeypatch.setattr(itm, "_get_driver", lambda: _SlowStartDriver)
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


class _ReentrancyDriver:
    """Driver stand-in that raises if two blocking calls ever overlap.

    `busy` is a plain (non-async, non-thread-safe-by-design) shared flag:
    if the provider's serialization lock ever lets two offloaded calls
    run concurrently, both threads will observe `busy is True` at the
    same time and the second one in will raise.
    """

    DEFAULT_IMAGE = "img:test"
    busy = False
    max_observed_concurrency = 0
    current_concurrency = 0
    overlap_detected = False

    class InteractiveTmuxWorkspace:
        @classmethod
        def start_workspace(cls, **kwargs) -> _FakeHandle:
            return _ReentrancyDriver._enter_blocking_section()

    @classmethod
    def _enter_blocking_section(cls) -> _FakeHandle:
        if cls.busy:
            cls.overlap_detected = True
        cls.busy = True
        cls.current_concurrency += 1
        cls.max_observed_concurrency = max(cls.max_observed_concurrency, cls.current_concurrency)
        try:
            # Long enough that a second concurrent call, if the lock were
            # missing/broken, would reliably overlap with this one.
            time.sleep(0.1)
        finally:
            cls.current_concurrency -= 1
            cls.busy = False
        return _FakeHandle()


async def test_concurrent_creates_are_serialized(monkeypatch) -> None:
    monkeypatch.setattr(itm, "_get_driver", lambda: _ReentrancyDriver)
    _ReentrancyDriver.busy = False
    _ReentrancyDriver.max_observed_concurrency = 0
    _ReentrancyDriver.current_concurrency = 0
    _ReentrancyDriver.overlap_detected = False

    provider = _provider()
    await _noop_docker_exec(provider)

    await asyncio.gather(
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
        provider.create(WorkspaceConfig(provider="interactive-tmux")),
    )

    assert _ReentrancyDriver.overlap_detected is False, (
        "two offloaded driver calls ran concurrently -- the "
        "serialization lock failed to serialize them"
    )
    assert _ReentrancyDriver.max_observed_concurrency == 1


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
