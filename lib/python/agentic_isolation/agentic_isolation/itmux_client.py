"""Typed Python client for the `itmux` Rust subprocess.

`itmux` (`providers/workspaces/interactive-tmux/driver-rs`) is the Rust
port of the interactive-tmux workspace driver. It exposes six subcommands
(`start`, `send`, `await`, `capture`, `exec`, `stop`) and emits JSON on
stdout. This module shells out to the compiled binary and parses its
stdout into typed Pydantic models, so callers never touch raw dicts.

The subprocess runner is injectable (`ItmuxRunner`) so tests can exercise
argv construction and JSON parsing without a real `itmux` binary or
Docker daemon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

DEFAULT_TIMEOUT_S = 120.0

# `itmux` argv[0] name; used for PATH lookup fallback.
_ITMUX_BIN_NAME = "itmux"

# Relative path (from the agentic-primitives repo root) to the compiled
# Rust binary, mirroring the crate layout under
# `providers/workspaces/interactive-tmux/driver-rs`.
_REPO_RELATIVE_BIN = Path("providers/workspaces/interactive-tmux/driver-rs/target/release/itmux")


class AgentStartupStatus(BaseModel):
    """Per-agent readiness outcome embedded in `StartReport.startup_status`.

    Field shape matches the real `itmux start` output (and the Rust
    `AwaitResult` struct in `driver-rs/src/result.rs`), keyed by agent
    name in `StartReport.startup_status`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    duration_ms: float
    error: str | None
    pane: str
    ready: bool
    reason: str
    stable_polls_observed: int
    timed_out: bool


class StartReport(BaseModel):
    """Parsed stdout of `itmux start`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    container: str
    agents: list[str]
    startup_status: dict[str, AgentStartupStatus]


class AwaitResult(BaseModel):
    """Parsed stdout of `itmux await`.

    Mirrors the Rust `AwaitResult` struct (`driver-rs/src/result.rs`).
    `pane` and `error` default so this model still validates against the
    `itmux await` CLI output, which strips `pane` from the printed JSON
    (see `handle_await` in `driver-rs/src/main.rs`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    timed_out: bool
    reason: str
    duration_ms: float
    stable_polls_observed: int
    pane: str = ""
    error: str | None = None


class ExecResult(BaseModel):
    """Result of `itmux exec` - not itmux JSON, assembled from raw output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    stdout: str
    stderr: str


class ItmuxBinaryNotFound(Exception):
    """Raised when no `itmux` binary can be resolved."""

    def __init__(self, searched: Sequence[str]) -> None:
        self.searched = list(searched)
        super().__init__("itmux binary not found. Searched (in order): " + ", ".join(self.searched))


class ItmuxError(Exception):
    """Raised when an `itmux` subprocess exits with a non-zero status
    that the caller does not treat as a domain result (e.g. `start`,
    `send`, `capture`, `stop` failures, or `await` exit code 1).

    `stdout` is preserved because `itmux` prints structured JSON on
    stdout even on some non-zero exits (notably `start` exit 3, which
    still emits a full `StartReport` describing which agent failed
    readiness). Losing it would discard the actionable diagnostics.
    """

    def __init__(
        self, command: Sequence[str], returncode: int, stderr: str, stdout: str = ""
    ) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(
            f"itmux command failed (exit {returncode}): {' '.join(self.command)}\n{stderr}"
        )


class ItmuxStartupError(ItmuxError):
    """Raised by `ItmuxClient.start` when `itmux` exits 3 (agent startup
    readiness failure) but still printed a parseable `StartReport` on
    stdout. Carries the parsed `report` so callers can inspect
    `report.startup_status` to see which agent failed and why, instead
    of only seeing stderr.
    """

    def __init__(
        self,
        command: Sequence[str],
        returncode: int,
        stderr: str,
        stdout: str,
        report: StartReport,
    ) -> None:
        super().__init__(command, returncode, stderr, stdout)
        self.report = report


def resolve_itmux_bin(*, repo_root: Path | None = None) -> str:
    """Resolve the `itmux` binary path.

    Resolution order:
    1. `$AGENTIC_ITMUX_BIN` environment variable (if set, used verbatim).
    2. The compiled binary at
       `providers/workspaces/interactive-tmux/driver-rs/target/release/itmux`
       relative to `repo_root` (defaults to this file's repo root:
       `lib/python/agentic_isolation/agentic_isolation/itmux_client.py`
       -> repo root is four parents up).
    3. `itmux` found on `$PATH`.

    Raises `ItmuxBinaryNotFound` if none resolve.
    """
    searched: list[str] = []

    env_bin = os.environ.get("AGENTIC_ITMUX_BIN")
    if env_bin:
        searched.append(f"$AGENTIC_ITMUX_BIN={env_bin}")
        if Path(env_bin).is_file():
            return env_bin

    if repo_root is None:
        # itmux_client.py -> agentic_isolation -> agentic_isolation ->
        # python -> lib -> <repo root>
        repo_root = Path(__file__).resolve().parents[4]
    repo_bin = repo_root / _REPO_RELATIVE_BIN
    searched.append(str(repo_bin))
    if repo_bin.is_file():
        return str(repo_bin)

    path_bin = shutil.which(_ITMUX_BIN_NAME)
    searched.append(f"$PATH lookup for {_ITMUX_BIN_NAME!r}")
    if path_bin:
        return path_bin

    raise ItmuxBinaryNotFound(searched)


class ItmuxRunner(Protocol):
    """Injectable subprocess runner shape.

    Called as `runner(argv, stdin=..., timeout_s=..., env=...)` ->
    `(returncode, stdout, stderr)`. `env` carries extra environment
    variables for the subprocess (merged over `os.environ` by the real
    runner); `None` means "inherit the parent environment unchanged".
    Tests supply a fake implementation that records calls instead of
    shelling out.
    """

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None,
        timeout_s: float,
        env: dict[str, str] | None,
    ) -> tuple[int, str, str]: ...


def _run_subprocess(
    argv: Sequence[str],
    *,
    stdin: str | None,
    timeout_s: float,
    env: dict[str, str] | None,
) -> tuple[int, str, str]:
    """Real subprocess runner used by `ItmuxClient` by default.

    `env` (if given) is merged over the inherited process environment,
    so callers only specify the variables they want to add or override.
    """
    subprocess_env: dict[str, str] | None = None
    if env is not None:
        subprocess_env = {**os.environ, **env}
    completed = subprocess.run(  # noqa: S603
        list(argv),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
        env=subprocess_env,
    )
    return completed.returncode, completed.stdout, completed.stderr


class ItmuxClient:
    """Typed subprocess client for the `itmux` binary."""

    def __init__(
        self,
        *,
        itmux_bin: str | None = None,
        runner: ItmuxRunner | None = None,
        default_timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._itmux_bin = itmux_bin if itmux_bin is not None else resolve_itmux_bin()
        self._run: ItmuxRunner = runner if runner is not None else _run_subprocess
        self._default_timeout_s = default_timeout_s

    def _invoke(
        self,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        argv = [self._itmux_bin, *args]
        returncode, stdout, stderr = self._run(
            argv,
            stdin=None,
            timeout_s=timeout_s if timeout_s is not None else self._default_timeout_s,
            env=env,
        )
        if returncode != 0:
            raise ItmuxError(argv, returncode, stderr, stdout)
        return stdout

    def start(
        self,
        name: str,
        *,
        image: str,
        workdir: str,
        agents: list[str],
        startup_timeout_s: float,
        strict_startup: bool,
        claude_plugin_dirs: list[str] | None = None,
    ) -> StartReport:
        args = [
            "start",
            "--name",
            name,
            "--image",
            image,
            "--workdir",
            workdir,
            "--agents",
            ",".join(agents),
            "--startup-timeout",
            str(startup_timeout_s),
        ]
        if strict_startup:
            args.append("--strict-startup")
        # `itmux` has no CLI flag for plugin dirs: it reads the
        # colon-separated `ITMUX_CLAUDE_PLUGIN_DIRS` env var (like $PATH)
        # and translates each entry to a `claude --plugin-dir <path>`
        # launch flag. This is the only mechanism that actually loads
        # Claude Code plugins (settings.json injection is ignored by the
        # TUI), so skill injection depends on setting it here.
        env: dict[str, str] | None = None
        if claude_plugin_dirs:
            env = {"ITMUX_CLAUDE_PLUGIN_DIRS": ":".join(claude_plugin_dirs)}
        try:
            stdout = self._invoke(
                args, timeout_s=startup_timeout_s + self._default_timeout_s, env=env
            )
        except ItmuxError as exc:
            # `itmux start` exits 3 when the container came up but an
            # agent failed startup readiness - the common failure. It
            # still prints a full `StartReport` (with per-agent
            # `startup_status`) on stdout before exiting. Surface that as
            # a typed `ItmuxStartupError` carrying the parsed report so
            # callers can see which agent failed and why, instead of
            # discarding the diagnostics behind a bare stderr string.
            if exc.returncode == 3 and exc.stdout:
                try:
                    report = StartReport.model_validate_json(exc.stdout)
                except ValidationError:
                    raise exc from None
                raise ItmuxStartupError(
                    exc.command, exc.returncode, exc.stderr, exc.stdout, report
                ) from exc
            raise
        return StartReport.model_validate_json(stdout)

    def send(self, name: str, agent: str, text: str) -> None:
        self._invoke(["send", "--name", name, "--agent", agent, "--text", text])
        return None

    def await_ready(
        self,
        name: str,
        agent: str,
        *,
        timeout_s: float,
        stable_polls: int | None = None,
        poll_interval_s: float | None = None,
        warmup_s: float | None = None,
    ) -> AwaitResult:
        args = [
            "await",
            "--name",
            name,
            "--agent",
            agent,
            "--timeout",
            str(timeout_s),
        ]
        if stable_polls is not None:
            args.extend(["--stable-polls", str(stable_polls)])
        if poll_interval_s is not None:
            args.extend(["--poll-interval", str(poll_interval_s)])
        if warmup_s is not None:
            args.extend(["--warmup", str(warmup_s)])

        argv = [self._itmux_bin, *args]
        returncode, stdout, stderr = self._run(
            argv, stdin=None, timeout_s=timeout_s + self._default_timeout_s, env=None
        )
        # `itmux await` uses exit code 0 (ready) or 2 (not ready, not an
        # error) for a valid AwaitResult; any other non-zero code is a
        # real failure (e.g. unregistered workspace).
        if returncode not in (0, 2):
            raise ItmuxError(argv, returncode, stderr, stdout)
        return AwaitResult.model_validate_json(stdout)

    def capture(self, name: str, agent: str) -> str:
        return self._invoke(["capture", "--name", name, "--agent", agent])

    def exec(self, name: str, argv: list[str]) -> ExecResult:
        args = ["exec", "--name", name, "--", *argv]
        full_argv = [self._itmux_bin, *args]
        returncode, stdout, stderr = self._run(
            full_argv, stdin=None, timeout_s=self._default_timeout_s, env=None
        )
        # `exit_code` is the itmux-level exit code, NOT the inner
        # command's. The real `itmux exec` (`handle_exec`,
        # driver-rs/src/main.rs) ALWAYS returns success (0) on its Ok
        # path and only 1 on a driver-level failure - it does NOT
        # forward the inner command's exit code today. So a failing
        # inner command (e.g. `test -e /missing` -> inner exit 1) still
        # surfaces here as `exit_code == 0`. A non-zero code here means
        # itmux itself failed, so this does not raise.
        # TODO(follow-on): itmux exec should forward the inner exit code
        # so provider file-ops (e.g. file_exists via `test -e`) work -
        # tracked for Plan 1b Task 5.
        return ExecResult(exit_code=returncode, stdout=stdout, stderr=stderr)

    def stop(self, name: str) -> None:
        self._invoke(["stop", "--name", name])
        return None
