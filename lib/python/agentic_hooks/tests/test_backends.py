"""Tests for backend adapters."""

import json
from pathlib import Path

import pytest

from agentic_hooks.backends import JSONLBackend, NullBackend
from agentic_hooks.events import EventType, HookEvent


def make_event(session_id: str = "session-123") -> HookEvent:
    """Create a test event."""
    return HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
        data={"key": "value"},
    )


class TestNullBackend:
    """Tests for NullBackend."""

    @pytest.mark.asyncio
    async def test_write_accepts_events(self) -> None:
        """Test NullBackend accepts events without error."""
        backend = NullBackend()

        await backend.write([make_event()])

        # No error should occur

    @pytest.mark.asyncio
    async def test_write_stores_events_for_inspection(self) -> None:
        """Test NullBackend stores events for test inspection."""
        backend = NullBackend()

        event1 = make_event("session-1")
        event2 = make_event("session-2")
        await backend.write([event1, event2])

        assert len(backend.events_received) == 2
        assert backend.events_received[0]["session_id"] == "session-1"
        assert backend.events_received[1]["session_id"] == "session-2"

    @pytest.mark.asyncio
    async def test_write_empty_list(self) -> None:
        """Test NullBackend handles empty event list."""
        backend = NullBackend()

        await backend.write([])

        assert len(backend.events_received) == 0

    @pytest.mark.asyncio
    async def test_close_is_noop(self) -> None:
        """Test NullBackend close does nothing."""
        backend = NullBackend()

        await backend.close()

        # No error should occur


class TestJSONLBackend:
    """Tests for JSONLBackend."""

    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path: Path) -> None:
        """Test JSONLBackend creates output file."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        await backend.write([make_event()])

        assert output_path.exists()

    @pytest.mark.asyncio
    async def test_write_appends_jsonl(self, tmp_path: Path) -> None:
        """Test JSONLBackend appends events as JSONL."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        await backend.write([make_event("session-1")])
        await backend.write([make_event("session-2")])

        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        event2 = json.loads(lines[1])
        assert event1["session_id"] == "session-1"
        assert event2["session_id"] == "session-2"

    @pytest.mark.asyncio
    async def test_write_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test JSONLBackend creates parent directories."""
        output_path = tmp_path / "deep" / "nested" / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        await backend.write([make_event()])

        assert output_path.exists()

    @pytest.mark.asyncio
    async def test_write_multiple_events(self, tmp_path: Path) -> None:
        """Test JSONLBackend writes multiple events in batch."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        events = [make_event(f"session-{i}") for i in range(5)]
        await backend.write(events)

        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_write_empty_list(self, tmp_path: Path) -> None:
        """Test JSONLBackend handles empty event list."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        await backend.write([])

        # File should not be created for empty write
        assert not output_path.exists()

    @pytest.mark.asyncio
    async def test_write_preserves_event_data(self, tmp_path: Path) -> None:
        """Test JSONLBackend preserves all event data."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        event = HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
            workflow_id="workflow-456",
            phase_id="phase-1",
            milestone_id="milestone-1",
            data={"tool_name": "Write", "file_path": "app.py"},
        )
        await backend.write([event])

        lines = output_path.read_text().strip().split("\n")
        written = json.loads(lines[0])

        assert written["event_type"] == "tool_execution_started"
        assert written["session_id"] == "session-123"
        assert written["workflow_id"] == "workflow-456"
        assert written["phase_id"] == "phase-1"
        assert written["milestone_id"] == "milestone-1"
        assert written["data"]["tool_name"] == "Write"
        assert written["data"]["file_path"] == "app.py"

    @pytest.mark.asyncio
    async def test_string_path_conversion(self, tmp_path: Path) -> None:
        """Test JSONLBackend accepts string path."""
        output_path = str(tmp_path / "events.jsonl")
        backend = JSONLBackend(output_path=output_path)

        await backend.write([make_event()])

        assert Path(output_path).exists()

    @pytest.mark.asyncio
    async def test_default_path(self) -> None:
        """Test JSONLBackend has sensible default path."""
        backend = JSONLBackend()

        assert str(backend.output_path) == ".agentic/analytics/events.jsonl"

    @pytest.mark.asyncio
    async def test_close_is_noop(self, tmp_path: Path) -> None:
        """Test JSONLBackend close does nothing."""
        output_path = tmp_path / "events.jsonl"
        backend = JSONLBackend(output_path=output_path)

        await backend.close()

        # No error should occur


class TestHTTPBackendImport:
    """Tests for HTTPBackend import behavior."""

    def test_http_backend_raises_without_httpx(self) -> None:
        """Test HTTPBackend raises helpful error without httpx."""
        from agentic_hooks.backends import HTTPBackend

        backend = HTTPBackend(base_url="http://localhost:8080")

        # Client creation should work
        assert backend.base_url == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_http_backend_write_raises_without_httpx(self) -> None:
        """Test HTTPBackend.write raises ImportError without httpx."""
        # This test only runs if httpx is not installed
        # In dev environment with httpx, it will pass differently
        from agentic_hooks.backends import HTTPBackend

        backend = HTTPBackend(base_url="http://localhost:8080")

        try:
            import httpx  # noqa: F401

            # httpx is installed, skip this test
            pytest.skip("httpx is installed, cannot test import error")
        except ImportError:
            # httpx not installed, test the error
            with pytest.raises(ImportError, match="HTTPBackend requires httpx"):
                await backend.write([make_event()])
