"""Integration test using real subagent recording.

This test validates the subagent observability feature using a real
recording captured from Claude CLI with concurrent subagents.

Recording: v2.0.76_claude-haiku-4-5_subagent-concurrent.jsonl
- 2 subagents spawned via Task tool
- Each subagent runs a Bash command
- Validates event detection, duration calculation, and summary metrics
"""

from pathlib import Path

from agentic_isolation.providers.claude_cli.event_parser import EventParser
from agentic_isolation.providers.claude_cli.types import EventType

# Path to recording fixture (relative to agentic-primitives root)
RECORDING_PATH = (
    Path(__file__).parent.parent.parent.parent.parent.parent
    / "providers"
    / "workspaces"
    / "claude-cli"
    / "fixtures"
    / "recordings"
    / "v2.0.76_claude-haiku-4-5_subagent-concurrent.jsonl"
)


class TestSubagentRecording:
    """Integration tests using real subagent recording."""

    def test_recording_exists(self) -> None:
        """Recording fixture should exist."""
        assert RECORDING_PATH.exists(), f"Recording not found: {RECORDING_PATH}"

    def test_subagent_events_detected(self) -> None:
        """Should detect SUBAGENT_STARTED and SUBAGENT_STOPPED events."""
        parser = EventParser("integration-test")

        started_count = 0
        stopped_count = 0

        with RECORDING_PATH.open() as f:
            for line in f:
                events = parser.parse_line(line)
                for event in events:
                    if event.event_type == EventType.SUBAGENT_STARTED:
                        started_count += 1
                    elif event.event_type == EventType.SUBAGENT_STOPPED:
                        stopped_count += 1

        assert started_count == 2, f"Expected 2 SUBAGENT_STARTED, got {started_count}"
        assert stopped_count == 2, f"Expected 2 SUBAGENT_STOPPED, got {stopped_count}"

    def test_summary_subagent_metrics(self) -> None:
        """Summary should include accurate subagent metrics."""
        parser = EventParser("integration-test")

        with RECORDING_PATH.open() as f:
            for line in f:
                parser.parse_line(line)

        summary = parser.get_summary()

        assert summary.subagent_count == 2
        assert len(summary.subagent_names) == 2
        assert "Run date command" in summary.subagent_names
        assert "Run whoami command" in summary.subagent_names

        # Verify tools tracked per subagent
        assert len(summary.tools_by_subagent) == 2
        for name, tools in summary.tools_by_subagent.items():
            assert "Bash" in tools, f"Subagent '{name}' should have used Bash"

    def test_cost_extracted(self) -> None:
        """Summary should include cost from result event."""
        parser = EventParser("integration-test")

        with RECORDING_PATH.open() as f:
            for line in f:
                parser.parse_line(line)

        summary = parser.get_summary()

        # From the recording: total_cost_usd: 0.064721
        assert summary.total_cost_usd is not None
        assert summary.total_cost_usd > 0.06, f"Expected cost > $0.06, got {summary.total_cost_usd}"

    def test_duration_extracted(self) -> None:
        """Summary should include duration from result event."""
        parser = EventParser("integration-test")

        with RECORDING_PATH.open() as f:
            for line in f:
                parser.parse_line(line)

        summary = parser.get_summary()

        # From the recording: duration_ms: 7423
        assert summary.duration_ms is not None
        assert summary.duration_ms > 7000, f"Expected duration > 7000ms, got {summary.duration_ms}"

    def test_subagent_duration_calculated(self) -> None:
        """Subagent STOPPED events should have duration calculated from offsets."""
        parser = EventParser("integration-test")

        stopped_events = []

        with RECORDING_PATH.open() as f:
            for line in f:
                events = parser.parse_line(line)
                for event in events:
                    if event.event_type == EventType.SUBAGENT_STOPPED:
                        stopped_events.append(event)

        assert len(stopped_events) == 2

        # At least one subagent should have non-zero duration
        # (depends on recording having _offset_ms in events)
        durations = [e.duration_ms for e in stopped_events if e.duration_ms is not None]
        assert len(durations) > 0, "Expected at least one subagent with duration_ms set"

    def test_full_session_flow(self) -> None:
        """Should correctly parse full session: start → subagents → complete."""
        parser = EventParser("integration-test")

        all_events = []
        with RECORDING_PATH.open() as f:
            for line in f:
                events = parser.parse_line(line)
                all_events.extend(events)

        # Check event sequence
        event_types = [e.event_type for e in all_events]

        # Should start with session_started
        assert EventType.SESSION_STARTED in event_types

        # Should have subagent events
        assert EventType.SUBAGENT_STARTED in event_types
        assert EventType.SUBAGENT_STOPPED in event_types

        # Should have tool events
        assert EventType.TOOL_EXECUTION_STARTED in event_types
        assert EventType.TOOL_EXECUTION_COMPLETED in event_types

        # Should end with session_completed
        assert event_types[-1] == EventType.SESSION_COMPLETED
