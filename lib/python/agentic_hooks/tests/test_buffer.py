"""Tests for EventBuffer with batching logic."""

import asyncio

import pytest

from agentic_hooks.buffer import BufferConfig, EventBuffer
from agentic_hooks.events import EventType, HookEvent


def make_event(session_id: str = "session-123") -> HookEvent:
    """Create a test event."""
    return HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
    )


class TestBufferConfig:
    """Tests for BufferConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = BufferConfig()

        assert config.batch_size == 50
        assert config.flush_interval_seconds == 1.0
        assert config.max_buffer_size == 10000

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = BufferConfig(
            batch_size=100,
            flush_interval_seconds=0.5,
            max_buffer_size=5000,
        )

        assert config.batch_size == 100
        assert config.flush_interval_seconds == 0.5
        assert config.max_buffer_size == 5000


class TestEventBuffer:
    """Tests for EventBuffer."""

    @pytest.mark.asyncio
    async def test_add_single_event(self) -> None:
        """Test adding a single event to buffer."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        await buffer.add(make_event())

        assert buffer.pending_count == 1

    @pytest.mark.asyncio
    async def test_add_multiple_events(self) -> None:
        """Test adding multiple events to buffer."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        for i in range(10):
            await buffer.add(make_event(f"session-{i}"))

        assert buffer.pending_count == 10

    @pytest.mark.asyncio
    async def test_flush_returns_events(self) -> None:
        """Test flush returns all buffered events."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        for i in range(5):
            await buffer.add(make_event(f"session-{i}"))

        events = await buffer.flush()

        assert len(events) == 5
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self) -> None:
        """Test flush on empty buffer returns empty list."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        events = await buffer.flush()

        assert events == []
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_batch_size_triggers_flush(self) -> None:
        """Test that reaching batch size triggers flush."""
        flushed_events: list[HookEvent] = []

        async def on_flush(events: list[HookEvent]) -> None:
            flushed_events.extend(events)

        buffer = EventBuffer(
            config=BufferConfig(batch_size=5),
            on_flush=on_flush,
        )

        # Add exactly batch_size events
        for i in range(5):
            await buffer.add(make_event(f"session-{i}"))

        # Should have auto-flushed
        assert len(flushed_events) == 5
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_add_many_events(self) -> None:
        """Test add_many adds multiple events."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        events = [make_event(f"session-{i}") for i in range(10)]
        await buffer.add_many(events)

        assert buffer.pending_count == 10

    @pytest.mark.asyncio
    async def test_on_flush_callback_called(self) -> None:
        """Test on_flush callback is called during flush."""
        callback_called = False
        received_events: list[HookEvent] = []

        async def on_flush(events: list[HookEvent]) -> None:
            nonlocal callback_called, received_events
            callback_called = True
            received_events = events

        buffer = EventBuffer(
            config=BufferConfig(batch_size=50),
            on_flush=on_flush,
        )

        await buffer.add(make_event())
        await buffer.flush()

        assert callback_called
        assert len(received_events) == 1

    @pytest.mark.asyncio
    async def test_on_flush_sync_callback(self) -> None:
        """Test on_flush works with sync callback."""
        received_events: list[HookEvent] = []

        def on_flush(events: list[HookEvent]) -> None:
            received_events.extend(events)

        buffer = EventBuffer(
            config=BufferConfig(batch_size=50),
            on_flush=on_flush,
        )

        await buffer.add(make_event())
        await buffer.flush()

        assert len(received_events) == 1

    @pytest.mark.asyncio
    async def test_should_flush_by_batch_size(self) -> None:
        """Test should_flush returns True when batch size reached."""
        buffer = EventBuffer(config=BufferConfig(batch_size=5))

        for i in range(5):
            buffer._events.append(make_event(f"session-{i}"))

        assert buffer.should_flush() is True

    @pytest.mark.asyncio
    async def test_should_flush_returns_false_for_empty(self) -> None:
        """Test should_flush returns False for empty buffer."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        assert buffer.should_flush() is False

    @pytest.mark.asyncio
    async def test_overflow_protection(self) -> None:
        """Test buffer drops oldest events when full."""
        buffer = EventBuffer(config=BufferConfig(batch_size=100, max_buffer_size=100))

        # Fill buffer to max
        for i in range(100):
            buffer._events.append(make_event(f"session-{i}"))

        # Add one more - should trigger overflow protection
        await buffer.add(make_event("session-new"))

        # Buffer should have dropped 10% oldest + added 1 new
        assert buffer.pending_count == 91

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        """Test start and stop lifecycle."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        assert buffer.is_running is False

        await buffer.start()
        assert buffer.is_running is True

        await buffer.stop()
        assert buffer.is_running is False

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining_events(self) -> None:
        """Test stop flushes remaining events."""
        flushed_events: list[HookEvent] = []

        async def on_flush(events: list[HookEvent]) -> None:
            flushed_events.extend(events)

        buffer = EventBuffer(
            config=BufferConfig(batch_size=50),
            on_flush=on_flush,
        )

        await buffer.start()
        await buffer.add(make_event())
        await buffer.stop()

        assert len(flushed_events) == 1
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_periodic_flush(self) -> None:
        """Test periodic flush based on time interval."""
        flushed_events: list[HookEvent] = []

        async def on_flush(events: list[HookEvent]) -> None:
            flushed_events.extend(events)

        buffer = EventBuffer(
            config=BufferConfig(batch_size=100, flush_interval_seconds=0.1),
            on_flush=on_flush,
        )

        await buffer.start()
        await buffer.add(make_event())

        # Wait for periodic flush
        await asyncio.sleep(0.2)

        assert len(flushed_events) == 1

        await buffer.stop()

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        """Test calling start twice doesn't cause issues."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        await buffer.start()
        await buffer.start()  # Should be no-op

        assert buffer.is_running is True

        await buffer.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self) -> None:
        """Test calling stop twice doesn't cause issues."""
        buffer = EventBuffer(config=BufferConfig(batch_size=50))

        await buffer.start()
        await buffer.stop()
        await buffer.stop()  # Should be no-op

        assert buffer.is_running is False


class TestEventBufferErrorHandling:
    """Tests for error handling in EventBuffer."""

    @pytest.mark.asyncio
    async def test_flush_callback_error_requeues_events(self) -> None:
        """Test that events are requeued when flush callback fails."""
        call_count = 0

        async def failing_callback(events: list[HookEvent]) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Simulated failure")

        buffer = EventBuffer(
            config=BufferConfig(batch_size=50),
            on_flush=failing_callback,
        )

        await buffer.add(make_event())

        # Flush should raise and requeue events
        with pytest.raises(RuntimeError):
            await buffer.flush()

        # Events should be back in buffer
        assert buffer.pending_count == 1
