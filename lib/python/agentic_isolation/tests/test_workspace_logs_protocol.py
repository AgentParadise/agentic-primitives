"""`SupportsWorkspaceLogs` is an OPTIONAL capability, and the tests say why.

The motivating consumer is session capture: a workspace finalizer prints
whether the transcript reached the store, and that verdict lives only in the
container's own output. Without a way to read it back, the capture outcome is
unobservable to the orchestrator - it fails open and fails silent.

Three properties matter more than the happy path:

1. The capability is genuinely optional. Adding `logs` to `WorkspaceProvider`
   would force every backend to grow a method most can only raise from.
2. `logs` does not raise for operational failures. It runs during teardown,
   where the container may already be gone, and a caller reading a capture
   verdict must not be able to fail the teardown that produced it.
3. The verdict survives teardown. `docker stop` triggers the finalizer and
   `docker rm` destroys the stream it wrote to, so unless the output is
   captured between the two, the verdict is unreachable BY CONSTRUCTION rather
   than merely unread. This is the property the whole capability exists for.

These tests are hermetic: nothing here invokes a real Docker daemon, so they
behave identically on a machine without Docker.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_isolation import SupportsWorkspaceLogs
from agentic_isolation.providers.base import InteractiveSession
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider


def _provider() -> Any:
    """A provider with only the state these tests touch."""
    provider = WorkspaceDockerProvider.__new__(WorkspaceDockerProvider)
    provider._log_snapshots = {}
    return provider


class _Workspace:
    def __init__(self, handle: str = "container-abc") -> None:
        self._handle = handle


class _FakeProc:
    """Stands in for asyncio.subprocess.Process."""

    def __init__(
        self,
        *,
        out: bytes = b"",
        returncode: int = 0,
        communicate_exc: BaseException | None = None,
        kill_exc: BaseException | None = None,
    ) -> None:
        self._out = out
        self.returncode = returncode
        self._communicate_exc = communicate_exc
        self._kill_exc = kill_exc
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._communicate_exc is not None:
            raise self._communicate_exc
        return self._out, b""

    def kill(self) -> None:
        self.killed = True
        if self._kill_exc is not None:
            raise self._kill_exc

    async def wait(self) -> int:
        return self.returncode


def _patch_spawn(monkeypatch: pytest.MonkeyPatch, proc: Any) -> None:
    async def _spawn(*_a: object, **_k: object) -> Any:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


class TestCapabilityIsOptional:
    def test_docker_advertises_the_capability(self) -> None:
        assert isinstance(_provider(), SupportsWorkspaceLogs)

    def test_local_does_not(self) -> None:
        # Not a gap. A local workspace runs in the caller's own stdio, so there
        # is no separate stream to read back. If this ever flips to True it
        # should be because `logs` was implemented, never because the protocol
        # was widened until everything trivially satisfied it.
        assert not isinstance(
            WorkspaceLocalProvider.__new__(WorkspaceLocalProvider), SupportsWorkspaceLogs
        )

    def test_adding_a_protocol_did_not_disarm_a_neighbour(self) -> None:
        # Regression: SupportsWorkspaceLogs was once inserted between
        # @runtime_checkable and `class InteractiveSession`, silently stealing
        # the decorator. isinstance() against InteractiveSession then raised
        # TypeError at runtime, and no test noticed.
        assert isinstance(object(), InteractiveSession) is False


class TestOperationalFailuresYieldEmpty:
    def test_absent_docker_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _boom(*_a: object, **_k: object) -> None:
            raise OSError("docker not installed")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _boom)
        assert asyncio.run(_provider().logs(_Workspace())) == ""

    def test_nonzero_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spawn(monkeypatch, _FakeProc(out=b"No such container", returncode=1))
        assert asyncio.run(_provider().logs(_Workspace())) == ""

    def test_communicate_raises_something_unexpected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spawn(monkeypatch, _FakeProc(communicate_exc=RuntimeError("transport")))
        assert asyncio.run(_provider().logs(_Workspace())) == ""

    def test_timeout_kills_and_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proc = _FakeProc(communicate_exc=TimeoutError())
        _patch_spawn(monkeypatch, proc)
        assert asyncio.run(_provider().logs(_Workspace())) == ""
        assert proc.killed, "a timed-out docker logs must not be left running"

    def test_kill_racing_process_exit_is_not_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # kill() after the process already exited raises ProcessLookupError.
        proc = _FakeProc(communicate_exc=TimeoutError(), kill_exc=ProcessLookupError("gone"))
        _patch_spawn(monkeypatch, proc)
        assert asyncio.run(_provider().logs(_Workspace())) == ""

    def test_workspace_without_a_handle(self) -> None:
        class _Bare:
            pass

        assert asyncio.run(_provider().logs(_Bare())) == ""  # type: ignore[arg-type]

    def test_cancellation_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Swallowing CancelledError would make shutdown hang, which is worse
        # than losing a log line.
        _patch_spawn(monkeypatch, _FakeProc(communicate_exc=asyncio.CancelledError()))
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(_provider().logs(_Workspace()))


class TestOutputIsBounded:
    def test_one_enormous_line_is_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # --tail bounds LINES; a single agent-controlled line can be arbitrarily
        # long, so lines are not a resource bound.
        huge = b"x" * (WorkspaceDockerProvider._MAX_LOG_BYTES * 2)
        _patch_spawn(monkeypatch, _FakeProc(out=huge))
        result = asyncio.run(_provider().logs(_Workspace()))
        assert len(result) <= WorkspaceDockerProvider._MAX_LOG_BYTES

    def test_the_tail_is_kept_not_the_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The finalizer verdict is printed last, during shutdown, so truncating
        # from the wrong end would discard exactly what this exists to capture.
        verdict = b"upload complete (uploaded=1); spool retained at /spool"
        _patch_spawn(
            monkeypatch,
            _FakeProc(out=b"n" * (WorkspaceDockerProvider._MAX_LOG_BYTES * 2) + verdict),
        )
        assert asyncio.run(_provider().logs(_Workspace())).endswith(verdict.decode())


class TestVerdictSurvivesTeardown:
    """The property the capability exists for."""

    def test_snapshot_is_returned_after_the_container_is_gone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _provider()
        verdict = "upload complete (uploaded=1); spool retained at /spool"
        provider._remember_logs("container-abc", verdict)

        # Any live query would fail: the container has been removed.
        _patch_spawn(monkeypatch, _FakeProc(out=b"No such container", returncode=1))

        assert asyncio.run(provider.logs(_Workspace())) == verdict

    def test_snapshots_are_bounded(self) -> None:
        provider = _provider()
        limit = WorkspaceDockerProvider._MAX_LOG_SNAPSHOTS
        for i in range(limit + 10):
            provider._remember_logs(f"c{i}", f"verdict {i}")
        assert len(provider._log_snapshots) == limit
        # Oldest evicted first, newest retained.
        assert "c0" not in provider._log_snapshots
        assert f"c{limit + 9}" in provider._log_snapshots

    def test_empty_output_is_not_remembered(self) -> None:
        # Otherwise an empty snapshot would mask a later successful live read.
        provider = _provider()
        provider._remember_logs("c", "")
        assert provider._log_snapshots == {}
