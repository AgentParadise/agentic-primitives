"""Docker container provider for production isolation.

This provider creates Docker containers for isolated execution,
providing real process and filesystem isolation.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    BaseProvider,
    ExecuteResult,
    Workspace,
)


class DockerProvider(BaseProvider):
    """Docker container workspace provider.

    Creates isolated Docker containers for agent execution.
    Requires Docker to be installed and running.

    Usage:
        provider = DockerProvider()
        workspace = await provider.create(config)
        result = await provider.execute(workspace, "echo hello")
        await provider.destroy(workspace)
    """

    def __init__(
        self,
        docker_host: str | None = None,
        default_image: str = "python:3.12-slim",
    ):
        """Initialize Docker provider.

        Args:
            docker_host: Docker daemon URL (default: local socket)
            default_image: Default image for workspaces
        """
        self._docker_host = docker_host
        self._default_image = default_image
        self._client: Any = None
        self._workspaces: dict[str, Workspace] = {}

    @property
    def name(self) -> str:
        """Provider name."""
        return "docker"

    async def _get_client(self) -> Any:
        """Get or create Docker client."""
        if self._client is None:
            try:
                import docker
            except ImportError as e:
                raise ImportError(
                    "Docker SDK required. Install with: pip install docker"
                ) from e

            self._client = docker.from_env()

        return self._client

    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create a Docker container workspace."""
        client = await self._get_client()

        workspace_id = f"ws-{uuid.uuid4().hex[:12]}"
        image = config.image or self._default_image

        # Build environment variables
        env_vars = {
            "WORKSPACE_ID": workspace_id,
            **config.environment,
            **config.secrets,  # Secrets as env vars (consider more secure methods)
        }

        # Build mounts
        mounts = []
        for mount_config in config.mounts:
            mounts.append(mount_config.to_docker_mount())

        # Build labels
        labels = {
            "agentic.workspace.id": workspace_id,
            "agentic.provider": self.name,
            **config.labels,
        }

        # Create container
        container = client.containers.create(
            image=image,
            command="tail -f /dev/null",  # Keep container running
            working_dir=config.working_dir,
            environment=env_vars,
            mounts=mounts if mounts else None,
            labels=labels,
            detach=True,
            **config.limits.to_docker_args(),
        )

        # Start container
        container.start()

        workspace = Workspace(
            id=workspace_id,
            provider=self.name,
            path=Path(config.working_dir),
            config=config,
            metadata={
                "container_id": container.id,
                "image": image,
            },
            _handle=container,
        )

        self._workspaces[workspace_id] = workspace
        return workspace

    async def destroy(self, workspace: Workspace) -> None:
        """Stop and remove the Docker container."""
        if workspace.id in self._workspaces:
            del self._workspaces[workspace.id]

        container = workspace._handle
        if container:
            try:
                container.stop(timeout=10)
                container.remove(force=True)
            except Exception:
                pass  # Container may already be stopped/removed

    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """Execute a command in the Docker container."""
        container = workspace._handle
        if not container:
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr="Container not available",
                duration_ms=0,
            )

        # Build exec command
        work_dir = cwd or workspace.config.working_dir
        exec_env = env or {}

        start_time = time.time()

        try:
            # Use docker exec
            exit_code, output = container.exec_run(
                cmd=["sh", "-c", command],
                workdir=work_dir,
                environment=exec_env,
                demux=True,  # Separate stdout/stderr
            )

            duration_ms = (time.time() - start_time) * 1000

            stdout = ""
            stderr = ""
            if output:
                if isinstance(output, tuple):
                    stdout = output[0].decode("utf-8", errors="replace") if output[0] else ""
                    stderr = output[1].decode("utf-8", errors="replace") if output[1] else ""
                else:
                    stdout = output.decode("utf-8", errors="replace")

            return ExecuteResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                timed_out=False,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                timed_out=False,
            )

    async def write_file(
        self,
        workspace: Workspace,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write a file in the Docker container."""
        container = workspace._handle
        if not container:
            raise RuntimeError("Container not available")

        # Use docker exec to write file via cat
        if isinstance(content, str):
            content = content.encode("utf-8")

        # Create parent directory
        parent_dir = str(Path(path).parent)
        if parent_dir and parent_dir != ".":
            container.exec_run(["mkdir", "-p", parent_dir])

        # Write file using tar
        import io
        import tarfile

        file_data = io.BytesIO()
        with tarfile.open(fileobj=file_data, mode="w") as tar:
            file_info = tarfile.TarInfo(name=Path(path).name)
            file_info.size = len(content)
            tar.addfile(file_info, io.BytesIO(content))

        file_data.seek(0)
        container.put_archive(str(Path(path).parent) or "/", file_data)

    async def read_file(
        self,
        workspace: Workspace,
        path: str,
    ) -> str:
        """Read a file from the Docker container."""
        container = workspace._handle
        if not container:
            raise RuntimeError("Container not available")

        # Use docker exec to read file
        exit_code, output = container.exec_run(["cat", path])

        if exit_code != 0:
            raise FileNotFoundError(f"File not found: {path}")

        return output.decode("utf-8", errors="replace")

    async def file_exists(
        self,
        workspace: Workspace,
        path: str,
    ) -> bool:
        """Check if a file exists in the Docker container."""
        container = workspace._handle
        if not container:
            return False

        exit_code, _ = container.exec_run(["test", "-f", path])
        return exit_code == 0
