"""Local filesystem provider for development and testing.

This provider creates workspaces in the local filesystem,
useful for development and testing without Docker overhead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    BaseProvider,
    ExecuteResult,
    Workspace,
)

logger = logging.getLogger(__name__)


class WorkspaceLocalProvider(BaseProvider):
    """Local filesystem workspace provider.

    Creates isolated directories in a temporary location.
    Suitable for development and testing, but provides
    no real isolation from the host system.

    WARNING: No security isolation! Agent code runs with your permissions.
    Use WorkspaceDockerProvider for untrusted workloads.

    Usage:
        provider = WorkspaceLocalProvider()
        workspace = await provider.create(config)
        result = await provider.execute(workspace, "echo hello")
        await provider.destroy(workspace)
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        shell: str = "/bin/bash",
    ):
        """Initialize local provider.

        Args:
            base_dir: Base directory for workspaces (default: system temp)
            shell: Shell to use for command execution
        """
        self._base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
        self._shell = shell
        self._workspaces: dict[str, Workspace] = {}

    @property
    def name(self) -> str:
        """Provider name."""
        return "local"

    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create a local workspace directory."""
        workspace_id = f"ws-{uuid.uuid4().hex[:12]}"
        workspace_path = self._base_dir / "agentic-workspaces" / workspace_id

        # Create workspace directory
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create working directory if different from root
        if config.working_dir != "/workspace":
            working_path = workspace_path / config.working_dir.lstrip("/")
            working_path.mkdir(parents=True, exist_ok=True)

        workspace = Workspace(
            id=workspace_id,
            provider=self.name,
            path=workspace_path,
            config=config,
            metadata={
                "shell": self._shell,
                "base_dir": str(self._base_dir),
            },
        )

        self._workspaces[workspace_id] = workspace
        return workspace

    async def destroy(self, workspace: Workspace) -> None:
        """Remove the workspace directory."""
        if workspace.id in self._workspaces:
            del self._workspaces[workspace.id]

        if workspace.path.exists():
            shutil.rmtree(workspace.path, ignore_errors=True)

    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """Execute a command in the workspace."""
        # Determine working directory
        if cwd:
            work_dir = workspace.path / cwd.lstrip("/")
        else:
            work_dir = workspace.path / workspace.config.working_dir.lstrip("/")

        # Ensure working directory exists
        work_dir.mkdir(parents=True, exist_ok=True)

        # Build environment
        exec_env = os.environ.copy()
        exec_env.update(workspace.config.environment)
        exec_env.update(workspace.config.secrets)  # Inject secrets
        if env:
            exec_env.update(env)

        # Set workspace-specific variables
        exec_env["WORKSPACE_ID"] = workspace.id
        exec_env["WORKSPACE_PATH"] = str(workspace.path)

        start_time = time.time()
        timed_out = False

        try:
            # Use asyncio subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                env=exec_env,
            )

            # Wait with optional timeout
            effective_timeout = timeout or workspace.config.limits.timeout_seconds
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                timed_out = True
                stdout = b""
                stderr = f"Command timed out after {effective_timeout}s".encode()

            duration_ms = (time.time() - start_time) * 1000

            # Handle exit code - returncode is None until process completes
            exit_code = process.returncode
            if exit_code is None:
                exit_code = 124 if timed_out else 0

            return ExecuteResult(
                exit_code=exit_code,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
                timed_out=timed_out,
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
        """Write a file in the workspace."""
        file_path = workspace.path / path.lstrip("/")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)

    async def read_file(
        self,
        workspace: Workspace,
        path: str,
    ) -> str:
        """Read a file from the workspace."""
        file_path = workspace.path / path.lstrip("/")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def file_exists(
        self,
        workspace: Workspace,
        path: str,
    ) -> bool:
        """Check if a file exists in the workspace."""
        file_path = workspace.path / path.lstrip("/")
        return file_path.exists()

    async def stream(
        self,
        workspace: Workspace,
        command: list[str],
        *,
        timeout_seconds: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream stdout lines from command execution.

        Args:
            workspace: Workspace to execute in
            command: Command as list of strings
            timeout_seconds: Max execution time
            cwd: Working directory override
            env: Additional environment variables

        Yields:
            Individual stdout lines as they are produced
        """
        # Determine working directory
        if cwd:
            work_dir = workspace.path / cwd.lstrip("/")
        else:
            work_dir = workspace.path / workspace.config.working_dir.lstrip("/")

        work_dir.mkdir(parents=True, exist_ok=True)

        # Build environment
        exec_env = os.environ.copy()
        exec_env.update(workspace.config.environment)
        exec_env.update(workspace.config.secrets)
        if env:
            exec_env.update(env)
        exec_env["WORKSPACE_ID"] = workspace.id
        exec_env["WORKSPACE_PATH"] = str(workspace.path)

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
            env=exec_env,
        )

        start_time = time.perf_counter()

        try:
            while True:
                if proc.stdout is None:
                    break

                if timeout_seconds:
                    elapsed = time.perf_counter() - start_time
                    if elapsed > timeout_seconds:
                        logger.warning("Stream timeout after %.1fs", elapsed)
                        proc.kill()
                        break

                try:
                    line_bytes = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=1.0,
                    )
                except TimeoutError:
                    if proc.returncode is not None:
                        break
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
                if line:
                    yield line

        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except (TimeoutError, ProcessLookupError):
                    proc.kill()
