"""Docker container provider for production isolation.

This provider creates Docker containers for isolated execution,
providing real process and filesystem isolation with security hardening.

Features:
- Security hardening (cap-drop, no-new-privileges, read-only root)
- gVisor runtime support (auto-detected)
- Real-time stdout streaming
- Resource limits (memory, CPU, pids)
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from agentic_isolation.config import SecurityConfig, WorkspaceConfig
from agentic_isolation.providers.base import (
    BaseProvider,
    ExecuteResult,
    Workspace,
)

logger = logging.getLogger(__name__)

# Default network for workspace containers
DEFAULT_NETWORK = "agentic-workspace-net"


class WorkspaceDockerProvider(BaseProvider):
    """Production-grade Docker workspace provider.

    Creates isolated Docker containers with security hardening for agent execution.
    Supports real-time stdout streaming for observability.

    Security features (enabled by default):
    - --cap-drop=ALL: Remove all Linux capabilities
    - --security-opt=no-new-privileges: Block privilege escalation
    - --read-only: Immutable root filesystem
    - --tmpfs: Writable /tmp and /home/agent in memory
    - --pids-limit: Process count limit
    - --runtime=runsc: gVisor sandbox (if available)

    Usage:
        provider = WorkspaceDockerProvider()
        workspace = await provider.create(config)

        # Execute with full output
        result = await provider.execute(workspace, "echo hello")

        # Stream output in real-time
        async for line in provider.stream(workspace, ["python", "-u", "agent.py"]):
            print(line)

        await provider.destroy(workspace)
    """

    def __init__(
        self,
        *,
        default_image: str = "python:3.12-slim",
        default_network: str = DEFAULT_NETWORK,
        security: SecurityConfig | None = None,
        workspace_base_dir: Path | str | None = None,
    ):
        """Initialize Docker provider.

        Args:
            default_image: Default Docker image for workspaces
            default_network: Docker network for containers
            security: Security configuration (defaults to production)
            workspace_base_dir: Base directory for workspace mounts
        """
        self._default_image = default_image
        self._default_network = default_network
        self._security = security or SecurityConfig.production()
        self._workspace_base_dir = Path(workspace_base_dir) if workspace_base_dir else None
        self._workspaces: dict[str, Workspace] = {}
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Provider name."""
        return "docker"

    @staticmethod
    def is_available() -> bool:
        """Check if Docker is available."""
        return shutil.which("docker") is not None

    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create a Docker container workspace with security hardening."""
        short_id = uuid.uuid4().hex[:8]
        workspace_id = f"ws-{short_id}"
        container_name = f"agentic-ws-{short_id}"

        # Create workspace directory for volume mount
        if self._workspace_base_dir:
            self._workspace_base_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir = self._workspace_base_dir / workspace_id
        else:
            workspace_dir = Path(tempfile.mkdtemp(prefix=f"agentic-ws-{short_id}-"))
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Ensure network exists
        await self._ensure_network(self._default_network)

        # Build docker run command
        image = config.image or self._default_image
        security = config.security if hasattr(config, "security") else self._security

        cmd = self._build_run_command(
            container_name=container_name,
            workspace_id=workspace_id,
            workspace_dir=workspace_dir,
            image=image,
            config=config,
            security=security,
        )

        logger.info(
            "Creating workspace container (id=%s, image=%s, gvisor=%s)",
            workspace_id,
            image,
            security.use_gvisor,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise RuntimeError(f"Failed to create container: {error_msg}")

            container_id = stdout.decode().strip()

            # Wait for container to be running
            await self._wait_for_running(container_name)

            workspace = Workspace(
                id=workspace_id,
                provider=self.name,
                path=Path(config.working_dir),
                config=config,
                metadata={
                    "container_id": container_id,
                    "container_name": container_name,
                    "image": image,
                    "workspace_dir": str(workspace_dir),
                },
                _handle=container_name,  # Use name for docker exec
            )

            async with self._lock:
                self._workspaces[workspace_id] = workspace

            logger.info("Container created (id=%s, container=%s)", workspace_id, container_name)
            return workspace

        except Exception as e:
            logger.exception("Failed to create container: %s", e)
            await self._cleanup_container(container_name)
            shutil.rmtree(workspace_dir, ignore_errors=True)
            raise

    def _build_run_command(
        self,
        *,
        container_name: str,
        workspace_id: str,
        workspace_dir: Path,
        image: str,
        config: WorkspaceConfig,
        security: SecurityConfig,
    ) -> list[str]:
        """Build docker run command with security hardening."""
        cmd = [
            "docker",
            "run",
            "-d",  # Detached
            f"--name={container_name}",
            f"--network={self._default_network}",
        ]

        # Security hardening
        cmd.extend(security.to_docker_run_args())

        # Resource limits
        limits = config.limits
        cmd.append(f"--memory={limits.memory}")
        cmd.append(f"--cpus={limits.cpu}")

        # Workspace mount
        cmd.append(f"-v={workspace_dir}:/workspace:rw")
        cmd.append("-w=/workspace")

        # Environment variables
        env_vars = {
            "WORKSPACE_ID": workspace_id,
            **config.environment,
            **config.secrets,
        }
        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Labels
        cmd.extend([
            f"--label=agentic.workspace.id={workspace_id}",
            f"--label=agentic.provider={self.name}",
        ])
        for key, value in config.labels.items():
            cmd.append(f"--label={key}={value}")

        # Image and keep-alive command
        cmd.append(image)
        cmd.extend(["sleep", "infinity"])

        return cmd

    async def destroy(self, workspace: Workspace) -> None:
        """Stop and remove the Docker container."""
        async with self._lock:
            self._workspaces.pop(workspace.id, None)

        container_name = workspace._handle
        workspace_dir = workspace.metadata.get("workspace_dir")

        logger.info("Destroying workspace (id=%s)", workspace.id)

        await self._cleanup_container(container_name)

        if workspace_dir:
            shutil.rmtree(workspace_dir, ignore_errors=True)

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
        container_name = workspace._handle
        if not container_name:
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr="Container not available",
                duration_ms=0,
            )

        exec_cmd = ["docker", "exec"]

        if cwd:
            exec_cmd.extend(["-w", cwd])
        else:
            exec_cmd.extend(["-w", "/workspace"])

        if env:
            for key, value in env.items():
                exec_cmd.extend(["-e", f"{key}={value}"])

        exec_cmd.append(container_name)
        exec_cmd.extend(["sh", "-c", command])

        start_time = time.perf_counter()
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout or 3600,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                timed_out = True
                stdout, stderr = b"", b"Command timed out"

            duration_ms = (time.perf_counter() - start_time) * 1000

            return ExecuteResult(
                exit_code=-1 if timed_out else (proc.returncode or 0),
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                duration_ms=duration_ms,
                timed_out=timed_out,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                timed_out=False,
            )

    async def stream(
        self,
        workspace: Workspace,
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
            workspace: Workspace to execute in
            command: Command as list of strings
            timeout_seconds: Max execution time
            cwd: Working directory override
            env: Additional environment variables

        Yields:
            Individual stdout lines as they are produced
        """
        container_name = workspace._handle
        if not container_name:
            raise RuntimeError("Container not available")

        exec_cmd = ["docker", "exec", "-i"]

        if cwd:
            exec_cmd.extend(["-w", cwd])
        else:
            exec_cmd.extend(["-w", "/workspace"])

        if env:
            for key, value in env.items():
                exec_cmd.extend(["-e", f"{key}={value}"])

        exec_cmd.append(container_name)
        exec_cmd.extend(command)

        logger.debug("Starting stream (container=%s, cmd=%s)", container_name, command)

        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        start_time = time.perf_counter()

        try:
            while True:
                if proc.stdout is None:
                    break

                # Check timeout
                if timeout_seconds:
                    elapsed = time.perf_counter() - start_time
                    if elapsed > timeout_seconds:
                        logger.warning("Stream timeout after %.1fs", elapsed)
                        proc.kill()
                        break

                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=1.0,  # Check timeout every second
                    )
                except TimeoutError:
                    # Check if process ended
                    if proc.returncode is not None:
                        break
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
                if line:
                    yield line

        finally:
            # Ensure process is terminated
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except (TimeoutError, ProcessLookupError):
                    proc.kill()

    async def write_file(
        self,
        workspace: Workspace,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write a file in the Docker container via mounted volume."""
        workspace_dir = workspace.metadata.get("workspace_dir")
        if not workspace_dir:
            raise RuntimeError("Workspace directory not available")

        file_path = Path(workspace_dir) / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            file_path.write_text(content)
        else:
            file_path.write_bytes(content)

    async def read_file(
        self,
        workspace: Workspace,
        path: str,
    ) -> str:
        """Read a file from the Docker container via mounted volume."""
        workspace_dir = workspace.metadata.get("workspace_dir")
        if not workspace_dir:
            raise RuntimeError("Workspace directory not available")

        file_path = Path(workspace_dir) / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        return file_path.read_text()

    async def file_exists(
        self,
        workspace: Workspace,
        path: str,
    ) -> bool:
        """Check if a file exists in the workspace."""
        workspace_dir = workspace.metadata.get("workspace_dir")
        if not workspace_dir:
            return False

        return (Path(workspace_dir) / path).exists()

    async def _ensure_network(self, network_name: str) -> None:
        """Ensure Docker network exists."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "network", "inspect", network_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode != 0:
            proc = await asyncio.create_subprocess_exec(
                "docker", "network", "create", network_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

    async def _wait_for_running(self, container_name: str, timeout: float = 30.0) -> None:
        """Wait for container to be in running state."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout.decode().strip().lower() == "true":
                return
            await asyncio.sleep(0.1)

        raise RuntimeError(f"Container {container_name} did not start within {timeout}s")

    async def _cleanup_container(self, container_name: str) -> None:
        """Stop and remove a container."""
        # Stop
        proc = await asyncio.create_subprocess_exec(
            "docker", "stop", "-t", "5", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        # Remove
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
