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
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

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
    "run_agent",
]


# ---------------------------------------------------------------------------
# Contract models (mirror `contract.rs` serde field names exactly).
# ---------------------------------------------------------------------------

# `frozen=True` mirrors the immutability of the Rust structs; `extra="forbid"`
# mirrors serde's `#[serde(deny_unknown_fields)]` so a typo'd or stale field
# fails loudly instead of being silently ignored.
_CONTRACT_CONFIG = ConfigDict(frozen=True, extra="forbid")


class AgentRunOutcome(BaseModel):
    """The success/failure verdict for a run (Rust ``AgentRunOutcome``)."""

    model_config = _CONTRACT_CONFIG

    success: bool
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
    seq: int
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
    success: bool = False
    output_summary: str | None = None


class TokenUsageEvent(_RunEventEnvelope):
    """``type: "token_usage"`` payload."""

    type: Literal["token_usage"] = "token_usage"
    input_tokens: int
    output_tokens: int
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

_DEFAULT_KILL_GRACE_S = 5.0


def _terminate_process_group(
    proc: subprocess.Popen[str],
    *,
    grace_s: float = _DEFAULT_KILL_GRACE_S,
) -> None:
    """Signal the child's whole process group: ``SIGTERM`` then ``SIGKILL``.

    The child is started with ``start_new_session=True`` so it leads its own
    process group; signalling the group reaches the Rust process AND any
    ``docker exec`` children it spawned, so nothing is left orphaned.
    """
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return

    try:
        proc.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
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
    argv = [itmux_bin, "run", "--recipe", str(recipe), "--task", task]
    if image is not None:
        argv += ["--image", image]
    # `--json` is a clap `ArgAction::Set` bool (default true): it REQUIRES an
    # explicit value, so pass `--json true` rather than a bare `--json` flag.
    argv += ["--json", "true"]

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

    timed_out = threading.Event()
    watchdog: threading.Timer | None = None
    if timeout is not None:

        def _on_timeout() -> None:
            timed_out.set()
            _terminate_process_group(proc)

        watchdog = threading.Timer(timeout, _on_timeout)
        watchdog.daemon = True
        watchdog.start()

    result: AgentRunResult | None = None
    returncode: int = 0
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
        returncode = proc.wait()
    except BaseException:
        # KeyboardInterrupt, timeout-driven pipe close, parse failure, or any
        # other error: tear the whole process group down before propagating so
        # we never leave the Rust process (or its docker children) orphaned.
        _terminate_process_group(proc)
        raise
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if proc.poll() is None:
            _terminate_process_group(proc)
        stderr_thread.join(timeout=_DEFAULT_KILL_GRACE_S)

    stderr_text = "".join(stderr_chunks)

    if timed_out.is_set():
        raise ItmuxRunError(
            f"itmux run timed out after {timeout}s",
            returncode=returncode,
            stderr=stderr_text,
        )
    if result is None:
        if returncode != 0:
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
    return result
