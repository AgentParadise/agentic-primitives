"""Tests demonstrating recording playback for testing.

These tests use a real recording captured from a Claude CLI session
to validate the event pipeline without making API calls.

Recording: v2.0.74_claude-sonnet-4-5_list-files.jsonl
Task: "List files in directory" - uses Bash tool
"""

from pathlib import Path

import pytest

from agentic_events import SessionPlayer, get_recordings_dir, load_recording

pytestmark = pytest.mark.integration

# Use fixture helpers for path resolution
FIXTURES_DIR = get_recordings_dir()
SAMPLE_RECORDING = FIXTURES_DIR / "v2.0.74_claude-sonnet-4-5_list-files.jsonl"


@pytest.fixture
def recording_exists():
    """Skip if recording doesn't exist."""
    if not SAMPLE_RECORDING.exists():
        pytest.skip(f"Recording not found: {SAMPLE_RECORDING}")
    return SAMPLE_RECORDING


@pytest.fixture
def list_files_player():
    """Load list-files recording using fixture helper."""
    try:
        return load_recording("list-files")
    except FileNotFoundError:
        pytest.skip("list-files recording not found")


class TestRecordingPlayback:
    """Tests using real recorded sessions."""

    def test_load_recording(self, recording_exists: Path):
        """Load a real recording and verify metadata."""
        player = SessionPlayer(recording_exists)

        # Verify metadata
        assert player.metadata.cli_version == "2.0.74"
        assert (
            "claude" in player.metadata.model.lower() or "sonnet" in player.metadata.model.lower()
        )
        assert player.metadata.event_count > 0
        assert player.session_id is not None

    def test_get_events_returns_correct_count(self, recording_exists: Path):
        """Events count matches metadata."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        assert len(events) == player.metadata.event_count

    def test_events_have_session_id(self, recording_exists: Path):
        """All events have session_id."""
        player = SessionPlayer(recording_exists)

        for event in player.get_events():
            assert "session_id" in event, f"Missing session_id in event: {event.get('type')}"

    def test_events_have_type(self, recording_exists: Path):
        """All events have a type field."""
        player = SessionPlayer(recording_exists)

        for event in player.get_events():
            # Events have either 'type' (CLI native) or 'event_type' (hooks)
            assert "type" in event or "event_type" in event

    def test_contains_tool_use(self, recording_exists: Path):
        """Recording contains tool use events (since it ran a Bash command)."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        # Look for tool_use in assistant messages
        tool_uses = []
        for event in events:
            if event.get("type") == "assistant":
                message = event.get("message", {})
                content = message.get("content", [])
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        tool_uses.append(item)

        assert len(tool_uses) > 0, "Expected at least one tool_use in recording"
        assert tool_uses[0].get("name") == "Bash", "Expected Bash tool to be used"

    def test_contains_tool_result(self, recording_exists: Path):
        """Recording contains tool result events."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        # Look for user messages with tool_result
        tool_results = [e for e in events if e.get("type") == "user"]

        assert len(tool_results) > 0, "Expected at least one tool result"

    def test_session_has_result(self, recording_exists: Path):
        """Recording ends with a result event."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        # Last event should be result
        result_events = [e for e in events if e.get("type") == "result"]
        assert len(result_events) == 1, "Expected exactly one result event"

        result = result_events[0]
        assert result.get("subtype") == "success"
        assert "duration_ms" in result
        assert "total_cost_usd" in result

    @pytest.mark.asyncio
    async def test_async_playback(self, recording_exists: Path):
        """Test async playback at high speed."""
        player = SessionPlayer(recording_exists)
        received = []

        async def emit(event):
            received.append(event)

        # Play at 10000x speed (instant)
        count = await player.play(emit_fn=emit, speed=10000)

        assert count == player.metadata.event_count
        assert len(received) == count

    def test_sync_playback(self, recording_exists: Path):
        """Test sync playback."""
        player = SessionPlayer(recording_exists)
        received = []

        count = player.play_sync(emit_fn=received.append)

        assert count == player.metadata.event_count
        assert len(received) == count


class TestEventExtraction:
    """Tests for extracting specific data from recordings."""

    def test_extract_session_id(self, recording_exists: Path):
        """Extract session ID from recording."""
        player = SessionPlayer(recording_exists)

        # Session ID should be in first system event
        events = player.get_events()
        system_event = next(e for e in events if e.get("type") == "system")

        assert "session_id" in system_event
        assert system_event["session_id"] == player.session_id

    def test_extract_model_info(self, recording_exists: Path):
        """Extract model info from recording."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        system_event = next(e for e in events if e.get("type") == "system")

        assert "model" in system_event
        assert "claude_code_version" in system_event

    def test_extract_available_tools(self, recording_exists: Path):
        """Extract available tools from init event."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        system_event = next(e for e in events if e.get("type") == "system")
        tools = system_event.get("tools", [])

        assert "Bash" in tools
        assert "Read" in tools
        assert "Write" in tools

    def test_extract_cost(self, recording_exists: Path):
        """Extract total cost from result event."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        result_event = next(e for e in events if e.get("type") == "result")
        cost = result_event.get("total_cost_usd", 0)

        # Should have a small cost
        assert cost > 0
        assert cost < 1.0  # Shouldn't be more than $1 for this simple task

    def test_extract_duration(self, recording_exists: Path):
        """Extract duration from result event."""
        player = SessionPlayer(recording_exists)
        events = player.get_events()

        result_event = next(e for e in events if e.get("type") == "result")
        duration = result_event.get("duration_ms", 0)

        # Should have reasonable duration
        assert duration > 0
        assert duration < 60000  # Less than 1 minute
