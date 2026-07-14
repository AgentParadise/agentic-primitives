"""Tests for the `run()` orchestrator (Plan 1b Task 4).

Uses a FAKE `ItmuxClient` (records calls, returns canned
`StartReport`/`AwaitResult`/pane text) - no `itmux` binary or Docker is
invoked. Covers: pure mappers (`recipe_to_start_args`,
`build_submit_text`), call ordering, live event delivery, and the
two-tier (`graceful` / `hard`) cancellation contract.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import pytest

from agentic_isolation.agent_run_events import (
    AgentRunEvent,
    SessionEndEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from agentic_isolation.agent_run_result import AgentRunResult
from agentic_isolation.agent_run_spec import AgentRunCredentials, AgentRunLimits, AgentRunSpec
from agentic_isolation.itmux_client import AwaitResult, ItmuxClient, StartReport
from agentic_isolation.recipe import AgentRecipe, ModelSpec, SystemInstructions
from agentic_isolation.workspace_run import (
    CancelToken,
    ItmuxStartArgs,
    build_submit_text,
    recipe_to_start_args,
    run,
)

CLAUDE_RECIPE = AgentRecipe(
    name="quick-fix",
    agent="claude",
    model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
    skills=("/plugins/skill-a", "/plugins/skill-b"),
)

CODEX_RECIPE = AgentRecipe(
    name="quick-fix-codex",
    agent="codex",
    model=ModelSpec(name="openai/gpt-5-codex", effort="medium"),
)


def _make_start_report(name: str, *, ready: bool = True) -> StartReport:
    return StartReport(
        name=name,
        container=f"interactive-tmux-{name}",
        agents=["claude"],
        startup_status={},
    )


def _make_await_result(*, ready: bool) -> AwaitResult:
    return AwaitResult(
        ready=ready,
        timed_out=not ready,
        reason="ready" if ready else "timed_out",
        duration_ms=42.0,
        stable_polls_observed=1,
    )


@dataclass
class FakeItmuxClient:
    """Records calls in order; returns canned results. Not a subclass of
    `ItmuxClient` - `run()` only depends on the method surface. Cast via
    `as_client()` at call sites so `run()`'s real signature is exercised.
    """

    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = field(default_factory=list)
    await_ready_value: AwaitResult = field(default_factory=lambda: _make_await_result(ready=True))
    captured_pane: str = "session pane output"
    on_send: Callable[[], None] | None = None
    raise_on_await: Exception | None = None
    raise_on_start: Exception | None = None
    raise_on_stop: Exception | None = None
    # When set, `start` blocks (in its worker thread) on this gate until
    # the test releases it - used to hold `start` in flight while a hard
    # cancel is requested, exercising the drain-before-teardown ordering.
    start_gate: threading.Event | None = None
    # Coarse lifecycle order (start begin/registered, stop) so tests can
    # assert that teardown happens AFTER an in-flight start registers.
    lifecycle: list[str] = field(default_factory=list)

    def start(self, name: str, **kwargs: object) -> StartReport:
        self.calls.append(("start", (name,), kwargs))
        self.lifecycle.append("start:begin")
        if self.start_gate is not None:
            self.start_gate.wait(timeout=5.0)
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.lifecycle.append("start:registered")
        return _make_start_report(name)

    def send(self, name: str, agent: str, text: str) -> None:
        self.calls.append(("send", (name, agent, text), {}))
        if self.on_send is not None:
            self.on_send()
        return None

    def await_ready(self, name: str, agent: str, **kwargs: object) -> AwaitResult:
        self.calls.append(("await_ready", (name, agent), kwargs))
        if self.raise_on_await is not None:
            raise self.raise_on_await
        return self.await_ready_value

    def capture(self, name: str, agent: str) -> str:
        self.calls.append(("capture", (name, agent), {}))
        return self.captured_pane

    def stop(self, name: str) -> None:
        self.calls.append(("stop", (name,), {}))
        self.lifecycle.append("stop")
        if self.raise_on_stop is not None:
            raise self.raise_on_stop
        return None


def _make_spec(recipe: AgentRecipe, *, task: str = "do the thing") -> AgentRunSpec:
    return AgentRunSpec(recipe=recipe, task=task, credentials=AgentRunCredentials())


def as_client(fake: FakeItmuxClient) -> ItmuxClient:
    """`run()` is typed against the concrete `ItmuxClient`; `FakeItmuxClient`
    matches its method surface structurally but is not a subclass, so
    tests cast explicitly at the call boundary instead of scattering
    `# type: ignore` comments.
    """
    return cast(ItmuxClient, fake)


class TestRecipeToStartArgs:
    def test_claude_recipe_maps_agents_and_plugin_dirs(self) -> None:
        args = recipe_to_start_args(CLAUDE_RECIPE, image="img:latest", workdir="/workspace")
        assert args == ItmuxStartArgs(
            image="img:latest",
            workdir="/workspace",
            agents=("claude",),
            claude_plugin_dirs=("/plugins/skill-a", "/plugins/skill-b"),
        )

    def test_codex_recipe_has_no_plugin_dirs(self) -> None:
        args = recipe_to_start_args(CODEX_RECIPE, image="img:latest", workdir="/workspace")
        assert args.agents == ("codex",)
        assert args.claude_plugin_dirs is None

    def test_claude_recipe_without_skills_has_no_plugin_dirs(self) -> None:
        recipe = AgentRecipe(
            name="no-skills",
            agent="claude",
            model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
        )
        args = recipe_to_start_args(recipe, image="img:latest", workdir="/workspace")
        assert args.claude_plugin_dirs is None


class TestBuildSubmitText:
    def test_no_system_instructions_returns_task_verbatim(self) -> None:
        recipe = AgentRecipe(
            name="r",
            agent="claude",
            model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
        )
        assert build_submit_text(recipe, "fix the bug") == "fix the bug"

    def test_append_stacks_content_before_task(self) -> None:
        recipe = AgentRecipe(
            name="r",
            agent="claude",
            model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
            system_instructions=SystemInstructions(mode="append", content="Be terse."),
        )
        assert build_submit_text(recipe, "fix the bug") == "Be terse.\n\nfix the bug"

    def test_replace_currently_matches_append_wire_text(self) -> None:
        # Documented gap: itmux has no separate system-prompt channel,
        # so "replace" produces the same submitted text as "append"
        # today. See build_submit_text's docstring.
        recipe_append = AgentRecipe(
            name="r",
            agent="claude",
            model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
            system_instructions=SystemInstructions(mode="append", content="Be terse."),
        )
        recipe_replace = AgentRecipe(
            name="r",
            agent="claude",
            model=ModelSpec(name="anthropic/claude-opus-4-8", effort="low"),
            system_instructions=SystemInstructions(mode="replace", content="Be terse."),
        )
        assert build_submit_text(recipe_replace, "fix the bug") == build_submit_text(
            recipe_append, "fix the bug"
        )
        assert build_submit_text(recipe_replace, "fix the bug") == "Be terse.\n\nfix the bug"


class TestRunOrdering:
    async def test_run_calls_in_order_and_returns_result(self) -> None:
        client = FakeItmuxClient()
        spec = _make_spec(CLAUDE_RECIPE)

        result = await run(spec, client=as_client(client), image="img:latest", name="ws-1")

        call_names = [c[0] for c in client.calls]
        assert call_names == ["start", "send", "await_ready", "capture", "stop"]
        assert isinstance(result, AgentRunResult)
        assert result.session_log == client.captured_pane
        assert result.result.success is True

    async def test_run_reflects_not_ready_as_failure(self) -> None:
        client = FakeItmuxClient(await_ready_value=_make_await_result(ready=False))
        spec = _make_spec(CLAUDE_RECIPE)

        result = await run(spec, client=as_client(client), image="img:latest", name="ws-2")

        assert result.result.success is False

    async def test_stop_always_called_even_if_await_ready_raises(self) -> None:
        client = FakeItmuxClient(raise_on_await=RuntimeError("boom"))
        spec = _make_spec(CLAUDE_RECIPE)

        with pytest.raises(RuntimeError):
            await run(spec, client=as_client(client), image="img:latest", name="ws-3")

        call_names = [c[0] for c in client.calls]
        assert "stop" in call_names
        assert call_names[-1] == "stop"

    async def test_stop_called_when_start_raises(self) -> None:
        # The real itmux registers the container BEFORE checking agent
        # startup readiness, then exits non-zero if an agent fails to
        # boot - so `start()` can raise with a live container behind it.
        # Teardown must run unconditionally, not gated on a successful
        # start, or the container + registry entry leak.
        client = FakeItmuxClient(raise_on_start=RuntimeError("agent failed startup (exit 3)"))
        spec = _make_spec(CLAUDE_RECIPE)

        with pytest.raises(RuntimeError):
            await run(spec, client=as_client(client), image="img:latest", name="ws-leak")

        call_names = [c[0] for c in client.calls]
        assert call_names == ["start", "stop"]
        # stop was called with the same workspace name that start used.
        stop_call = next(c for c in client.calls if c[0] == "stop")
        assert stop_call[1] == ("ws-leak",)

    async def test_stop_error_is_swallowed_and_does_not_mask_run_outcome(self) -> None:
        # A teardown failure must not mask the run's real result.
        client = FakeItmuxClient(raise_on_stop=RuntimeError("stop failed"))
        spec = _make_spec(CLAUDE_RECIPE)

        result = await run(spec, client=as_client(client), image="img:latest", name="ws-10")

        assert result.result.success is True
        assert [c[0] for c in client.calls][-1] == "stop"

    async def test_timeout_s_from_limits_passed_to_await_ready(self) -> None:
        client = FakeItmuxClient()
        spec = AgentRunSpec(
            recipe=CLAUDE_RECIPE,
            task="do it",
            credentials=AgentRunCredentials(),
            limits=AgentRunLimits(timeout_s=17.0),
        )

        await run(spec, client=as_client(client), image="img:latest", name="ws-4")

        await_call = next(c for c in client.calls if c[0] == "await_ready")
        assert await_call[2]["timeout_s"] == 17.0


class TestRunEventsDelivery:
    async def test_on_event_receives_start_and_session_end(self) -> None:
        client = FakeItmuxClient()
        spec = _make_spec(CLAUDE_RECIPE)
        events: list[AgentRunEvent] = []

        await run(
            spec, client=as_client(client), on_event=events.append, image="img:latest", name="ws-5"
        )

        assert any(isinstance(e, ToolStartEvent) for e in events)
        assert any(isinstance(e, SessionEndEvent) for e in events)
        assert isinstance(events[-1], SessionEndEvent)
        assert events[-1].success is True

    async def test_on_event_receives_tool_end_pairs(self) -> None:
        client = FakeItmuxClient()
        spec = _make_spec(CLAUDE_RECIPE)
        events: list[AgentRunEvent] = []

        await run(
            spec, client=as_client(client), on_event=events.append, image="img:latest", name="ws-6"
        )

        starts = [e.tool_name for e in events if isinstance(e, ToolStartEvent)]
        ends = [e.tool_name for e in events if isinstance(e, ToolEndEvent)]
        assert starts == ["itmux.start", "itmux.send", "itmux.await", "itmux.capture"]
        assert ends == starts

    async def test_failure_closes_open_tool_and_session(self) -> None:
        # When an itmux boundary raises, the live stream must not be left
        # with a permanently-open tool/session: the interrupted tool gets
        # ToolEnd(success=False) and the session ends with
        # SessionEnd(success=False) before the exception propagates.
        client = FakeItmuxClient(raise_on_await=RuntimeError("await blew up"))
        spec = _make_spec(CLAUDE_RECIPE)
        events: list[AgentRunEvent] = []

        with pytest.raises(RuntimeError):
            await run(
                spec,
                client=as_client(client),
                on_event=events.append,
                image="img:latest",
                name="ws-fail",
            )

        # The last opened tool was itmux.await; it must be closed as a
        # failure, and the very last event is the failed SessionEnd.
        assert isinstance(events[-1], SessionEndEvent)
        assert events[-1].success is False
        last_await_end = [
            e for e in events if isinstance(e, ToolEndEvent) and e.tool_name == "itmux.await"
        ]
        assert last_await_end == [
            ToolEndEvent(tool_name="itmux.await", tool_use_id="ws-fail", success=False)
        ]
        # No dangling open await: exactly one start and one (failed) end.
        await_starts = [
            e for e in events if isinstance(e, ToolStartEvent) and e.tool_name == "itmux.await"
        ]
        assert len(await_starts) == 1


class TestCancellation:
    async def test_graceful_cancel_returns_partial_result_and_stops(self) -> None:
        cancel = CancelToken()

        def _request_graceful() -> None:
            cancel.request("graceful")

        client = FakeItmuxClient(on_send=_request_graceful)
        spec = _make_spec(CLAUDE_RECIPE)

        result = await run(
            spec, client=as_client(client), image="img:latest", name="ws-7", cancel=cancel
        )

        call_names = [c[0] for c in client.calls]
        # graceful still runs the remaining steps through one final
        # capture, then stops - no exception raised.
        assert call_names == ["start", "send", "await_ready", "capture", "stop"]
        assert result.result.success is False
        assert result.session_log == client.captured_pane

    async def test_hard_cancel_stops_immediately_without_capture(self) -> None:
        cancel = CancelToken()

        def _request_hard() -> None:
            cancel.request("hard")

        client = FakeItmuxClient(on_send=_request_hard)
        spec = _make_spec(CLAUDE_RECIPE)

        result = await run(
            spec, client=as_client(client), image="img:latest", name="ws-8", cancel=cancel
        )

        call_names = [c[0] for c in client.calls]
        assert call_names == ["start", "send", "stop"]
        assert "await_ready" not in call_names
        assert "capture" not in call_names
        assert result.result.success is False
        assert result.session_log == ""

    async def test_hard_cancel_emits_session_end(self) -> None:
        cancel = CancelToken()
        client = FakeItmuxClient(on_send=lambda: cancel.request("hard"))
        spec = _make_spec(CLAUDE_RECIPE)
        events: list[AgentRunEvent] = []

        await run(
            spec,
            client=as_client(client),
            on_event=events.append,
            image="img:latest",
            name="ws-9",
            cancel=cancel,
        )

        assert isinstance(events[-1], SessionEndEvent)
        assert events[-1].success is False

    async def test_hard_cancel_during_start_drains_before_teardown(self) -> None:
        # Orphan race: a hard cancel fires while `start` is still in
        # flight (thread blocked on the gate). Teardown MUST wait for
        # start to finish registering the container before calling stop -
        # otherwise stop returns NotFound-success and the container leaks.
        gate = threading.Event()
        cancel = CancelToken()
        client = FakeItmuxClient(start_gate=gate)
        spec = _make_spec(CLAUDE_RECIPE)

        run_task = asyncio.ensure_future(
            run(
                spec,
                client=as_client(client),
                image="img:latest",
                name="ws-race",
                cancel=cancel,
            )
        )

        # Wait until `start` is actually in flight (thread entered and is
        # blocked on the gate), then request the hard cancel.
        for _ in range(200):
            await asyncio.sleep(0.01)
            if client.lifecycle and client.lifecycle[0] == "start:begin":
                break
        assert client.lifecycle == ["start:begin"]

        cancel.request("hard")
        # Let the run loop observe the cancel and abandon the in-flight
        # start to the drain list. stop must NOT have run yet - start is
        # still blocked on the gate.
        await asyncio.sleep(0.02)
        assert "stop" not in client.lifecycle
        assert "start:registered" not in client.lifecycle

        # Release start; teardown drains it, THEN stops.
        gate.set()
        result = await run_task

        assert client.lifecycle == ["start:begin", "start:registered", "stop"]
        assert result.result.success is False
        assert "hard" in result.result.summary
