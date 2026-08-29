"""`run()`: orchestrates a single `AgentRunSpec` execution over an `ItmuxClient`.

Implements Plan 1b Task 4. This module is the glue between the
harness-neutral contract types (`AgentRecipe`, `AgentRunSpec`, `AgentRunResult`,
`AgentRunEvent`) and the concrete `itmux` subprocess client
(`itmux_client.py`): it maps a recipe onto `ItmuxClient.start()`
arguments, drives the `start -> send -> await -> capture -> stop`
sequence, emits live `AgentRunEvent`s at each orchestration boundary, and
supports two-tier cancellation (`graceful` / `hard`) via `CancelToken`.

Known gaps (documented rather than papered over):

- `ModelSpec.name` / `ModelSpec.effort` are carried on `AgentRecipe`
  but `itmux start` has no CLI flag or env var for model selection or
  reasoning effort yet. `recipe_to_start_args()` does not fabricate
  one; wiring this through is a follow-on once `itmux` grows the
  capability.
- `AgentRecipe.skills` are treated as already-resolved Claude Code
  plugin directory paths (passed straight through to
  `ITMUX_CLAUDE_PLUGIN_DIRS` via `ItmuxClient.start(claude_plugin_dirs=...)`).
  Resolving a skill *reference* (e.g. a marketplace slug) into a
  concrete plugin directory on disk is out of scope here - see Plan 1c
  / issue #772 (skills replace claude_plugins).
- `itmux` has no separate system-prompt channel; the only way to
  influence the harness's behavior is the chat text sent via
  `itmux send`. `build_submit_text()` documents how `append` and
  `replace` currently collapse to the same wire format as a result
  (see its docstring).
- `AgentRunSpec.credentials` and `AgentRunSpec.input_artifacts` are collected by
  the contract but NOT yet applied by `run()`. `itmux` currently
  sources credentials from the host environment
  (`ITMUX_CLAUDE_HOME` / `$HOME`), so per-`AgentRunSpec` credentials are
  ignored, and no input artifacts are staged into the workspace before
  the agent runs. Staging per-`AgentRunSpec` credentials and input
  artifacts into the workspace is a Plan 1b Task 5 (provider rewire)
  follow-on. Until then, `run()` deliberately does not read these two
  fields rather than silently half-applying them.
- Cancellation races a background `asyncio.to_thread` call against a
  cancel signal at each orchestration boundary. Python threads cannot
  be killed, so a `hard` cancel that fires while an itmux call is in
  flight does not interrupt that subprocess early. `run()` drains an
  in-flight `start` before calling `stop`, preventing a late container
  registration from being orphaned.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from typing import TypeVar, cast

from pydantic import BaseModel, ConfigDict

from agentic_isolation.agent_run_events import (
    AgentRunCancelMode,
    AgentRunEvent,
    AgentRunEventCallback,
    SessionEndEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from agentic_isolation.agent_run_result import AgentRunOutcome, AgentRunResult
from agentic_isolation.agent_run_spec import AgentRunSpec
from agentic_isolation.itmux_client import AwaitResult, ItmuxClient
from agentic_isolation.recipe import AgentRecipe

# `itmux start --startup-timeout` default: how long to wait for the
# harness process itself to come up in the pane before `start` gives
# up. This is distinct from `AgentRunSpec.limits.timeout_s`, which bounds
# how long we wait for the *agent* to finish the task (`await_ready`).
DEFAULT_STARTUP_TIMEOUT_S = 60.0

# Default `itmux await --timeout` when `AgentRunSpec.limits.timeout_s` is
# not set. `AgentRunSpec.limits.timeout_s`, when present, is authoritative
# and overrides this.
DEFAULT_AWAIT_TIMEOUT_S = 120.0

T = TypeVar("T")


class ItmuxStartArgs(BaseModel):
    """Pure mapping of an `AgentRecipe` (+ workspace image/workdir) onto
    the subset of `ItmuxClient.start()` keyword arguments the recipe
    determines.

    Deliberately does not carry `name`, `startup_timeout_s`, or
    `strict_startup` - those are run-level orchestration concerns, not
    something a recipe determines.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    image: str
    workdir: str
    # Tuples (not lists) for real immutability on this frozen model.
    agents: tuple[str, ...]
    claude_plugin_dirs: tuple[str, ...] | None = None


def recipe_to_start_args(recipe: AgentRecipe, *, image: str, workdir: str) -> ItmuxStartArgs:
    """Map an `AgentRecipe` onto `ItmuxStartArgs`.

    - `recipe.agent` becomes the single-element `agents` list (`itmux`
      supports multiple agents per workspace, but a recipe describes
      exactly one harness).
    - `recipe.skills` becomes `claude_plugin_dirs`, but only for the
      `claude` agent (Codex has no plugin-dir mechanism in `itmux`
      today) and only when non-empty. Each skill entry is treated as
      an already-resolved plugin directory path, not a skill
      reference to be looked up - see the module docstring.
    - `recipe.model` (name + effort) is intentionally NOT mapped to
      anything: `itmux` has no flag or env var for it yet. This is a
      known, documented gap, not an oversight.
    """
    claude_plugin_dirs = (
        tuple(recipe.skills) if recipe.agent == "claude" and recipe.skills else None
    )
    return ItmuxStartArgs(
        image=image,
        workdir=workdir,
        agents=(recipe.agent,),
        claude_plugin_dirs=claude_plugin_dirs,
    )


def build_submit_text(recipe: AgentRecipe, task: str) -> str:
    """Build the text submitted to the harness via `itmux send`.

    Interpretation:

    - No `system_instructions`: submit `task` verbatim.
    - `mode="append"`: the harness's own default system prompt (if
      any) still applies inside the container; we additionally stack
      `content` ahead of `task` in the single chat-text channel `itmux
      send` exposes, so the harness sees the extra instructions before
      the task.
    - `mode="replace"`: conceptually, `content` should replace the
      harness's default system prompt rather than stack on top of it.
      `itmux` has no separate system-prompt channel today - only
      `send`'s chat text - so there is no way to actually suppress the
      harness's own default from here. The submitted prompt is still
      `task`, with `content` applied as leading instructions, which
      means `replace` currently produces the *same* wire text as
      `append`. The distinction is preserved in the model (and this
      function) so that once a harness adapter gains a real
      system-prompt flag (e.g. `claude --system-prompt` vs
      `--append-system-prompt`), `replace` is the one that maps onto
      the non-stacking flag and `append` onto the stacking one. Do not
      collapse the two `SystemInstructions.mode` branches into one at
      the call site; keep the (currently identical) branches in this
      function so that future harness-specific divergence has a single
      place to land.
    """
    instructions = recipe.system_instructions
    if instructions is None:
        return task
    if instructions.mode == "append":
        return f"{instructions.content}\n\n{task}"
    # mode == "replace" - see docstring: same wire text as "append"
    # given itmux's current single-channel `send`, documented gap.
    return f"{instructions.content}\n\n{task}"


class CancelToken:
    """Two-tier cooperative cancellation signal for `run()`.

    `request("graceful")` asks the run to stop after the current
    orchestration step completes, still collecting a best-effort
    partial `AgentRunResult` (a final `capture` is still performed).

    `request("hard")` asks the run to stop immediately: no further
    `itmux` calls are made after the request is observed, only
    `client.stop()` runs (via `run()`'s `finally`).

    Requesting `hard` after `graceful` upgrades the request; the
    reverse is a no-op (`hard` already wins - a run cannot be
    downgraded back to graceful once hard has been requested).
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._mode: AgentRunCancelMode | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def request(self, mode: AgentRunCancelMode) -> None:
        with self._lock:
            if self._mode == "hard":
                return
            self._mode = mode
            loop = self._loop

        if loop is None:
            # No waiter has bound the token to an event loop yet. There are no
            # Event waiters to wake, so setting it directly is safe.
            self._event.set()
        else:
            loop.call_soon_threadsafe(self._event.set)

    @property
    def mode(self) -> AgentRunCancelMode | None:
        with self._lock:
            return self._mode

    async def wait(self) -> AgentRunCancelMode:
        with self._lock:
            self._loop = asyncio.get_running_loop()
            requested = self._mode is not None
        if requested:
            self._event.set()
        await self._event.wait()
        with self._lock:
            assert self._mode is not None
            return self._mode


class _HardCancelRequested(Exception):
    """Internal signal: a hard cancel was observed before or during an
    itmux call. Caught at the top of `run()` to build a minimal
    `AgentRunResult` without performing any further itmux calls.
    """


def _emit(on_event: AgentRunEventCallback | None, event: AgentRunEvent) -> None:
    if on_event is not None:
        on_event(event)


async def _call(
    cancel: CancelToken | None,
    inflight: list[asyncio.Task[object]],
    fn: Callable[..., T],
    *args: object,
    **kwargs: object,
) -> T:
    """Run a blocking `ItmuxClient` call in a thread, racing it against
    `cancel`.

    - If `cancel` already reports `hard` before the call even starts,
      raise `_HardCancelRequested` immediately without invoking `fn`.
    - If `cancel` reports `hard` while the call is in flight, register
      the still-running task in `inflight` (so `run()`'s teardown can
      DRAIN it - await its completion - BEFORE calling `stop`) and
      raise `_HardCancelRequested`. The background thread cannot be
      killed (see module docstring), so draining is how we guarantee an
      in-flight `start` finishes registering the container before we
      tear it down; it also observes any exception the abandoned task
      raises, avoiding an unobserved-task warning.
    - If `cancel` reports `graceful` (before or during the call),
      let the call run to completion and return its result normally;
      graceful cancellation only takes effect at the caller's
      post-await checkpoint, not by aborting in-flight calls.
    - If `cancel` is `None`, just await the call.
    """
    if cancel is not None and cancel.mode == "hard":
        raise _HardCancelRequested()

    call_task: asyncio.Task[T] = asyncio.ensure_future(asyncio.to_thread(fn, *args, **kwargs))
    if cancel is None:
        return await call_task

    cancel_task: asyncio.Task[AgentRunCancelMode] = asyncio.ensure_future(cancel.wait())
    done, _pending = await asyncio.wait(
        {call_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
    )
    if call_task in done:
        cancel_task.cancel()
        return call_task.result()

    # cancel_task fired first.
    cancel_task.cancel()
    if cancel.mode == "hard":
        # Do NOT abandon the in-flight thread: hand it to run() to drain
        # before teardown, so `start` finishes registering the container
        # before `stop` runs. cast() is needed because `asyncio.Task[T]`
        # is invariant in T and does not widen to `asyncio.Task[object]`.
        inflight.append(cast("asyncio.Task[object]", call_task))
        raise _HardCancelRequested()
    # graceful: let the in-flight call finish and use its result.
    return await call_task


async def run(
    spec: AgentRunSpec,
    *,
    client: ItmuxClient,
    on_event: AgentRunEventCallback | None = None,
    image: str,
    workdir: str = "/workspace",
    name: str | None = None,
    cancel: CancelToken | None = None,
) -> AgentRunResult:
    """Execute `spec` over `client`, driving `start -> send -> await ->
    capture -> stop` and emitting `AgentRunEvent`s at each step boundary.

    `spec.limits.timeout_s`, when set, is authoritative for the
    `await_ready` call (overrides `DEFAULT_AWAIT_TIMEOUT_S`).

    Always tears the workspace down via `client.stop(name)` in a
    `finally` - unconditionally and best-effort - so no orphaned
    workspace is left behind even when `client.start()` itself raises
    (the real `itmux` registers the container before failing agent
    readiness), when `await_ready` raises, or when cancellation is
    requested.
    """
    workspace_name = name if name is not None else f"run-{uuid.uuid4().hex[:12]}"
    recipe = spec.recipe
    agent = recipe.agent
    start_args = recipe_to_start_args(recipe, image=image, workdir=workdir)
    await_timeout_s = (
        spec.limits.timeout_s
        if spec.limits is not None and spec.limits.timeout_s is not None
        else DEFAULT_AWAIT_TIMEOUT_S
    )
    # In-flight itmux calls abandoned by a hard cancel. Drained (awaited)
    # before teardown so, e.g., an in-flight `start` finishes registering
    # the container before `stop` runs - otherwise `stop` could return
    # NotFound-success and the container would leak.
    inflight: list[asyncio.Task[object]] = []
    # Tracks the currently-open tool boundary so a failure can close it
    # with a matching `ToolEndEvent(success=False)` before propagating,
    # instead of leaving live consumers with a permanently-open tool.
    open_tool: str | None = None

    async def boundary(tool_name: str, fn: Callable[..., T], *args: object, **kwargs: object) -> T:
        nonlocal open_tool
        _emit(on_event, ToolStartEvent(tool_name=tool_name, tool_use_id=workspace_name))
        open_tool = tool_name
        result = await _call(cancel, inflight, fn, *args, **kwargs)
        # On success the caller emits the ToolEnd (await's success flag
        # reflects readiness, not just "did not raise"), so only clear
        # the open-tool marker here.
        open_tool = None
        return result

    def emit_tool_end(tool_name: str, *, success: bool) -> None:
        _emit(
            on_event,
            ToolEndEvent(tool_name=tool_name, tool_use_id=workspace_name, success=success),
        )

    try:
        try:
            await boundary(
                "itmux.start",
                client.start,
                workspace_name,
                image=start_args.image,
                workdir=start_args.workdir,
                agents=list(start_args.agents),
                startup_timeout_s=DEFAULT_STARTUP_TIMEOUT_S,
                strict_startup=True,
                claude_plugin_dirs=(
                    list(start_args.claude_plugin_dirs)
                    if start_args.claude_plugin_dirs is not None
                    else None
                ),
            )
            emit_tool_end("itmux.start", success=True)

            submit_text = build_submit_text(recipe, spec.task)
            await boundary("itmux.send", client.send, workspace_name, agent, submit_text)
            emit_tool_end("itmux.send", success=True)

            await_result: AwaitResult = await boundary(
                "itmux.await",
                client.await_ready,
                workspace_name,
                agent,
                timeout_s=await_timeout_s,
            )
            emit_tool_end("itmux.await", success=await_result.ready)

            # Sampled once after `await_ready` returns: a graceful cancel
            # requested up to this point still gets one final `capture`
            # (below) before `run()` returns a partial result.
            graceful_cancelled = cancel is not None and cancel.mode == "graceful"

            session_log: str = await boundary(
                "itmux.capture", client.capture, workspace_name, agent
            )
            emit_tool_end("itmux.capture", success=True)

            if graceful_cancelled:
                success = False
                summary = (
                    "run cancelled (graceful): partial result collected after last completed step"
                )
            else:
                success = await_result.ready
                summary = (
                    "run completed"
                    if success
                    else f"agent did not become ready: {await_result.reason}"
                )

            result = AgentRunResult(
                result=AgentRunOutcome(success=success, summary=summary),
                session_log=session_log,
            )
            _emit(on_event, SessionEndEvent(success=success))
            return result
        except _HardCancelRequested:
            # Close the interrupted tool boundary and the session so live
            # consumers never see a permanently-open tool/session.
            if open_tool is not None:
                emit_tool_end(open_tool, success=False)
                open_tool = None
            _emit(on_event, SessionEndEvent(success=False))
            return AgentRunResult(
                result=AgentRunOutcome(
                    success=False, summary="run cancelled (hard): no result collected"
                ),
                session_log="",
            )
        except Exception:
            # Any itmux boundary raised (e.g. `start` exit 3, `await`
            # failure). Close the open tool with success=False and end
            # the session before propagating, so the live-event stream is
            # never left dangling. Then re-raise - the caller still sees
            # the real exception.
            if open_tool is not None:
                emit_tool_end(open_tool, success=False)
                open_tool = None
            _emit(on_event, SessionEndEvent(success=False))
            raise
    finally:
        # Drain any in-flight itmux call abandoned by a hard cancel BEFORE
        # tearing down. An in-flight `start` must finish registering the
        # container before `stop` runs, or `stop` returns NotFound-success
        # and the container leaks. Draining also observes exceptions the
        # abandoned task raised (no unobserved-task warning).
        for task in inflight:
            try:
                await task
            except Exception:  # noqa: BLE001 - draining a best-effort abandoned call
                pass
        # Unconditional, best-effort teardown. The real `itmux` binary
        # CREATES and REGISTERS the container before it checks agent
        # startup readiness, then exits non-zero (exit 3) if an agent
        # fails to become ready - the common failure - so `client.start()`
        # can raise with a live container behind it. `itmux stop` on an
        # unregistered name is NotFound-tolerant (exit 0), so calling it
        # even when nothing was created is safe. Errors here are swallowed
        # so a teardown failure never masks the run's real outcome.
        try:
            await asyncio.to_thread(client.stop, workspace_name)
        except Exception:  # noqa: BLE001 - best-effort teardown must not mask the run outcome
            pass
