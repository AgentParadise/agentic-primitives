"""Tests for WorkspaceLocalProvider."""

import pytest

from agentic_isolation import (
    AgenticWorkspace,
    WorkspaceConfig,
    WorkspaceLocalProvider,
)


class TestWorkspaceLocalProvider:
    """Tests for WorkspaceLocalProvider."""

    @pytest.fixture
    def provider(self) -> WorkspaceLocalProvider:
        """Create a local provider."""
        return WorkspaceLocalProvider()

    @pytest.mark.asyncio
    async def test_create_workspace(self, provider: WorkspaceLocalProvider) -> None:
        """Should create workspace directory."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            assert workspace.id.startswith("ws-")
            assert workspace.path.exists()
            assert workspace.provider == "local"
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_destroy_workspace(self, provider: WorkspaceLocalProvider) -> None:
        """Should remove workspace directory."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)
        path = workspace.path

        await provider.destroy(workspace)

        assert not path.exists()

    @pytest.mark.asyncio
    async def test_execute_command(self, provider: WorkspaceLocalProvider) -> None:
        """Should execute command and return result."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "echo hello")

            assert result.exit_code == 0
            assert "hello" in result.stdout
            assert result.success is True
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_execute_with_env(self, provider: WorkspaceLocalProvider) -> None:
        """Should pass environment variables."""
        config = WorkspaceConfig(
            provider="local",
            environment={"TEST_VAR": "test_value"},
        )
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "echo $TEST_VAR")

            assert "test_value" in result.stdout
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_execute_with_secrets(self, provider: WorkspaceLocalProvider) -> None:
        """Should inject secrets as environment variables."""
        config = WorkspaceConfig(
            provider="local",
            secrets={"SECRET_KEY": "secret123"},
        )
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "echo $SECRET_KEY")

            assert "secret123" in result.stdout
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_execute_failing_command(self, provider: WorkspaceLocalProvider) -> None:
        """Should capture failed command exit code."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "exit 42")

            assert result.exit_code == 42
            assert result.success is False
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, provider: WorkspaceLocalProvider) -> None:
        """Should write and read files."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            await provider.write_file(workspace, "test.txt", "hello world")
            content = await provider.read_file(workspace, "test.txt")

            assert content == "hello world"
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_write_file_creates_directories(self, provider: WorkspaceLocalProvider) -> None:
        """Should create parent directories."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            await provider.write_file(workspace, "deep/nested/file.txt", "content")
            content = await provider.read_file(workspace, "deep/nested/file.txt")

            assert content == "content"
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_file_exists(self, provider: WorkspaceLocalProvider) -> None:
        """Should check file existence."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            assert not await provider.file_exists(workspace, "missing.txt")

            await provider.write_file(workspace, "exists.txt", "content")
            assert await provider.file_exists(workspace, "exists.txt")
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_raises(self, provider: WorkspaceLocalProvider) -> None:
        """Should raise FileNotFoundError for missing files."""
        config = WorkspaceConfig(provider="local")
        workspace = await provider.create(config)

        try:
            with pytest.raises(FileNotFoundError):
                await provider.read_file(workspace, "nonexistent.txt")
        finally:
            await provider.destroy(workspace)


class TestAgenticWorkspaceLocal:
    """Tests for AgenticWorkspace with local provider."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Should work as async context manager."""
        async with AgenticWorkspace.create(provider="local") as workspace:
            assert workspace.id is not None
            assert workspace.path.exists()

    @pytest.mark.asyncio
    async def test_auto_cleanup(self) -> None:
        """Should cleanup workspace on exit."""
        async with AgenticWorkspace.create(provider="local") as workspace:
            path = workspace.path
            assert path.exists()

        assert not path.exists()

    @pytest.mark.asyncio
    async def test_execute_shorthand(self) -> None:
        """Should provide execute shorthand."""
        async with AgenticWorkspace.create(provider="local") as workspace:
            result = await workspace.execute("echo test")
            assert "test" in result.stdout

    @pytest.mark.asyncio
    async def test_file_operations(self) -> None:
        """Should provide file operation shorthands."""
        async with AgenticWorkspace.create(provider="local") as workspace:
            await workspace.write_file("test.py", "print('hello')")
            assert await workspace.file_exists("test.py")

            content = await workspace.read_file("test.py")
            assert "hello" in content

    @pytest.mark.asyncio
    async def test_secrets_injection(self) -> None:
        """Should inject secrets."""
        async with AgenticWorkspace.create(
            provider="local",
            secrets={"MY_SECRET": "secret_value"},
        ) as workspace:
            result = await workspace.execute("echo $MY_SECRET")
            assert "secret_value" in result.stdout

    @pytest.mark.asyncio
    async def test_to_dict(self) -> None:
        """Should convert to dictionary."""
        async with AgenticWorkspace.create(provider="local") as workspace:
            data = workspace.to_dict()
            assert "id" in data
            assert "provider" in data
            assert data["provider"] == "local"
