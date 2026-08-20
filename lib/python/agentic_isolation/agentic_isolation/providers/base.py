"""Base protocol and types for workspace providers."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from agentic_isolation.config import WorkspaceConfig

if TYPE_CHECKING:
    from agentic_isolation.harnesses import TranscriptSource

logger = logging.getLogger(__name__)


@dataclass
class ExecuteResult:
    """Result of executing a command in a workspace."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float = 0.0
    timed_out: bool = False

    @property
    def success(self) -> bool:
        """Whether the command succeeded (exit code 0)."""
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "success": self.success,
        }


@runtime_checkable
class AwaitResult(Protocol):
    """Structural read port for the result of waiting for an interactive
    agent pane to reach a ready/idle state.

    This is a *structural* Protocol, not a concrete dataclass. The
    interactive-tmux driver defines its own `AwaitResult` dataclass
    (`providers/workspaces/interactive-tmux/driver/interactive_tmux.py`)
    and that real object is what `interactive_session().await_completion()`
    actually returns. Declaring this as a Protocol (rather than a duplicate
    dataclass) means `isinstance(driver_result, AwaitResult)` is True at
    runtime, the two definitions can never drift, and `agentic_isolation`
    still never needs to import the driver (which is stdlib-only and lives
    outside this package).

    Exposes only the read surface consumers need:

      - ready=True                          -> adapter is_ready() held stable
      - timed_out=True, ready=False         -> deadline hit before idle
      - ready=False, reason="never_ready"   -> never reached even one ready frame
      - ready=False, reason="unstable"      -> ready frames seen but pane kept changing

    `pane` carries the last captured pane text so callers don't have to
    re-capture to inspect post-mortem; `success` mirrors `ready`.
    Serialization (`to_dict()`) lives on the concrete driver dataclass, not
    on this read port.
    """

    @property
    def ready(self) -> bool: ...

    @property
    def timed_out(self) -> bool: ...

    @property
    def reason(self) -> str: ...

    @property
    def duration_ms(self) -> float: ...

    @property
    def stable_polls_observed(self) -> int: ...

    @property
    def pane(self) -> str: ...

    @property
    def error(self) -> str | None: ...

    @property
    def success(self) -> bool: ...


@dataclass
class Workspace:
    """Represents an active isolated workspace."""

    id: str
    provider: str
    path: Path  # Path to workspace root
    config: WorkspaceConfig
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    # Provider-specific handle (e.g., container ID)
    _handle: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "provider": self.provider,
            "path": str(self.path),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@runtime_checkable
class WorkspaceProvider(Protocol):
    """Protocol for workspace providers.

    Implementations must provide methods to create, manage,
    and destroy isolated workspaces.
    """

    @property
    def name(self) -> str:
        """Provider name (e.g., 'local', 'docker', 'e2b')."""
        ...

    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create a new isolated workspace.

        Args:
            config: Workspace configuration

        Returns:
            Workspace instance

        Raises:
            WorkspaceError: If creation fails
        """
        ...

    async def destroy(self, workspace: Workspace) -> None:
        """Destroy a workspace and clean up resources.

        Args:
            workspace: Workspace to destroy
        """
        ...

    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """Execute a command in the workspace.

        Args:
            workspace: Target workspace
            command: Command to execute
            timeout: Optional timeout in seconds
            cwd: Working directory (relative to workspace root)
            env: Additional environment variables

        Returns:
            ExecuteResult with output and exit code
        """
        ...

    async def write_file(
        self,
        workspace: Workspace,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write a file in the workspace.

        Args:
            workspace: Target workspace
            path: Path relative to workspace root
            content: File content
        """
        ...

    async def read_file(
        self,
        workspace: Workspace,
        path: str,
    ) -> str:
        """Read a file from the workspace.

        Args:
            workspace: Target workspace
            path: Path relative to workspace root

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def file_exists(
        self,
        workspace: Workspace,
        path: str,
    ) -> bool:
        """Check if a file exists in the workspace.

        Args:
            workspace: Target workspace
            path: Path relative to workspace root

        Returns:
            True if file exists
        """
        ...


@runtime_checkable
class SupportsWorkspaceLogs(Protocol):
    """Optional capability: read back what a workspace wrote to its own output.

    Deliberately NOT part of `WorkspaceProvider`. Not every isolation backend
    has a log stream that outlives the process - a local provider runs in the
    caller's own stdio, and a future remote backend may expose logs only
    through its vendor API. Widening the base protocol would force every
    implementation to grow a method most of them can only raise from, so this
    is a separate protocol a caller tests for:

        if isinstance(provider, SupportsWorkspaceLogs):
            tail = await provider.logs(workspace, tail=200)

    The motivating consumer is session capture. A workspace's finalizer runs
    during shutdown and prints whether the transcript reached the store; that
    verdict exists only in the container's own output, so without a way to
    read it back the capture outcome is entirely unobservable.

    DIAGNOSTIC, NOT AUTHORITATIVE. In a typical workspace image the agent and
    the finalizer run as the same user, so anything the finalizer can print,
    the agent can also print. A caller must therefore treat a success line read
    from here as unverified: useful for surfacing "we saw no verdict at all",
    never sufficient to assert that a transcript was stored. An authoritative
    answer has to come from a channel the agent cannot write to, such as the
    host invoking the exporter itself and reading its exit status, or asking
    the store whether the session arrived.
    """

    async def logs(self, workspace: Workspace, *, tail: int = 200) -> str:
        """Return the workspace's combined stdout and stderr.

        Implementations MUST NOT raise when the workspace is already gone; a
        caller reading logs during teardown is the expected case, and a
        best-effort empty string is more useful there than an exception. The
        result is UNTRUSTED: it contains agent-controlled output.

        Args:
            workspace: Workspace to read from
            tail: Maximum number of trailing lines to return

        Returns:
            Combined output, or an empty string if it cannot be read
        """
        ...


@runtime_checkable
class SupportsStagedTeardown(Protocol):
    """Optional capability: run caller work at the safe points inside teardown.

    `destroy()` collapses stopping the container, removing it, and deleting the
    host workspace directory into one call. For a caller with nothing to do in
    between that is right, and it stays the default.

    Session capture has work to do in between, and the ordering is forced
    rather than preferred:

        while the container is still RUNNING
          -> the HOST invokes the exporter and reads its exit status
        stop, remove
        before the workspace directory is deleted
          -> archive the spool and confirm the archive is durable
        delete the workspace directory

    The exporter must run while the container is up, because there is nothing
    to exec into afterwards. The archive must precede deletion, because the
    workspace directory IS the spool. And it must be confirmed durable before
    deletion, or a failed upload silently becomes permanent loss.

    WHY HOOKS AND NOT THREE PUBLIC METHODS. An earlier draft exposed
    `stop_container`, `remove_container` and `delete_workspace_dir` for the
    caller to sequence itself. Each was individually idempotent, and the order
    was documented. But the motivating failure here IS permanent loss, and an
    API whose misuse costs data should not rely on the caller reading a
    docstring: calling `delete_workspace_dir` first would destroy the spool
    while the container was still writing to it, and nothing would have
    stopped it. The order is enforced here instead, so it cannot be got wrong.
    """

    async def teardown(
        self,
        workspace: Workspace,
        *,
        while_running: Callable[[], Awaitable[None]] | None = None,
        before_delete: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Tear the workspace down, running the hooks at their safe points.

        Args:
            workspace: Workspace to tear down
            while_running: Awaited BEFORE the container is stopped, so it may
                still exec into it. Raising aborts teardown with the container
                intact, which is recoverable; a caller that would rather
                proceed should catch its own errors.
            before_delete: Awaited after the container is gone but BEFORE the
                workspace directory is deleted. This is where a durable
                archive belongs. **If it raises, the workspace directory is
                NOT deleted**, so the data it failed to archive is still there
                for a retry. That retention is the point: deleting anyway
                would convert a failed upload into permanent loss.

        Implementations MUST NOT delete the workspace directory when
        `before_delete` raises, and MUST leave the container stopped and
        removed regardless, so a failure cannot strand a running container.
        """
        ...


@runtime_checkable
class InteractiveSession(Protocol):
    """Typed port for driving an interactive, prompt-based agent session
    (e.g. a tmux-driven claude/codex/gemini TUI running in a container).

    This is a structural protocol: any object exposing these three
    methods with compatible signatures satisfies it, including the
    driver's `InteractiveTmuxWorkspace` instance today (no wrapper class
    needed). It exists so consumers can type against a stable port
    instead of reaching into a provider-specific `Workspace._handle: Any`.
    """

    def send_message(self, agent: str, text: str) -> None:
        """Send a message/prompt to the named agent's pane."""
        ...

    def await_completion(
        self,
        agent: str,
        *,
        timeout: float = 60.0,
        stable_polls: int = 4,
        poll_interval: float = 0.5,
    ) -> AwaitResult:
        """Block until the named agent's pane reaches a stable ready state.

        Args:
            agent: Agent name (e.g. "claude", "codex", "gemini").
            timeout: Overall deadline in seconds.
            stable_polls: Number of consecutive "ready" polls required.
            poll_interval: Seconds between polls.

        Returns:
            AwaitResult describing whether/how readiness was reached.
        """
        ...

    def capture_response(self, agent: str) -> str:
        """Capture the current response text from the named agent's pane."""
        ...


class BaseProvider(ABC):
    """Abstract base class for workspace providers.

    Provides common functionality and enforces the protocol.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...

    @abstractmethod
    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create a workspace."""
        ...

    @abstractmethod
    async def destroy(self, workspace: Workspace) -> None:
        """Destroy a workspace."""
        ...

    @abstractmethod
    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        """Execute a command."""
        ...

    @abstractmethod
    async def write_file(
        self,
        workspace: Workspace,
        path: str,
        content: str | bytes,
    ) -> None:
        """Write a file."""
        ...

    @abstractmethod
    async def read_file(
        self,
        workspace: Workspace,
        path: str,
    ) -> str:
        """Read a file."""
        ...

    @abstractmethod
    async def file_exists(
        self,
        workspace: Workspace,
        path: str,
    ) -> bool:
        """Check if file exists."""
        ...

    def interactive_session(self, workspace: Workspace) -> InteractiveSession | None:
        """Return an `InteractiveSession` port for `workspace`, if supported.

        Default implementation returns `None`: most providers (docker,
        local) don't support interactive prompt round-trips. Providers
        that do (e.g. `InteractiveTmuxProvider`) should override this to
        return an object satisfying the `InteractiveSession` protocol.
        """
        return None

    def transcript_source(self, workspace: Workspace, agent: str) -> TranscriptSource | None:
        """Return a `TranscriptSource` for `agent` in `workspace`, if supported.

        Default returns None: a provider that cannot run commands inside the
        workspace cannot recover harness transcripts.
        """
        return None

    @staticmethod
    async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
        """Ensure a subprocess is terminated."""
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (TimeoutError, ProcessLookupError):
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (TimeoutError, ProcessLookupError):
                pass

    @staticmethod
    def _check_stream_timeout(
        proc: asyncio.subprocess.Process,
        timeout_seconds: int | None,
        start_time: float,
    ) -> bool:
        """Check if stream has exceeded timeout. Returns True if timed out."""
        if not timeout_seconds:
            return False
        elapsed = time.perf_counter() - start_time
        if elapsed > timeout_seconds:
            logger.warning("Stream timeout after %.1fs", elapsed)
            proc.kill()
            return True
        return False

    @staticmethod
    async def _read_stream_lines(
        proc: asyncio.subprocess.Process,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[str]:
        """Read lines from a subprocess stdout stream.

        Shared by docker and local providers. Yields decoded lines
        as they are produced, with periodic timeout checking.
        """
        start_time = time.perf_counter()

        try:
            while proc.stdout is not None:
                if BaseProvider._check_stream_timeout(proc, timeout_seconds, start_time):
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
            await BaseProvider._terminate_process(proc)
