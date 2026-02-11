"""Types for Claude CLI output parsing.

These types represent normalized events and summaries that AEF
can consume without understanding Claude CLI internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Normalized event types for observability."""

    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"
    TOKEN_USAGE = "token_usage"
    ERROR = "error"
    # Subagent lifecycle events
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_STOPPED = "subagent_stopped"


@dataclass
class TokenUsage:
    """Token usage from a message or session."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        """Add two token usages together."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )


@dataclass
class ObservabilityEvent:
    """Normalized event from Claude CLI output.

    This is the clean interface that AEF consumes - all Claude CLI
    specifics are parsed and normalized by the EventParser.
    """

    event_type: EventType
    session_id: str
    timestamp: datetime
    raw_event: dict[str, Any]  # Original for storage

    # Tool-specific fields (set for tool events)
    tool_name: str | None = None
    tool_use_id: str | None = None
    tool_input: dict[str, Any] | None = None
    success: bool | None = None

    # Subagent-specific fields (set for subagent events)
    parent_tool_use_id: str | None = None  # Links tool to spawning Task
    agent_name: str | None = None  # Subagent name from Task input
    subagent_tool_use_id: str | None = None  # The Task tool_use_id
    duration_ms: int | None = None  # Subagent execution duration
    tools_used: dict[str, int] | None = None  # Tools used by subagent: {tool_name: count}

    # Token usage (set for token_usage events)
    tokens: TokenUsage | None = None

    # Error info (set for error events)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        result: dict[str, Any] = {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_use_id:
            result["tool_use_id"] = self.tool_use_id
        if self.tool_input:
            result["tool_input"] = self.tool_input
        if self.success is not None:
            result["success"] = self.success
        if self.parent_tool_use_id:
            result["parent_tool_use_id"] = self.parent_tool_use_id
        if self.agent_name:
            result["agent_name"] = self.agent_name
        if self.subagent_tool_use_id:
            result["subagent_tool_use_id"] = self.subagent_tool_use_id
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.tools_used:
            result["tools_used"] = self.tools_used
        if self.tokens:
            result["tokens"] = {
                "input": self.tokens.input_tokens,
                "output": self.tokens.output_tokens,
                "cache_creation": self.tokens.cache_creation_tokens,
                "cache_read": self.tokens.cache_read_tokens,
            }
        if self.error_message:
            result["error"] = self.error_message

        return result


@dataclass
class SessionSummary:
    """Aggregated summary of a completed session.

    Provides quick access to key metrics without needing
    to replay the entire conversation.
    """

    session_id: str
    started_at: datetime
    completed_at: datetime | None = None

    # Counts
    event_count: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)  # {"Bash": 5, "Read": 3}
    num_turns: int = 0  # Number of conversation turns

    # Token totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Cost and timing from result event (accurate values from Claude CLI)
    total_cost_usd: float | None = None  # Total cost in USD
    result_duration_ms: int | None = None  # Wall clock duration from result
    result_duration_api_ms: int | None = None  # API latency from result

    # Subagent metrics
    subagent_count: int = 0
    subagent_names: list[str] = field(default_factory=list)
    tools_by_subagent: dict[str, dict[str, int]] = field(
        default_factory=dict
    )  # {"subagent-1": {"Bash": 2, "Read": 1}}

    # Outcome
    success: bool = True
    error_message: str | None = None

    @property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds.

        Prefers the accurate duration from result event if available,
        otherwise calculates from timestamps.
        """
        # Prefer result event duration (more accurate)
        if self.result_duration_ms is not None:
            return self.result_duration_ms
        # Fall back to calculated duration
        if self.completed_at is None:
            return None
        delta = self.completed_at - self.started_at
        return int(delta.total_seconds() * 1000)

    @property
    def total_tool_calls(self) -> int:
        """Total number of tool calls."""
        return sum(self.tool_calls.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "duration_api_ms": self.result_duration_api_ms,
            "num_turns": self.num_turns,
            "event_count": self.event_count,
            "tool_calls": self.tool_calls,
            "total_tool_calls": self.total_tool_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "subagent_count": self.subagent_count,
            "subagent_names": self.subagent_names,
            "tools_by_subagent": self.tools_by_subagent,
            "success": self.success,
            "error_message": self.error_message,
        }
