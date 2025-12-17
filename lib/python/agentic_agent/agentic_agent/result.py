"""Agent execution results and metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass
class ToolCall:
    """Record of a single tool call."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str | None = None
    tool_output: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    success: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_use_id": self.tool_use_id,
            "tool_output": self.tool_output,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }


@dataclass
class SessionMetrics:
    """Aggregate metrics for an agent session."""

    session_id: str
    model: str
    start_time: datetime
    end_time: datetime
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    interaction_count: int = 0
    tool_call_count: int = 0
    duration_ms: float = 0.0

    @property
    def total_tokens(self) -> int:
        """Total tokens used in session."""
        return self.input_tokens + self.output_tokens

    @property
    def tokens_per_second(self) -> float:
        """Token velocity."""
        if self.duration_ms == 0:
            return 0.0
        return self.total_tokens / (self.duration_ms / 1000)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "model": self.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "interaction_count": self.interaction_count,
            "tool_call_count": self.tool_call_count,
            "duration_ms": self.duration_ms,
            "tokens_per_second": self.tokens_per_second,
        }


@dataclass
class AgentResult:
    """Result from an agent execution.

    Contains the response text, metrics, and tool call history.
    """

    text: str
    metrics: SessionMetrics
    tool_calls: list[ToolCall] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    raw_result: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "metrics": self.metrics.to_dict(),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "success": self.success,
            "error": self.error,
        }
