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
    p._teardown_locks = {}
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

    def test_a_failed_while_running_hook_KEEPS_the_registration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Deliberately the opposite of an earlier version of this test. If the
        # hook fails the container is still LIVE, and deregistering would make
        # a running container invisible to the provider that owns it. The
        # registration is what lets a caller find it and retry.
        _record(monkeypatch, [])
        provider = _provider()
        ws = _Workspace()
        provider._workspaces[ws.id] = ws

        async def _fails() -> None:
            raise RuntimeError("exporter blew up")

        with pytest.raises(RuntimeError):
            asyncio.run(provider.teardown(ws, while_running=_fails))
        assert provider._workspaces == {ws.id: ws}

    def test_deregisters_when_a_before_delete_hook_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # By this point the container is genuinely gone, so keeping the
        # registration would leak. Only the DIRECTORY is retained.
        _record(monkeypatch, [])
        provider = _provider()
        d = tmp_path / "ws"
        d.mkdir()
        ws = _Workspace(workspace_dir=str(d))
        provider._workspaces[ws.id] = ws

        async def _fails() -> None:
            raise RuntimeError("store unreachable")

        with pytest.raises(RuntimeError):
            asyncio.run(provider.teardown(ws, before_delete=_fails))
        assert provider._workspaces == {}
        assert d.exists()


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


class TestAsyncFailureModes:
    """The cases plain happy-path tests cannot reach.

    Review found both of these by reading, not by running: a cancel during the
    log snapshot skipped removal entirely, leaving a stopped-but-present and
    already-deregistered container; and two concurrent teardowns could both
    proceed, letting one delete a directory the other was still archiving.
    """

    def test_real_task_cancellation_during_the_stop_still_removes(self) -> None:
        """Cancel the TASK, not a hand-raised CancelledError.

        An earlier version of this test raised CancelledError from inside the
        subprocess factory. That proves the `finally` runs, but it does NOT
        exercise the shield: the await in the finally only needs shielding when
        the surrounding TASK is being cancelled. The weaker test passed with
        the shield removed, so it was verifying nothing about the thing it was
        written for.
        """
        seq: list[str] = []

        async def _main() -> None:
            provider = _provider()
            reached_logs = asyncio.Event()

            async def _spawn(*argv: str, **_k: object) -> Any:
                head = " ".join(argv[:2])
                seq.append(head)
                if head == "docker logs":
                    reached_logs.set()
                    await asyncio.sleep(3600)  # park here until cancelled
                return _Proc()

            import agentic_isolation.providers.docker as mod

            orig = asyncio.create_subprocess_exec
            mod.asyncio.create_subprocess_exec = _spawn  # type: ignore[assignment]
            try:
                ws = _Workspace()
                provider._workspaces[ws.id] = ws
                task = asyncio.create_task(provider.teardown(ws))
                await reached_logs.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                # The `finally` is what guarantees this. Removing the shield
                # does NOT break it - checked by mutation - because asyncio
                # delivers cancellation once. Removing the `finally` does.
                assert "docker rm" in seq, seq
                assert provider._workspaces == {}
            finally:
                mod.asyncio.create_subprocess_exec = orig  # type: ignore[assignment]

        asyncio.run(_main())

    def test_concurrent_teardown_cannot_delete_during_an_archive(self, tmp_path: Any) -> None:
        """A second teardown must wait, not race the first one's archive."""

        async def _main() -> None:
            provider = _provider()
            d = tmp_path / "ws"
            d.mkdir()
            (d / "spool.jsonl").write_text("transcript")
            ws = _Workspace(workspace_dir=str(d))
            provider._workspaces[ws.id] = ws

            async def _spawn(*_a: str, **_k: object) -> Any:
                return _Proc()

            import agentic_isolation.providers.docker as mod

            orig = asyncio.create_subprocess_exec
            mod.asyncio.create_subprocess_exec = _spawn  # type: ignore[assignment]

            observed: dict[str, bool] = {}
            started = asyncio.Event()

            async def _slow_archive() -> None:
                started.set()
                await asyncio.sleep(0.05)
                # If the other teardown raced ahead, the spool is gone by now.
                observed["spool_present"] = (d / "spool.jsonl").exists()
                raise RuntimeError("store unreachable")

            try:
                first = asyncio.create_task(provider.teardown(ws, before_delete=_slow_archive))
                await started.wait()
                second = asyncio.create_task(provider.teardown(ws))
                results = await asyncio.gather(first, second, return_exceptions=True)
            finally:
                mod.asyncio.create_subprocess_exec = orig  # type: ignore[assignment]

            assert observed["spool_present"], (
                "a concurrent teardown deleted the workspace mid-archive"
            )
            assert isinstance(results[0], RuntimeError)

        asyncio.run(_main())
