"""Tests for HookClient."""

import asyncio

import pytest

from agentic_hooks.backends import JSONLBackend, NullBackend
from agentic_hooks.client import HookClient
from agentic_hooks.events import EventType, HookEvent


def make_event(session_id: str = "session-123") -> HookEvent:
    """Create a test event."""
    return HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
    )


class TestHookClientInit:
    """Tests for HookClient initialization."""

    def test_default_backend_is_jsonl(self) -> None:
        """Test default backend is JSONLBackend."""
        client = HookClient()

        assert isinstance(client.backend, JSONLBackend)

    def test_backend_url_creates_http_backend(self) -> None:
        """Test backend_url creates HTTPBackend."""
        from agentic_hooks.backends import HTTPBackend

        client = HookClient(backend_url="http://localhost:8080")

        assert isinstance(client.backend, HTTPBackend)
        assert client.backend.base_url == "http://localhost:8080"

    def test_custom_backend_overrides_url(self) -> None:
        """Test custom backend takes precedence over URL."""
        backend = NullBackend()
        client = HookClient(
            backend_url="http://localhost:8080",
            backend=backend,
        )

        assert client.backend is backend

    def test_custom_batch_size(self) -> None:
        """Test custom batch size configuration."""
        client = HookClient(batch_size=100)

        assert client.batch_size == 100
        assert client._buffer.config.batch_size == 100

    def test_custom_flush_interval(self) -> None:
        """Test custom flush interval configuration."""
        client = HookClient(flush_interval_seconds=0.5)

        assert client.flush_interval_seconds == 0.5
        assert client._buffer.config.flush_interval_seconds == 0.5


class TestHookClientLifecycle:
    """Tests for HookClient lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_starts_and_stops(self) -> None:
        """Test context manager properly starts and stops client."""
        backend = NullBackend()

        async with HookClient(backend=backend) as client:
            assert client._started is True
            await client.emit(make_event())

        assert client._started is False

    @pytest.mark.asyncio
    async def test_manual_start_stop(self) -> None:
        """Test manual start and stop."""
        backend = NullBackend()
        client = HookClient(backend=backend)

        assert client._started is False

        await client.start()
        assert client._started is True

        await client.close()
        assert client._started is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        """Test calling start twice is safe."""
        backend = NullBackend()
        client = HookClient(backend=backend)

        await client.start()
        await client.start()  # Should be no-op

        assert client._started is True

        await client.close()

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self) -> None:
        """Test calling close twice is safe."""
        backend = NullBackend()
        client = HookClient(backend=backend)

        await client.start()
        await client.close()
        await client.close()  # Should be no-op

        assert client._started is False


class TestHookClientEmit:
    """Tests for HookClient emit methods."""

    @pytest.mark.asyncio
    async def test_emit_single_event(self) -> None:
        """Test emitting a single event."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=50) as client:
            await client.emit(make_event())
            assert client.pending_count == 1

            await client.flush()
            assert client.pending_count == 0

        assert len(backend.events_received) == 1

    @pytest.mark.asyncio
    async def test_emit_many_events(self) -> None:
        """Test emitting multiple events at once."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=50) as client:
            events = [make_event(f"session-{i}") for i in range(10)]
            await client.emit_many(events)
            assert client.pending_count == 10

            await client.flush()
            assert client.pending_count == 0

        assert len(backend.events_received) == 10

    @pytest.mark.asyncio
    async def test_emit_auto_starts_client(self) -> None:
        """Test emit auto-starts client if not started."""
        backend = NullBackend()
        client = HookClient(backend=backend)

        assert client._started is False

        await client.emit(make_event())

        assert client._started is True

        await client.close()

    @pytest.mark.asyncio
    async def test_emit_triggers_batch_flush(self) -> None:
        """Test emit triggers flush when batch size reached."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=5) as client:
            # Emit exactly batch_size events
            for i in range(5):
                await client.emit(make_event(f"session-{i}"))

            # Should have auto-flushed
            assert client.pending_count == 0
            assert len(backend.events_received) == 5

    @pytest.mark.asyncio
    async def test_pending_count(self) -> None:
        """Test pending_count property."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=50) as client:
            assert client.pending_count == 0

            await client.emit(make_event())
            assert client.pending_count == 1

            await client.emit(make_event())
            assert client.pending_count == 2

            await client.flush()
            assert client.pending_count == 0


class TestHookClientFlush:
    """Tests for HookClient flush behavior."""

    @pytest.mark.asyncio
    async def test_flush_sends_all_events(self) -> None:
        """Test flush sends all buffered events."""
        backend = NullBackend()

        async with HookClient(backend=backend, batch_size=50) as client:
            for i in range(10):
                await client.emit(make_event(f"session-{i}"))

            await client.flush()

        assert len(backend.events_received) == 10

    @pytest.mark.asyncio
    async def test_flush_empty_buffer(self) -> None:
        """Test flush on empty buffer."""
        backend = NullBackend()

        async with HookClient(backend=backend) as client:
            await client.flush()

        assert len(backend.events_received) == 0

    @pytest.mark.asyncio
    async def test_close_flushes_remaining(self) -> None:
        """Test close flushes remaining events."""
        backend = NullBackend()
        client = HookClient(backend=backend, batch_size=50)

        await client.start()

        for i in range(3):
            await client.emit(make_event(f"session-{i}"))

        # Don't manually flush
        await client.close()

        # Events should be flushed on close
        assert len(backend.events_received) == 3


class TestHookClientPeriodicFlush:
    """Tests for periodic flush behavior."""

    @pytest.mark.asyncio
    async def test_periodic_flush(self) -> None:
        """Test periodic flush based on time interval."""
        backend = NullBackend()

        async with HookClient(
            backend=backend,
            batch_size=100,  # High batch size
            flush_interval_seconds=0.1,  # Short interval
        ) as client:
            await client.emit(make_event())

            # Wait for periodic flush
            await asyncio.sleep(0.2)

            # Should have been flushed by periodic task
            assert len(backend.events_received) >= 1


class TestHookClientRetry:
    """Tests for retry behavior."""

    @pytest.mark.asyncio
    async def test_retry_on_backend_failure(self) -> None:
        """Test client retries on backend failure."""

        class FailingBackend:
            """Backend that fails on first attempt."""

            def __init__(self) -> None:
                self.attempt_count = 0
                self.events_received: list[dict] = []

            async def write(self, events: list[HookEvent]) -> None:
                self.attempt_count += 1
                if self.attempt_count < 2:
                    raise RuntimeError("Simulated failure")
                for event in events:
                    self.events_received.append(event.to_dict())

            async def close(self) -> None:
                pass

        backend = FailingBackend()

        async with HookClient(backend=backend, max_retry_attempts=3) as client:  # type: ignore[arg-type]
            await client.emit(make_event())
            await client.flush()

        # Should have succeeded on retry
        assert backend.attempt_count == 2
        assert len(backend.events_received) == 1

    @pytest.mark.asyncio
    async def test_fail_safe_on_all_retries_exhausted(self) -> None:
        """Test client is fail-safe when all retries exhausted."""

        class AlwaysFailingBackend:
            """Backend that always fails."""

            def __init__(self) -> None:
                self.attempt_count = 0

            async def write(self, events: list[HookEvent]) -> None:
                self.attempt_count += 1
                raise RuntimeError("Always fails")

            async def close(self) -> None:
                pass

        backend = AlwaysFailingBackend()

        # Should not raise even when backend always fails
        async with HookClient(backend=backend, max_retry_attempts=3) as client:  # type: ignore[arg-type]
            await client.emit(make_event())
            await client.flush()

        # All retries should have been attempted
        assert backend.attempt_count == 3
