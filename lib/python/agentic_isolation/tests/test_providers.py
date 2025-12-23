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
