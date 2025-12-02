"""Tests for storage adapters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hooks_backend.models import HookEventStored
from hooks_backend.storage.jsonl import JSONLStorage


def make_event(session_id: str = "session-123") -> HookEventStored:
    """Create a test event."""
    return HookEventStored(
        event_id=f"event-{session_id}",
        event_type="session_started",
        session_id=session_id,
        workflow_id=None,
        phase_id=None,
        milestone_id=None,
        data={"key": "value"},
        timestamp=datetime.now(UTC),
    )


class TestJSONLStorage:
    """Tests for JSONLStorage."""

    @pytest.mark.asyncio
    async def test_store_creates_file(self, tmp_path: Path) -> None:
        """Test store creates the JSONL file."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        await storage.store([make_event()])

        assert path.exists()

    @pytest.mark.asyncio
    async def test_store_writes_jsonl(self, tmp_path: Path) -> None:
        """Test store writes events as JSONL."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        await storage.store([make_event("session-1")])
        await storage.store([make_event("session-2")])

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

        event1 = json.loads(lines[0])
        event2 = json.loads(lines[1])
        assert event1["session_id"] == "session-1"
        assert event2["session_id"] == "session-2"

    @pytest.mark.asyncio
    async def test_store_batch(self, tmp_path: Path) -> None:
        """Test storing a batch of events."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        events = [make_event(f"session-{i}") for i in range(10)]
        count = await storage.store(events)

        assert count == 10
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 10

    @pytest.mark.asyncio
    async def test_store_empty_list(self, tmp_path: Path) -> None:
        """Test storing empty list."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        count = await storage.store([])

        assert count == 0
        assert not path.exists()

    @pytest.mark.asyncio
    async def test_store_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test store creates parent directories."""
        path = tmp_path / "deep" / "nested" / "events.jsonl"
        storage = JSONLStorage(path=path)

        await storage.store([make_event()])

        assert path.exists()

    @pytest.mark.asyncio
    async def test_store_preserves_all_fields(self, tmp_path: Path) -> None:
        """Test store preserves all event fields."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        event = HookEventStored(
            event_id="event-123",
            event_type="tool_execution_started",
            session_id="session-456",
            workflow_id="workflow-789",
            phase_id="phase-1",
            milestone_id="milestone-1",
            data={"tool_name": "Write", "file_path": "app.py"},
            timestamp=datetime(2025, 12, 1, 10, 30, 0, tzinfo=UTC),
        )
        await storage.store([event])

        stored = json.loads(path.read_text().strip())
        assert stored["event_id"] == "event-123"
        assert stored["event_type"] == "tool_execution_started"
        assert stored["session_id"] == "session-456"
        assert stored["workflow_id"] == "workflow-789"
        assert stored["phase_id"] == "phase-1"
        assert stored["milestone_id"] == "milestone-1"
        assert stored["data"]["tool_name"] == "Write"

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, tmp_path: Path) -> None:
        """Test health check returns True for valid path."""
        path = tmp_path / "events.jsonl"
        storage = JSONLStorage(path=path)

        is_healthy = await storage.health_check()

        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_name_property(self, tmp_path: Path) -> None:
        """Test name property returns 'jsonl'."""
        storage = JSONLStorage(path=tmp_path / "events.jsonl")

        assert storage.name == "jsonl"


class TestStorageReturns:
    """Tests for storage return values."""

    @pytest.mark.asyncio
    async def test_store_returns_count(self, tmp_path: Path) -> None:
        """Test store returns the count of stored events."""
        storage = JSONLStorage(path=tmp_path / "events.jsonl")

        count = await storage.store([make_event()])
        assert count == 1

        count = await storage.store([make_event(), make_event()])
        assert count == 2
