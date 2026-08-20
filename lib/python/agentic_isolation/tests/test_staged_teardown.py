"""`SupportsStagedTeardown` runs caller work at the points where it is safe.

`destroy()` collapses stop, remove and delete-workspace into one call, which is
right for a caller with nothing to do in between. Session capture has work to
do in between, and the order is forced:

  - the exporter must run while the container is still RUNNING, because there
    is nothing to exec into afterwards
  - the archive must precede deleting the workspace directory, because that
    directory IS the spool
  - a FAILED archive must not delete anything, or a failed upload silently
    becomes permanent loss

An earlier draft exposed three freely callable methods and documented the
order. Review rejected that, correctly: an API whose misuse costs data should
not depend on the caller reading a docstring. These tests pin the ordering as
enforced behaviour, not as prose.

Hermetic - no Docker daemon.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_isolation import SupportsStagedTeardown
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider


class _Workspace:
    def __init__(self, handle: str = "container-abc", workspace_dir: str | None = None):
        self.id = "ws-1"
        self._handle = handle
        self.metadata: dict[str, Any] = {}
        if workspace_dir is not None:
            self.metadata["workspace_dir"] = workspace_dir


class _Proc:
    returncode = 0

    async def wait(self) -> int:
        return 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""

    @property
    def stdout(self) -> Any:
        class _R:
            async def read(self, _n: int) -> bytes:
                return b""

        return _R()


def _provider() -> Any:
    p = WorkspaceDockerProvider.__new__(WorkspaceDockerProvider)
    p._log_snapshots = {}
    p._workspaces = {}
    p._lock = asyncio.Lock()
    return p


def _record(monkeypatch: pytest.MonkeyPatch, sink: list[str]) -> None:
    async def _spawn(*argv: str, **_k: object) -> Any:
        sink.append(" ".join(argv[:2]))
        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


class TestCapabilityIsOptional:
    def test_docker_advertises_it(self) -> None:
        assert isinstance(_provider(), SupportsStagedTeardown)

    def test_local_does_not(self) -> None:
        assert not isinstance(
            WorkspaceLocalProvider.__new__(WorkspaceLocalProvider), SupportsStagedTeardown
        )


class TestHooksRunAtTheSafePoints:
    def test_while_running_runs_before_the_stop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The exporter is invoked here. After `docker stop` there is nothing to
        # exec into, so running it later would make the verdict unobtainable.
        seq: list[str] = []
        _record(monkeypatch, seq)

        async def _hook() -> None:
            seq.append("HOOK while_running")

        asyncio.run(_provider().teardown(_Workspace(), while_running=_hook))
        assert seq.index("HOOK while_running") < seq.index("docker stop")

    def test_before_delete_runs_after_removal_and_before_deletion(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        seq: list[str] = []
        _record(monkeypatch, seq)
        d = tmp_path / "ws"
        d.mkdir()
        (d / "spool.jsonl").write_text("transcript")
        seen: dict[str, bool] = {}

        async def _archive() -> None:
            seq.append("HOOK before_delete")
            seen["spool_present"] = (d / "spool.jsonl").exists()

        asyncio.run(_provider().teardown(_Workspace(workspace_dir=str(d)), before_delete=_archive))
        assert seq.index("docker rm") < seq.index("HOOK before_delete")
        assert seen["spool_present"], "the archive hook must still see the spool"
        assert not d.exists(), "the workspace is deleted once archiving succeeded"

    def test_full_order(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        seq: list[str] = []
        _record(monkeypatch, seq)
        d = tmp_path / "ws"
        d.mkdir()

        async def _run() -> None:
            seq.append("HOOK while_running")

        async def _arch() -> None:
            seq.append("HOOK before_delete")

        asyncio.run(
            _provider().teardown(
                _Workspace(workspace_dir=str(d)),
                while_running=_run,
                before_delete=_arch,
            )
        )
        assert seq == [
            "HOOK while_running",
            "docker stop",
            "docker logs",
            "docker rm",
            "HOOK before_delete",
        ], seq


class TestFailedArchiveRetainsTheData:
    """The property the whole design exists for."""

    def test_workspace_survives_a_failing_before_delete(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        _record(monkeypatch, [])
        d = tmp_path / "ws"
        d.mkdir()
        (d / "spool.jsonl").write_text("transcript")

        async def _fails() -> None:
            raise RuntimeError("store unreachable")

        with pytest.raises(RuntimeError):
            asyncio.run(
                _provider().teardown(_Workspace(workspace_dir=str(d)), before_delete=_fails)
            )

        # Deleting anyway would turn a retryable upload failure into permanent
        # loss, which is exactly what this capability exists to prevent.
        assert (d / "spool.jsonl").exists()

    def test_container_is_still_torn_down_when_archiving_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        seq: list[str] = []
        _record(monkeypatch, seq)
        d = tmp_path / "ws"
        d.mkdir()

        async def _fails() -> None:
            raise RuntimeError("store unreachable")

        with pytest.raises(RuntimeError):
            asyncio.run(
                _provider().teardown(_Workspace(workspace_dir=str(d)), before_delete=_fails)
            )

        # Retaining data must not come at the cost of stranding a container.
        assert "docker stop" in seq and "docker rm" in seq

    def test_failing_while_running_leaves_the_container_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seq: list[str] = []
        _record(monkeypatch, seq)

        async def _fails() -> None:
            raise RuntimeError("exporter blew up")

        with pytest.raises(RuntimeError):
            asyncio.run(_provider().teardown(_Workspace(), while_running=_fails))

        # Recoverable: nothing has been destroyed yet, so a caller can retry.
        assert seq == [], seq


class TestRegistryIsNotLeaked:
    def test_teardown_deregisters_the_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # destroy() popped from _workspaces; a staged path that did not would
        # grow the registry without bound for any caller that switched.
        _record(monkeypatch, [])
        provider = _provider()
        ws = _Workspace()
        provider._workspaces[ws.id] = ws
        asyncio.run(provider.teardown(ws))
        assert provider._workspaces == {}

    def test_deregisters_even_when_a_hook_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _record(monkeypatch, [])
        provider = _provider()
        ws = _Workspace()
        provider._workspaces[ws.id] = ws

        async def _fails() -> None:
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            asyncio.run(provider.teardown(ws, while_running=_fails))
        assert provider._workspaces == {}


class TestDestroyIsUnchanged:
    def test_destroy_still_stops_removes_and_deletes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        seq: list[str] = []
        _record(monkeypatch, seq)
        d = tmp_path / "ws"
        d.mkdir()
        provider = _provider()
        ws = _Workspace(workspace_dir=str(d))
        provider._workspaces[ws.id] = ws

        asyncio.run(provider.destroy(ws))

        assert seq == ["docker stop", "docker logs", "docker rm"], seq
        assert not d.exists()
        assert provider._workspaces == {}
