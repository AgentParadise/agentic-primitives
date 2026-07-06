"""Tests for the `run()` orchestrator (Plan 1b Task 4).

Uses a FAKE `ItmuxClient` (records calls, returns canned
`StartReport`/`AwaitResult`/pane text) - no `itmux` binary or Docker is
invoked. Covers: pure mappers (`recipe_to_start_args`,
`build_submit_text`), call ordering, live event delivery, and the
two-tier (`graceful` / `hard`) cancellation contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import pytest

from agentic_isolation.itmux_client import AwaitResult, ItmuxClient, StartReport
from agentic_isolation.recipe import AgentRecipe, ModelSpec, SystemInstructions
from agentic_isolation.run_events import RunEvent, SessionEndEvent, ToolEndEvent, ToolStartEvent
from agentic_isolation.run_result import RunResult
from agentic_isolation.run_spec import RunCredentials, RunLimits, RunSpec
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
    skills=["/plugins/skill-a", "/plugins/skill-b"],
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

    def start(self, name: str, **kwargs: object) -> StartReport:
        self.calls.append(("start", (name,), kwargs))
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
        return None


def _make_spec(recipe: AgentRecipe, *, task: str = "do the thing") -> RunSpec:
    return RunSpec(recipe=recipe, task=task, credentials=RunCredentials())


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
            agents=["claude"],
            claude_plugin_dirs=["/plugins/skill-a", "/plugins/skill-b"],
        )

    def test_codex_recipe_has_no_plugin_dirs(self) -> None:
        args = recipe_to_start_args(CODEX_RECIPE, image="img:latest", workdir="/workspace")
        assert args.agents == ["codex"]
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
        assert isinstance(result, RunResult)
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

    async def test_timeout_s_from_limits_passed_to_await_ready(self) -> None:
        client = FakeItmuxClient()
        spec = RunSpec(
            recipe=CLAUDE_RECIPE,
            task="do it",
            credentials=RunCredentials(),
            limits=RunLimits(timeout_s=17.0),
        )

        await run(spec, client=as_client(client), image="img:latest", name="ws-4")

        await_call = next(c for c in client.calls if c[0] == "await_ready")
        assert await_call[2]["timeout_s"] == 17.0


class TestRunEventsDelivery:
    async def test_on_event_receives_start_and_session_end(self) -> None:
        client = FakeItmuxClient()
        spec = _make_spec(CLAUDE_RECIPE)
        events: list[RunEvent] = []

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
        events: list[RunEvent] = []

        await run(
            spec, client=as_client(client), on_event=events.append, image="img:latest", name="ws-6"
        )

        starts = [e.tool_name for e in events if isinstance(e, ToolStartEvent)]
        ends = [e.tool_name for e in events if isinstance(e, ToolEndEvent)]
        assert starts == ["itmux.start", "itmux.send", "itmux.await", "itmux.capture"]
        assert ends == starts


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
        events: list[RunEvent] = []

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
