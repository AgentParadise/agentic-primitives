"""`run()`: orchestrates a single `RunSpec` execution over an `ItmuxClient`.

Implements Plan 1b Task 4. This module is the glue between the
harness-neutral contract types (`AgentRecipe`, `RunSpec`, `RunResult`,
`RunEvent`) and the concrete `itmux` subprocess client
(`itmux_client.py`): it maps a recipe onto `ItmuxClient.start()`
arguments, drives the `start -> send -> await -> capture -> stop`
sequence, emits live `RunEvent`s at each orchestration boundary, and
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
- `RunSpec.credentials` and `RunSpec.input_artifacts` are collected by
  the contract but NOT yet applied by `run()`. `itmux` currently
  sources credentials from the host environment
  (`ITMUX_CLAUDE_HOME` / `$HOME`), so per-`RunSpec` credentials are
  ignored, and no input artifacts are staged into the workspace before
  the agent runs. Staging per-`RunSpec` credentials and input
  artifacts into the workspace is a Plan 1b Task 5 (provider rewire)
  follow-on. Until then, `run()` deliberately does not read these two
  fields rather than silently half-applying them.
- Cancellation races a background `asyncio.to_thread` call against a
  cancel signal at each orchestration boundary. Python threads cannot
  be killed, so a `hard` cancel that fires *while* a blocking itmux
  subprocess call is in flight does not interrupt that subprocess call
  early - it only stops `run()` from waiting on or acting on its
  result, and skips all subsequent steps. The workspace is always
  torn down via `client.stop()` in a `finally` once `client.start()`
  has actually completed.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from agentic_isolation.itmux_client import AwaitResult, ItmuxClient
from agentic_isolation.recipe import AgentRecipe
from agentic_isolation.run_events import (
    CancelMode,
    EventCallback,
    RunEvent,
    SessionEndEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from agentic_isolation.run_result import RunOutcome, RunResult
from agentic_isolation.run_spec import RunSpec

# `itmux start --startup-timeout` default: how long to wait for the
# harness process itself to come up in the pane before `start` gives
# up. This is distinct from `RunSpec.limits.timeout_s`, which bounds
# how long we wait for the *agent* to finish the task (`await_ready`).
DEFAULT_STARTUP_TIMEOUT_S = 60.0

# Default `itmux await --timeout` when `RunSpec.limits.timeout_s` is
# not set. `RunSpec.limits.timeout_s`, when present, is authoritative
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
    agents: list[str]
    claude_plugin_dirs: list[str] | None = None


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
    claude_plugin_dirs = list(recipe.skills) if recipe.agent == "claude" and recipe.skills else None
    return ItmuxStartArgs(
        image=image,
        workdir=workdir,
        agents=[recipe.agent],
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
    partial `RunResult` (a final `capture` is still performed).

    `request("hard")` asks the run to stop immediately: no further
    `itmux` calls are made after the request is observed, only
    `client.stop()` runs (via `run()`'s `finally`).

    Requesting `hard` after `graceful` upgrades the request; the
    reverse is a no-op (`hard` already wins - a run cannot be
    downgraded back to graceful once hard has been requested).
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._mode: CancelMode | None = None

    def request(self, mode: CancelMode) -> None:
        if self._mode == "hard":
            return
        self._mode = mode
        self._event.set()

    @property
    def mode(self) -> CancelMode | None:
        return self._mode

    async def wait(self) -> CancelMode:
        await self._event.wait()
        assert self._mode is not None
        return self._mode


class _HardCancelRequested(Exception):
    """Internal signal: a hard cancel was observed before or during an
    itmux call. Caught at the top of `run()` to build a minimal
    `RunResult` without performing any further itmux calls.
    """


def _emit(on_event: EventCallback | None, event: RunEvent) -> None:
    if on_event is not None:
        on_event(event)


async def _call(
    cancel: CancelToken | None,
    fn: Callable[..., T],
    *args: object,
    **kwargs: object,
) -> T:
    """Run a blocking `ItmuxClient` call in a thread, racing it against
    `cancel`.

    - If `cancel` already reports `hard` before the call even starts,
      raise `_HardCancelRequested` immediately without invoking `fn`.
    - If `cancel` reports `hard` while the call is in flight, raise
      `_HardCancelRequested` without waiting for the call to finish
      (the background thread is not killed - see module docstring -
      but its result is discarded).
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

    cancel_task: asyncio.Task[CancelMode] = asyncio.ensure_future(cancel.wait())
    done, _pending = await asyncio.wait(
        {call_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
    )
    if call_task in done:
        cancel_task.cancel()
        return call_task.result()

    # cancel_task fired first.
    if cancel.mode == "hard":
        raise _HardCancelRequested()
    # graceful: let the in-flight call finish and use its result.
    return await call_task


async def run(
    spec: RunSpec,
    *,
    client: ItmuxClient,
    on_event: EventCallback | None = None,
    image: str,
    workdir: str = "/workspace",
    name: str | None = None,
    cancel: CancelToken | None = None,
) -> RunResult:
    """Execute `spec` over `client`, driving `start -> send -> await ->
    capture -> stop` and emitting `RunEvent`s at each step boundary.

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

    try:
        try:
            _emit(on_event, ToolStartEvent(tool_name="itmux.start", tool_use_id=workspace_name))
            await _call(
                cancel,
                client.start,
                workspace_name,
                image=start_args.image,
                workdir=start_args.workdir,
                agents=start_args.agents,
                startup_timeout_s=DEFAULT_STARTUP_TIMEOUT_S,
                strict_startup=True,
                claude_plugin_dirs=start_args.claude_plugin_dirs,
            )
            _emit(
                on_event,
                ToolEndEvent(tool_name="itmux.start", tool_use_id=workspace_name, success=True),
            )

            submit_text = build_submit_text(recipe, spec.task)
            _emit(on_event, ToolStartEvent(tool_name="itmux.send", tool_use_id=workspace_name))
            await _call(cancel, client.send, workspace_name, agent, submit_text)
            _emit(
                on_event,
                ToolEndEvent(tool_name="itmux.send", tool_use_id=workspace_name, success=True),
            )

            _emit(on_event, ToolStartEvent(tool_name="itmux.await", tool_use_id=workspace_name))
            await_result: AwaitResult = await _call(
                cancel,
                client.await_ready,
                workspace_name,
                agent,
                timeout_s=await_timeout_s,
            )
            _emit(
                on_event,
                ToolEndEvent(
                    tool_name="itmux.await",
                    tool_use_id=workspace_name,
                    success=await_result.ready,
                ),
            )

            # Sampled once after `await_ready` returns: a graceful cancel
            # requested up to this point still gets one final `capture`
            # (below) before `run()` returns a partial result.
            graceful_cancelled = cancel is not None and cancel.mode == "graceful"

            _emit(on_event, ToolStartEvent(tool_name="itmux.capture", tool_use_id=workspace_name))
            session_log: str = await _call(cancel, client.capture, workspace_name, agent)
            _emit(
                on_event,
                ToolEndEvent(tool_name="itmux.capture", tool_use_id=workspace_name, success=True),
            )

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

            result = RunResult(
                result=RunOutcome(success=success, summary=summary),
                session_log=session_log,
            )
            _emit(on_event, SessionEndEvent(success=success))
            return result
        except _HardCancelRequested:
            _emit(on_event, SessionEndEvent(success=False))
            return RunResult(
                result=RunOutcome(
                    success=False, summary="run cancelled (hard): no result collected"
                ),
                session_log="",
            )
    finally:
        # Unconditional, best-effort teardown. The real `itmux` binary
        # CREATES and REGISTERS the container before it checks agent
        # startup readiness, then exits non-zero (exit 3) if an agent
        # fails to become ready - the common failure. In that case
        # `client.start()` raised and `started` is still False, but the
        # container + registry entry already exist and would leak if we
        # gated teardown on `started`. `itmux stop` on an unregistered
        # name is NotFound-tolerant (exit 0), so calling it even when
        # nothing was created is safe. Errors here are swallowed so a
        # teardown failure never masks the run's real outcome (and this
        # also best-effort covers a hard cancel racing start).
        try:
            await asyncio.to_thread(client.stop, workspace_name)
        except Exception:  # noqa: BLE001 - best-effort teardown must not mask the run outcome
            pass
