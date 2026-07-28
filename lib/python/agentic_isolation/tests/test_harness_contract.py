"""Contract tests for the per-harness plugin model. See issue #792.

Covers: HarnessPlugin and TranscriptSource are structurally satisfiable;
optional slots return None rather than raising; the registry round-trips.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_isolation.harnesses import (
    AgentName,
    HarnessPlugin,
    HarnessTranscript,
    TranscriptExtractionResult,
    TranscriptSource,
    get_harness,
    register_harness,
)


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
    @property
    def name(self) -> str:
        return "claude"

    def transcript_source(self, exec_fn: object) -> TranscriptSource | None:
        return _FakeSource()


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

    def test_result_success_flips_on_errors(self) -> None:
        assert TranscriptExtractionResult().success is True
        assert TranscriptExtractionResult(errors=["x"]).success is False

    def test_transcript_to_dict(self) -> None:
        t = HarnessTranscript(agent="claude", session_id="s1", lines=["{}"], source_path="/p")
        assert t.to_dict()["session_id"] == "s1"
