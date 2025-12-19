"""Tests for BatchBuffer."""

import asyncio

import pytest

from agentic_events import BatchBuffer, enrich_event, parse_jsonl_line


class TestBatchBuffer:
    """Tests for BatchBuffer class."""

    @pytest.mark.asyncio
    async def test_add_event(self):
        """Test adding an event to the buffer."""
        buffer = BatchBuffer(flush_size=10)
        await buffer.add({"event_type": "test"})
        assert buffer.size == 1

    @pytest.mark.asyncio
    async def test_flush_on_size(self):
        """Test that buffer flushes when reaching flush_size."""
        flushed_events: list[list[dict]] = []

        async def on_flush(events):
            flushed_events.append(events)

        buffer = BatchBuffer(on_flush=on_flush, flush_size=3)

        await buffer.add({"event_type": "test1"})
        await buffer.add({"event_type": "test2"})
        assert len(flushed_events) == 0  # Not yet flushed

        await buffer.add({"event_type": "test3"})
        assert len(flushed_events) == 1  # Flushed!
        assert len(flushed_events[0]) == 3

    @pytest.mark.asyncio
    async def test_manual_flush(self):
        """Test manual flush."""
        buffer = BatchBuffer(flush_size=100)

        await buffer.add({"event_type": "test1"})
        await buffer.add({"event_type": "test2"})

        events = await buffer.flush()
        assert len(events) == 2
        assert buffer.size == 0

    @pytest.mark.asyncio
    async def test_periodic_flush(self):
        """Test periodic flush task."""
        flushed_events: list[list[dict]] = []

        async def on_flush(events):
            flushed_events.append(events)

        buffer = BatchBuffer(on_flush=on_flush, flush_size=1000, flush_interval=0.05)

        await buffer.start()
        await buffer.add({"event_type": "test"})

        # Wait for periodic flush
        await asyncio.sleep(0.1)

        await buffer.stop()

        assert len(flushed_events) >= 1

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining(self):
        """Test that stop() flushes remaining events."""
        flushed_events: list[list[dict]] = []

        async def on_flush(events):
            flushed_events.append(events)

        buffer = BatchBuffer(on_flush=on_flush, flush_size=1000)

        await buffer.add({"event_type": "test"})
        await buffer.stop()

        assert len(flushed_events) == 1

    @pytest.mark.asyncio
    async def test_add_many(self):
        """Test adding multiple events at once."""
        buffer = BatchBuffer(flush_size=100)

        events = [{"event_type": f"test{i}"} for i in range(10)]
        await buffer.add_many(events)

        assert buffer.size == 10


class TestParseJsonlLine:
    """Tests for parse_jsonl_line function."""

    def test_parse_valid_event(self):
        """Test parsing a valid event line."""
        line = '{"event_type": "test", "session_id": "123"}'
        event = parse_jsonl_line(line)
        assert event is not None
        assert event["event_type"] == "test"

    def test_parse_empty_line(self):
        """Test parsing an empty line."""
        assert parse_jsonl_line("") is None
        assert parse_jsonl_line("   ") is None

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        assert parse_jsonl_line("not json") is None
        assert parse_jsonl_line("{invalid}") is None

    def test_parse_non_event_json(self):
        """Test parsing JSON without event_type."""
        assert parse_jsonl_line('{"foo": "bar"}') is None
        assert parse_jsonl_line("123") is None
        assert parse_jsonl_line('"string"') is None


class TestEnrichEvent:
    """Tests for enrich_event function."""

    def test_enrich_with_execution_context(self):
        """Test enriching event with execution context."""
        event = {"event_type": "test", "session_id": "123"}
        enriched = enrich_event(
            event,
            execution_id="exec-456",
            phase_id="phase-789",
            container_id="container-abc",
        )

        assert enriched["execution_id"] == "exec-456"
        assert enriched["phase_id"] == "phase-789"
        assert enriched["container_id"] == "container-abc"
        # Original event should be unchanged
        assert "execution_id" not in event

    def test_enrich_adds_timestamp_if_missing(self):
        """Test that enrichment adds timestamp if missing."""
        event = {"event_type": "test"}
        enriched = enrich_event(event)
        assert "timestamp" in enriched

    def test_enrich_preserves_existing_timestamp(self):
        """Test that enrichment preserves existing timestamp."""
        event = {"event_type": "test", "timestamp": "2025-01-01T00:00:00Z"}
        enriched = enrich_event(event)
        assert enriched["timestamp"] == "2025-01-01T00:00:00Z"
