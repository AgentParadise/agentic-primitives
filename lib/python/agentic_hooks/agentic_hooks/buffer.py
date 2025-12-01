"""Event buffer with batching logic for high-throughput scenarios.

This module provides an efficient buffer that batches events before sending
to reduce network overhead and improve throughput.

Features:
    - Configurable batch size
    - Configurable flush interval
    - Thread-safe async operations
    - Overflow protection

Example:
    buffer = EventBuffer(batch_size=50, flush_interval=1.0)
    buffer.add(event)

    if buffer.should_flush():
        events = buffer.flush()
        # Send events to backend
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentic_hooks.events import HookEvent

# Type alias for flush callbacks (can be sync or async)
FlushCallback = Callable[[list["HookEvent"]], None | Awaitable[None]]


@dataclass
class BufferConfig:
    """Configuration for event buffer.

    Attributes:
        batch_size: Number of events to batch before flushing.
        flush_interval_seconds: Maximum time to wait before flushing.
        max_buffer_size: Maximum events in buffer (overflow protection).
    """

    batch_size: int = 50
    flush_interval_seconds: float = 1.0
    max_buffer_size: int = 10000


@dataclass
class EventBuffer:
    """Async event buffer with batching and automatic flushing.

    This buffer collects events and triggers flushes based on:
    - Batch size threshold (e.g., 50 events)
    - Time interval (e.g., every 1 second)
    - Manual flush request

    Thread-safety is achieved through asyncio locks.

    Attributes:
        config: Buffer configuration.
        on_flush: Callback invoked when buffer is flushed.

    Example:
        async def send_events(events):
            await http_client.post("/events/batch", json=events)

        buffer = EventBuffer(
            config=BufferConfig(batch_size=50),
            on_flush=send_events,
        )
        await buffer.start()
        await buffer.add(event)
        # Events are automatically flushed
        await buffer.stop()
    """

    config: BufferConfig = field(default_factory=BufferConfig)
    on_flush: FlushCallback | None = None

    _events: list[HookEvent] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _last_flush_time: float = field(default_factory=time.monotonic)
    _flush_task: asyncio.Task[None] | None = field(default=None)
    _running: bool = field(default=False)

    async def start(self) -> None:
        """Start the background flush task.

        This starts a background task that periodically flushes
        the buffer based on the configured interval.
        """
        if self._running:
            return

        self._running = True
        self._last_flush_time = time.monotonic()
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the background flush task and flush remaining events.

        This cancels the periodic flush task and flushes any
        remaining events in the buffer.
        """
        self._running = False

        if self._flush_task is not None:
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
            self._flush_task = None

        # Flush remaining events
        await self.flush()

    async def add(self, event: HookEvent) -> None:
        """Add an event to the buffer.

        If the buffer reaches the batch size threshold, it will
        trigger an immediate flush.

        Args:
            event: Event to add to the buffer.
        """
        async with self._lock:
            # Overflow protection - drop oldest events if buffer is full
            if len(self._events) >= self.config.max_buffer_size:
                # Drop 10% of oldest events to make room
                drop_count = self.config.max_buffer_size // 10
                self._events = self._events[drop_count:]

            self._events.append(event)

            # Check if we should flush based on batch size
            if len(self._events) >= self.config.batch_size:
                await self._do_flush()

    async def add_many(self, events: list[HookEvent]) -> None:
        """Add multiple events to the buffer.

        Args:
            events: Events to add to the buffer.
        """
        for event in events:
            await self.add(event)

    async def flush(self) -> list[HookEvent]:
        """Force flush all buffered events.

        Returns:
            List of events that were flushed.
        """
        async with self._lock:
            return await self._do_flush()

    async def _do_flush(self) -> list[HookEvent]:
        """Internal flush implementation (must hold lock).

        Returns:
            List of events that were flushed.
        """
        if not self._events:
            return []

        events = self._events.copy()
        self._events.clear()
        self._last_flush_time = time.monotonic()

        if self.on_flush is not None:
            try:
                result: Any = self.on_flush(events)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # TODO: Add logging for flush failures
                # Fail-safe: don't lose events on callback error
                # Re-add events to buffer for retry
                self._events.extend(events)
                raise

        return events

    async def _periodic_flush(self) -> None:
        """Background task for periodic flushing."""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds / 2)

                async with self._lock:
                    elapsed = time.monotonic() - self._last_flush_time
                    if elapsed >= self.config.flush_interval_seconds and len(self._events) > 0:
                        await self._do_flush()

            except asyncio.CancelledError:
                break
            except Exception:
                # TODO: Add logging for periodic flush errors
                pass

    @property
    def pending_count(self) -> int:
        """Number of events waiting to be flushed."""
        return len(self._events)

    @property
    def is_running(self) -> bool:
        """Whether the background flush task is running."""
        return self._running

    def should_flush(self) -> bool:
        """Check if buffer should be flushed based on size or time.

        Returns:
            True if flush is recommended.
        """
        if len(self._events) >= self.config.batch_size:
            return True

        elapsed = time.monotonic() - self._last_flush_time
        return elapsed >= self.config.flush_interval_seconds and len(self._events) > 0
