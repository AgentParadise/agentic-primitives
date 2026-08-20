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
from agentic_isolation.harnesses import ExecFn, TranscriptSource, get_harness
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
        workspace_host_dir: Path | str | None = None,
    ):
        """Initialize Docker provider.

        Args:
            default_image: Default Docker image for workspaces
            default_network: Docker network for containers
            security: Security configuration (defaults to production)
            workspace_base_dir: Base directory for workspace files (this process)
            workspace_host_dir: Base directory for Docker volume mounts (host path).
                Required when running inside a container (Docker-in-Docker).
                If not set, uses workspace_base_dir for mounts.
        """
        self._default_image = default_image
        self._default_network = default_network
        self._security = security or SecurityConfig.production()
        self._workspace_base_dir = (
            Path(workspace_base_dir).resolve() if workspace_base_dir else None
        )
        # Host dir is used for Docker -v mounts and must refer to the Docker
        # *host* filesystem, not this process's filesystem.  When running inside
        # a container (DinD), resolve() would map to the container's CWD — wrong.
        self._workspace_host_dir = Path(workspace_host_dir) if workspace_host_dir else None
        self._workspaces: dict[str, Workspace] = {}
        # Container output captured during teardown, keyed by container name.
        # Insertion-ordered so eviction is oldest-first. See _remember_logs.
        self._log_snapshots: dict[str, str] = {}
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
        # Resolve plugin env vars before creating container
        if config.plugins:
            config.resolve_plugin_env()

        short_id = uuid.uuid4().hex[:8]
        workspace_id = f"ws-{short_id}"
        container_name = f"agentic-ws-{short_id}"

        # Create workspace directory for file I/O
        if self._workspace_base_dir:
            self._workspace_base_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir = self._workspace_base_dir / workspace_id
        else:
            workspace_dir = Path(tempfile.mkdtemp(prefix=f"agentic-ws-{short_id}-"))
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Determine host path for Docker volume mount
        # When running Docker-in-Docker, container path != host path
        if self._workspace_host_dir:
            host_mount_dir = self._workspace_host_dir / workspace_id
        else:
            host_mount_dir = workspace_dir

        # Ensure network exists
        await self._ensure_network(self._default_network)

        # Build docker run command
        image = config.image or self._default_image
        security = config.security or self._security

        cmd = self._build_run_command(
            container_name=container_name,
            workspace_id=workspace_id,
            workspace_dir=host_mount_dir,  # Use HOST path for volume mount
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

        # Network isolation (if limits.network is False)
        if hasattr(limits, "network") and limits.network is False:
            cmd.append("--network=none")

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
        cmd.extend(
            [
                f"--label=agentic.workspace.id={workspace_id}",
                f"--label=agentic.provider={self.name}",
            ]
        )
        for key, value in config.labels.items():
            # Validate label values to prevent command injection
            label_value = str(value)
            if "\n" in label_value or "\r" in label_value:
                raise ValueError(
                    f"Invalid Docker label value for key {key!r}: "
                    "label values must not contain newline characters"
                )
            cmd.append(f"--label={key}={label_value}")

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

    #: Cap on returned log bytes. `docker logs --tail` bounds LINES, and a
    #: single agent-controlled line can be arbitrarily long, so lines are not a
    #: resource bound. Keep the TAIL of the output: the finalizer verdict is
    #: printed last, during shutdown.
    _MAX_LOG_BYTES = 256 * 1024

    #: How many teardown snapshots to retain. Bounded so a long-lived provider
    #: cannot accumulate log text for every container it has ever destroyed.
    _MAX_LOG_SNAPSHOTS = 64

    async def logs(self, workspace: Workspace, *, tail: int = 200) -> str:
        """Return the container's combined stdout and stderr (best effort).

        Implements `SupportsWorkspaceLogs`. Does not raise for any operational
        failure to retrieve logs: it is called during teardown, where the
        container may already be gone, and a caller reading a capture verdict
        must not be able to fail the teardown that produced it. Every such path
        yields "". `asyncio.CancelledError` DOES propagate, because swallowing
        cancellation would make shutdown hang.

        If the container was destroyed through this provider, the snapshot
        taken between `docker stop` and `docker rm` is returned instead of
        querying a container that no longer exists. Without that, the finalizer
        verdict would be unreachable by construction: it is printed during stop
        and the container is removed immediately afterwards.

        The returned text is UNTRUSTED - it is whatever the agent and its
        tooling printed - so callers must parse defensively and must not print
        it to a terminal unsanitised.
        """
        container_name = getattr(workspace, "_handle", None)
        if not container_name:
            return ""

        snapshot = self._log_snapshots.get(container_name)
        if snapshot is not None:
            return snapshot

        return await self._read_container_logs(container_name, tail=tail)

    async def _read_container_logs(self, container_name: str, *, tail: int) -> str:
        """`docker logs` with every operational failure collapsed to "".

        Split out so teardown can reuse it while the container still exists.
        """
        # A negative or absurd tail asks docker for the entire history, which
        # defeats the byte cap's purpose of bounding work as well as memory.
        safe_tail = max(1, min(int(tail), 10_000))

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "logs",
                "--tail",
                str(safe_tail),
                container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.CancelledError:
            # Shutdown must not be blocked by a best-effort log read.
            if proc is not None:
                await self._terminate(proc)
            raise
        except (TimeoutError, OSError, ValueError) as exc:
            logger.debug("docker logs failed for %s: %s", container_name, exc)
            if proc is not None:
                await self._terminate(proc)
            return ""
        except Exception as exc:  # noqa: BLE001 - contract is "never fail teardown"
            logger.debug("docker logs raised unexpectedly for %s: %s", container_name, exc)
            if proc is not None:
                await self._terminate(proc)
            return ""

        if proc.returncode != 0:
            # Expected once the container has been removed. Debug, not warning:
            # a teardown race here is normal and not actionable.
            logger.debug("docker logs exited %s for %s", proc.returncode, container_name)
            return ""

        return (out or b"")[-self._MAX_LOG_BYTES :].decode(errors="replace")

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        """Kill a subprocess without letting cleanup raise or hang."""
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            return  # already exited
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (TimeoutError, OSError):
            logger.debug("gave up waiting for a killed docker subprocess")

    def _remember_logs(self, container_name: str, text: str) -> None:
        """Retain a teardown snapshot, evicting oldest first."""
        if not text:
            return
        self._log_snapshots[container_name] = text
        while len(self._log_snapshots) > self._MAX_LOG_SNAPSHOTS:
            self._log_snapshots.pop(next(iter(self._log_snapshots)))

    def _build_docker_exec_cmd(
        self,
        container_name: str,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        interactive: bool = False,
    ) -> list[str]:
        """Build a docker exec command with optional cwd and env."""
        exec_cmd = ["docker", "exec"]
        if interactive:
            exec_cmd.append("-i")

        exec_cmd.extend(["-w", cwd or "/workspace"])

        if env:
            for key, value in env.items():
                exec_cmd.extend(["-e", f"{key}={value}"])

        exec_cmd.append(container_name)
        exec_cmd.extend(command)
        return exec_cmd

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

        exec_cmd = self._build_docker_exec_cmd(
            container_name,
            ["sh", "-c", command],
            cwd=cwd,
            env=env,
        )
        return await self._run_exec(exec_cmd, timeout=timeout or 3600)

    async def _run_exec(
        self,
        exec_cmd: list[str],
        *,
        timeout: float,
    ) -> ExecuteResult:
        """Run a docker exec command and return the result."""
        start_time = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                duration_ms = (time.perf_counter() - start_time) * 1000
                return ExecuteResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Command timed out",
                    duration_ms=duration_ms,
                    timed_out=True,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecuteResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
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

        ARCHITECTURE NOTE — stderr=STDOUT is intentional (ADR-043):
        -----------------------------------------------------------------
        Git observability hooks (post-commit, pre-push, etc.) emit JSONL event
        lines to STDERR. Using stderr=STDOUT merges them into stdout so callers
        receive both Claude's stream-json output AND git hook JSONL on one pipe.
        parse_jsonl_line() distinguishes them: hook events have "event_type",
        Claude stream-json has "type".

        NOTE: This class (WorkspaceDockerProvider) is used in agentic_isolation
        contexts. The dashboard's primary docker exec path is in:
          syn_adapters/workspace_backends/agentic/adapter.py → AgenticEventStreamAdapter.stream()
        Both must keep stderr=STDOUT. Do not revert to PIPE or DEVNULL.
        """
        container_name = workspace._handle
        if not container_name:
            raise RuntimeError("Container not available")

        exec_cmd = self._build_docker_exec_cmd(
            container_name,
            command,
            cwd=cwd,
            env=env,
            interactive=True,
        )

        logger.debug("Starting stream (container=%s, cmd=%s)", container_name, command)

        # stderr=STDOUT: merge stderr so git hook JSONL events reach the engine.
        # See docstring above for rationale. Do NOT change to PIPE or DEVNULL.
        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async for line in self._read_stream_lines(proc, timeout_seconds):
            yield line

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

    def transcript_source(self, workspace: Workspace, agent: str) -> TranscriptSource | None:
        """Return a `TranscriptSource` for `agent` in `workspace`.

        `None` if `agent` names a harness this build does not know (see
        `AgentName.parse` - lenient by design, never raises). The bound
        `exec_fn` below satisfies the `ExecFn` protocol by calling this
        provider's own `execute()` against `workspace`, exactly like any
        other consumer of `WorkspaceProvider.execute`.
        """
        plugin = get_harness(agent)
        if plugin is None:
            return None

        async def exec_fn(
            command: str,
            *,
            timeout: float | None = None,
            cwd: str | None = None,
            env: dict[str, str] | None = None,
        ) -> ExecuteResult:
            return await self.execute(workspace, command, timeout=timeout, cwd=cwd, env=env)

        exec_fn_typed: ExecFn = exec_fn
        return plugin.transcript_source(exec_fn_typed)

    async def _ensure_network(self, network_name: str) -> None:
        """Ensure Docker network exists."""
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "network",
            "inspect",
            network_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode != 0:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "network",
                "create",
                network_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

    async def _wait_for_running(self, container_name: str, timeout: float = 30.0) -> None:
        """Wait for container to be in running state."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                container_name,
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
        # This "-t 5" grace is coupled to __TERM_GRACE_TICKS in
        # workspace/entrypoint.sh's section 6
        # wrapper (ADR-040): that constant must stay strictly below this
        # value, with headroom left over for the post-agent finalize hooks
        # (e.g. a session-store upload) to actually run before docker's own
        # SIGKILL lands. Changing this value without adjusting that one can
        # silently make finalize stop running on every SIGTERM shutdown.
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            "-t",
            "5",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        # Between stop and rm is the ONLY window in which the finalizer's
        # output can still be read: `docker stop` is what triggers finalizers,
        # and `docker rm` destroys the log stream they wrote to. A caller
        # asking for logs after destroy() would otherwise always get nothing,
        # which would make the session-capture verdict unreachable rather than
        # merely unread.
        self._remember_logs(
            container_name, await self._read_container_logs(container_name, tail=200)
        )

        # Remove
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
