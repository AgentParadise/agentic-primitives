"""Contract tests for the per-harness plugin model. See issue #792.

Covers: HarnessPlugin and TranscriptSource are structurally satisfiable;
optional slots return None rather than raising; the registry round-trips
and rejects names AgentName does not recognize; the exec_argv helper
shell-quotes argv exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from agentic_isolation.harnesses import (
    AgentName,
    ExecFn,
    HarnessPlugin,
    HarnessTranscript,
    TranscriptExtractionResult,
    TranscriptSource,
    exec_argv,
    get_harness,
    register_harness,
)
from agentic_isolation.providers.base import ExecuteResult


@dataclass
class _FakeSource:
    _agent: str = "claude"

    @property
    def agent(self) -> str:
        return self._agent

    async def extract(self) -> TranscriptExtractionResult:
        return TranscriptExtractionResult()


@dataclass
class _FakeHarness:
    _name: str = "claude"

    @property
    def name(self) -> str:
        return self._name

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        return _FakeSource()


class _RecordingExec:
    """Minimal stand-in for `Workspace.execute` / `WorkspaceProvider.execute`."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def __call__(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        self.commands.append(command)
        return ExecuteResult(exit_code=0, stdout="", stderr="")


class TestHarnessContract:
    def test_source_satisfies_protocol(self) -> None:
        assert isinstance(_FakeSource(), TranscriptSource)

    def test_harness_satisfies_protocol(self) -> None:
        assert isinstance(_FakeHarness(), HarnessPlugin)

    def test_agent_name_is_lenient(self) -> None:
        assert AgentName.parse("CLAUDE") is AgentName.CLAUDE
        assert AgentName.parse("unknown-harness") is None

    def test_registry_round_trips(self) -> None:
        register_harness(_FakeHarness())
        assert get_harness("claude") is not None
        assert get_harness("nope") is None

    def test_registry_rejects_names_agentname_does_not_know(self) -> None:
        """A harness must not register under a name the rest of the
        system (AgentName) would never recognize - see issue #792."""
        with pytest.raises(ValueError, match="unknown harness name"):
            register_harness(_FakeHarness(_name="not-a-real-harness"))

    def test_result_success_flips_on_errors(self) -> None:
        assert TranscriptExtractionResult().success is True
        assert TranscriptExtractionResult(errors=["x"]).success is False

    def test_transcript_to_dict(self) -> None:
        t = HarnessTranscript(agent="claude", session_id="s1", lines=["{}"], source_path="/p")
        assert t.to_dict()["session_id"] == "s1"

    async def test_exec_argv_shell_quotes_once(self) -> None:
        recorder = _RecordingExec()
        await exec_argv(recorder, ["echo", "hello world"])
        assert recorder.commands == ["echo 'hello world'"]
