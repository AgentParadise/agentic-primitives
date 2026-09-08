"""A failed provider subprocess must report the status that decided it failed.

Issue #1247: `WorkspaceDockerProvider.create()` built its error from stderr
alone and substituted the literal string `Unknown error` when stderr was
empty, so run `exec-abdef9078efe` failed with

    Failed to create container: Unknown error

and could not be attributed: no exit code, no signal, no stderr. The exit
status is what decides the subprocess failed, and it was thrown away between
that decision and the message.

The same shape existed at two more sites in the same package
(`InteractiveTmuxProvider.write_file` / `.read_file`, which raised
`f"... failed: {stderr}"` — an empty stderr there produces a message that
trails off into nothing). All three now raise `SubprocessFailure`.

These tests drive the PROVIDER METHODS, not `SubprocessFailure` itself: the
defect was a value dropped between the subprocess and the raise, so what has
to be pinned is what the operator actually receives from the call. Docker is
never contacted — `asyncio.create_subprocess_exec` is monkeypatched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import SubprocessFailure
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider

pytestmark = pytest.mark.unit


class _FailingProc:
    """A finished process that failed, with whatever stderr it managed."""

    def __init__(self, returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self, _stdin: bytes | None = None) -> tuple[bytes, bytes]:
        return b"", self._stderr

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        """Teardown after a failed create() terminates leftover subprocesses."""

    @property
    def stdout(self) -> Any:
        class _EmptyReader:
            async def read(self, _n: int) -> bytes:
                return b""

        return _EmptyReader()


def _fail_subprocess_with(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stderr: bytes = b"",
    *,
    only: str | None = None,
) -> None:
    """Make `create_subprocess_exec` return a failed process.

    `only` restricts the failure to argv containing that token, so a test can
    fail `docker run` while letting the `docker network` probe succeed.
    """

    async def _spawn(*argv: str, **_kwargs: object) -> Any:
        if only is not None and only not in argv:
            return _FailingProc(0)
        return _FailingProc(returncode, stderr)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)


def _docker_provider(tmp_path: Path) -> WorkspaceDockerProvider:
    return WorkspaceDockerProvider(workspace_base_dir=tmp_path / "ws")


def _tmux_provider() -> InteractiveTmuxProvider:
    return InteractiveTmuxProvider(
        default_host_auth={"claude": Path("/tmp/nowhere/.claude")},
        default_host_claude_dotjson=Path("/tmp/nowhere/.claude.json"),
        default_claude_plugin_dirs=[],
    )


class _FakeHandle:
    container = "itws-fake"


def _tmux_workspace() -> Any:
    class _WS:
        id = "ws-1"
        _handle = _FakeHandle()
        metadata: dict[str, Any] = {"workdir": "/workspace"}

    return _WS()


class TestDockerCreate:
    """`docker run` failing during `create()` — the site issue #1247 reports."""

    async def test_empty_stderr_still_names_the_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The exact shape that produced `Unknown error` on exec-abdef9078efe.

        125 is docker's own "the daemon refused to run the container", and it
        is a status the unfixed code could not have put in the message.
        """
        _fail_subprocess_with(monkeypatch, 125, b"", only="run")

        with pytest.raises(RuntimeError) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        message = str(excinfo.value)
        assert "125" in message
        assert "no stderr" in message
        assert "Unknown error" not in message

    async def test_stderr_is_reported_alongside_the_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _fail_subprocess_with(
            monkeypatch,
            125,
            b"docker: Error response from daemon: no such image\n",
            only="run",
        )

        with pytest.raises(RuntimeError) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        message = str(excinfo.value)
        assert "125" in message
        assert "no such image" in message

    async def test_killed_client_is_reported_as_a_signal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A negative returncode is a signal, and reads as one.

        This is the case the issue calls out as unattributable: OOM-killing
        the docker client leaves no stderr at all.
        """
        _fail_subprocess_with(monkeypatch, -9, b"", only="run")

        with pytest.raises(RuntimeError) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        message = str(excinfo.value)
        assert "signal 9" in message
        assert "SIGKILL" in message

    async def test_message_names_the_container(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Without the container name a failure cannot be tied to a run."""
        _fail_subprocess_with(monkeypatch, 125, b"", only="run")

        with pytest.raises(RuntimeError) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        assert "agentic-ws-" in str(excinfo.value)

    async def test_status_survives_as_data_not_only_as_prose(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A wrapping caller can attribute the failure without parsing text."""
        _fail_subprocess_with(monkeypatch, 125, b"", only="run")

        with pytest.raises(SubprocessFailure) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        assert excinfo.value.returncode == 125

    async def test_undecodable_stderr_does_not_replace_the_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Non-UTF-8 stderr used to raise UnicodeDecodeError from the error path.

        `stderr.decode()` was strict, so a container image emitting raw bytes
        on failure lost the failure and reported a decoding problem instead.
        """
        _fail_subprocess_with(monkeypatch, 125, b"\xff\xfe boom", only="run")

        with pytest.raises(SubprocessFailure) as excinfo:
            await _docker_provider(tmp_path).create(WorkspaceConfig(image="busybox"))

        message = str(excinfo.value)
        assert "125" in message
        assert "boom" in message


class TestInteractiveTmuxFileTransfer:
    """The same shape, two sites over in the interactive-tmux provider."""

    async def test_write_file_empty_stderr_names_the_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`docker exec ... tee` failing silently — e.g. a read-only mount."""
        _fail_subprocess_with(monkeypatch, 1, b"")

        with pytest.raises(RuntimeError) as excinfo:
            await _tmux_provider().write_file(_tmux_workspace(), "out.txt", "hello")

        message = str(excinfo.value)
        assert "exit code 1" in message
        assert "no stderr" in message
        assert "out.txt" in message

    async def test_read_file_reports_exit_code_with_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fail_subprocess_with(monkeypatch, 13, b"cat: /workspace/x: Permission denied\n")

        with pytest.raises(RuntimeError) as excinfo:
            await _tmux_provider().read_file(_tmux_workspace(), "x")

        message = str(excinfo.value)
        assert "13" in message
        assert "Permission denied" in message

    async def test_read_file_still_maps_missing_files_to_filenotfound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The missing-file branch sits in front of the raise that was changed."""
        _fail_subprocess_with(monkeypatch, 1, b"cat: /workspace/gone: No such file or directory\n")

        with pytest.raises(FileNotFoundError):
            await _tmux_provider().read_file(_tmux_workspace(), "gone")
