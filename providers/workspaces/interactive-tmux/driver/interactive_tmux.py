"""Host-side driver for the `interactive-tmux` workspace provider.

Five public primitives (matches the EXP-05 contract the orchestrator
specified):

  start_workspace(name, host_auth, image, ...) -> InteractiveTmuxWorkspace
  ws.send_message(agent, text)
  ws.await_completion(agent, timeout)
  ws.capture_response(agent)
  ws.stop()

The driver encodes the per-agent matrix discovered in EXP-01..04 so callers
do NOT see per-agent quirks:

  * Claude:
      - submit  = `send-keys -l text` then `send-keys Enter` (two-step)
      - init    = pre-seed ~/.claude.json with hasCompletedOnboarding/theme/
                  projects.<workspace>.hasTrustDialogAccepted (avoids the
                  theme picker and the per-project trust dialog)
      - auth    = mount ~/.claude (for .credentials.json) AND ~/.claude.json
                  (for oauthAccount metadata — without it, claude falls back
                  to API Usage Billing instead of Max plan)
      - ready   = three-signal heuristic: no "esc to interrupt", empty `❯ `
                  prompt line, "? for shortcuts" footer present
  * Codex:
      - submit  = `send-keys text` then `C-j C-m` (first-send gotcha:
                  bare C-m alone often does not dispatch the first message)
      - init    = `codex --no-alt-screen`, then `1` Enter for trust banner,
                  then Escape to close hooks-review screen
      - auth    = mount ~/.codex
      - ready   = `• Working` marker absent and a known idle-state marker
                  visible
  * Gemini:
      - submit  = `send-keys text Enter` (NEVER C-m — confirmed by EXP-03)
      - init    = pre-patch ~/.gemini/settings.json with
                  security.folderTrust.enabled = false, then `gemini` Enter
      - auth    = mount ~/.gemini
      - ready   = `Type your message` prompt indicator present

Standard library only (Python 3.11+). Designed to be importable AND runnable
as a CLI (`python -m interactive_tmux`).
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases and constants

AgentName = Literal["claude", "codex", "gemini"]
AGENTS: tuple[AgentName, ...] = ("claude", "codex", "gemini")

DEFAULT_IMAGE = "agentic-workspace-interactive-tmux:latest"
DEFAULT_TMUX_SIZE = (200, 50)
TMUX_SESSION = "agents"

# ---------------------------------------------------------------------------
# Phase 3 (reliability) constants
#
# Every subprocess.run/docker-exec call used to be unbounded — a wedged
# container (or a docker daemon that stops responding) could hang the
# calling process forever. These bound every such call; `await_completion`'s
# own overall deadline stays separate (see `poll_timeout_s` below) so a
# single stuck poll can't eat the whole budget silently.
DEFAULT_EXEC_TIMEOUT_S = 15.0  # bound for one docker-exec/tmux operation
DEFAULT_RUN_TIMEOUT_S = 30.0  # bound for `docker run` / `docker rm -f`

# tmux `send-keys -l` caps payloads around 16KB; above this we stage the
# text via `load-buffer` + `paste-buffer` instead (see `_tmux_send_literal`).
TMUX_SEND_KEYS_MAX_BYTES = 12_000

# Claude readiness — empty `❯ ` prompt line (whitespace tolerated). Pre-
# compiled because await_completion polls this 2x/sec per agent.
_CLAUDE_EMPTY_PROMPT_RE = re.compile(r"^❯\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Structured results (M3 from EXP-05 codex cross-review)
#
# Before the review, `await_completion` returned a bare bool and the startup
# phase swallowed readiness failures as `logger.warning`. Syntropic137 needs
# to distinguish "timed out" / "never ready yet" / "agent errored" + reason.
# The `AwaitResult` shape mirrors `agentic_isolation.ExecuteResult` so an
# adapter (see `lib/python/agentic_isolation/.../interactive_tmux/`) can map
# 1-to-1 without a translation step.


@dataclass
class AwaitResult:
    """Result of waiting for an agent pane to reach a ready/idle state.

    The `ready` boolean is what existing call sites care about; the other
    fields exist so Syntropic137 (or any orchestrator) can distinguish
    failure modes that used to be invisible:

      - timed_out=True, ready=False         → deadline hit before idle
      - ready=False, reason="never_ready"   → never reached even one ready frame
      - ready=False, reason="unstable"      → ready frames seen but pane kept changing
      - ready=True                          → adapter is_ready() held stable

    `pane` carries the last captured pane text so callers don't have to
    re-capture to inspect post-mortem.
    """

    ready: bool
    timed_out: bool
    reason: str  # "ready" | "timeout_never_ready" | "timeout_unstable" | "error"
    duration_ms: float
    stable_polls_observed: int
    pane: str = ""
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.ready

    def to_dict(self) -> dict:
        return asdict(self)


class StartupReadinessError(RuntimeError):
    """Raised by `start_workspace(..., strict_startup=True)` (default) when
    one or more agent panes did not reach their per-adapter `is_ready()`
    state within `startup_timeout_s`.

    The attached `startup_status` is a {agent: AwaitResult} dict so callers
    can inspect which panes failed and why without re-running the workspace.
    """

    def __init__(self, startup_status: dict[str, AwaitResult]):
        failed = [a for a, r in startup_status.items() if not r.ready]
        super().__init__(
            f"start_workspace: per-agent readiness failed for {failed} "
            f"(see .startup_status for details)"
        )
        self.startup_status = startup_status


# ---------------------------------------------------------------------------
# Executor seam (Phase 2, ADR-driven docker-out-of-docker fix)
#
# Every tmux operation (send-keys, capture-pane) and every credential-seeding
# file write ultimately needs to run a command *inside* the workspace
# target (container, VM, SSH host, ...). Historically that meant
# `subprocess.run(["docker", "exec", ...])` sprinkled through this module.
# `CommandExecutor` pulls that behind a small Protocol so:
#   1. tests can inject a fake executor instead of monkeypatching subprocess
#      at the module level;
#   2. a future transport (E2B, a remote agent, SSH/VPS, ...) can implement
#      the same one-method surface without touching the tmux/adapter logic
#      above.
# `DockerExecExecutor` is the only implementation today and preserves the
# exact `docker exec <container> <command...>` behavior this module always
# had. All identifiers threaded through the tmux/exec helpers below are
# named `target` (not `container`) so they read as backend-neutral: for
# Docker it holds the container name; for other backends (see the
# `Environment` seam further below) it holds whatever opaque label that
# backend uses for logging.


@dataclass
class ExecResult:
    """Result of running one command inside a workspace container.

    `timed_out` (Phase 3) is set by `DockerExecExecutor.exec()` when the
    underlying `subprocess.run(..., timeout=...)` call itself expired,
    instead of letting `subprocess.TimeoutExpired` propagate and hang the
    caller's stack. Defaults to `False` so existing call sites that only
    ever cared about `exit_code`/`stdout`/`stderr` are unaffected.
    """

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


@runtime_checkable
class CommandExecutor(Protocol):
    def exec(self, command: Sequence[str], *, timeout_s: float | None = None) -> ExecResult: ...


@dataclass
class DockerExecExecutor:
    """Default `CommandExecutor`: shells out to `docker exec <container> ...`.

    Behavior-preserving extraction of what `_docker_exec` always did; the
    only new capability is `timeout_s`, forwarded to `subprocess.run(...,
    timeout=...)` so a hung `docker exec` can't block forever (a bare
    `subprocess.run` with no timeout blocks indefinitely on a wedged
    container).
    """

    target: str

    def exec(self, command: Sequence[str], *, timeout_s: float | None = None) -> ExecResult:
        cmd = ["docker", "exec", self.target, *command]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            # Phase 3: a wedged `docker exec` used to hang the calling
            # thread forever. Return a `timed_out` ExecResult instead of
            # letting the exception propagate, so pollers (await_completion)
            # can treat it as "not ready yet" and keep going within their
            # own overall deadline.
            partial_out = exc.stdout if isinstance(exc.stdout, str) else ""
            partial_err = exc.stderr if isinstance(exc.stderr, str) else ""
            return ExecResult(
                exit_code=-1,
                stdout=partial_out,
                stderr=(f"docker exec timed out after {timeout_s}s" + (f": {partial_err}" if partial_err else "")),
                timed_out=True,
            )
        return ExecResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


# ---------------------------------------------------------------------------
# Environment seam (provisioning, one layer above `CommandExecutor`)
#
# `CommandExecutor` answers "how do I run one command against an already-
# running target?". `Environment` answers the layer above that: "how do I
# bring a target into existence, and get a `CommandExecutor` for it, and
# tear it down later?". Docker is the only implementation today
# (`DockerEnvironment`, extracted behavior-preserving from what
# `start_workspace`/`stop` always did), but the seam exists so Local and
# SSH/VPS backends can be added as day-one alternatives without touching
# any tmux/adapter/workspace logic — they only need to provision *something*
# that a `CommandExecutor` can run commands against.


@runtime_checkable
class Environment(Protocol):
    def start(self) -> CommandExecutor: ...
    def stop(self) -> None: ...


@dataclass
class DockerEnvironment:
    """Default `Environment`: provisions a workspace via `docker run` /
    `docker rm -f`.

    Behavior-preserving extraction of the `docker run ...` / `docker rm -f
    ...` logic `start_workspace`/`stop` always ran inline. `start()` returns
    a `DockerExecExecutor(target=self.name)` bound to the container it just
    created; `stop()` best-effort removes that same container.
    """

    name: str
    image: str
    workdir: str
    run_timeout_s: float | None = DEFAULT_RUN_TIMEOUT_S

    def start(self) -> CommandExecutor:
        run_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            self.name,
            "--workdir",
            self.workdir,
            self.image,
            "sleep",
            "infinity",
        ]
        _run(run_cmd, timeout_s=self.run_timeout_s)
        return DockerExecExecutor(self.name)

    def stop(self) -> None:
        try:
            subprocess.run(
                ["docker", "rm", "-f", self.name],
                check=False,
                capture_output=True,
                timeout=self.run_timeout_s or DEFAULT_RUN_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            logger.warning("docker rm -f %s timed out during DockerEnvironment.stop()", self.name)


@dataclass
class LocalExecutor:
    """`CommandExecutor` that runs argv directly on the host — no docker
    prefix, no target at all. Mirrors `DockerExecExecutor.exec()`'s
    timeout/error handling exactly so callers see identical `ExecResult`
    shapes regardless of which `Environment` backs them."""

    workdir: str | Path

    def exec(self, command: Sequence[str], *, timeout_s: float | None = None) -> ExecResult:
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=self.workdir,
            )
        except subprocess.TimeoutExpired as exc:
            # Same rationale as DockerExecExecutor: a wedged local command
            # must not hang the caller forever; return a `timed_out`
            # ExecResult so pollers can treat it as "not ready yet".
            partial_out = exc.stdout if isinstance(exc.stdout, str) else ""
            partial_err = exc.stderr if isinstance(exc.stderr, str) else ""
            return ExecResult(
                exit_code=-1,
                stdout=partial_out,
                stderr=(f"local exec timed out after {timeout_s}s" + (f": {partial_err}" if partial_err else "")),
                timed_out=True,
            )
        return ExecResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


@dataclass
class LocalEnvironment:
    """`Environment` that runs directly on the host — no container, no SSH
    hop. The host is already "up" by construction (it's the machine this
    process is running on), so `start()` has no provisioning step of its
    own; it only verifies the tools the driver depends on are present and
    returns a `LocalExecutor` bound to `workdir`.

    `stop()` is a no-op: there is nothing this environment created that it
    would need to tear down (unlike `DockerEnvironment`, which must `docker
    rm -f` the container it `docker run`'d). Any tmux session left running
    on the host outliving the `LocalEnvironment` object is intentional —
    the host itself is not owned by this class the way a container is.
    """

    workdir: str | Path
    require_tools: Sequence[str] = ("tmux",)

    def start(self) -> CommandExecutor:
        missing = [tool for tool in self.require_tools if shutil.which(tool) is None]
        if missing:
            raise RuntimeError(
                "LocalEnvironment.start(): required tool(s) not found on PATH: "
                f"{', '.join(missing)}. Install them before starting a local "
                "interactive-tmux workspace."
            )
        return LocalExecutor(self.workdir)

    def stop(self) -> None:
        # No-op: see class docstring — a local environment doesn't own the
        # host, so there is nothing to tear down.
        return None


@dataclass
class SSHExecutor:
    """`CommandExecutor` that runs argv on a remote host over `ssh`.

    `base_argv` is the full `ssh` invocation up to (but not including) the
    remote command itself — e.g. `["ssh", "-o", "BatchMode=yes", "-o",
    "ConnectTimeout=10", "-i", "/key", "-p", "22", "user@host"]`. `exec()`
    joins `command` into a single shell string (via `shlex.join`, optionally
    prefixed with `cd <workdir> &&`) and appends it as the final argv
    element, mirroring `DockerExecExecutor`/`LocalExecutor`'s timeout and
    `ExecResult` handling exactly so callers see identical result shapes
    regardless of backend.

    Exit-code semantics are intentionally *not* special-cased beyond what
    the other two executors do: `ssh` returns 255 for a connection-level
    failure (vs. the remote command's own exit code otherwise), but that
    raw exit code is simply surfaced via `ExecResult.exit_code` like any
    other — callers that care about the distinction can inspect `stderr`.
    """

    base_argv: list[str]
    workdir: str | None = None

    def exec(self, command: Sequence[str], *, timeout_s: float | None = None) -> ExecResult:
        remote_cmd = shlex.join(command)
        if self.workdir:
            remote_cmd = f"cd {shlex.quote(self.workdir)} && {remote_cmd}"
        cmd = [*self.base_argv, remote_cmd]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            # Same rationale as DockerExecExecutor/LocalExecutor: a wedged
            # remote command must not hang the caller forever.
            partial_out = exc.stdout if isinstance(exc.stdout, str) else ""
            partial_err = exc.stderr if isinstance(exc.stderr, str) else ""
            return ExecResult(
                exit_code=-1,
                stdout=partial_out,
                stderr=(f"ssh exec timed out after {timeout_s}s" + (f": {partial_err}" if partial_err else "")),
                timed_out=True,
            )
        return ExecResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


@dataclass
class SSHEnvironment:
    """`Environment` that provisions a workspace target on a remote host
    reachable over `ssh`.

    Unlike `DockerEnvironment` there is no `docker run` step: the "target"
    is simply the remote host itself, assumed already up. `start()`
    fails fast with a reachability check (`ssh ... true`) rather than
    letting the first tmux command discover a dead host mid-session, then
    returns an `SSHExecutor` bound to the `ssh` argv it just proved works.

    Known limitation / follow-up: this simple version opens a fresh `ssh`
    process per `exec()` call (no persistent connection is held open
    between execs). A future version could hold one persistent `ssh
    ControlMaster` connection for lower per-call latency.
    """

    host: str
    user: str
    key_path: str | Path | None = None
    port: int = 22
    workdir: str | None = None
    connect_timeout_s: float = 10.0

    def _base_argv(self) -> list[str]:
        return [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={int(self.connect_timeout_s)}",
            *(["-i", str(self.key_path)] if self.key_path else []),
            "-p",
            str(self.port),
            "--",
            f"{self.user}@{self.host}",
        ]

    def start(self) -> CommandExecutor:
        base_argv = self._base_argv()
        try:
            proc = subprocess.run(
                [*base_argv, "true"],
                capture_output=True,
                text=True,
                timeout=self.connect_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"SSHEnvironment.start(): reachability check to {self.user}@{self.host}:{self.port} "
                f"timed out after {self.connect_timeout_s}s"
            ) from exc
        if proc.returncode != 0:
            raise RuntimeError(
                f"SSHEnvironment.start(): reachability check to {self.user}@{self.host}:{self.port} "
                f"failed (exit {proc.returncode}): {proc.stderr.strip()}"
            )
        return SSHExecutor(base_argv, workdir=self.workdir)

    def stop(self) -> None:
        # No-op in this simple version: no persistent connection is held
        # open between execs, so there is nothing to tear down. See class
        # docstring for the ControlMaster follow-up.
        return None


# ---------------------------------------------------------------------------
# tmux send-keys helpers (the only place that talks to docker exec tmux)


def _redact_cmd(cmd: list[str]) -> str:
    """Render a command for logging with literal `send-keys` payloads
    redacted. Prompt bodies often carry secrets, tokens, or user data; the
    arg following `-l` (skipping a `--` terminator) is replaced with its
    length so debug logs stay useful without leaking content."""
    parts: list[str] = []
    redact_next = False
    for tok in cmd:
        if redact_next and tok != "--":
            parts.append(f"<redacted {len(tok)} chars>")
            redact_next = False
        else:
            parts.append(tok)
            if tok == "-l":
                redact_next = True
    return " ".join(parts)


def _run(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
    timeout_s: float | None = DEFAULT_RUN_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Run a subprocess; return CompletedProcess. Raises on non-zero unless
    `check=False`.

    Phase 3: bounded by `timeout_s` (default `DEFAULT_RUN_TIMEOUT_S`) so a
    wedged `docker run`/`docker rm` can't block the caller forever;
    `subprocess.TimeoutExpired` propagates (bounded, not silent) same as
    any other subprocess failure.
    """
    logger.debug("exec: %s", _redact_cmd(cmd))
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout_s,
    )


def _docker_exec(
    target: str,
    *args: str,
    check: bool = True,
    executor: CommandExecutor | None = None,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> subprocess.CompletedProcess:
    """Run `docker exec <target> <args...>`, via `executor` if given.

    Defaults to constructing a fresh `DockerExecExecutor(target)` so
    every existing call site (which doesn't know about the executor seam)
    behaves exactly as before. Returns a `subprocess.CompletedProcess` for
    backward compatibility with callers that inspect `.stdout` /
    `.returncode`.

    Phase 3: `timeout_s` (default `DEFAULT_EXEC_TIMEOUT_S`) is forwarded to
    the executor so no `docker exec` call in this module can block forever.

    `target` is a label only when `executor` is supplied (it feeds the
    logged/returned `docker exec <target> ...` command shape, but the
    actual command runs through `executor.exec()`, which may not be
    Docker-backed at all) — see the `Environment` seam above.
    """
    cmd = ["docker", "exec", target, *args]
    logger.debug("exec: %s", _redact_cmd(cmd))
    exec_ = executor or DockerExecExecutor(target)
    result = exec_.exec(list(args), timeout_s=timeout_s)
    if check and result.exit_code != 0:
        raise subprocess.CalledProcessError(
            result.exit_code, cmd, result.stdout, result.stderr
        )
    return subprocess.CompletedProcess(cmd, result.exit_code, result.stdout, result.stderr)


def _tmux_send_keys(
    target: str,
    window: str,
    *keys: str,
    executor: CommandExecutor | None = None,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> None:
    pane = f"{TMUX_SESSION}:{window}"
    _docker_exec(target, "tmux", "send-keys", "-t", pane, *keys, executor=executor, timeout_s=timeout_s)


def _tmux_send_literal(
    target: str,
    window: str,
    text: str,
    *,
    executor: CommandExecutor | None = None,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> None:
    """Send `text` byte-for-byte (no special-key interpretation).

    Phase 3: tmux's `send-keys -l` caps payloads around 16KB — a long
    model prompt (or a pasted file) silently truncates past that ceiling.
    Payloads at or under `TMUX_SEND_KEYS_MAX_BYTES` keep using the small,
    fast `send-keys -l` path unchanged; larger payloads are staged into a
    tmux paste buffer instead: the bytes are written into a container-side
    temp file (base64-chunked over the executor, same mechanism the
    credential transfer uses), loaded into a named tmux buffer with
    `load-buffer`, and dispatched into the target pane with `paste-buffer`.
    """
    pane = f"{TMUX_SESSION}:{window}"
    payload = text.encode("utf-8")
    if len(payload) <= TMUX_SEND_KEYS_MAX_BYTES:
        # `--` ends option parsing so a prompt beginning with `-` (e.g.
        # "-R", "--help") is treated as literal text, not a send-keys flag.
        _docker_exec(
            target, "tmux", "send-keys", "-t", pane, "-l", "--", text,
            executor=executor, timeout_s=timeout_s,
        )
        return

    exec_ = executor or DockerExecExecutor(target)
    token = uuid.uuid4().hex
    buf_path = f"/tmp/.itmux-sendkeys-{token}.buf"
    buf_name = f"itmux-{token[:12]}"
    try:
        _write_bytes_to_container(exec_, buf_path, payload, timeout_s=timeout_s)
        _run_exec_checked(
            exec_, ["tmux", "load-buffer", "-b", buf_name, buf_path], timeout_s=timeout_s
        )
        _run_exec_checked(
            exec_, ["tmux", "paste-buffer", "-b", buf_name, "-d", "-t", pane], timeout_s=timeout_s
        )
    finally:
        # Best-effort cleanup of the staged temp file; a failure here must
        # not mask the paste having already succeeded (or failed) above.
        exec_.exec(["rm", "-f", buf_path], timeout_s=timeout_s)


def _tmux_capture(
    target: str,
    window: str,
    *,
    executor: CommandExecutor | None = None,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> str:
    """Capture the full pane buffer including scrollback.

    `-S -` = start at the top of the history; `-E -` = end at the bottom
    of the visible pane. Together they return EVERYTHING the TUI has
    written, not just the rows the terminal happens to render right now.

    Without this, the visible window is `DEFAULT_TMUX_SIZE` (200x50) — a
    multi-paragraph model reply that overflows the visible pane is
    silently truncated. EXP-03 documented `-S - -E -` from the start;
    the Python driver shipped without it (D-block-3 from the
    Syntropic137 stress run, experiments/stress/STRESS-REPORT.md).
    """
    pane = f"{TMUX_SESSION}:{window}"
    return _docker_exec(
        target, "tmux", "capture-pane", "-p", "-t", pane, "-S", "-", "-E", "-",
        executor=executor, timeout_s=timeout_s,
    ).stdout


def _pane_tail(pane_text: str, n_lines: int = DEFAULT_TMUX_SIZE[1]) -> str:
    """Return the bottom `n_lines` lines of a captured pane.

    Used by `is_started` / `is_ready` predicates so they evaluate against
    the CURRENT visible region rather than the entire scrollback. With
    the full-scrollback capture (above), the buffer now contains every
    prompt the user has typed and every prior generation — the absence
    checks (`"esc to interrupt" not in pane`) would otherwise be fooled
    by old generations that have long finished, and the empty-chevron
    regex would match against ancient prompts. Defaults to one tmux
    pane height (50 rows) — same window as before the scrollback flip,
    so the readiness predicates retain their original semantics.

    Surfaced by Syntropic137 stress D-block-2: per-agent readiness took
    the full 240s timeout (16x waste) when a multi-paragraph reply
    pushed the idle markers out of the visible region the predicates
    were checking against. With the tail, idle markers anchored at the
    bottom of the live TUI window are evaluated correctly.
    """
    if not pane_text:
        return ""
    lines = pane_text.splitlines()
    if len(lines) <= n_lines:
        return pane_text
    tail = "\n".join(lines[-n_lines:])
    if pane_text.endswith("\n"):
        tail += "\n"
    return tail


# ---------------------------------------------------------------------------
# TmuxSession (Phase 4: agent-agnostic session/window handle)
#
# Everything above this point (`_tmux_send_keys`, `_tmux_send_literal`,
# `_tmux_capture`) is already agent-agnostic — it operates on a
# `(container, window)` pair with no claude/codex/gemini knowledge. Before
# Phase 4, that genericity was implicit: callers reached for the bare
# functions directly. `TmuxSession` makes it an explicit, reusable handle so
# a 4th agent adapter can be built on top of it without touching this class,
# and so `InteractiveTmuxWorkspace` has one object per enabled agent to hold
# session state (rather than re-threading `target`/`window`/`executor`
# through every call). Must not reference any agent name — only generic
# pane/window operations, all routed through the injected `CommandExecutor`.
# `target` is backend-neutral: whatever `Environment.start()` produced an
# executor for (a Docker container name today; an opaque host label for
# other backends).


@dataclass
class TmuxSession:
    """One tmux window inside the shared `TMUX_SESSION`, agent-agnostic.

    Thin, stateless-except-for-identity wrapper around the module-level
    `_tmux_send_keys` / `_tmux_send_literal` / `_tmux_capture` / `_docker_exec`
    helpers. Deliberately delegates to those free functions (rather than
    reimplementing their logic) so:
      1. existing tests that monkeypatch the module-level functions keep
         working unchanged whether a caller goes through `TmuxSession` or
         calls the free functions directly;
      2. Phase 2/3 behavior (executor injection, timeouts, payload batching)
         is inherited for free instead of duplicated.
    """

    target: str
    window: str
    executor: CommandExecutor

    def start(
        self,
        cols: int,
        rows: int,
        *,
        as_new_window: bool = False,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        """Create this window: a new tmux session (first agent) or a new
        window in the existing session (subsequent agents)."""
        if as_new_window:
            _docker_exec(
                self.target,
                "tmux",
                "new-window",
                "-t",
                TMUX_SESSION,
                "-n",
                self.window,
                executor=self.executor,
                timeout_s=timeout_s,
            )
        else:
            _docker_exec(
                self.target,
                "tmux",
                "new-session",
                "-d",
                "-s",
                TMUX_SESSION,
                "-n",
                self.window,
                "-x",
                str(cols),
                "-y",
                str(rows),
                executor=self.executor,
                timeout_s=timeout_s,
            )

    def stop(self, *, timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S) -> None:
        """Best-effort kill of this window. Non-fatal: tearing down the
        container (the workspace-level `stop()`) removes the window anyway;
        this exists for callers that want to retire one agent's pane
        without stopping the whole workspace."""
        pane = f"{TMUX_SESSION}:{self.window}"
        _docker_exec(
            self.target,
            "tmux",
            "kill-window",
            "-t",
            pane,
            executor=self.executor,
            check=False,
            timeout_s=timeout_s,
        )

    def send_keys(self, *keys: str, timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S) -> None:
        _tmux_send_keys(self.target, self.window, *keys, executor=self.executor, timeout_s=timeout_s)

    def send_literal(self, text: str, *, timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S) -> None:
        _tmux_send_literal(self.target, self.window, text, executor=self.executor, timeout_s=timeout_s)

    def capture_pane(self, *, timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S) -> str:
        return _tmux_capture(self.target, self.window, executor=self.executor, timeout_s=timeout_s)

    def get_incremental_output(
        self,
        previous: str | None,
        *,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> tuple[str, str]:
        """Return `(new_text, full_pane)` for this window.

        `new_text` is the substring diff against `previous` (an earlier
        `capture_pane()`/`get_incremental_output()` result) when the current
        capture starts with it — the common case, since tmux scrollback only
        grows. When it doesn't (pane was cleared, history rolled off the
        scrollback limit, or `previous` is falsy), `new_text` falls back to
        the full current capture rather than guessing at a diff.
        """
        current = self.capture_pane(timeout_s=timeout_s)
        if previous and current.startswith(previous):
            return current[len(previous) :], current
        return current, current

    def is_alive(self, *, timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S) -> bool:
        """Whether the shared tmux session (not just this window) is still
        reachable inside the container."""
        result = self.executor.exec(["tmux", "has-session", "-t", TMUX_SESSION], timeout_s=timeout_s)
        return result.exit_code == 0


# ---------------------------------------------------------------------------
# Per-agent adapters
#
# Each adapter is responsible for:
#   prepare_host_auth(src) -> Path | None  : produce a throwaway dir/file
#                                            for bind-mount; returns the
#                                            host path (or None to skip).
#   launch_in_window(container, window)    : tmux send-keys to start the CLI
#                                            and walk init gates
#   submit(container, window, text)        : encode the submit pattern
#   is_ready(pane_text) -> bool            : readiness heuristic
#
# The dispatcher (InteractiveTmuxWorkspace) calls these via the agent name.


@dataclass
class _AdapterContext:
    """What a per-agent adapter needs from the workspace at runtime."""

    container: str
    workdir: str  # container path (e.g., /workspace)
    host_throwaway_dir: Path  # per-workspace temp dir on the host
    # Optional explicit `.claude.json` path. When set, `_ClaudeAdapter` uses
    # this as the source for the synthesized container-side `~/.claude.json`
    # instead of looking for a sibling of `host_src`. Set via the
    # `start_workspace(host_claude_dotjson=...)` kwarg or the
    # `ITMUX_CLAUDE_JSON` env var (see `_default_claude_dotjson_from_env`).
    # Surfaces the DooD case: when the caller runs the driver inside another
    # container with credentials mounted at unrelated paths, the parent-of-
    # CLAUDE_HOME heuristic does not find the host's dotjson.
    host_claude_dotjson: Path | None = None


class _ClaudeAdapter:
    """Encodes EXP-01 friction findings.

    Auth surface: ~/.claude/ (directory, for .credentials.json) AND
    ~/.claude.json (file, for oauthAccount metadata + onboarding markers).
    See EXP-05's "Open contradiction" section for the empirical resolution
    of where the OAuth token lives, and EXP-05a for the full 2×2 mount
    matrix proving BOTH files are required.

    Synthetic ~/.claude.json policy (EXP-05 codex cross-review m1):
    -------------------------------------------------------------
    EXP-05a tested four mount combinations on the host (`none`, `.claude`
    only, `.claude.json` only, both). Only "both" yielded an authenticated
    start. This adapter, however, ALWAYS synthesizes ~/.claude.json in
    the container even when the host's ~/.claude.json is absent. The
    synthesized file carries onboarding-skip markers, the workspace's
    project-trust map, and (when available) the host's `oauthAccount`
    metadata copied through. Token material is never synthesized — only
    `~/.claude/.credentials.json` carries tokens, and it MUST exist on
    the host. Concretely:

      - host has `.claude/` + `.claude.json` → both copied; behaves
        identically to EXP-05a's "both" cell (authenticated start, no
        wizards).
      - host has `.claude/` only             → `.claude/.credentials.json`
        copied; `.claude.json` is SYNTHESIZED. This case is OUTSIDE
        EXP-05a's matrix; it works because the synthesized file supplies
        the onboarding/trust markers Claude expects, while the tokens
        come from `.credentials.json`. Functionally equivalent to "both"
        for this provider.
      - host has neither                     → `prepare_host_auth`
        raises (we never start a container that can't authenticate).

    Net: callers do not need to manage `.claude.json` themselves; this
    adapter's fallback is the recommended path. If a consumer wants to
    suppress synthesis and mount their own `.claude.json` byte-for-byte,
    they should call `host_auth["claude"] = …` with a directory that
    contains both `.credentials.json` AND a sibling `.claude.json` — but
    the synthesized file is the path EXP-05a's "both" outcome generalizes
    to inside this container image.
    """

    window = "claude"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        """Return {mount_id: (host_path, container_path)} for the bind mounts.

        host_src is the path to the live `~/.claude` directory; the sibling
        `~/.claude.json` is auto-resolved at `{host_src.parent}/.claude.json`.
        Throwaway copies live under ctx.host_throwaway_dir.
        """
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"claude auth dir not found: {host_src}")
        creds = host_src / ".credentials.json"
        if not creds.is_file():
            raise FileNotFoundError(
                f"claude .credentials.json missing under {host_src}; cannot mount Max-plan auth"
            )

        # Throwaway ~/.claude/ — copy .credentials.json only to avoid leaking
        # session history. Runtime claude will recreate cache/sessions/etc.
        dst_dir = ctx.host_throwaway_dir / "claude.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(creds, dst_dir / ".credentials.json")
        os.chmod(dst_dir / ".credentials.json", 0o600)
        # Ownership matches the in-container agent user (uid 1000).
        _chown_recursive(dst_dir, 1000, 1000)

        # Throwaway ~/.claude.json — pre-seeded with onboarding-skip markers,
        # the workspace project trust pre-accepted, and (if available) the
        # host's oauthAccount metadata copied through so "Welcome back" lands
        # cleanly instead of triggering a fresh-account flow.
        #
        # Source resolution order (caller > sibling > nothing):
        #   1. `ctx.host_claude_dotjson` (explicit; set by
        #      `ITMUX_CLAUDE_JSON` or `start_workspace(host_claude_dotjson=)`)
        #   2. `host_src.parent / ".claude.json"` — the historical default for
        #      callers running outside a container, where `host_src` is the
        #      operator's `~/.claude` and the dotjson sits next to it.
        # If neither resolves, `_build_seeded_claude_dotjson` synthesizes a
        # fresh dotjson with onboarding/trust markers only (no oauthAccount
        # passthrough) — see EXP-05a for which cells survive that mode.
        dotjson_src = ctx.host_claude_dotjson or (host_src.parent / ".claude.json")
        dotjson_dst = ctx.host_throwaway_dir / "claude.json"
        seeded = _build_seeded_claude_dotjson(dotjson_src, ctx.workdir)
        dotjson_dst.write_text(json.dumps(seeded, indent=2))
        os.chmod(dotjson_dst, 0o600)
        _chown_path(dotjson_dst, 1000, 1000)

        return {
            "claude_dir": (dst_dir, "/home/agent/.claude"),
            "claude_dotjson": (dotjson_dst, "/home/agent/.claude.json"),
        }

    @staticmethod
    def launch_in_window(
        container: str,
        _workdir: str,
        plugin_dirs: Sequence[Path] | None = None,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        """Start `claude` in its tmux window, with optional `--plugin-dir` flags.

        The Syntropic137 workflow-skills bridge experiment
        (`docs/plans/workflow-skills.md` §9) showed that injecting plugins
        via `~/.claude.json` `installedPlugins` is silently ignored by the
        TUI; only the `--plugin-dir` CLI flag is honored. This adapter
        builds one flag per entry — paths are passed through `shlex.quote`
        so directory names with spaces or special characters survive the
        tmux send-keys path.
        """
        if plugin_dirs:
            flags = " ".join(f"--plugin-dir {shlex.quote(str(p))}" for p in plugin_dirs)
            cmd = f"claude {flags}"
            _tmux_send_literal(
                container,
                _ClaudeAdapter.window,
                cmd,
                executor=executor,
                timeout_s=timeout_s,
            )
            _tmux_send_keys(
                container,
                _ClaudeAdapter.window,
                "Enter",
                executor=executor,
                timeout_s=timeout_s,
            )
        else:
            _tmux_send_keys(
                container,
                _ClaudeAdapter.window,
                "claude",
                "Enter",
                executor=executor,
                timeout_s=timeout_s,
            )

    @staticmethod
    def build_launch_command(plugin_dirs: Sequence[Path] | None = None) -> str:
        """Return the exact shell command this adapter will send to tmux.

        Exposed for unit tests so they can assert the `--plugin-dir` flags
        land verbatim without spawning a container. Mirrors
        `launch_in_window`'s string construction one-to-one.
        """
        if not plugin_dirs:
            return "claude"
        flags = " ".join(f"--plugin-dir {shlex.quote(str(p))}" for p in plugin_dirs)
        return f"claude {flags}"

    @staticmethod
    def submit(
        container: str,
        text: str,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        # EXP-01: two-step is the documented default. -l makes the bytes
        # land literally (no special-key interpretation in the text body),
        # then a separate Enter dispatches.
        _tmux_send_literal(container, _ClaudeAdapter.window, text, executor=executor, timeout_s=timeout_s)
        _tmux_send_keys(container, _ClaudeAdapter.window, "Enter", executor=executor, timeout_s=timeout_s)

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # EXP-01 FRICTION F-5 three-signal heuristic for *post-turn* idle.
        # The codex cross-review flagged that the old code only checked 2
        # of the 3 codified signals despite the class docstring claiming
        # three; fixed here:
        #   1. `esc to interrupt` absent (no generation in progress)
        #   2. `? for shortcuts` present (steady-state TUI footer, not a modal)
        #   3. `^❯\s*$` matches somewhere in the capture (input box prompt
        #      line is empty — only the chevron, optional whitespace)
        # NOTE: this predicate is intentionally strict on the empty-prompt
        # signal so it can distinguish "just finished a turn" from "model
        # still rendering". The startup welcome screen shows the chevron
        # with a placeholder hint (e.g., `❯ Try "..."`), which fails this
        # check — that is why `is_started()` below has its own (looser)
        # predicate for the startup phase.
        return (
            "esc to interrupt" not in pane_text
            and "? for shortcuts" in pane_text
            and _CLAUDE_EMPTY_PROMPT_RE.search(pane_text) is not None
        )

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Startup-phase readiness: the TUI is past the splash/trust/login
        # gates and is willing to accept input, regardless of whether the
        # chevron line is empty or showing the placeholder hint. Used by
        # `_wait_for_started` during `start_workspace`; once the workspace
        # is running, `is_ready` is the predicate that matters per turn.
        return (
            "esc to interrupt" not in pane_text
            and "? for shortcuts" in pane_text
            and "❯" in pane_text
        )

    @staticmethod
    def response_marker() -> str:
        # Used by the smoke to distinguish the model's response from the
        # echoed prompt. The TUI prefixes the model's reply with a filled
        # bullet (U+25CF). Prompts use `❯`.
        return "● "


class _CodexAdapter:
    """Encodes EXP-02 friction findings.

    Submit gotcha: first user message often does not dispatch with bare
    C-m alone; reliable pattern is C-j C-m. After the first turn, the
    same pattern keeps working.

    Init gotchas: trust banner (numbered prompt) and hooks-review screen
    fire on every fresh container start.
    """

    window = "codex"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"codex auth dir not found: {host_src}")
        dst_dir = ctx.host_throwaway_dir / "codex.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        # Copy the .codex/ tree but skip the live tmp/ subdir — codex races
        # there (creates and deletes argv files during normal operation), so
        # copytree against it sees vanished files. The auth lives in
        # auth.json / config.toml / sessions/ at the top level.
        skip = {"tmp", "log", "logs"}
        for item in host_src.iterdir():
            if item.name in skip:
                continue
            target = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(item, target)
        _chown_recursive(dst_dir, 1000, 1000)
        return {"codex_dir": (dst_dir, "/home/agent/.codex")}

    @staticmethod
    def launch_in_window(
        container: str,
        _workdir: str,
        plugin_dirs: Sequence[Path] | None = None,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        # `plugin_dirs` is accepted for signature parity with the claude
        # adapter; codex has no equivalent `--plugin-dir` flag, so any
        # value is silently ignored.
        del plugin_dirs
        # --no-alt-screen so capture-pane sees the same buffer the TUI uses.
        _tmux_send_keys(
            container,
            _CodexAdapter.window,
            "codex --no-alt-screen",
            "Enter",
            executor=executor,
            timeout_s=timeout_s,
        )
        # Trust banner: select option 1 ("Yes, trust"), confirm with Enter.
        time.sleep(2)
        _tmux_send_keys(
            container,
            _CodexAdapter.window,
            "1",
            "Enter",
            executor=executor,
            timeout_s=timeout_s,
        )
        # Hooks-review modal: close with Escape.
        time.sleep(1)
        _tmux_send_keys(
            container,
            _CodexAdapter.window,
            "Escape",
            executor=executor,
            timeout_s=timeout_s,
        )
        time.sleep(1)

    @staticmethod
    def submit(
        container: str,
        text: str,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        # EXP-02: literal text first (so the body's bytes don't get
        # tmux-special-key-interpreted), then C-j C-m to dispatch.
        # C-j C-m is the gotcha — bare C-m alone often does not submit
        # the first message.
        _tmux_send_literal(container, _CodexAdapter.window, text, executor=executor, timeout_s=timeout_s)
        _tmux_send_keys(container, _CodexAdapter.window, "C-j", "C-m", executor=executor, timeout_s=timeout_s)

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # Codex marks generation with `• Working (...)`. Idle state shows
        # the input box marker `›` (U+203A) on a line by itself, plus the
        # footer suggestion line (the "Tip:" or "Write tests for @filename"
        # hint that codex shows once at idle). Two positive signals OR'd
        # together so a transient hint loss doesn't false-fail.
        if "• Working" in pane_text:
            return False
        return ("› " in pane_text) or ("Write tests for" in pane_text) or ("Tip:" in pane_text)

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Codex's idle markers already cover the startup case (post-trust,
        # post-hooks-review the TUI shows the input box + tip line).
        return _CodexAdapter.is_ready(pane_text)

    @staticmethod
    def response_marker() -> str:
        # Codex prefixes the model reply with U+2022 (bullet operator). The
        # prompt uses `›` so the two are distinguishable in capture.
        return "• "


class _GeminiAdapter:
    """Encodes EXP-03 friction findings.

    Submit gotcha: must use literal `Enter` keyword; `C-m` does not
    reliably dispatch through `docker exec tmux send-keys`.
    Init gotcha: must pre-patch ~/.gemini/settings.json with
      security.folderTrust.enabled = false
    or the trust modal blocks startup (the `--yolo` flag does NOT skip it).
    """

    window = "gemini"

    @staticmethod
    def prepare_host_auth(
        host_src: Path | None,
        ctx: _AdapterContext,
    ) -> dict[str, tuple[Path, str]]:
        if host_src is None:
            return {}
        if not host_src.is_dir():
            raise FileNotFoundError(f"gemini auth dir not found: {host_src}")
        dst_dir = ctx.host_throwaway_dir / "gemini.dir"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in host_src.iterdir():
            target = dst_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        # Patch settings.json with folderTrust.enabled=false (EXP-03 fix).
        settings_path = dst_dir / "settings.json"
        settings: dict = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())
            except json.JSONDecodeError:
                settings = {}
        security = settings.setdefault("security", {})
        folder_trust = security.setdefault("folderTrust", {})
        folder_trust["enabled"] = False
        settings_path.write_text(json.dumps(settings, indent=2))
        _chown_recursive(dst_dir, 1000, 1000)
        return {"gemini_dir": (dst_dir, "/home/agent/.gemini")}

    @staticmethod
    def launch_in_window(
        container: str,
        _workdir: str,
        plugin_dirs: Sequence[Path] | None = None,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        # `plugin_dirs` is accepted for signature parity with the claude
        # adapter; gemini has no equivalent `--plugin-dir` flag, so any
        # value is silently ignored.
        del plugin_dirs
        _tmux_send_keys(
            container,
            _GeminiAdapter.window,
            "gemini",
            "Enter",
            executor=executor,
            timeout_s=timeout_s,
        )
        time.sleep(1)

    @staticmethod
    def submit(
        container: str,
        text: str,
        *,
        executor: CommandExecutor | None = None,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        # EXP-03: text first, then Enter — never C-m.
        _tmux_send_literal(container, _GeminiAdapter.window, text, executor=executor, timeout_s=timeout_s)
        _tmux_send_keys(container, _GeminiAdapter.window, "Enter", executor=executor, timeout_s=timeout_s)

    @staticmethod
    def is_ready(pane_text: str) -> bool:
        # EXP-03: idle = `Type your message` prompt indicator present AND
        # the model is not currently `Thinking...`. The bare presence-of
        # `Type your message` is NOT sufficient: the prompt-hint line stays
        # visible at the bottom of the pane even while the model is mid-
        # generation, so smoke runs were observed to false-pass on it. The
        # active-generation indicator `Thinking...` (or `esc to cancel`)
        # must also be absent.
        if "Thinking..." in pane_text or "esc to cancel" in pane_text:
            return False
        return "Type your message" in pane_text

    @staticmethod
    def is_started(pane_text: str) -> bool:
        # Gemini's idle marker `Type your message` is the same signal we
        # want at startup (no separate splash/auth gate that hides it).
        return _GeminiAdapter.is_ready(pane_text)

    @staticmethod
    def response_marker() -> str:
        # Gemini prefixes the model reply with a four-pointed star (U+2726).
        # The prompt indicator is `›` / `>` so the two are distinguishable.
        return "✦ "


_ADAPTERS = {
    "claude": _ClaudeAdapter,
    "codex": _CodexAdapter,
    "gemini": _GeminiAdapter,
}
# Phase 4: `_ADAPTERS` is the registry a 4th agent joins by registering an
# adapter object here — no edits to `TmuxSession` (which knows nothing about
# any agent name) or to the workspace's dispatch logic are needed. Adapters
# sit ON TOP of `TmuxSession`: they encode submit/readiness heuristics and
# receive a plain `container` + `executor` (matching their existing static
# method signatures, preserved for backward compatibility with callers/tests
# that invoke them directly), while `InteractiveTmuxWorkspace` holds one
# `TmuxSession` per enabled agent for generic pane operations.


# ---------------------------------------------------------------------------
# Helpers


def _chown_path(path: Path, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except PermissionError:
        # Non-fatal when running as non-root host user — docker will run as
        # the requested uid inside the container regardless. Worst case: the
        # in-container agent can't write to the mount. We warn; smoke will
        # surface this fast enough.
        logger.warning("chown %s to %s:%s failed (continuing)", path, uid, gid)


def _chown_recursive(path: Path, uid: int, gid: int) -> None:
    _chown_path(path, uid, gid)
    for sub in path.rglob("*"):
        _chown_path(sub, uid, gid)


def _run_exec_checked(
    executor: CommandExecutor,
    command: list[str],
    *,
    timeout_s: float | None = None,
) -> ExecResult:
    """`executor.exec(command)`, raising `RuntimeError` on non-zero exit.

    Credential transfer is not optional best-effort work — a silently
    failed `mkdir -p` or base64 write leaves the container half-seeded
    with auth material, which is worse than failing loudly at
    `start_workspace` time.
    """
    result = executor.exec(command, timeout_s=timeout_s)
    if result.exit_code != 0:
        raise RuntimeError(
            f"container command failed (exit {result.exit_code}): {command!r}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _write_bytes_to_container(
    executor: CommandExecutor,
    container_path: str,
    data: bytes,
    *,
    chunk_size: int = 6000,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> None:
    """Write `data` into `container_path` inside the container over `executor`.

    Replaces host bind-mounting of credential material (the docker-out-of-
    docker fix): instead of `-v host:container` at `docker run` time, the
    file's bytes are base64-encoded and pushed in over `docker exec` in
    `chunk_size`-sized pieces (tmux's ~16KB send-keys ceiling doesn't apply
    here, but keeping writes chunked avoids hitting exec/argv length limits
    on very large credential files). Each chunk is base64 so arbitrary
    bytes (including newlines/binary) survive the `sh -c` round-trip.

    `timeout_s` (Phase 3) bounds each individual exec call so a wedged
    container can't hang the transfer forever.
    """
    parent = posixpath.dirname(container_path)
    if parent:
        _run_exec_checked(executor, ["mkdir", "-p", parent], timeout_s=timeout_s)
    quoted_path = shlex.quote(container_path)
    # Truncate/create the destination before appending chunks so a re-run
    # (or a shorter payload than a stale prior write) doesn't leave trailing
    # garbage from an earlier attempt.
    _run_exec_checked(executor, ["sh", "-c", f"> {quoted_path}"], timeout_s=timeout_s)
    encoded = base64.b64encode(data).decode("ascii")
    for start in range(0, len(encoded), chunk_size):
        chunk = encoded[start : start + chunk_size]
        cmd = f"printf '%s' {shlex.quote(chunk)} | base64 -d >> {quoted_path}"
        _run_exec_checked(executor, ["sh", "-c", cmd], timeout_s=timeout_s)


def _transfer_path_to_container(
    executor: CommandExecutor,
    host_path: Path,
    container_path: str,
    *,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> None:
    """Copy a host file or directory tree into the container over `executor`.

    Mirrors what a `-v host_path:container_path` bind mount used to provide,
    but works when the driver itself runs inside a container (the host
    path the caller staged files into is invisible to a sibling `docker
    run -v`, but `docker exec` into the *target* container always works).
    """
    if host_path.is_dir():
        for root, _dirs, files in os.walk(host_path):
            rel_root = Path(root).relative_to(host_path)
            for fname in files:
                src = Path(root) / fname
                rel = fname if rel_root == Path(".") else f"{rel_root.as_posix()}/{fname}"
                dst = f"{container_path.rstrip('/')}/{rel}"
                _write_bytes_to_container(executor, dst, src.read_bytes(), timeout_s=timeout_s)
    else:
        _write_bytes_to_container(executor, container_path, host_path.read_bytes(), timeout_s=timeout_s)


def _secure_container_path(
    executor: CommandExecutor,
    container_path: str,
    *,
    is_dir: bool,
    timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
) -> None:
    """chown the transferred path to the in-container agent user (uid/gid
    1000) and lock file permissions to 0600 — mirrors what the host-side
    `_chown_recursive` / `os.chmod(..., 0o600)` calls used to guarantee
    before the bind-mount path was removed.
    """
    quoted = shlex.quote(container_path)
    if is_dir:
        cmd = f"chown -R 1000:1000 {quoted} && find {quoted} -type f -exec chmod 600 {{}} +"
    else:
        cmd = f"chown 1000:1000 {quoted} && chmod 600 {quoted}"
    _run_exec_checked(executor, ["sh", "-c", cmd], timeout_s=timeout_s)


def _build_seeded_claude_dotjson(host_dotjson: Path, workspace_path: str) -> dict:
    """Build the synthetic ~/.claude.json the container should see.

    Carries over the host's `oauthAccount` (so claude shows "Welcome back"
    instead of triggering a fresh-account flow) and forces the onboarding
    and per-workspace trust markers so the TUI lands on the prompt rather
    than a wizard or trust dialog.
    """
    base: dict = {}
    if host_dotjson.is_file():
        try:
            base = json.loads(host_dotjson.read_text())
        except json.JSONDecodeError:
            base = {}

    seeded = {
        "numStartups": int(base.get("numStartups", 5) or 5),
        "installMethod": "npm-global",
        "autoUpdates": False,
        "hasCompletedOnboarding": True,
        "theme": base.get("theme", "dark"),
    }
    # Carry oauthAccount through if present (account uuid/email/org) — this is
    # what makes claude say "Welcome back Neural" instead of running fresh.
    if "oauthAccount" in base:
        seeded["oauthAccount"] = base["oauthAccount"]

    # Pre-accept the workspace project. claude looks up `projects.<absolute
    # path>` keyed by the workspace dir.
    seeded["projects"] = {
        workspace_path: {
            "hasTrustDialogAccepted": True,
            "hasCompletedProjectOnboarding": True,
        }
    }
    return seeded


# ---------------------------------------------------------------------------
# The workspace


@dataclass
class InteractiveTmuxWorkspace:
    name: str
    container: str
    image: str
    workdir: str
    tmux_size: tuple[int, int]
    host_throwaway_dir: Path
    enabled_agents: tuple[str, ...]

    # M1 (codex cross-review): per-agent startup readiness status. Populated
    # by `_bootstrap_tmux_and_launch`; surfaced through the public attribute
    # `startup_status` for non-strict callers. With `strict_startup=True`
    # (the default), any per-agent failure raises `StartupReadinessError`
    # before this dict is observable, so the dict is always populated only
    # with successful AwaitResults in the strict path.
    startup_status: dict[str, AwaitResult] = field(default_factory=dict)

    # Internal: track per-agent first-send state for adapters that care
    # (e.g., Codex's first-send-needs-C-j-C-m can be relaxed after turn 1
    # in a future iteration; we keep C-j C-m always-on for now since it
    # works in both positions per EXP-02).
    _started: dict[str, bool] = field(default_factory=dict)

    # Per-agent launch-time CLI extras (currently only `claude_plugin_dirs`
    # — paths to load via `claude --plugin-dir <path>`). Set by
    # `start_workspace` from its kwargs before the bootstrap runs; consumed
    # by `_bootstrap_tmux_and_launch` when it calls each adapter's
    # `launch_in_window`. Lists of pathlib.Path values.
    _launch_extras: dict[str, list[Path]] = field(default_factory=dict)

    # Phase 2 executor seam: the `CommandExecutor` used for this workspace's
    # container. Defaults to a `DockerExecExecutor(self.container)` in
    # `__post_init__` when not supplied — every existing caller (including
    # `_load_workspace`, which never knew about executors) gets identical
    # behavior. Injectable so tests (and future non-docker transports) don't
    # need to monkeypatch subprocess/docker.
    executor: CommandExecutor | None = None

    # Environment seam: the `Environment` used to provision this workspace's
    # backing target (Docker today) and, correspondingly, tear it down in
    # `stop()`. `None` for workspaces reconstructed via `_load_workspace`
    # (the registry only persists identifiers, not live provisioning
    # objects) — `stop()` falls back to the historical `docker rm -f` in
    # that case, preserving CLI behavior.
    environment: Environment | None = None

    # Phase 4: one agent-agnostic `TmuxSession` per enabled agent, built in
    # `__post_init__`. `send_message`/`await_completion`/`capture_response`
    # and the startup-wait loop delegate their pane operations here instead
    # of re-deriving `(container, window, executor)` inline; adapter submit
    # patterns (still keyed by agent) stay separate since they're agent-
    # specific, not generic tmux operations. Excluded from `repr`/equality —
    # it's a derived cache, not part of the workspace's identity.
    _sessions: dict[str, TmuxSession] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.executor is None:
            self.executor = DockerExecExecutor(self.container)
        self._sessions = {
            agent: TmuxSession(target=self.container, window=_ADAPTERS[agent].window, executor=self.executor)
            for agent in self.enabled_agents
            if agent in _ADAPTERS
        }

    # -----------------------------------------------------------------------
    # Lifecycle

    @classmethod
    def start_workspace(
        cls,
        name: str,
        host_auth: dict[str, Path | None] | None = None,
        image: str = DEFAULT_IMAGE,
        workdir: str = "/workspace",
        tmux_size: tuple[int, int] = DEFAULT_TMUX_SIZE,
        startup_timeout_s: float = 45.0,
        strict_startup: bool = True,
        host_claude_dotjson: Path | None = None,
        claude_plugin_dirs: Sequence[Path] | None = None,
        environment: Environment | None = None,
    ) -> InteractiveTmuxWorkspace:
        """Start a new interactive-tmux workspace.

        Args:
            name: workspace name (also used as a container name suffix).
            host_auth: per-agent host paths to live credential dirs / files.
                Keys: "claude" (path to ~/.claude), "codex" (~/.codex),
                "gemini" (~/.gemini). A value of None disables that agent's
                pane (it is not launched).
            image: docker image tag to run.
            workdir: container working directory (also keyed into claude's
                project-trust map).
            tmux_size: (cols, rows) for the tmux session. The default 200x50
                fixes EXP-01 FRICTION F-3 (default 80x24 truncates the TUI).
            startup_timeout_s: how long to wait per agent for its idle/ready
                state before giving up.
            strict_startup: if True (default), raise `StartupReadinessError`
                when any enabled agent fails to reach `is_ready()` within
                `startup_timeout_s`. If False, log a warning and return the
                workspace with per-agent results on `ws.startup_status` —
                callers can inspect status before `send_message`. EXP-05
                cross-review M1: bare success on a missed readiness gate is
                a footgun for orchestrators like Syntropic137. Strict is the
                safer default; lax is opt-in for callers who already check
                `ws.startup_status` themselves.
            host_claude_dotjson: explicit host-side path to `~/.claude.json`.
                If `None` (default), the driver looks for it as a sibling of
                `host_auth["claude"]` — which is correct when the caller runs
                outside a container. Inside a container (docker-out-of-docker),
                the operator's `.claude.json` may be mounted at an unrelated
                path; pass it explicitly here. Equivalent to setting
                `ITMUX_CLAUDE_JSON` in the environment. Surfaced as a bug fix
                for the Syntropic137 integration e2e (PR #202 follow-up).
            claude_plugin_dirs: list of container-side paths to load as Claude
                Code plugin dirs. The driver launches `claude --plugin-dir P1
                --plugin-dir P2 ...` — the only mechanism that actually loads
                plugins into the tmux-driven TUI (settings.json injection is
                silently ignored; proven by Syntropic137's workflow-skills
                bridge experiment, `docs/plans/workflow-skills.md` §9).
                Equivalent to setting `ITMUX_CLAUDE_PLUGIN_DIRS` (colon-
                separated, like `$PATH`).
            environment: the `Environment` used to provision the workspace's
                backing target and obtain a `CommandExecutor` for it. When
                `None` (default), a `DockerEnvironment` is constructed from
                `image`/`workdir` (and the generated container name) —
                identical to this method's historical behavior. Pass an
                explicit `Environment` to provision on a different backend
                (local process, SSH/VPS, ...) without changing any
                tmux/adapter logic.

        Returns:
            InteractiveTmuxWorkspace. In both strict and lax modes,
            `ws.startup_status` is populated with per-agent `AwaitResult`s.

        Raises:
            StartupReadinessError: in strict mode, when any agent pane fails
                to reach its is_ready() state within `startup_timeout_s`.
        """
        host_auth = host_auth or {}
        container = f"interactive-tmux-{name}-{uuid.uuid4().hex[:8]}"
        host_throwaway_dir = Path(tempfile.mkdtemp(prefix=f"interactive-tmux-{name}-"))

        # Decide which agents are enabled (passed in host_auth) and prepare
        # their per-agent mounts.
        enabled: list[str] = []
        all_mounts: list[tuple[Path, str]] = []
        ctx = _AdapterContext(
            container=container,
            workdir=workdir,
            host_throwaway_dir=host_throwaway_dir,
            host_claude_dotjson=host_claude_dotjson,
        )
        # Everything between mkdtemp above and the workspace object taking
        # ownership of host_throwaway_dir (via `cls(...)` below) must remove
        # the throwaway credential copies on failure; otherwise a failed
        # `docker run` (or a bad host auth dir) leaks staged auth material
        # under /tmp.
        try:
            # Phase 4: iterate the adapter registry (not the closed `AGENTS`
            # tuple) so a 4th agent becomes enable-able purely by registering
            # its adapter in `_ADAPTERS`, without editing this loop.
            for agent in _ADAPTERS:
                adapter = _ADAPTERS[agent]
                src = host_auth.get(agent)
                if src is None:
                    continue
                mounts = adapter.prepare_host_auth(Path(src), ctx)
                if not mounts:
                    continue
                enabled.append(agent)
                for _mount_id, pair in mounts.items():
                    all_mounts.append(pair)

            if not enabled:
                raise ValueError("start_workspace called with no enabled agents (host_auth empty)")

            # Provision the workspace's backing target WITHOUT credential
            # bind mounts (Phase 2: docker-out-of-docker fix). Bind-mounting
            # `-v host:container` requires the *outer* docker daemon to
            # resolve `host` on its own filesystem — that breaks when this
            # driver itself runs inside a container, where the throwaway
            # staging dir is only visible to the driver's own mount
            # namespace, not the sibling daemon's. Instead, credentials are
            # pushed into the running target below via the executor
            # `Environment.start()` returns (see `_transfer_path_to_
            # container`), which always targets the right backend
            # regardless of where the driver process lives.
            if environment is None:
                environment = DockerEnvironment(name=container, image=image, workdir=workdir)
            executor: CommandExecutor = environment.start()

            # Target is up; transfer each prepared credential file/dir
            # into it over the executor seam instead of bind-mounting.
            for host_path, container_path in all_mounts:
                _transfer_path_to_container(executor, host_path, container_path)
                _secure_container_path(executor, container_path, is_dir=host_path.is_dir())
        except Exception:
            # Best-effort: provisioning can fail after the target is
            # created (e.g. start failure), so tear it down too.
            try:
                if environment is not None:
                    environment.stop()
            except Exception:
                # Best-effort cleanup only; don't let a failed/wedged
                # teardown mask the original failure being re-raised below.
                logger.warning("environment.stop() failed during start_workspace cleanup", exc_info=True)
            shutil.rmtree(host_throwaway_dir, ignore_errors=True)
            raise

        # Container is up; bootstrap tmux + one window per enabled agent.
        ws = cls(
            name=name,
            container=container,
            image=image,
            workdir=workdir,
            tmux_size=tmux_size,
            host_throwaway_dir=host_throwaway_dir,
            enabled_agents=tuple(enabled),
            executor=executor,
            environment=environment,
        )
        # Per-agent launch options. Today only claude has plugin-dir
        # support; codex/gemini ignore the kwarg with `del plugin_dirs`.
        # If other agents grow a plugin loading mechanism, plumb their
        # own list through here.
        ws._launch_extras = {"claude": list(claude_plugin_dirs or [])}
        try:
            ws._bootstrap_tmux_and_launch(startup_timeout_s, strict_startup)
        except Exception:
            ws.stop()
            raise
        return ws

    def _bootstrap_tmux_and_launch(
        self,
        startup_timeout_s: float,
        strict_startup: bool,
    ) -> None:
        cols, rows = self.tmux_size
        first = self.enabled_agents[0]
        # Create the session with the first agent's window name.
        self._sessions[first].start(cols, rows)
        # Create additional windows for the rest.
        for agent in self.enabled_agents[1:]:
            self._sessions[agent].start(cols, rows, as_new_window=True)

        # Launch each agent's CLI in its window, then wait until each pane
        # reports `is_started()` (M1 cross-review fix). Each adapter
        # exposes a startup-phase predicate that recognizes its welcome
        # screen — for claude this differs from the strict post-turn
        # `is_ready` because the welcome pane shows a placeholder `Try …`
        # in the input box; for codex/gemini, is_started == is_ready. This
        # replaces the prior `_wait_for_text(expects_welcome_marker)` and
        # removes the codex `gpt-` substring flake EXP-06 documented as a
        # benign warning.
        for agent in self.enabled_agents:
            adapter = _ADAPTERS[agent]
            extras = self._launch_extras.get(agent) or None
            adapter.launch_in_window(
                self.container,
                self.workdir,
                plugin_dirs=extras,
                executor=self.executor,
            )
            self._started[agent] = True
            self.startup_status[agent] = self._wait_for_started(agent, startup_timeout_s)

        failed = {a: r for a, r in self.startup_status.items() if not r.ready}
        if failed:
            if strict_startup:
                raise StartupReadinessError(self.startup_status)
            logger.warning(
                "start_workspace: %d agent(s) not ready within %.1fs (strict_startup=False): %s",
                len(failed),
                startup_timeout_s,
                sorted(failed),
            )

    def _wait_for_started(self, agent: str, timeout_s: float) -> AwaitResult:
        """Block until `agent`'s pane reports `is_started()`, or timeout."""
        adapter = _ADAPTERS[agent]
        session = self._sessions[agent]
        start = time.monotonic()
        deadline = start + timeout_s
        pane = ""
        while time.monotonic() < deadline:
            try:
                pane = session.capture_pane()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                # Phase 3: a single wedged/failed capture during startup
                # polling must not abort the whole wait — keep polling
                # until the overall `timeout_s` deadline.
                logger.warning("wait_for_started(%s): capture failed mid-poll: %s", agent, exc)
                time.sleep(0.5)
                continue
            # D-block-2 fix: predicate evaluated on the bottom-of-pane
            # tail so historical text in scrollback (now captured by
            # default) can't fool absence checks like
            # `"esc to interrupt" not in pane`.
            if adapter.is_started(_pane_tail(pane)):
                duration_ms = (time.monotonic() - start) * 1000
                return AwaitResult(
                    ready=True,
                    timed_out=False,
                    reason="ready",
                    duration_ms=duration_ms,
                    stable_polls_observed=1,
                    pane=pane,
                )
            time.sleep(0.5)
        duration_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "wait_for_started(%s) timed out after %.1fs",
            agent,
            timeout_s,
        )
        return AwaitResult(
            ready=False,
            timed_out=True,
            reason="timeout_never_ready",
            duration_ms=duration_ms,
            stable_polls_observed=0,
            pane=pane,
        )

    # -----------------------------------------------------------------------
    # The five public primitives

    def send_message(
        self,
        agent: AgentName,
        text: str,
        *,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> None:
        """Submit `text` to `agent`'s tmux pane using the per-agent submit pattern.

        Phase 3: `timeout_s` bounds each underlying tmux/docker-exec call
        (default `DEFAULT_EXEC_TIMEOUT_S`) so a wedged container can't hang
        this call forever. Payloads over `TMUX_SEND_KEYS_MAX_BYTES` are
        automatically staged via tmux's paste-buffer instead of raw
        `send-keys` (see `_tmux_send_literal`).
        """
        self._check_agent(agent)
        _ADAPTERS[agent].submit(self.container, text, executor=self.executor, timeout_s=timeout_s)

    def await_completion(
        self,
        agent: AgentName,
        timeout: float = 60.0,
        stable_polls: int = 4,
        poll_interval: float = 0.5,
        warmup: float = 2.0,
        poll_timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> AwaitResult:
        """Block until `agent` returns to a stable ready state, or `timeout` passes.

        EXP-05 codex cross-review M3: returns an `AwaitResult` mirroring
        `agentic_isolation.ExecuteResult` (`timed_out`/`reason`/`duration_ms`)
        so orchestrators can distinguish failure modes. Existing call sites
        that only need a boolean should use `result.ready`.

        Two layered checks make this robust against transient redraw
        frames that single-poll heuristics get fooled by:

        1. The adapter's per-agent `is_ready(pane)` heuristic must return
           True (these are the per-agent matrix predicates).
        2. The pane content must be **identical** across `stable_polls`
           consecutive observations separated by `poll_interval` seconds.

        Codex specifically motivates check (2): its `• Working (Ns ...)`
        timer updates each second, and tmux capture occasionally catches
        a frame between updates where `Working` is briefly absent — a
        naive `is_ready` poll then false-passes. Requiring content
        identity across N captures filters those transients out
        (a still-rendering TUI doesn't produce identical captures).

        `warmup` skips the pre-generation window (the small gap between
        `send_message` and the agent rendering its generation marker)
        so the first ready observation isn't a stale idle frame.

        `poll_timeout_s` (Phase 3) bounds each *individual* pane-capture
        call, distinct from the overall `timeout` deadline above: a single
        wedged `docker exec` no longer blocks past `poll_timeout_s` (default
        `DEFAULT_EXEC_TIMEOUT_S`), and a poll that fails/times out is
        treated as "not ready this round" rather than raising — the loop
        keeps polling until the overall `timeout` is reached.

        Returns an `AwaitResult`:
            - `.ready=True, .reason="ready"` when a stable ready state was
               reached;
            - `.ready=False, .timed_out=True, .reason="timeout_unstable"`
               when readiness was observed but never held stable;
            - `.ready=False, .timed_out=True, .reason="timeout_never_ready"`
               when readiness was never observed before deadline.
        """
        self._check_agent(agent)
        adapter = _ADAPTERS[agent]
        session = self._sessions[agent]
        start = time.monotonic()
        deadline = start + timeout
        time.sleep(warmup)
        # D-block-2 + D-block-3 fix: capture now returns the full scrollback,
        # so the readiness predicate AND stability comparison both operate
        # on the bottom-of-pane tail (last DEFAULT_TMUX_SIZE[1] lines).
        # Stability check on the full buffer would fail forever — any new
        # response token appended changes the buffer, even if the live TUI
        # at the bottom of the window has settled. Comparing tails matches
        # the pre-stress-fix semantics (the visible region is stable).
        last_tail: str | None = None
        consecutive_stable_ready = 0
        ever_ready = False
        pane = ""
        tail = ""
        while time.monotonic() < deadline:
            try:
                pane = session.capture_pane(timeout_s=poll_timeout_s)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                # Phase 3: a single failed/wedged poll must not abort the
                # whole await — treat it as "not ready this round" and keep
                # polling until the overall deadline above.
                logger.warning("await_completion(%s): capture failed/timed out mid-poll: %s", agent, exc)
                consecutive_stable_ready = 0
                last_tail = None
                time.sleep(poll_interval)
                continue
            tail = _pane_tail(pane)
            if adapter.is_ready(tail):
                ever_ready = True
                if tail == last_tail:
                    consecutive_stable_ready += 1
                    if consecutive_stable_ready >= stable_polls:
                        duration_ms = (time.monotonic() - start) * 1000
                        return AwaitResult(
                            ready=True,
                            timed_out=False,
                            reason="ready",
                            duration_ms=duration_ms,
                            stable_polls_observed=consecutive_stable_ready,
                            pane=pane,
                        )
                else:
                    consecutive_stable_ready = 0
            else:
                consecutive_stable_ready = 0
            last_tail = tail
            time.sleep(poll_interval)
        duration_ms = (time.monotonic() - start) * 1000
        reason = "timeout_unstable" if ever_ready else "timeout_never_ready"
        logger.warning(
            "await_completion(%s) timed out after %.1fs (stable_ready=%d, reason=%s)",
            agent,
            timeout,
            consecutive_stable_ready,
            reason,
        )
        return AwaitResult(
            ready=False,
            timed_out=True,
            reason=reason,
            duration_ms=duration_ms,
            stable_polls_observed=consecutive_stable_ready,
            pane=pane,
        )

    def capture_response(
        self,
        agent: AgentName,
        *,
        timeout_s: float | None = DEFAULT_EXEC_TIMEOUT_S,
    ) -> str:
        """Return the current contents of `agent`'s tmux pane.

        Phase 3: bounded by `timeout_s` (default `DEFAULT_EXEC_TIMEOUT_S`)
        so a wedged container can't hang this call forever.
        """
        self._check_agent(agent)
        return self._sessions[agent].capture_pane(timeout_s=timeout_s)

    def stop(self) -> None:
        """Tear down the backing target and remove throwaway credential
        copies.

        Delegates to `self.environment.stop()` when set (the normal path
        for anything returned by `start_workspace`). Falls back to the
        historical `docker rm -f` when `environment` is `None` — e.g. a
        workspace reconstructed by `_load_workspace`, which only persists
        identifiers, not live `Environment` objects.
        """
        if self.environment is not None:
            self.environment.stop()
        else:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self.container],
                    check=False,
                    capture_output=True,
                    timeout=DEFAULT_RUN_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                # Phase 3: bounded — a wedged `docker rm -f` must not hang
                # `stop()` forever. Still clean up the host-side throwaway dir.
                logger.warning("docker rm -f %s timed out during stop()", self.container)
        shutil.rmtree(self.host_throwaway_dir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Helpers

    def _check_agent(self, agent: str) -> None:
        if agent not in self.enabled_agents:
            raise ValueError(
                f"agent {agent!r} not enabled for workspace {self.name!r} "
                f"(enabled: {self.enabled_agents})"
            )


# ---------------------------------------------------------------------------
# CLI (for shell-script consumers — e.g., scripts/smoke.sh)


# Per-agent env var names for explicit host-credential paths. These take
# precedence over `$HOME/.{agent}` discovery and let callers run the driver
# from inside another container (docker-out-of-docker), where `$HOME` does
# not point at the operator's real credentials. Reported by Syntropic137
# integration e2e: with no $HOME match, every agent slot became None and
# `start_workspace` failed with `no enabled agents (host_auth empty)`.
_HOST_HOME_ENV = {
    "claude": "ITMUX_CLAUDE_HOME",
    "codex": "ITMUX_CODEX_HOME",
    "gemini": "ITMUX_GEMINI_HOME",
}

# Claude is special: the auth surface is BOTH `~/.claude/` AND `~/.claude.json`
# (EXP-05a). The directory is selected by ITMUX_CLAUDE_HOME above; this env var
# overrides the sibling-of-CLAUDE_HOME default for the dotjson file, in case
# the caller has them in non-default locations (e.g. mounted into a container
# at unrelated paths).
_HOST_CLAUDE_JSON_ENV = "ITMUX_CLAUDE_JSON"

# Colon-separated list of host paths to load as Claude Code plugin dirs
# (`claude --plugin-dir <path>` per entry). settings.json injection does
# NOT work for loading plugins into tmux-driven claude — the workflow-skills
# bridge experiment proved this. Surfaced by Syntropic137
# `feat/workflow-skills`, `docs/plans/workflow-skills.md` §9. Path syntax
# mirrors $PATH: `/p1:/p2:/p3`. Empty entries are silently dropped.
_CLAUDE_PLUGIN_DIRS_ENV = "ITMUX_CLAUDE_PLUGIN_DIRS"


def _default_host_auth_from_env() -> dict[str, Path | None]:
    """Build a host_auth dict honoring `ITMUX_{AGENT}_HOME` env vars first.

    Resolution per agent:
      1. `ITMUX_{AGENT}_HOME` if set (caller takes responsibility for the path
         existing; if set but missing, we still propagate `None` so the caller
         gets the same "agent disabled" outcome as without the env var).
      2. `$HOME/.{agent}` if the directory exists on disk.
      3. None — agent disabled.

    Missing dirs are dropped so callers can `if host_auth["codex"]:` without
    a stat — same shape as before this env-var support was added.
    """
    home = Path(os.path.expanduser("~"))
    out: dict[str, Path | None] = {}
    for agent in AGENTS:
        override = os.environ.get(_HOST_HOME_ENV[agent])
        if override:
            path = Path(override).expanduser()
            out[agent] = path if path.is_dir() else None
            continue
        fallback = home / f".{agent}"
        out[agent] = fallback if fallback.is_dir() else None
    return out


def _default_claude_plugin_dirs_from_env() -> list[Path]:
    """Parse `ITMUX_CLAUDE_PLUGIN_DIRS` (`:`-separated, like $PATH).

    Returns an empty list when the env var is unset or empty. The
    driver translates each path to a `claude --plugin-dir <path>` flag
    when launching the claude TUI inside the container. Paths point at
    HOST directories that the caller has already arranged to be mounted
    into the container at the same path (typical setup: the integrator
    bind-mounts `/opt/plugins` host-side into `/opt/plugins` container-
    side; the env var holds container-side paths because that's what
    `claude` resolves at launch time).

    No `is_dir()` check on the host side — these may be container-only
    paths that don't exist in the calling process's filesystem.
    """
    raw = os.environ.get(_CLAUDE_PLUGIN_DIRS_ENV, "")
    if not raw:
        return []
    return [Path(entry) for entry in raw.split(":") if entry]


def _default_claude_dotjson_from_env() -> Path | None:
    """Resolve `~/.claude.json` honoring `ITMUX_CLAUDE_JSON` first, then $HOME.

    Returning `None` when neither path resolves is fine — `_ClaudeAdapter`
    treats absent dotjson as "synthesize from scratch", which is the same
    behavior as a host that has `~/.claude/` but no sibling `~/.claude.json`
    (one of the EXP-05a matrix cells the adapter explicitly supports).
    """
    override = os.environ.get(_HOST_CLAUDE_JSON_ENV)
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    fallback = Path(os.path.expanduser("~")) / ".claude.json"
    return fallback if fallback.is_file() else None


_WORKSPACE_REGISTRY_DIR = Path(tempfile.gettempdir()) / "interactive-tmux-workspaces"

# Workspace names become registry filenames and reach `docker rm -f` /
# rmtree via the stored record. Constrain them to a strict allowlist so a
# crafted `--name` (absolute path, `..`, separators) cannot escape the
# registry dir and act on attacker-controlled records. Kept byte-identical
# to the Rust driver's `registry::validate_name`.
_WORKSPACE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _registry_path(name: str) -> Path:
    if name in (".", "..") or not _WORKSPACE_NAME_RE.fullmatch(name):
        raise ValueError(
            f"invalid workspace name {name!r}: must match [A-Za-z0-9_.-]+ and not be '.' or '..'"
        )
    return _WORKSPACE_REGISTRY_DIR / f"{name}.json"


def _save_workspace(ws: InteractiveTmuxWorkspace) -> None:
    path = _registry_path(ws.name)
    _WORKSPACE_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": ws.name,
        "container": ws.container,
        "image": ws.image,
        "workdir": ws.workdir,
        "tmux_size": list(ws.tmux_size),
        "host_throwaway_dir": str(ws.host_throwaway_dir),
        "enabled_agents": list(ws.enabled_agents),
    }
    path.write_text(json.dumps(payload, indent=2))


def _load_workspace(name: str) -> InteractiveTmuxWorkspace:
    path = _registry_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"no registered workspace {name!r} at {path}")
    p = json.loads(path.read_text())
    # Defense in depth: a record's own name must match the one requested,
    # so a swapped or planted file can't redirect the caller's intent.
    if p.get("name") != name:
        raise ValueError(
            f"workspace record at {path} has name {p.get('name')!r}, expected {name!r}"
        )
    return InteractiveTmuxWorkspace(
        name=p["name"],
        container=p["container"],
        image=p["image"],
        workdir=p["workdir"],
        tmux_size=tuple(p["tmux_size"]),  # type: ignore[arg-type]
        host_throwaway_dir=Path(p["host_throwaway_dir"]),
        enabled_agents=tuple(p["enabled_agents"]),
    )


def _forget_workspace(name: str) -> None:
    path = _registry_path(name)
    if path.exists():
        path.unlink()


def _cli() -> int:
    parser = argparse.ArgumentParser(prog="interactive_tmux")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s_start = sub.add_parser("start", help="start a workspace")
    s_start.add_argument("--name", required=True)
    s_start.add_argument("--image", default=DEFAULT_IMAGE)
    s_start.add_argument("--workdir", default="/workspace")
    s_start.add_argument(
        "--agents",
        default="claude,codex,gemini",
        help="comma-separated list of agents to enable (default: all three)",
    )
    s_start.add_argument(
        "--strict-startup",
        action="store_true",
        help="raise on any agent's startup readiness miss (default: lax — print "
        "structured per-agent status in the JSON output and exit non-zero "
        "only if no agent is ready)",
    )

    s_send = sub.add_parser("send", help="send a message to an agent")
    s_send.add_argument("--name", required=True)
    s_send.add_argument("--agent", required=True, choices=AGENTS)
    s_send.add_argument("--text", required=True)

    s_await = sub.add_parser("await", help="block until agent is ready or timeout")
    s_await.add_argument("--name", required=True)
    s_await.add_argument("--agent", required=True, choices=AGENTS)
    s_await.add_argument("--timeout", type=float, default=60.0)

    s_cap = sub.add_parser("capture", help="print captured pane contents")
    s_cap.add_argument("--name", required=True)
    s_cap.add_argument("--agent", required=True, choices=AGENTS)

    s_stop = sub.add_parser("stop", help="stop a workspace")
    s_stop.add_argument("--name", required=True)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.cmd == "start":
        host_auth_all = _default_host_auth_from_env()
        wanted = set(args.agents.split(","))
        host_auth = {a: (host_auth_all[a] if a in wanted else None) for a in AGENTS}
        try:
            ws = InteractiveTmuxWorkspace.start_workspace(
                name=args.name,
                host_auth=host_auth,
                image=args.image,
                workdir=args.workdir,
                strict_startup=args.strict_startup,
                # DooD fix: honor ITMUX_CLAUDE_JSON when the CLI is invoked
                # from inside another container where `$HOME/.claude.json`
                # is not the operator's actual file.
                host_claude_dotjson=_default_claude_dotjson_from_env(),
                # Plugin-dirs: honor ITMUX_CLAUDE_PLUGIN_DIRS (colon-separated)
                # so the launched `claude` TUI loads the requested plugin
                # directories. settings.json injection is silently ignored
                # by the TUI (Syntropic137 workflow-skills bridge).
                claude_plugin_dirs=_default_claude_plugin_dirs_from_env(),
            )
        except StartupReadinessError as exc:
            # M1: surface per-agent failure structurally instead of an
            # opaque non-zero exit. The CLI exit code is 3 (distinct from
            # 2 = await timeout) so smoke harnesses can tell them apart.
            print(
                json.dumps(
                    {
                        "error": "startup_readiness",
                        "startup_status": {a: r.to_dict() for a, r in exc.startup_status.items()},
                    }
                )
            )
            return 3
        _save_workspace(ws)
        print(
            json.dumps(
                {
                    "name": ws.name,
                    "container": ws.container,
                    "agents": list(ws.enabled_agents),
                    "startup_status": {a: r.to_dict() for a, r in ws.startup_status.items()},
                }
            )
        )
        # Exit non-zero only if NO agent reached ready — preserves the
        # historical "smoke continues to pass on benign per-agent misses"
        # behavior while exposing the structured status that the codex
        # cross-review (M1) called out as missing.
        all_failed = ws.startup_status and not any(r.ready for r in ws.startup_status.values())
        return 0 if not all_failed else 3

    if args.cmd == "send":
        ws = _load_workspace(args.name)
        ws.send_message(args.agent, args.text)
        return 0

    if args.cmd == "await":
        ws = _load_workspace(args.name)
        result = ws.await_completion(args.agent, timeout=args.timeout)
        # M3: emit the full structured result, not just `{"ready": bool}`.
        # Exit code stays bool-compatible so existing shells don't break.
        print(json.dumps({k: v for k, v in result.to_dict().items() if k != "pane"}))
        return 0 if result.ready else 2

    if args.cmd == "capture":
        ws = _load_workspace(args.name)
        sys.stdout.write(ws.capture_response(args.agent))
        return 0

    if args.cmd == "stop":
        try:
            ws = _load_workspace(args.name)
        except FileNotFoundError:
            return 0
        ws.stop()
        _forget_workspace(args.name)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(_cli())
