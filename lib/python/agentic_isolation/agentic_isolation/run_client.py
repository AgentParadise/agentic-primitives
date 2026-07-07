"""Thin Python client for the Rust ``itmux run`` binary (Plan B, Task 7).

This module is deliberately *thin*: it owns no orchestration and no business
logic. All of that lives in the Rust ``itmux run`` subcommand. The client's
sole responsibilities are:

1. Mirror the wire contract (`AgentRunSpec` / `AgentRunResult` / `AgentRunEvent`)
   as strict Pydantic v2 models whose field names match the Rust serde names
   exactly. See the authoritative source at
   ``providers/workspaces/interactive-tmux/driver-rs/src/run/contract.rs`` and
   the generated JSON schema under ``.../driver-rs/docs/contract/``.
2. Spawn ``itmux run`` in JSON mode, stream the stdout event JSONL, parse each
   line into a typed :data:`AgentRunEvent`, and return the terminal
   :class:`AgentRunResult`.
3. Never leak a child process. The child (and any ``docker exec`` grandchildren
   it spawns) runs in its own process group; on cancel / crash / timeout the
   whole group is signalled ``SIGTERM`` then, after a grace period, ``SIGKILL``
   (R10 process-group cleanup).

Supersedes the hand-written Python contract proposed in #240 - that contract is
replaced by this Rust-mirrored one and #240 is closed separately.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    TypeAdapter,
    ValidationError,
)

__all__ = [
    "AgentRunOutcome",
    "ObservabilityBundle",
    "AgentRunResult",
    "ToolStartEvent",
    "ToolEndEvent",
    "TokenUsageEvent",
    "SessionEndEvent",
    "ResultEvent",
    "AgentRunEvent",
    "ItmuxRunError",
    "ItmuxRunRequest",
    "build_run_argv",
    "run_agent",
]


_ALLOWED_SECRET_KEYS: frozenset[str] = frozenset(
    {"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_AUTH_FILE"}
)


@dataclass(frozen=True)
class ItmuxRunRequest:
    """Credential-safe input for building an ``itmux run`` command."""

    recipe: Path
    task: str
    image: str | None = None
    env_file: Path | None = None
    credentials: Mapping[str, str] | None = None
    allow_host_auth_fallback: bool = False


def build_run_argv(request: ItmuxRunRequest, *, binary: str = "itmux") -> list[str]:
    """Build argv without placing credential values in it."""

    argv = [binary, "run", "--recipe", str(request.recipe), "--task", request.task]
    if request.image is not None:
        argv += ["--image", request.image]
    if request.env_file is not None:
        argv += ["--env-file", str(request.env_file)]
    if request.allow_host_auth_fallback:
        argv.append("--allow-host-auth-fallback")
    argv += ["--json", "true"]
    return argv


def _render_env_file(credentials: Mapping[str, str]) -> str:
    """Render allowlisted credentials as a shell-compatible private env file."""

    lines: list[str] = []
    for key, value in credentials.items():
        if key in _ALLOWED_SECRET_KEYS:
            escaped = value.replace("'", "'\\\\''")
            lines.append(f"{key}='{escaped}'")
    return "\n".join(lines) + ("\n" if lines else "")


@contextmanager
def _materialized_env_file(credentials: Mapping[str, str]) -> Iterator[Path]:
    """Materialize credentials to a 0600 file and remove it after the run."""

    fd, name = tempfile.mkstemp(prefix="itmux-run-creds-", suffix=".env")
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_render_env_file(credentials))
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Contract models (mirror `contract.rs` serde field names exactly).
# ---------------------------------------------------------------------------

# `frozen=True` mirrors the immutability of the Rust structs; `extra="forbid"`
# mirrors serde's `#[serde(deny_unknown_fields)]` so a typo'd or stale field
# fails loudly instead of being silently ignored.
_CONTRACT_CONFIG = ConfigDict(frozen=True, extra="forbid")

# Rust `u64` fields (schema `minimum:0`). `strict=True` refuses lax coercion
# (e.g. the string "1" -> 1) so malformed lines are rejected exactly as serde
# would reject them; `ge=0` enforces the unsigned lower bound. `bool` fields use
# `StrictBool` so the string "false" is rejected rather than coerced to a bool.
_U64 = Annotated[int, Field(strict=True, ge=0)]


class AgentRunOutcome(BaseModel):
    """The success/failure verdict for a run (Rust ``AgentRunOutcome``)."""

    model_config = _CONTRACT_CONFIG

    success: StrictBool
    summary: str


class ObservabilityBundle(BaseModel):
    """Plan 3 placeholder bundle (Rust ``ObservabilityBundle``)."""

    model_config = _CONTRACT_CONFIG

    name: str = ""
    # serde: `serde_json::Value` defaulting to null -> arbitrary JSON, default None.
    data: JsonValue = None


class AgentRunResult(BaseModel):
    """Terminal result of ``itmux run`` (Rust ``AgentRunResult``)."""

    model_config = _CONTRACT_CONFIG

    result: AgentRunOutcome
    # serde `PathBuf` serializes as a string; default empty list.
    output_artifacts: list[str] = Field(default_factory=list)
    session_log: str
    observability: ObservabilityBundle | None = None


class _RunEventEnvelope(BaseModel):
    """Common envelope fields flattened onto every ``AgentRunEvent`` line."""

    model_config = _CONTRACT_CONFIG

    run_id: str
    seq: _U64
    ts: str


class ToolStartEvent(_RunEventEnvelope):
    """``type: "tool_start"`` payload."""

    type: Literal["tool_start"] = "tool_start"
    tool_name: str
    tool_input: JsonValue = None


class ToolEndEvent(_RunEventEnvelope):
    """``type: "tool_end"`` payload."""

    type: Literal["tool_end"] = "tool_end"
    tool_name: str
    success: StrictBool = False
    output_summary: str | None = None


class TokenUsageEvent(_RunEventEnvelope):
    """``type: "token_usage"`` payload."""

    type: Literal["token_usage"] = "token_usage"
    input_tokens: _U64
    output_tokens: _U64
    cost_usd: float | None = None


class SessionEndEvent(_RunEventEnvelope):
    """``type: "session_end"`` terminal lifecycle payload."""

    type: Literal["session_end"] = "session_end"
    outcome: AgentRunOutcome


class ResultEvent(_RunEventEnvelope):
    """``type: "result"`` final-result delivery envelope."""

    type: Literal["result"] = "result"
    result: AgentRunResult


# Internally-tagged discriminated union on the ``type`` field, mirroring the
# Rust ``#[serde(tag = "type")]`` enum. Pydantic uses the ``type`` discriminator
# to pick exactly one variant, and each variant's ``extra="forbid"`` rejects any
# stray key - the same guarantee serde's per-variant `deny_unknown_fields` gives.
AgentRunEvent = Annotated[
    ToolStartEvent | ToolEndEvent | TokenUsageEvent | SessionEndEvent | ResultEvent,
    Field(discriminator="type"),
]

_EVENT_ADAPTER: TypeAdapter[AgentRunEvent] = TypeAdapter(AgentRunEvent)


def parse_event(line: str) -> AgentRunEvent:
    """Parse one JSONL line of ``itmux run`` stdout into a typed event.

    Raises :class:`ItmuxRunError` if the line is not a valid ``AgentRunEvent``.
    """
    try:
        return _EVENT_ADAPTER.validate_json(line)
    except ValidationError as exc:
        raise ItmuxRunError(f"unparseable itmux run event: {line!r}") from exc


# ---------------------------------------------------------------------------
# Error type.
# ---------------------------------------------------------------------------


class ItmuxRunError(RuntimeError):
    """Raised when an ``itmux run`` invocation fails to produce a valid result.

    Covers: non-zero exit with no terminal result, unparseable stdout, a
    missing terminal result event, and run timeout.
    """

    def __init__(
        self,
        message: str,
        *,
        returncode: int | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Process-group cleanup (R10).
# ---------------------------------------------------------------------------

# Grace for crash / timeout / cancel teardown: the Rust leader may be mid-run
# and needs time after SIGTERM to tear its container down before we SIGKILL.
_DEFAULT_KILL_GRACE_S = 5.0
# Grace once a terminal result has already been delivered: the leader has
# finished its work (the orchestrator tears the container down BEFORE emitting
# the result) and is exiting, so only a short SIGTERM->SIGKILL window is needed.
_RESULT_TEARDOWN_GRACE_S = 0.5
# Chunk the grace sleep so we do not oversleep a short grace.
_GRACE_SLEEP_CHUNK_S = 0.05


def _killpg_quiet(pgid: int, sig: int) -> bool:
    """Signal a process group, swallowing "already gone" errors.

    Returns ``True`` if the signal was delivered (group still existed),
    ``False`` if the group was already gone or the call was rejected.
    """
    try:
        os.killpg(pgid, sig)
        return True
    except (ProcessLookupError, OSError):
        return False


def _terminate_process_group(
    proc: subprocess.Popen[str],
    *,
    grace_s: float = _DEFAULT_KILL_GRACE_S,
) -> None:
    """Tear the child's whole process group down, kill-before-reap.

    The child is started with ``start_new_session=True`` so it leads its own
    process group whose pgid equals the leader pid. Signalling the group reaches
    the Rust process AND any ``docker exec`` grandchildren it spawned.

    Ordering (codex must-fix 1+2, refined):

    1. ``SIGTERM`` the whole group FIRST so the Rust leader can run its own
       graceful container teardown; a premature ``SIGKILL`` would orphan the
       docker CONTAINER (the orchestrator tears it down on graceful signals,
       see #248).
    2. Wait a bounded grace period WITHOUT reaping the leader.
    3. ``SIGKILL`` the whole group to reap any survivor (a docker-exec
       grandchild can outlive the leader).
    4. ONLY THEN reap the leader zombie.

    PID-reuse safety - the load-bearing invariant: the leader must stay
    UNREAPED (alive or zombie) until AFTER the final group signal. An unreaped
    leader keeps its pid (== pgid) reserved by the kernel, so every ``killpg``
    below provably targets OUR group and can never hit a recycled pgid. This is
    why the grace phase must NOT call ``proc.poll()`` / ``proc.wait()`` /
    ``os.waitpid`` - reaping the zombie frees the pid and the pgid could be
    recycled by a concurrent fork before step 3. ``killpg(pgid, 0)`` also cannot
    detect "descendants gone" while the unreaped zombie still occupies the
    group, so there is no correct non-reaping early exit: we simply sleep the
    (short) grace. Teardown latency is an acceptable trade for the guarantee.
    The early ``returncode`` guard covers a second teardown pass: if the leader
    was already reaped, never signal its possibly-recycled pgid again.
    """
    # Guard: if the leader has already been reaped, its pid (== pgid) may have
    # been recycled by the kernel - never signal it again.
    if proc.returncode is not None:
        return

    # start_new_session=True guarantees pgid == leader pid.
    pgid = proc.pid

    # 1. Graceful group termination first.
    _killpg_quiet(pgid, signal.SIGTERM)

    # 2. Bounded grace, WITHOUT reaping (see the PID-reuse invariant above).
    deadline = time.monotonic() + grace_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(_GRACE_SLEEP_CHUNK_S, remaining))

    # 3. Force-kill the whole group. Provably safe: the still-unreaped leader
    #    has kept the pgid reserved to us. Any surviving grandchild dies here.
    _killpg_quiet(pgid, signal.SIGKILL)

    # 4. Reap the leader LAST. Grandchildren SIGKILL'd above are orphaned to
    #    init, which reaps them.
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def run_agent(
    recipe: Path,
    task: str,
    *,
    image: str | None = None,
    itmux_bin: str = "itmux",
    on_event: Callable[[AgentRunEvent], None] | None = None,
    timeout: float | None = None,
    env_file: Path | None = None,
    credentials: Mapping[str, str] | None = None,
    allow_host_auth_fallback: bool = False,
) -> AgentRunResult:
    """Run a recipe via ``itmux run`` and return its terminal result.

    Spawns ``itmux run --recipe <recipe> --task <task> [--image <image>]
    --json true`` in its own process group, streams the stdout event JSONL,
    invokes ``on_event`` once per parsed :data:`AgentRunEvent`, and returns the
    :class:`AgentRunResult` carried by the terminal ``result``-payload event.

    Args:
        recipe: Path to a recipe directory (Plan A shape).
        task: Task text handed to the recipe's default agent.
        image: Optional container image override.
        itmux_bin: Path or name of the ``itmux`` binary (default ``"itmux"``).
        on_event: Optional callback invoked once per streamed event.
        timeout: Optional wall-clock timeout (seconds) for the whole run.

    Raises:
        ItmuxRunError: on non-zero exit with no result, unparseable output,
            a missing terminal result, or timeout.
    """
    if credentials is not None and env_file is not None:
        raise ValueError("set only one of env_file or credentials")
    if credentials is not None:
        with _materialized_env_file(credentials) as materialized:
            return run_agent(
                recipe,
                task,
                image=image,
                itmux_bin=itmux_bin,
                on_event=on_event,
                timeout=timeout,
                env_file=materialized,
                allow_host_auth_fallback=allow_host_auth_fallback,
            )

    argv = build_run_argv(
        ItmuxRunRequest(
            recipe=recipe,
            task=task,
            image=image,
            env_file=env_file,
            allow_host_auth_fallback=allow_host_auth_fallback,
        ),
        binary=itmux_bin,
    )

    # `start_new_session=True` -> os.setsid in the child: it leads a new process
    # group so cleanup can signal the whole tree (Rust + docker exec children).
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        # Drain stderr concurrently so a chatty child (human logs go to stderr)
        # can never deadlock against a full pipe while we read stdout.
        if proc.stderr is not None:
            for line in proc.stderr:
                stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # Teardown must run at most once. The watchdog (on timeout) and the finally
    # block are two independent teardown paths on different threads; if both ran
    # a full SIGTERM->grace->SIGKILL->reap, one could reap the leader while the
    # other is still sleeping its grace, freeing the pgid before that thread's
    # SIGKILL (the exact PID-reuse race we must avoid). The lock + once-flag
    # serialize them: the first caller does the whole teardown holding the lock;
    # the second blocks, then sees it is done and returns.
    teardown_lock = threading.Lock()
    torn_down = False

    def _teardown(grace_s: float) -> None:
        nonlocal torn_down
        with teardown_lock:
            if torn_down:
                return
            _terminate_process_group(proc, grace_s=grace_s)
            torn_down = True

    timed_out = threading.Event()
    watchdog: threading.Timer | None = None
    if timeout is not None:

        def _on_timeout() -> None:
            timed_out.set()
            # Timeout/cancel path: the leader may be mid-run - give it the full
            # grace to tear its container down after SIGTERM.
            _teardown(_DEFAULT_KILL_GRACE_S)

        watchdog = threading.Timer(timeout, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

    result: AgentRunResult | None = None
    try:
        assert proc.stdout is not None  # PIPE is always set above
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            event = parse_event(line)
            if on_event is not None:
                on_event(event)
            if isinstance(event, ResultEvent):
                result = event.result
                # The Rust contract guarantees the process exits after the
                # terminal result event. We break rather than draining to EOF so
                # a child that emits the result then hangs cannot block us when
                # `timeout` is None - liveness must not depend on that guarantee.
                break
    finally:
        if watchdog is not None:
            watchdog.cancel()
        # Kill-before-reap: tear the whole process group down BEFORE reaping the
        # leader (see `_terminate_process_group`). Runs on every exit path -
        # normal return, timeout, parse error, KeyboardInterrupt. A delivered
        # result means the leader has finished and is exiting, so a short grace
        # suffices; otherwise use the full crash/cancel grace.
        _teardown(_RESULT_TEARDOWN_GRACE_S if result is not None else _DEFAULT_KILL_GRACE_S)
        # Join the stderr drain only AFTER the group is dead - otherwise a
        # surviving grandchild holding the stderr pipe could block the join.
        stderr_thread.join(timeout=_DEFAULT_KILL_GRACE_S)

    returncode = proc.returncode
    stderr_text = "".join(stderr_chunks)

    # Result wins over a simultaneous timeout (Claude nit 1): if a valid terminal
    # result was delivered, return it even if the watchdog fired in the same
    # instant. Only treat the run as timed out / failed when there is no result.
    if result is not None:
        return result
    if timed_out.is_set():
        raise ItmuxRunError(
            f"itmux run timed out after {timeout}s",
            returncode=returncode,
            stderr=stderr_text,
        )
    if returncode is not None and returncode != 0:
        raise ItmuxRunError(
            f"itmux run exited with code {returncode} and produced no result",
            returncode=returncode,
            stderr=stderr_text,
        )
    raise ItmuxRunError(
        "itmux run produced no terminal result event",
        returncode=returncode,
        stderr=stderr_text,
    )
