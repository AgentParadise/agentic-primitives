"""Claude CLI JSONL event parser with tool name enrichment and subagent tracking.

Parses raw JSONL lines from Claude CLI and produces normalized
ObservabilityEvents. Handles the tool_use_id → tool_name mapping
that Claude CLI doesn't provide in tool_result events.

Subagent Tracking:
- Detects Task tool usage as SUBAGENT_STARTED
- Tracks concurrent subagents by their Task tool_use_id
- Tags events with parent_tool_use_id for correlation
- Emits SUBAGENT_STOPPED when Task tool_result is received
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from agentic_isolation.providers.claude_cli.types import (
    EventType,
    ObservabilityEvent,
    SessionSummary,
    TokenUsage,
)

logger = logging.getLogger(__name__)


@dataclass
class SubagentState:
    """Tracks state of an active subagent.

    Used to correlate events and calculate duration when the subagent stops.
    """

    tool_use_id: str  # The Task tool_use_id (unique identifier)
    name: str  # Subagent name from Task input
    started_at: datetime
    tools_used: dict[str, int] = field(default_factory=dict)  # {tool_name: count}


class EventParser:
    """Parse Claude CLI JSONL events with tool name enrichment and subagent tracking.

    Claude CLI emits events in a specific format:
    - assistant messages contain tool_use with {id, name, input}
    - user messages contain tool_result with {tool_use_id} but NO name

    This parser caches tool_use_id → tool_name mappings to enrich
    tool_result events with the missing tool name.

    Subagent Tracking:
    - Detects `tool_use.name == "Task"` as subagent start
    - Tracks concurrent subagents in `_active_subagents` dict
    - Correlates events via `parent_tool_use_id` field
    - Emits SUBAGENT_STOPPED when Task tool_result is received

    Usage:
        parser = EventParser(session_id="session-123")

        for line in jsonl_lines:
            for event in parser.parse_line(line):
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

        # Active subagents: Task tool_use_id → SubagentState
        self._active_subagents: dict[str, SubagentState] = {}

        # Completed subagent names (for summary)
        self._subagent_names: list[str] = []
        self._tools_by_subagent: dict[str, dict[str, int]] = {}

        # Accumulate summary metrics
        self._event_count = 0
        self._tool_calls: dict[str, int] = {}
        self._total_tokens = TokenUsage()
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._success = True
        self._error_message: str | None = None

        # Recording playback support
        self._base_time: datetime | None = None  # Base timestamp for offset calculation

        # Cost and duration from result event
        self._total_cost_usd: float | None = None
        self._result_duration_ms: int | None = None
        self._result_duration_api_ms: int | None = None
        self._num_turns: int = 0

    def set_base_time(self, base_time: datetime) -> None:
        """Set base timestamp for recording playback.

        When parsing recordings, events have `_offset_ms` relative to
        the recording start. Call this with the recording's `recorded_at`
        timestamp to enable accurate duration calculation.

        Args:
            base_time: The recording's start timestamp
        """
        self._base_time = base_time
        logger.debug("Base time set to: %s", base_time.isoformat())

    def parse_line(self, line: str) -> list[ObservabilityEvent]:
        """Parse a single JSONL line into ObservabilityEvents.

        A single Claude CLI event may produce multiple ObservabilityEvents.
        For example, an assistant message with tool_use produces both:
        - TOKEN_USAGE (from message.usage)
        - TOOL_EXECUTION_STARTED (from tool_use content)

        Args:
            line: Raw JSONL line from Claude CLI

        Returns:
            List of ObservabilityEvents (may be empty)
        """
        line = line.strip()
        if not line:
            return []

        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Non-JSON line: %s", line[:50])
            return []

        # Handle recording metadata - extract base time and skip
        if "_recording" in raw:
            recording_meta = raw["_recording"]
            if recorded_at := recording_meta.get("recorded_at"):
                try:
                    # Parse ISO format timestamp
                    self.set_base_time(datetime.fromisoformat(recorded_at))
                except ValueError:
                    logger.warning("Invalid recorded_at timestamp: %s", recorded_at)
            return []

        event_type = raw.get("type", "")
        timestamp = self._parse_timestamp(raw)

        self._event_count += 1

        # Handle different event types
        if event_type == "system":
            event = self._handle_system(raw, timestamp)
            return [event] if event else []
        elif event_type == "assistant":
            return self._handle_assistant(raw, timestamp)
        elif event_type == "user":
            return self._handle_user(raw, timestamp)
        elif event_type == "result":
            event = self._handle_result(raw, timestamp)
            return [event] if event else []
        else:
            # Unknown type - skip
            return []

    def _parse_timestamp(self, raw: dict[str, Any]) -> datetime:
        """Extract timestamp from event.

        For recordings with `_offset_ms`, calculates timestamp from base_time.
        For live events, uses current time.

        Args:
            raw: Raw event dict

        Returns:
            Timestamp for this event
        """
        # Use _offset_ms from recordings if base_time is set
        if self._base_time is not None:
            if (offset_ms := raw.get("_offset_ms")) is not None:
                return self._base_time + timedelta(milliseconds=offset_ms)

        # Live event or no offset - use current time
        return datetime.now(UTC)

    def _extract_subagent_name(self, tool_input: dict[str, Any]) -> str:
        """Extract subagent name from Task tool input.

        Task tool input may contain:
        - description: Short description of the task
        - prompt: The actual prompt given to the subagent

        We use description if available, otherwise derive from prompt.
        """
        if description := tool_input.get("description"):
            return str(description)[:50]  # Truncate long descriptions
        if prompt := tool_input.get("prompt"):
            # Use first line or first 50 chars
            first_line = str(prompt).split("\n")[0]
            return first_line[:50]
        return "unnamed-subagent"

    def _handle_system(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent:
        """Handle system.init events."""
        self._started_at = timestamp

        return ObservabilityEvent(
            event_type=EventType.SESSION_STARTED,
            session_id=self.session_id,
            timestamp=timestamp,
            raw_event=raw,
        )

    def _handle_assistant(
        self, raw: dict[str, Any], timestamp: datetime
    ) -> list[ObservabilityEvent]:
        """Handle assistant message events.

        These contain tool_use items that we need to cache for later enrichment.
        Also detects Task tool usage for subagent tracking.

        IMPORTANT: Assistant messages may contain BOTH:
        - message.usage (token counts for this turn)
        - message.content with tool_use items

        We emit separate events for each to ensure token tracking is complete.
        """
        events: list[ObservabilityEvent] = []
        message = raw.get("message", {})
        content = message.get("content", [])

        # Check for parent_tool_use_id (indicates this is from a subagent)
        parent_tool_use_id = raw.get("parent_tool_use_id")

        # ALWAYS extract token usage first (even if there are tool_use items)
        usage = message.get("usage", {})
        if usage:
            tokens = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            )
            self._total_tokens = self._total_tokens + tokens

            events.append(ObservabilityEvent(
                event_type=EventType.TOKEN_USAGE,
                session_id=self.session_id,
                timestamp=timestamp,
                raw_event=raw,
                tokens=tokens,
                parent_tool_use_id=parent_tool_use_id,
            ))

        # Then handle tool_use items
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

                # If this event is from a subagent, track tools used by that subagent
                if parent_tool_use_id and parent_tool_use_id in self._active_subagents:
                    subagent = self._active_subagents[parent_tool_use_id]
                    subagent.tools_used[tool_name] = subagent.tools_used.get(tool_name, 0) + 1

                # Check if this is a Task tool (subagent spawn)
                if tool_name == "Task":
                    subagent_name = self._extract_subagent_name(tool_input)

                    # Track as active subagent
                    self._active_subagents[tool_use_id] = SubagentState(
                        tool_use_id=tool_use_id,
                        name=subagent_name,
                        started_at=timestamp,
                    )

                    logger.debug("Subagent started: %s (%s)", subagent_name, tool_use_id)

                    events.append(ObservabilityEvent(
                        event_type=EventType.SUBAGENT_STARTED,
                        session_id=self.session_id,
                        timestamp=timestamp,
                        raw_event=raw,
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        tool_input=tool_input,
                        agent_name=subagent_name,
                        subagent_tool_use_id=tool_use_id,
                        parent_tool_use_id=parent_tool_use_id,
                    ))
                else:
                    # Regular tool execution
                    events.append(ObservabilityEvent(
                        event_type=EventType.TOOL_EXECUTION_STARTED,
                        session_id=self.session_id,
                        timestamp=timestamp,
                        raw_event=raw,
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        tool_input=tool_input,
                        parent_tool_use_id=parent_tool_use_id,
                    ))

        return events

    def _handle_user(self, raw: dict[str, Any], timestamp: datetime) -> list[ObservabilityEvent]:
        """Handle user message events (contains tool_result).

        Enriches tool_result with tool_name from cache.
        Detects Task tool_result as subagent completion.
        """
        events: list[ObservabilityEvent] = []
        message = raw.get("message", {})
        content = message.get("content", [])

        # Check for parent_tool_use_id (indicates this is from a subagent)
        parent_tool_use_id = raw.get("parent_tool_use_id")

        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "tool_result":
                tool_use_id = item.get("tool_use_id", "")
                is_error = item.get("is_error", False)

                # Enrich with cached tool name
                tool_name = self._tool_names.get(tool_use_id, "unknown")

                # Check if this is a Task completion (subagent stopped)
                if tool_use_id in self._active_subagents:
                    subagent = self._active_subagents.pop(tool_use_id)
                    duration_ms = int((timestamp - subagent.started_at).total_seconds() * 1000)

                    # Record for summary
                    self._subagent_names.append(subagent.name)
                    self._tools_by_subagent[subagent.name] = subagent.tools_used.copy()

                    logger.debug(
                        "Subagent stopped: %s (duration: %dms)",
                        subagent.name,
                        duration_ms,
                    )

                    events.append(ObservabilityEvent(
                        event_type=EventType.SUBAGENT_STOPPED,
                        session_id=self.session_id,
                        timestamp=timestamp,
                        raw_event=raw,
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        success=not is_error,
                        agent_name=subagent.name,
                        subagent_tool_use_id=tool_use_id,
                        duration_ms=duration_ms,
                        tools_used=subagent.tools_used.copy() if subagent.tools_used else None,
                        parent_tool_use_id=parent_tool_use_id,
                    ))
                else:
                    # Regular tool completion
                    events.append(ObservabilityEvent(
                        event_type=EventType.TOOL_EXECUTION_COMPLETED,
                        session_id=self.session_id,
                        timestamp=timestamp,
                        raw_event=raw,
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        success=not is_error,
                        parent_tool_use_id=parent_tool_use_id,
                    ))

        return events

    def _handle_result(self, raw: dict[str, Any], timestamp: datetime) -> ObservabilityEvent:
        """Handle result events (session completion).

        Extracts cost, duration, and token metrics from the result event.
        """
        self._completed_at = timestamp
        self._success = not raw.get("is_error", False)

        # Extract cost and duration metrics
        self._total_cost_usd = raw.get("total_cost_usd")
        self._result_duration_ms = raw.get("duration_ms")
        self._result_duration_api_ms = raw.get("duration_api_ms")
        self._num_turns = raw.get("num_turns", 0)

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

    def get_active_subagent_count(self) -> int:
        """Get the number of currently active subagents.

        Useful for monitoring concurrent subagent activity.
        """
        return len(self._active_subagents)

    def get_summary(self) -> SessionSummary:
        """Get aggregated summary of parsed events.

        Call this after parsing all lines.

        Returns:
            SessionSummary with aggregated metrics including subagent info
        """
        return SessionSummary(
            session_id=self.session_id,
            started_at=self._started_at or datetime.now(UTC),
            completed_at=self._completed_at,
            event_count=self._event_count,
            tool_calls=self._tool_calls.copy(),
            num_turns=self._num_turns,
            total_input_tokens=self._total_tokens.input_tokens,
            total_output_tokens=self._total_tokens.output_tokens,
            total_cost_usd=self._total_cost_usd,
            result_duration_ms=self._result_duration_ms,
            result_duration_api_ms=self._result_duration_api_ms,
            subagent_count=len(self._subagent_names),
            subagent_names=self._subagent_names.copy(),
            tools_by_subagent=self._tools_by_subagent.copy(),
            success=self._success,
            error_message=self._error_message,
        )
