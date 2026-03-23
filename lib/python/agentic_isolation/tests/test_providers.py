"""Tests for provider base types."""

from agentic_isolation import WorkspaceLocalProvider
from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    ExecuteResult,
    Workspace,
    WorkspaceProvider,
)


class TestExecuteResult:
    """Tests for ExecuteResult dataclass."""

    def test_success_property(self) -> None:
        """Should report success for exit code 0."""
        result = ExecuteResult(exit_code=0, stdout="", stderr="")
        assert result.success is True

    def test_failure_property(self) -> None:
        """Should report failure for non-zero exit code."""
        result = ExecuteResult(exit_code=1, stdout="", stderr="error")
        assert result.success is False

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        result = ExecuteResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100.5,
            timed_out=False,
        )
        data = result.to_dict()

        assert data["exit_code"] == 0
        assert data["stdout"] == "output"
        assert data["duration_ms"] == 100.5
        assert data["success"] is True

    def test_timed_out_result(self) -> None:
        """Should track timeout."""
        result = ExecuteResult(
            exit_code=124,
            stdout="",
            stderr="timeout",
            timed_out=True,
        )
        assert result.timed_out is True


class TestWorkspace:
    """Tests for Workspace dataclass."""

    def test_creation(self) -> None:
        """Should create workspace."""
        from pathlib import Path

        config = WorkspaceConfig()
        workspace = Workspace(
            id="ws-123",
            provider="local",
            path=Path("/tmp/test"),
            config=config,
        )

        assert workspace.id == "ws-123"
        assert workspace.provider == "local"

    def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        from pathlib import Path

        config = WorkspaceConfig()
        workspace = Workspace(
            id="ws-123",
            provider="local",
            path=Path("/tmp/test"),
            config=config,
        )
        data = workspace.to_dict()

        assert data["id"] == "ws-123"
        assert data["provider"] == "local"
        assert "created_at" in data


class TestReadStreamLines:
    """Tests for BaseProvider._read_stream_lines shared helper."""

    async def test_yields_decoded_lines(self) -> None:
        """Should yield decoded stdout lines from a subprocess."""
        import asyncio

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "printf", "line1\nline2\nline3\n",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        lines = [line async for line in BaseProvider._read_stream_lines(proc)]
        assert lines == ["line1", "line2", "line3"]

    async def test_skips_empty_lines(self) -> None:
        """Should skip empty lines in output."""
        import asyncio

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "printf", "hello\n\nworld\n",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        lines = [line async for line in BaseProvider._read_stream_lines(proc)]
        assert lines == ["hello", "world"]

    async def test_timeout_kills_process(self) -> None:
        """Should kill the process when timeout is reached."""
        import asyncio

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "sleep", "60",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        lines = [
            line async for line in BaseProvider._read_stream_lines(proc, timeout_seconds=1)
        ]
        assert lines == []
        # Process should be terminated
        assert proc.returncode is not None


class TestCheckStreamTimeout:
    """Tests for BaseProvider._check_stream_timeout."""

    async def test_no_timeout_returns_false(self) -> None:
        """Should return False when no timeout is set."""
        import asyncio
        import time

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "sleep", "0",
            stdout=asyncio.subprocess.PIPE,
        )
        assert BaseProvider._check_stream_timeout(proc, None, time.perf_counter()) is False
        proc.kill()
        await proc.wait()

    async def test_within_timeout_returns_false(self) -> None:
        """Should return False when within timeout."""
        import asyncio
        import time

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "sleep", "60",
            stdout=asyncio.subprocess.PIPE,
        )
        assert BaseProvider._check_stream_timeout(proc, 30, time.perf_counter()) is False
        proc.kill()
        await proc.wait()


class TestTerminateProcess:
    """Tests for BaseProvider._terminate_process."""

    async def test_terminates_running_process(self) -> None:
        """Should terminate a running process."""
        import asyncio

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "sleep", "60",
            stdout=asyncio.subprocess.PIPE,
        )
        assert proc.returncode is None
        await BaseProvider._terminate_process(proc)
        assert proc.returncode is not None

    async def test_noop_on_already_exited(self) -> None:
        """Should be safe to call on already-exited process."""
        import asyncio

        from agentic_isolation.providers.base import BaseProvider

        proc = await asyncio.create_subprocess_exec(
            "true",
            stdout=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        # Should not raise
        await BaseProvider._terminate_process(proc)


class TestWorkspaceProviderProtocol:
    """Tests for WorkspaceProvider protocol."""

    def test_local_provider_is_workspace_provider(self) -> None:
        """WorkspaceLocalProvider should implement WorkspaceProvider."""
        provider = WorkspaceLocalProvider()
        assert isinstance(provider, WorkspaceProvider)

    def test_provider_has_name(self) -> None:
        """Provider should have a name."""
        provider = WorkspaceLocalProvider()
        assert provider.name == "local"
