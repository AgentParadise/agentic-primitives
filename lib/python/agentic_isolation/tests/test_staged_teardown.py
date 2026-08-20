"""`SupportsStagedTeardown` exists so session capture can act between the steps.

`destroy()` collapses stop, remove, and delete-workspace into one call. For a
caller with nothing to do in between that is correct and should stay the
default. Session capture has three things to do in between, and each boundary
is load-bearing:

  - the exporter must be invoked while the container is still RUNNING, because
    there is nothing to exec into afterwards
  - the archive must happen before the workspace directory is deleted, because
    that directory IS the spool
  - the archive must be confirmed durable before anything is deleted, or a
    failed upload silently becomes permanent loss

These tests pin the ordering guarantees and the property that matters most for
maintenance: the combined path and the staged path share one implementation, so
they cannot drift into behaving differently.

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
    id = "ws-1"

    def __init__(self, handle: str = "container-abc", workspace_dir: str | None = None):
        self._handle = handle
        self.metadata: dict[str, Any] = {}
        if workspace_dir is not None:
            self.metadata["workspace_dir"] = workspace_dir


class _Proc:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""

    async def wait(self) -> int:
        return 0

    @property
    def stdout(self) -> Any:
        class _R:
            async def read(self, _n: int) -> bytes:
                return b""

        return _R()


def _provider() -> Any:
    p = WorkspaceDockerProvider.__new__(WorkspaceDockerProvider)
    p._log_snapshots = {}
    return p


def _record(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    async def _spawn(*argv: str, **_k: object) -> Any:
        calls.append(" ".join(argv[:2]))
        return _Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


class TestCapabilityIsOptional:
    def test_docker_advertises_it(self) -> None:
        assert isinstance(_provider(), SupportsStagedTeardown)

    def test_local_does_not(self) -> None:
        assert not isinstance(
            WorkspaceLocalProvider.__new__(WorkspaceLocalProvider), SupportsStagedTeardown
        )


class TestStepsAreActuallySeparate:
    """Each step must do ONLY its own part - that is the whole point."""

    def test_stop_does_not_remove(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = _record(monkeypatch)
        asyncio.run(_provider().stop_container(_Workspace()))
        assert "docker stop" in calls
        assert "docker rm" not in calls, "stop must leave the container present"

    def test_stop_does_not_delete_the_workspace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        _record(monkeypatch)
        d = tmp_path / "ws"
        d.mkdir()
        (d / "spooled.jsonl").write_text("transcript")
        asyncio.run(_provider().stop_container(_Workspace(workspace_dir=str(d))))
        assert (d / "spooled.jsonl").exists(), "the spool must survive stop"

    def test_remove_does_not_delete_the_workspace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # This is the boundary archival depends on: the container can go while
        # the spool stays, so an archive can still be taken from disk.
        _record(monkeypatch)
        d = tmp_path / "ws"
        d.mkdir()
        (d / "spooled.jsonl").write_text("transcript")
        asyncio.run(_provider().remove_container(_Workspace(workspace_dir=str(d))))
        assert (d / "spooled.jsonl").exists(), "the spool must survive container removal"

    def test_delete_workspace_dir_removes_it(self, tmp_path: Any) -> None:
        d = tmp_path / "ws"
        d.mkdir()
        (d / "spooled.jsonl").write_text("transcript")
        asyncio.run(_provider().delete_workspace_dir(_Workspace(workspace_dir=str(d))))
        assert not d.exists()

    def test_delete_workspace_dir_without_one_is_not_an_error(self) -> None:
        asyncio.run(_provider().delete_workspace_dir(_Workspace()))


class TestVerdictIsStillCapturedAtStop:
    def test_stop_snapshots_logs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # stop triggers the finalizer and remove destroys its stream, so the
        # snapshot has to be taken here or not at all.
        verdict = b"upload complete (uploaded=1); spool retained at /spool"

        class _LogProc(_Proc):
            @property
            def stdout(self) -> Any:
                data = {"v": verdict}

                class _R:
                    async def read(self, _n: int) -> bytes:
                        out, data["v"] = data["v"], b""
                        return out

                return _R()

        async def _spawn(*argv: str, **_k: object) -> Any:
            return _LogProc() if argv[:2] == ("docker", "logs") else _Proc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
        provider = _provider()
        asyncio.run(provider.stop_container(_Workspace()))
        assert provider._log_snapshots["container-abc"] == verdict.decode()


class TestCombinedPathIsBuiltFromTheStagedOne:
    def test_cleanup_still_stops_then_removes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # destroy() must keep working unchanged for every caller that has
        # nothing to do between the steps.
        calls = _record(monkeypatch)
        asyncio.run(_provider()._cleanup_container("container-abc"))
        assert calls == ["docker stop", "docker logs", "docker rm"], calls
