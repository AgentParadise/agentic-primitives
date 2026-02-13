"""AgenticWorkspace - Main entry point for workspace isolation.

Provides a high-level async context manager for creating and
managing isolated execution environments.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentic_isolation.config import (
    MountConfig,
    ResourceLimits,
    SecurityConfig,
    WorkspaceConfig,
)
from agentic_isolation.providers.base import (
    ExecuteResult,
    Workspace,
    WorkspaceProvider,
)
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider

if TYPE_CHECKING:
    from types import TracebackType


# Provider registry
_PROVIDERS: dict[str, type[WorkspaceProvider]] = {
    "local": WorkspaceLocalProvider,
    "docker": WorkspaceDockerProvider,
}


def register_provider(name: str, provider_class: type[WorkspaceProvider]) -> None:
    """Register a custom workspace provider.

    Args:
        name: Provider name for configuration
        provider_class: Provider class implementing WorkspaceProvider
    """
    _PROVIDERS[name] = provider_class


class AgenticWorkspace:
    """High-level async context manager for isolated workspaces.

    Provides a convenient interface for creating, using, and
    cleaning up isolated execution environments with optional
    real-time stdout streaming.

    Usage:
        async with AgenticWorkspace.create(
            provider="docker",
            image="agentic-workspace-claude-cli:latest",
            security=SecurityConfig.production(),
        ) as workspace:
            result = await workspace.execute("echo hello")
            await workspace.write_file("test.py", "print('hi')")
            content = await workspace.read_file("test.py")

    With streaming (for real-time observability):
        async with AgenticWorkspace.create(provider="docker") as workspace:
            async for line in workspace.stream(["claude", "-p", "Hello"]):
                print(line)  # Real-time output

    With configuration object:
        config = WorkspaceConfig(
            provider="local",
            working_dir="/workspace",
        )
        async with AgenticWorkspace(config) as workspace:
            await workspace.execute("ls -la")
    """

    def __init__(
        self,
        config: WorkspaceConfig,
        provider: WorkspaceProvider | None = None,
    ):
        """Initialize AgenticWorkspace.

        Args:
            config: Workspace configuration
            provider: Optional provider instance (auto-created if not provided)
        """
        self._config = config
        self._provider = provider
        self._workspace: Workspace | None = None
        self._error_occurred = False

    @classmethod
    def create(
        cls,
        provider: str = "local",
        image: str = "python:3.12-slim",
        working_dir: str = "/workspace",
        secrets: dict[str, str] | None = None,
        environment: dict[str, str] | None = None,
        mounts: list[tuple[str, str, bool]] | None = None,
        plugins: list[str] | None = None,
        limits: ResourceLimits | None = None,
        security: SecurityConfig | None = None,
        auto_cleanup: bool = True,
        **kwargs: Any,
    ) -> AgenticWorkspace:
        """Create an AgenticWorkspace with common options.

        Args:
            provider: Provider name ("local", "docker", "e2b")
            image: Docker image (for docker provider)
            working_dir: Working directory inside workspace
            secrets: Secrets to inject as environment variables
            environment: Non-secret environment variables
            mounts: List of (host_path, container_path, read_only) tuples
            plugins: Plugin directories to load via --plugin-dir (ADR-033)
            limits: Resource limits
            security: Security configuration (docker provider only)
            auto_cleanup: Whether to cleanup on exit
            **kwargs: Additional config options

        Returns:
            AgenticWorkspace instance (use as async context manager)
        """
        # Build mounts list
        mount_configs = []
        if mounts:
            for mount in mounts:
                if len(mount) == 2:
                    mount_configs.append(MountConfig(mount[0], mount[1], False))
                else:
                    mount_configs.append(MountConfig(mount[0], mount[1], mount[2]))

        config = WorkspaceConfig(
            provider=provider,
            image=image,
            working_dir=working_dir,
            secrets=secrets or {},
            environment=environment or {},
            mounts=mount_configs,
            plugins=plugins or [],
            limits=limits or ResourceLimits(),
            security=security or SecurityConfig(),
            auto_cleanup=auto_cleanup,
            **kwargs,
        )

        return cls(config)

    async def __aenter__(self) -> AgenticWorkspace:
        """Enter the async context and create the workspace."""
        # Get or create provider
        if self._provider is None:
            provider_name = self._config.provider
            if provider_name not in _PROVIDERS:
                raise ValueError(f"Unknown provider: {provider_name}")
            self._provider = _PROVIDERS[provider_name]()

        # Create workspace
        self._workspace = await self._provider.create(self._config)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context and cleanup."""
        self._error_occurred = exc_type is not None

        # Cleanup if configured
        should_cleanup = self._config.auto_cleanup and (
            not self._error_occurred or not self._config.keep_on_error
        )

        if should_cleanup and self._workspace and self._provider:
            await self._provider.destroy(self._workspace)

    @property
    def id(self) -> str:
        """Workspace ID."""
        if not self._workspace:
            raise RuntimeError("Workspace not created. Use as async context manager.")
        return self._workspace.id

    @property
    def path(self) -> Path:
        """Workspace path."""
        if not self._workspace:
            raise RuntimeError("Workspace not created. Use as async context manager.")
        return self._workspace.path

    @property
    def provider_name(self) -> str:
        """Provider name."""
        if not self._provider:
            return self._config.provider
        return self._provider.name

    async def execute(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """Execute a command in the workspace.

        Args:
            command: Command to execute
            timeout: Optional timeout in seconds
            cwd: Working directory (relative to workspace root)
            env: Additional environment variables

        Returns:
            ExecuteResult with output and exit code
        """
        if not self._workspace or not self._provider:
            raise RuntimeError("Workspace not created. Use as async context manager.")

        return await self._provider.execute(
            self._workspace,
            command,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )

    async def stream(
        self,
        command: list[str],
        *,
        timeout_seconds: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream stdout lines from command execution in real-time.

        This is the key method for observability - yields lines as they
        are produced, enabling real-time dashboard updates.

        Args:
            command: Command as list of strings
            timeout_seconds: Max execution time
            cwd: Working directory override
            env: Additional environment variables

        Yields:
            Individual stdout lines as they are produced

        Example:
            async for line in workspace.stream(["claude", "-p", "Hello"]):
                # Each line is yielded as soon as it's available
                await event_store.insert(parse_event(line))
        """
        if not self._workspace or not self._provider:
            raise RuntimeError("Workspace not created. Use as async context manager.")

        # Check if provider supports streaming
        if not hasattr(self._provider, "stream"):
            raise NotImplementedError(f"Provider {self._provider.name} does not support streaming")

        async for line in self._provider.stream(
            self._workspace,
            command,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env=env,
        ):
            yield line

    async def write_file(
        self,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write a file in the workspace.

        Args:
            path: Path relative to workspace root
            content: File content
        """
        if not self._workspace or not self._provider:
            raise RuntimeError("Workspace not created. Use as async context manager.")

        await self._provider.write_file(self._workspace, path, content)

    async def read_file(self, path: str) -> str:
        """Read a file from the workspace.

        Args:
            path: Path relative to workspace root

        Returns:
            File content as string
        """
        if not self._workspace or not self._provider:
            raise RuntimeError("Workspace not created. Use as async context manager.")

        return await self._provider.read_file(self._workspace, path)

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in the workspace.

        Args:
            path: Path relative to workspace root

        Returns:
            True if file exists
        """
        if not self._workspace or not self._provider:
            raise RuntimeError("Workspace not created. Use as async context manager.")

        return await self._provider.file_exists(self._workspace, path)

    def to_dict(self) -> dict[str, Any]:
        """Convert workspace info to dictionary."""
        if not self._workspace:
            return {"provider": self._config.provider, "status": "not_created"}
        return self._workspace.to_dict()
