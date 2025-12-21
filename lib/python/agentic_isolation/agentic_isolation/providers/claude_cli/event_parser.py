"""Claude CLI JSONL event parser with tool name enrichment.

Parses raw JSONL lines from Claude CLI and produces normalized
ObservabilityEvents. Handles the tool_use_id → tool_name mapping
that Claude CLI doesn't provide in tool_result events.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from agentic_isolation.providers.claude_cli.types import (
    EventType,
    ObservabilityEvent,
    SessionSummary,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class EventParser:
    """Parse Claude CLI JSONL events with tool name enrichment.

    Claude CLI emits events in a specific format:
    - assistant messages contain tool_use with {id, name, input}
    - user messages contain tool_result with {tool_use_id} but NO name

    This parser caches tool_use_id → tool_name mappings to enrich
    tool_result events with the missing tool name.

    Usage:
        parser = EventParser(session_id="session-123")

        for line in jsonl_lines:
            event = parser.parse_line(line)
            if event:
                yield event

        summary = parser.get_summary()
    """

    def __init__(self, session_id: str) -> None:
        """Initialize parser with session ID.

        Args:
            session_id: Session identifier for events
        """
        self.session_id = session_id

        # Tool name cache: tool_use_id → tool_name
        self._tool_names: dict[str, str] = {}

        # Accumulate summary metrics
        self._event_count = 0
        self._tool_calls: dict[str, int] = {}
        self._total_tokens = TokenUsage()
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._success = True
        self._error_message: str | None = None

    def parse_line(self, line: str) -> ObservabilityEvent | None:
        """Parse a single JSONL line into an ObservabilityEvent.

        Args:
            line: Raw JSONL line from Claude CLI

        Returns:
            ObservabilityEvent if parseable, None otherwise
        """
        line = line.strip()
        if not line:
            return None

        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Non-JSON line: %s", line[:50])
            return None

        # Skip recording metadata
        if "_recording" in raw:
            return None

        event_type = raw.get("type", "")
        timestamp = self._parse_timestamp(raw)

        self._event_count += 1

        # Handle different event types
        if event_type == "system":
            return self._handle_system(raw, timestamp)
        elif event_type == "assistant":
            return self._handle_assistant(raw, timestamp)
        elif event_type == "user":
            return self._handle_user(raw, timestamp)
        elif event_type == "result":
            return self._handle_result(raw, timestamp)
        else:
            # Unknown type - skip
            return None

    def _parse_timestamp(self, raw: dict[str, Any]) -> datetime:
        """Extract timestamp from event or use now."""
        # Claude CLI doesn't always include timestamps
        # Use _offset_ms from recordings if available
        return datetime.now(UTC)

    def _handle_system(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent:
        """Handle system.init events."""
        self._started_at = timestamp

        return ObservabilityEvent(
            event_type=EventType.SESSION_STARTED,
            session_id=self.session_id,
            timestamp=timestamp,
            raw_event=raw,
        )

    def _handle_assistant(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent | None:
        """Handle assistant message events.

        These contain tool_use items that we need to cache for later enrichment.
        """
        message = raw.get("message", {})
        content = message.get("content", [])

        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "tool_use":
                tool_use_id = item.get("id", "")
                tool_name = item.get("name", "unknown")
                tool_input = item.get("input", {})

                # Cache for tool_result enrichment
                self._tool_names[tool_use_id] = tool_name

                # Track tool usage
                self._tool_calls[tool_name] = self._tool_calls.get(tool_name, 0) + 1

                return ObservabilityEvent(
                    event_type=EventType.TOOL_EXECUTION_STARTED,
                    session_id=self.session_id,
                    timestamp=timestamp,
                    raw_event=raw,
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    tool_input=tool_input,
                )

        # Text-only assistant message - extract tokens if available
        usage = message.get("usage", {})
        if usage:
            tokens = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            )
            self._total_tokens = self._total_tokens + tokens

            return ObservabilityEvent(
                event_type=EventType.TOKEN_USAGE,
                session_id=self.session_id,
                timestamp=timestamp,
                raw_event=raw,
                tokens=tokens,
            )

        return None

    def _handle_user(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent | None:
        """Handle user message events (contains tool_result).

        Enriches tool_result with tool_name from cache.
        """
        message = raw.get("message", {})
        content = message.get("content", [])

        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "tool_result":
                tool_use_id = item.get("tool_use_id", "")
                is_error = item.get("is_error", False)

                # Enrich with cached tool name
                tool_name = self._tool_names.get(tool_use_id, "unknown")

                return ObservabilityEvent(
                    event_type=EventType.TOOL_EXECUTION_COMPLETED,
                    session_id=self.session_id,
                    timestamp=timestamp,
                    raw_event=raw,
                    tool_name=tool_name,
                    tool_use_id=tool_use_id,
                    success=not is_error,
                )

        return None

    def _handle_result(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent:
        """Handle result events (session completion)."""
        self._completed_at = timestamp
        self._success = not raw.get("is_error", False)

        # Extract final token counts
        usage = raw.get("usage", {})
        if usage:
            tokens = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            )
            # Result usage is cumulative, so replace rather than add
            self._total_tokens = tokens

        return ObservabilityEvent(
            event_type=EventType.SESSION_COMPLETED,
            session_id=self.session_id,
            timestamp=timestamp,
            raw_event=raw,
            success=self._success,
        )

    def get_summary(self) -> SessionSummary:
        """Get aggregated summary of parsed events.

        Call this after parsing all lines.

        Returns:
            SessionSummary with aggregated metrics
        """
        return SessionSummary(
            session_id=self.session_id,
            started_at=self._started_at or datetime.now(UTC),
            completed_at=self._completed_at,
            event_count=self._event_count,
            tool_calls=self._tool_calls.copy(),
            total_input_tokens=self._total_tokens.input_tokens,
            total_output_tokens=self._total_tokens.output_tokens,
            success=self._success,
            error_message=self._error_message,
        )
