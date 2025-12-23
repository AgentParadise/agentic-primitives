"""Session output stream for Claude CLI.

Provides a clean interface for consuming agent output.
AEF uses this without knowing Claude CLI internals.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agentic_isolation.providers.claude_cli.event_parser import EventParser
from agentic_isolation.providers.claude_cli.types import (
    ObservabilityEvent,
    SessionSummary,
)

if TYPE_CHECKING:
    pass


class SessionOutputStream:
    """Stream of structured outputs from a Claude CLI session.

    This is the clean interface that AEF consumes. It provides:
    - Parsed observability events (for TimescaleDB)
    - Raw JSONL lines (for S3 conversation storage)
    - Session summary (for quick metrics)

    The stream can be consumed in different ways:

    1. Events only (for real-time observability):
        async for event in stream.events():
            await store.insert(event)

    2. Raw lines only (for conversation storage):
        async for line in stream.raw_lines():
            buffer.append(line)

    3. Dual consumption (for both):
        # Use tee() to consume both
        async for line, event in stream.tee():
            buffer.append(line)
            if event:
                await store.insert(event)

    Usage:
        stream = SessionOutputStream(
            session_id="session-123",
            lines_source=workspace.stream_command(cmd),
        )

        # Consume with dual output
        async for line, event in stream.tee():
            conversation_buffer.append(line)
            if event:
                await event_store.insert(event.to_dict())

        summary = stream.get_summary()
    """

    def __init__(
        self,
        session_id: str,
        lines_source: AsyncIterator[str],
    ) -> None:
        """Initialize the output stream.

        Args:
            session_id: Session identifier for correlation
            lines_source: Async iterator yielding raw JSONL lines
        """
        self._session_id = session_id
        self._lines_source = lines_source
        self._parser = EventParser(session_id)

        # Buffer for replay if needed
        self._raw_lines: list[str] = []
        self._events: list[ObservabilityEvent] = []

        # State
        self._consumed = False

    @property
    def session_id(self) -> str:
        """Session identifier."""
        return self._session_id

    async def tee(self) -> AsyncIterator[tuple[str, ObservabilityEvent | None]]:
        """Consume stream yielding both raw lines and parsed events.

        This is the recommended way to consume for dual storage:
        - Raw lines go to S3 for conversation storage
        - Parsed events go to TimescaleDB for observability

        Yields:
            Tuple of (raw_line, parsed_event_or_none)
        """
        if self._consumed:
            # Replay from buffer
            for i, line in enumerate(self._raw_lines):
                event = self._events[i] if i < len(self._events) else None
                yield line, event
            return

        self._consumed = True

        async for line in self._lines_source:
            # Store raw line
            self._raw_lines.append(line)

            # Parse to event
            event = self._parser.parse_line(line)
            self._events.append(event)  # type: ignore

            yield line, event

    async def events(self) -> AsyncIterator[ObservabilityEvent]:
        """Stream parsed observability events.

        Yields:
            ObservabilityEvent for each parseable line
        """
        async for _, event in self.tee():
            if event is not None:
                yield event

    async def raw_lines(self) -> AsyncIterator[str]:
        """Stream raw JSONL lines for conversation storage.

        Yields:
            Raw JSONL line strings
        """
        async for line, _ in self.tee():
            yield line

    def get_summary(self) -> SessionSummary:
        """Get session summary after consumption.

        Returns:
            SessionSummary with aggregated metrics

        Raises:
            RuntimeError: If stream hasn't been consumed yet
        """
        if not self._consumed:
            raise RuntimeError("Stream must be consumed before getting summary")
        return self._parser.get_summary()

    async def consume(self) -> SessionSummary:
        """Consume entire stream and return summary.

        Convenience method that consumes all events and returns summary.
        Raw lines and events are buffered for later access.

        Returns:
            SessionSummary after consuming all events
        """
        async for _ in self.tee():
            pass
        return self.get_summary()

    @property
    def raw_lines_buffer(self) -> list[str]:
        """Get buffered raw lines after consumption.

        Returns:
            List of raw JSONL lines

        Raises:
            RuntimeError: If stream hasn't been consumed yet
        """
        if not self._consumed:
            raise RuntimeError("Stream must be consumed before accessing buffer")
        return self._raw_lines

    @property
    def events_buffer(self) -> list[ObservabilityEvent]:
        """Get buffered events after consumption.

        Returns:
            List of parsed events (may contain None entries)

        Raises:
            RuntimeError: If stream hasn't been consumed yet
        """
        if not self._consumed:
            raise RuntimeError("Stream must be consumed before accessing buffer")
        return [e for e in self._events if e is not None]


async def create_output_stream(
    session_id: str,
    lines: list[str],
) -> SessionOutputStream:
    """Create a SessionOutputStream from a list of lines.

    Convenience factory for testing or replaying recordings.

    Args:
        session_id: Session identifier
        lines: List of JSONL lines

    Returns:
        SessionOutputStream ready to consume
    """

    async def lines_generator() -> AsyncIterator[str]:
        for line in lines:
            yield line

    return SessionOutputStream(
        session_id=session_id,
        lines_source=lines_generator(),
    )
