"""Event buffer for batch processing.

Used by AEF's AgentRunner to buffer events and flush in batches
for high-throughput storage to TimescaleDB.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class BatchBuffer:
    """Buffer events for batch insertion.

    This buffer collects events and flushes them in batches for efficient
    database insertion. Designed for high-throughput scenarios (10K+ agents).

    The buffer flushes when either:
    1. The buffer reaches `flush_size` events
    2. `flush_interval` seconds have passed since last flush

    Example:
        >>> async def store_batch(events):
        ...     await db.insert_batch(events)
        >>>
        >>> buffer = BatchBuffer(on_flush=store_batch, flush_size=1000)
        >>> await buffer.start()
        >>> await buffer.add({"event_type": "tool_started", ...})
        >>> # Events are automatically flushed
        >>> await buffer.stop()
    """

    def __init__(
        self,
        on_flush: Callable[[list[dict[str, Any]]], Any] | None = None,
        flush_size: int = 1000,
        flush_interval: float = 0.1,
    ) -> None:
        """Initialize the batch buffer.

        Args:
            on_flush: Async callback to handle flushed events.
            flush_size: Number of events to trigger a flush.
            flush_interval: Seconds between periodic flushes.
        """
        self._buffer: list[dict[str, Any]] = []
        self._on_flush = on_flush
        self._flush_size = flush_size
        self._flush_interval = flush_interval
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def size(self) -> int:
        """Current number of events in the buffer."""
        return len(self._buffer)

    async def add(self, event: dict[str, Any]) -> None:
        """Add an event to the buffer.

        If the buffer reaches flush_size, it will be flushed immediately.

        Args:
            event: The event dict to buffer.
        """
        async with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self._flush_size:
                await self._flush_locked()

    async def add_many(self, events: list[dict[str, Any]]) -> None:
        """Add multiple events to the buffer.

        Args:
            events: List of event dicts to buffer.
        """
        async with self._lock:
            self._buffer.extend(events)
            while len(self._buffer) >= self._flush_size:
                await self._flush_locked()

    async def flush(self) -> list[dict[str, Any]]:
        """Flush all buffered events.

        Returns:
            The list of events that were flushed.
        """
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> list[dict[str, Any]]:
        """Flush buffer while already holding the lock.

        Returns:
            The list of events that were flushed.
        """
        if not self._buffer:
            return []

        events = self._buffer
        self._buffer = []

        if self._on_flush:
            await self._on_flush(events)

        return events

    async def start(self) -> None:
        """Start the periodic flush task."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop(self) -> None:
        """Stop the periodic flush task and flush remaining events."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass  # Expected when stopping the periodic flush task
            self._flush_task = None

        # Flush any remaining events
        await self.flush()

    async def _periodic_flush(self) -> None:
        """Periodically flush the buffer."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            if self._buffer:  # Only flush if there are events
                await self.flush()


def parse_jsonl_line(line: str) -> dict[str, Any] | None:
    """Parse a single JSONL line into an event dict.

    Args:
        line: A JSON line string.

    Returns:
        The parsed event dict, or None if parsing fails.
    """
    line = line.strip()
    if not line:
        return None

    try:
        event = json.loads(line)
        if isinstance(event, dict) and "event_type" in event:
            return event
    except json.JSONDecodeError:
        pass  # Not all lines are valid JSON; ignore non-JSON lines

    return None


def enrich_event(
    event: dict[str, Any],
    execution_id: str | None = None,
    phase_id: str | None = None,
    container_id: str | None = None,
) -> dict[str, Any]:
    """Enrich an event with additional context.

    This is used by AEF to add workflow context to events captured
    from agent containers.

    Args:
        event: The event dict to enrich.
        execution_id: Workflow execution ID.
        phase_id: Workflow phase ID.
        container_id: Container ID where the event originated.

    Returns:
        The enriched event dict.
    """
    enriched = event.copy()

    if execution_id:
        enriched["execution_id"] = execution_id
    if phase_id:
        enriched["phase_id"] = phase_id
    if container_id:
        enriched["container_id"] = container_id

    # Ensure timestamp is set
    if "timestamp" not in enriched:
        enriched["timestamp"] = datetime.now(UTC).isoformat()

    return enriched
