"""Claude CLI specific provider components.

This module provides Claude CLI-aware output streaming and parsing
for the agentic_isolation workspace providers.

Key Components:
    - SessionOutputStream: Clean interface for consuming agent output
    - EventParser: JSONL line parsing with tool name enrichment
    - ObservabilityEvent: Normalized event for storage
    - SessionSummary: Aggregated metrics from a session

Usage:
    from agentic_isolation.providers.claude_cli import (
        SessionOutputStream,
        ObservabilityEvent,
        SessionSummary,
    )

    # Create stream from raw JSONL lines
    stream = SessionOutputStream(
        session_id="session-123",
        lines_iterator=workspace.stream_stdout(),
    )

    # Consume parsed events
    async for event in stream.events():
        await store.insert(event)

    # Get raw lines for S3 storage
    async for line in stream.raw_lines():
        buffer.append(line)

    # Get summary after completion
    summary = await stream.summary()
"""

from agentic_isolation.providers.claude_cli.event_parser import EventParser
from agentic_isolation.providers.claude_cli.output_stream import SessionOutputStream
from agentic_isolation.providers.claude_cli.types import (
    EventType,
    ObservabilityEvent,
    SessionSummary,
    TokenUsage,
)

__all__ = [
    "SessionOutputStream",
    "EventParser",
    "EventType",
    "ObservabilityEvent",
    "SessionSummary",
    "TokenUsage",
]
