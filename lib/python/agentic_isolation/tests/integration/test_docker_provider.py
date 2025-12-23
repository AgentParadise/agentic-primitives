"""Integration tests for WorkspaceDockerProvider.

These tests require Docker to be installed and running.
Run with: pytest tests/integration/ -v --tb=short
"""

import time

import pytest

from agentic_isolation import (
    AgenticWorkspace,
    SecurityConfig,
    WorkspaceConfig,
    WorkspaceDockerProvider,
)


def docker_available() -> bool:
    """Check if Docker is available."""
    return WorkspaceDockerProvider.is_available()


# Skip all tests if Docker is not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not docker_available(), reason="Docker not available"),
]


class TestDockerProviderLifecycle:
    """Tests for container lifecycle management."""

    @pytest.fixture
    def provider(self) -> WorkspaceDockerProvider:
        """Create a Docker provider."""
        return WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.development(),  # Relaxed for faster tests
        )

    @pytest.mark.asyncio
    async def test_create_and_destroy_workspace(
        self, provider: WorkspaceDockerProvider
    ) -> None:
        """Should create and destroy Docker container."""
        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
        )

        workspace = await provider.create(config)
        try:
            assert workspace.id.startswith("ws-")
            assert workspace.provider == "docker"
            assert "container_id" in workspace.metadata
            assert "container_name" in workspace.metadata
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_execute_command(self, provider: WorkspaceDockerProvider) -> None:
        """Should execute command in container."""
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "echo hello")

            assert result.exit_code == 0
            assert "hello" in result.stdout
            assert result.success is True
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_execute_with_environment(
        self, provider: WorkspaceDockerProvider
    ) -> None:
        """Should pass environment variables to command."""
        config = WorkspaceConfig(
            provider="docker",
            image="python:3.12-slim",
            environment={"TEST_VAR": "test_value"},
        )
        workspace = await provider.create(config)

        try:
            result = await provider.execute(workspace, "echo $TEST_VAR")
            assert "test_value" in result.stdout
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_file_operations(self, provider: WorkspaceDockerProvider) -> None:
        """Should write and read files via mounted volume."""
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            # Write file
            await provider.write_file(workspace, "test.txt", "hello world")

            # Check exists
            assert await provider.file_exists(workspace, "test.txt")
            assert not await provider.file_exists(workspace, "missing.txt")

            # Read back
            content = await provider.read_file(workspace, "test.txt")
            assert content == "hello world"
        finally:
            await provider.destroy(workspace)


class TestDockerProviderStreaming:
    """Tests for real-time stdout streaming."""

    @pytest.fixture
    def provider(self) -> WorkspaceDockerProvider:
        """Create a Docker provider."""
        return WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.development(),
        )

    @pytest.mark.asyncio
    async def test_stream_yields_lines_realtime(
        self, provider: WorkspaceDockerProvider
    ) -> None:
        """Should yield lines as they are produced, not buffered."""
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            lines_with_times: list[tuple[str, float]] = []
            start = time.perf_counter()

            # Echo two lines with a delay between them
            command = ["sh", "-c", "echo line1; sleep 0.5; echo line2"]

            async for line in provider.stream(workspace, command):
                lines_with_times.append((line, time.perf_counter() - start))

            # Should have two lines
            assert len(lines_with_times) >= 2
            assert lines_with_times[0][0] == "line1"
            assert lines_with_times[1][0] == "line2"

            # Second line should come ~0.5s after first (streaming, not buffered)
            time_diff = lines_with_times[1][1] - lines_with_times[0][1]
            assert time_diff > 0.3, f"Lines came too fast ({time_diff}s), not streaming"
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_stream_handles_many_lines(
        self, provider: WorkspaceDockerProvider
    ) -> None:
        """Should handle many lines of output."""
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            lines: list[str] = []
            command = ["sh", "-c", "for i in $(seq 1 100); do echo line$i; done"]

            async for line in provider.stream(workspace, command):
                lines.append(line)

            assert len(lines) == 100
            assert lines[0] == "line1"
            assert lines[99] == "line100"
        finally:
            await provider.destroy(workspace)


class TestDockerSecurityHardening:
    """Tests for security hardening features."""

    @pytest.mark.asyncio
    async def test_capabilities_dropped(self) -> None:
        """Should drop all Linux capabilities in production mode."""
        provider = WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.production(),
        )
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            # Check effective capabilities are zero
            result = await provider.execute(
                workspace, "cat /proc/self/status | grep CapEff"
            )
            # CapEff should be 0000000000000000 (no effective capabilities)
            assert "0000000000000000" in result.stdout, (
                f"Expected no capabilities, got: {result.stdout}"
            )
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_root_filesystem_readonly(self) -> None:
        """Should have read-only root filesystem in production mode."""
        provider = WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.production(),
        )
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            # Try to write to root filesystem (should fail)
            result = await provider.execute(
                workspace, "touch /etc/test 2>&1 || echo READONLY"
            )
            assert "READONLY" in result.stdout or "Read-only" in result.stdout
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_tmpfs_writable(self) -> None:
        """Should have writable /tmp even with read-only root."""
        provider = WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.production(),
        )
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            # /tmp should be writable
            result = await provider.execute(
                workspace, "echo test > /tmp/testfile && cat /tmp/testfile"
            )
            assert result.exit_code == 0
            assert "test" in result.stdout
        finally:
            await provider.destroy(workspace)

    @pytest.mark.asyncio
    async def test_workspace_writable(self) -> None:
        """Should have writable /workspace."""
        provider = WorkspaceDockerProvider(
            default_image="python:3.12-slim",
            security=SecurityConfig.production(),
        )
        config = WorkspaceConfig(provider="docker", image="python:3.12-slim")
        workspace = await provider.create(config)

        try:
            result = await provider.execute(
                workspace,
                "echo hello > /workspace/test.txt && cat /workspace/test.txt",
            )
            assert result.exit_code == 0
            assert "hello" in result.stdout
        finally:
            await provider.destroy(workspace)


class TestAgenticWorkspaceDocker:
    """Tests for AgenticWorkspace with Docker provider."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Should work as async context manager."""
        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            security=SecurityConfig.development(),
        ) as workspace:
            assert workspace.id is not None
            assert workspace.provider_name == "docker"

    @pytest.mark.asyncio
    async def test_execute_shorthand(self) -> None:
        """Should provide execute shorthand."""
        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            security=SecurityConfig.development(),
        ) as workspace:
            result = await workspace.execute("echo test")
            assert "test" in result.stdout

    @pytest.mark.asyncio
    async def test_stream_shorthand(self) -> None:
        """Should provide stream shorthand."""
        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            security=SecurityConfig.development(),
        ) as workspace:
            lines = []
            async for line in workspace.stream(["echo", "hello"]):
                lines.append(line)
            assert "hello" in lines

    @pytest.mark.asyncio
    async def test_auto_cleanup(self) -> None:
        """Should cleanup container on exit."""
        import subprocess

        container_name = None

        async with AgenticWorkspace.create(
            provider="docker",
            image="python:3.12-slim",
            security=SecurityConfig.development(),
        ) as workspace:
            # Get container name from metadata
            # The workspace._workspace has the metadata
            container_name = workspace._workspace.metadata.get("container_name")
            assert container_name is not None

            # Verify container is running
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
            )
            assert "true" in result.stdout.lower()

        # After context exit, container should be gone
        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0  # Container should not exist
