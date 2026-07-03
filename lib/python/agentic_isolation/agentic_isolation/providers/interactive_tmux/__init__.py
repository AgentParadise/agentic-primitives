"""WorkspaceProvider adapter for the `interactive-tmux` provider.

Addresses EXP-05 codex cross-review Major 2: the interactive-tmux driver
exposes `start_workspace / send_message / await_completion / capture_response
/ stop` but `agentic_isolation.WorkspaceProvider` expects `create / destroy
/ execute / write_file / read_file / file_exists`. Without an adapter,
Syntropic137 cannot drop this provider into the existing isolation layer.

This adapter bridges them:

  * `create()`  → `InteractiveTmuxWorkspace.start_workspace(...)`
                  (the running container exposes claude/codex/gemini panes
                  via `interactive_session()` for orchestration code that
                  wants direct access).
  * `destroy()` → `InteractiveTmuxWorkspace.stop()`
  * `execute()`, `read_file()`, `write_file()`, `file_exists()`
                → `docker exec` into the running container. These do NOT
                  funnel through the agent panes; they hit the container's
                  shell directly. Same shape as `WorkspaceDockerProvider`
                  uses, returning a proper `ExecuteResult` so call sites
                  that already speak the protocol need no translation.

The richer prompt round-trip API (send/await/capture) is exposed as a
typed `agentic_isolation.providers.base.InteractiveSession` port via
`provider.interactive_session(workspace)` (structurally satisfied by the
underlying `InteractiveTmuxWorkspace` handle -- no wrapper class needed).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import shutil
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    BaseProvider,
    ExecuteResult,
    InteractiveSession,
    Workspace,
)

logger = logging.getLogger(__name__)


def _load_driver_module() -> Any:
    """Locate `interactive_tmux.py` and import it as a module.

    The driver is a single-file Python module living at
    `providers/workspaces/interactive-tmux/driver/interactive_tmux.py`. It
    isn't on PyPI yet (m1 from the EXP-06 docs validation tracks that). We
    look for it in:
      1. an already-imported `interactive_tmux` (caller pre-staged sys.path)
      2. `$AGENTIC_INTERACTIVE_TMUX_DRIVER` (override for tests / vendored)
      3. the repo-relative path, walking up from this file
    """
    if "interactive_tmux" in sys.modules:
        return sys.modules["interactive_tmux"]

    override = os.environ.get("AGENTIC_INTERACTIVE_TMUX_DRIVER")
    if override:
        path = Path(override)
        if not path.is_file():
            raise ImportError(
                f"$AGENTIC_INTERACTIVE_TMUX_DRIVER points at {path}, which is not a file."
            )
    else:
        # this file: …/agentic_isolation/providers/interactive_tmux/__init__.py
        # driver:    …/providers/workspaces/interactive-tmux/driver/interactive_tmux.py
        here = Path(__file__).resolve()
        for ancestor in here.parents:
            candidate = (
                ancestor
                / "providers"
                / "workspaces"
                / "interactive-tmux"
                / "driver"
                / "interactive_tmux.py"
            )
            if candidate.is_file():
                path = candidate
                break
        else:
            raise ImportError(
                "Could not locate interactive_tmux.py driver. Set "
                "$AGENTIC_INTERACTIVE_TMUX_DRIVER to the absolute path or "
                "ensure the providers/workspaces/interactive-tmux/driver/ "
                "directory is reachable from this module's path."
            )

    spec = importlib.util.spec_from_file_location("interactive_tmux", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not spec interactive_tmux driver at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["interactive_tmux"] = module
    spec.loader.exec_module(module)
    return module


_driver: Any = None


def _get_driver() -> Any:
    """Load the driver on first use (NOT at import time).

    The driver is not packaged inside the agentic-isolation wheel, so this
    module must import cleanly without it; only constructing/using the
    provider requires the driver to be reachable.
    """
    global _driver
    if _driver is None:
        _driver = _load_driver_module()
    return _driver


# Names re-exported from the driver, resolved lazily so that importing
# this module never fails when the driver is absent.
_DRIVER_EXPORTS = ("InteractiveTmuxWorkspace", "AwaitResult", "StartupReadinessError")

if TYPE_CHECKING:
    InteractiveTmuxWorkspace = Any
    AwaitResult = Any
    StartupReadinessError = Any


def __getattr__(name: str) -> Any:
    if name in _DRIVER_EXPORTS:
        return getattr(_get_driver(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Container path under which write_file/read_file are rooted. Mirrors the
# provider's default tmux workdir (set in InteractiveTmuxWorkspace).
DEFAULT_CONTAINER_WORKDIR = "/workspace"


def _unsupported_config_fields(config: WorkspaceConfig) -> list[str]:
    """Return WorkspaceConfig fields set to non-default values that this
    provider cannot honor (it would otherwise silently ignore them)."""
    defaults = WorkspaceConfig()
    unsupported: list[str] = []
    if config.image != defaults.image:
        unsupported.append("image")
    if config.dockerfile is not None:
        unsupported.append("dockerfile")
    if config.mounts:
        unsupported.append("mounts")
    if config.secrets:
        unsupported.append("secrets")
    if config.environment:
        unsupported.append("environment")
    if config.security != defaults.security:
        unsupported.append("security")
    if config.limits != defaults.limits:
        unsupported.append("limits")
    if config.plugins:
        unsupported.append("plugins")
    return unsupported


class InteractiveTmuxProvider(BaseProvider):
    """WorkspaceProvider adapter for the interactive-tmux Docker provider.

    Construction:
        provider = InteractiveTmuxProvider(
            default_host_auth={
                "claude": Path("~/.claude").expanduser(),
                "codex":  Path("~/.codex").expanduser(),
                "gemini": Path("~/.gemini").expanduser(),
            },
        )

    Usage matches every other WorkspaceProvider:
        workspace = await provider.create(WorkspaceConfig(...))
        result = await provider.execute(workspace, "echo hi")
        await provider.destroy(workspace)

    To reach the underlying claude/codex/gemini panes for prompt
    round-trips, get the typed `InteractiveSession` port:
        session = provider.interactive_session(workspace)
        session.send_message("claude", "hello")
        result = session.await_completion("claude")
        print(session.capture_response("claude"))
    """

    def __init__(
        self,
        *,
        default_host_auth: dict[str, Path | None] | None = None,
        default_image: str | None = None,
        default_enabled_agents: tuple[str, ...] = ("claude", "codex", "gemini"),
        startup_timeout_s: float = 45.0,
        strict_startup: bool = True,
        default_host_claude_dotjson: Path | None = None,
        default_claude_plugin_dirs: list[Path] | None = None,
    ) -> None:
        # `default_host_auth` resolution mirrors the driver CLI:
        # `ITMUX_{AGENT}_HOME` env vars > `$HOME/.{agent}` > None.
        # `default_host_claude_dotjson` mirrors `ITMUX_CLAUDE_JSON`. Both
        # exist so the adapter works inside another container (DooD), where
        # `$HOME` does not point at the operator's real credentials —
        # surfaced by the Syntropic137 integration e2e on PR #202.
        # `default_claude_plugin_dirs` mirrors `ITMUX_CLAUDE_PLUGIN_DIRS`
        # (colon-separated), the only mechanism that actually loads
        # plugins into the tmux-driven `claude` TUI (settings.json
        # injection is silently ignored — Syntropic137 workflow-skills
        # bridge).
        driver = _get_driver()
        if default_host_auth is None:
            default_host_auth = driver._default_host_auth_from_env()
        if default_host_claude_dotjson is None:
            default_host_claude_dotjson = driver._default_claude_dotjson_from_env()
        if default_claude_plugin_dirs is None:
            default_claude_plugin_dirs = driver._default_claude_plugin_dirs_from_env()
        self._default_host_auth = default_host_auth
        self._default_host_claude_dotjson = default_host_claude_dotjson
        self._default_claude_plugin_dirs = default_claude_plugin_dirs
        self._default_image = default_image
        self._default_enabled_agents = tuple(default_enabled_agents)
        self._startup_timeout_s = startup_timeout_s
        self._strict_startup = strict_startup
        self._workspaces: dict[str, Workspace] = {}
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "interactive-tmux"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("docker") is not None

    async def create(self, config: WorkspaceConfig) -> Workspace:
        """Create an interactive-tmux workspace honoring `config`.

        Honored `WorkspaceConfig` fields:
          * `config.working_dir`: sets the container workdir.
          * `config.labels["agents"]` (comma-sep): limits which agent panes
            get launched. Other labels are accepted (informational).
          * `config.auto_cleanup` / `config.keep_on_error`: handled by
            `AgenticWorkspace`, not this provider.

        Unsupported fields (`image`, `mounts`, `secrets`, `environment`,
        `security`, `limits`, `plugins`, `dockerfile`) are rejected loudly
        when set to non-default values: the interactive-tmux driver does
        its own bind-mount layout for credentials and runs a fixed
        `sleep infinity` entrypoint, so silently dropping them would break
        expectations set by the other WorkspaceProvider implementations.
        Override the image via the `default_image=` constructor kwarg
        (it must bundle tmux + the agent CLIs); pass plugin dirs via
        `default_claude_plugin_dirs=`. Plumbing the rest through is future
        work tracked alongside the streaming roadmap.

        Raises:
            ValueError: if `config` sets unsupported fields to non-default
                values (see `_unsupported_config_fields`).
        """
        unsupported = _unsupported_config_fields(config)
        if unsupported:
            raise ValueError(
                "InteractiveTmuxProvider does not support these WorkspaceConfig "
                f"fields (set to non-default values): {', '.join(unsupported)}. "
                "Honored fields: working_dir, labels['agents'], auto_cleanup, "
                "keep_on_error. Use the provider constructor kwargs "
                "(default_image=, default_claude_plugin_dirs=, ...) for "
                "image/plugin customization."
            )

        agents_label = config.labels.get("agents") if config.labels else None
        if agents_label:
            wanted = {a.strip() for a in agents_label.split(",")}
            host_auth = {
                a: self._default_host_auth.get(a) if a in wanted else None
                for a in self._default_enabled_agents
            }
        else:
            host_auth = {a: self._default_host_auth.get(a) for a in self._default_enabled_agents}

        driver = _get_driver()
        image = self._default_image or driver.DEFAULT_IMAGE
        workdir = config.working_dir or DEFAULT_CONTAINER_WORKDIR
        name = f"itws-{uuid.uuid4().hex[:8]}"

        # The driver is blocking (subprocess + sleep loops). Calling it
        # synchronously briefly blocks the event loop, but that's the
        # right tradeoff: when an executor thread shells out via
        # `subprocess.run` it races asyncio's child watcher and the docker
        # run/exec calls become flaky (we saw 127 from docker exec right
        # after a successful docker run -d). Holding the loop for the
        # ~5s container-start window is acceptable; if a future caller
        # needs concurrency, they can wrap `await provider.create(...)`
        # in their own thread.
        ws_handle: InteractiveTmuxWorkspace = driver.InteractiveTmuxWorkspace.start_workspace(
            name=name,
            host_auth=host_auth,
            image=image,
            workdir=workdir,
            startup_timeout_s=self._startup_timeout_s,
            strict_startup=self._strict_startup,
            host_claude_dotjson=self._default_host_claude_dotjson,
            claude_plugin_dirs=self._default_claude_plugin_dirs,
        )

        # The container is now running with throwaway claude/codex/gemini
        # credentials mounted. Any failure between here and a successful
        # return must stop it, or we leak a running container with staged
        # auth material until manual cleanup. Wrap all post-start setup.
        try:
            # Ensure the container workdir exists so write_file/read_file have
            # a rooted directory. The Dockerfile already creates /workspace,
            # but a custom config.working_dir might not exist yet.
            await self._docker_exec(ws_handle.container, "mkdir", "-p", workdir, timeout=10)

            workspace = Workspace(
                id=name,
                provider=self.name,
                path=Path(workdir),  # container-side path
                config=config,
                created_at=datetime.now(UTC),
                metadata={
                    "container": ws_handle.container,
                    "workdir": workdir,
                    "enabled_agents": list(ws_handle.enabled_agents),
                    "startup_status": {a: r.to_dict() for a, r in ws_handle.startup_status.items()},
                },
                _handle=ws_handle,
            )
            async with self._lock:
                self._workspaces[name] = workspace
            return workspace
        except BaseException:
            # Best-effort teardown, then re-raise. BaseException so a
            # cancellation mid-setup also cleans up the credential-mounted
            # container. stop() is synchronous and fast (<2s).
            try:
                ws_handle.stop()
            except Exception:
                logger.warning(
                    "failed to stop workspace %s during create() cleanup",
                    name,
                    exc_info=True,
                )
            raise

    async def destroy(self, workspace: Workspace) -> None:
        ws_handle: InteractiveTmuxWorkspace | None = workspace._handle
        async with self._lock:
            self._workspaces.pop(workspace.id, None)
        if ws_handle is None:
            return
        # Sync for the same reason as create(): the driver shells out
        # via subprocess.run and the asyncio child-watcher race causes
        # `docker rm -f` to return spurious non-zero exit codes from
        # an executor thread. Stop is fast (<2s).
        ws_handle.stop()

    def interactive_session(self, workspace: Workspace) -> InteractiveSession | None:
        """Return the `InteractiveSession` port for `workspace`.

        The underlying driver's `InteractiveTmuxWorkspace` handle already
        exposes `send_message`/`await_completion`/`capture_response` with
        signatures compatible with `InteractiveSession`; structural typing
        means it satisfies the protocol as-is, so no wrapper is needed.
        Returns `None` if the workspace has no live handle (e.g. already
        destroyed).
        """
        return workspace._handle

    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        ws_handle: InteractiveTmuxWorkspace | None = workspace._handle
        if ws_handle is None:
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr="container not available",
                duration_ms=0.0,
            )
        workdir = cwd or workspace.metadata.get("workdir") or DEFAULT_CONTAINER_WORKDIR
        exec_cmd = ["docker", "exec", "-w", workdir]
        if env:
            for k, v in env.items():
                exec_cmd.extend(["-e", f"{k}={v}"])
        exec_cmd.extend([ws_handle.container, "sh", "-c", command])
        return await self._run_exec(exec_cmd, timeout=timeout or 3600.0)

    async def write_file(
        self,
        workspace: Workspace,
        path: str,
        content: str | bytes,
    ) -> None:
        ws_handle: InteractiveTmuxWorkspace | None = workspace._handle
        if ws_handle is None:
            raise RuntimeError("container not available")
        workdir = workspace.metadata.get("workdir") or DEFAULT_CONTAINER_WORKDIR
        target = path if path.startswith("/") else f"{workdir.rstrip('/')}/{path}"
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        # Ensure parent dir exists, then pipe bytes into `tee` so we don't
        # have to escape arbitrary content for `sh -c`.
        parent = target.rsplit("/", 1)[0] or "/"
        await self._docker_exec(
            ws_handle.container,
            "mkdir",
            "-p",
            parent,
            timeout=10,
        )
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "-i",
            ws_handle.container,
            "tee",
            target,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(content_bytes)
        if proc.returncode != 0:
            raise RuntimeError(f"write_file({path!r}) failed: {stderr.decode('utf-8', 'replace')}")

    async def read_file(self, workspace: Workspace, path: str) -> str:
        ws_handle: InteractiveTmuxWorkspace | None = workspace._handle
        if ws_handle is None:
            raise RuntimeError("container not available")
        workdir = workspace.metadata.get("workdir") or DEFAULT_CONTAINER_WORKDIR
        target = path if path.startswith("/") else f"{workdir.rstrip('/')}/{path}"
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            ws_handle.container,
            "cat",
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", "replace")
            if "No such file" in stderr_text or "not found" in stderr_text.lower():
                raise FileNotFoundError(target)
            raise RuntimeError(f"read_file({path!r}) failed: {stderr_text}")
        return stdout.decode("utf-8", "replace")

    async def file_exists(self, workspace: Workspace, path: str) -> bool:
        ws_handle: InteractiveTmuxWorkspace | None = workspace._handle
        if ws_handle is None:
            return False
        workdir = workspace.metadata.get("workdir") or DEFAULT_CONTAINER_WORKDIR
        target = path if path.startswith("/") else f"{workdir.rstrip('/')}/{path}"
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            ws_handle.container,
            "test",
            "-e",
            target,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    # ------------------------------------------------------------------
    # Helpers

    async def _docker_exec(
        self,
        container: str,
        *args: str,
        timeout: float = 30.0,
    ) -> ExecuteResult:
        return await self._run_exec(
            ["docker", "exec", container, *args],
            timeout=timeout,
        )

    @staticmethod
    async def _run_exec(exec_cmd: list[str], *, timeout: float) -> ExecuteResult:
        start = time.perf_counter()
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
                duration_ms = (time.perf_counter() - start) * 1000
                return ExecuteResult(
                    exit_code=-1,
                    stdout="",
                    stderr="command timed out",
                    duration_ms=duration_ms,
                    timed_out=True,
                )
            duration_ms = (time.perf_counter() - start) * 1000
            return ExecuteResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", "replace") if stdout else "",
                stderr=stderr.decode("utf-8", "replace") if stderr else "",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return ExecuteResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=duration_ms,
            )


__all__ = [
    "InteractiveTmuxProvider",
    "InteractiveTmuxWorkspace",
    "AwaitResult",
    "StartupReadinessError",
]
