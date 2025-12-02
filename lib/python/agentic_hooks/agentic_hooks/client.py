"""Async hook client with batching for high-throughput scenarios.

This module provides the main HookClient class for emitting hook events.
The client buffers events and sends them in batches for efficiency.

Features:
    - Async batching for high throughput
    - Configurable flush intervals
    - Context manager support
    - Fail-safe operation

Example:
    from agentic_hooks import HookClient, HookEvent, EventType

    async with HookClient(backend_url="http://localhost:8080") as client:
        await client.emit(HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
        ))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentic_hooks.backends import Backend, HTTPBackend, JSONLBackend
from agentic_hooks.buffer import BufferConfig, EventBuffer

if TYPE_CHECKING:
    from agentic_hooks.events import HookEvent


@dataclass
class HookClient:
    """Async hook client with batching for high-throughput scenarios.

    This client buffers events and sends them in batches to reduce
    network overhead. It supports both HTTP and JSONL backends.

    Attributes:
        backend_url: URL of hook backend service (uses HTTP backend).
        backend: Custom backend adapter (overrides backend_url).
        batch_size: Number of events to batch before sending.
        flush_interval_seconds: Max time to wait before flushing.
        max_retry_attempts: Number of retries on failure.

    Example:
        # HTTP backend (production)
        async with HookClient(backend_url="http://localhost:8080") as client:
            await client.emit(event)

        # JSONL backend (local dev)
        async with HookClient(backend=JSONLBackend()) as client:
            await client.emit(event)

        # Custom configuration
        client = HookClient(
            backend_url="http://localhost:8080",
            batch_size=100,
            flush_interval_seconds=0.5,
        )
        await client.start()
        await client.emit(event)
        await client.close()
    """

    backend_url: str | None = None
    backend: Backend | None = None
    batch_size: int = 50
    flush_interval_seconds: float = 1.0
    max_retry_attempts: int = 3

    _buffer: EventBuffer = field(init=False)
    _started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize the buffer and backend."""
        # Determine backend
        if self.backend is None:
            if self.backend_url is not None:
                self.backend = HTTPBackend(base_url=self.backend_url)
            else:
                # Default to JSONL backend for local dev
                self.backend = JSONLBackend()

        # Create buffer with flush callback
        self._buffer = EventBuffer(
            config=BufferConfig(
                batch_size=self.batch_size,
                flush_interval_seconds=self.flush_interval_seconds,
            ),
            on_flush=self._on_flush,
        )

    async def _on_flush(self, events: list[HookEvent]) -> None:
        """Callback invoked when buffer flushes.

        Args:
            events: Events to write to backend.
        """
        if self.backend is None:
            return

        last_error: Exception | None = None

        for attempt in range(self.max_retry_attempts):
            try:
                await self.backend.write(events)
                return
            except Exception as e:
                last_error = e
                # TODO: Add exponential backoff for retries
                if attempt < self.max_retry_attempts - 1:
                    continue

        # All retries failed
        if last_error is not None:
            # TODO: Add logging for failed writes
            # Fail-safe: don't raise, just lose the events
            pass

    async def start(self) -> None:
        """Start the client and background flush task.

        Call this before emitting events if not using context manager.
        """
        if self._started:
            return

        self._started = True
        await self._buffer.start()

    async def close(self) -> None:
        """Close the client and flush remaining events.

        This flushes any buffered events and closes the backend.
        """
        if not self._started:
            return

        await self._buffer.stop()

        if self.backend is not None:
            await self.backend.close()

        self._started = False

    async def emit(self, event: HookEvent) -> None:
        """Emit a hook event (buffered, async).

        Events are added to the buffer and flushed based on
        batch size or time interval.

        Args:
            event: Event to emit.
        """
        if not self._started:
            await self.start()

        await self._buffer.add(event)

    async def emit_many(self, events: list[HookEvent]) -> None:
        """Emit multiple events at once.

        Args:
            events: Events to emit.
        """
        if not self._started:
            await self.start()

        await self._buffer.add_many(events)

    async def flush(self) -> None:
        """Force flush all buffered events.

        Call this to ensure all events are sent immediately.
        """
        await self._buffer.flush()

    @property
    def pending_count(self) -> int:
        """Number of events waiting to be flushed."""
        return self._buffer.pending_count

    async def __aenter__(self) -> HookClient:
        """Enter async context manager."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager."""
        await self.close()
