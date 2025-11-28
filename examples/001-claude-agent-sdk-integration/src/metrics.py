"""Metrics collection system for Claude Agent SDK integration.

Captures comprehensive metrics including:
- Token usage (input/output) per interaction
- Tool calls with timing
- Session aggregates with cost estimation
- JSONL output compatible with agentic_analytics

Metrics Reference:
- Cognitive Efficiency: Committed Tokens / Total Tokens
- Cost Efficiency: Cost / Committed Tokens
- Token Velocity: Quality Tokens / Hour
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.models import ModelConfig


@dataclass
class ToolCallMetric:
    """Metrics for a single tool call."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    blocked: bool = False
    block_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL output."""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


@dataclass
class InteractionMetrics:
    """Metrics for a single agent interaction (prompt/response cycle)."""

    input_tokens: int
    output_tokens: int
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tool_calls: list[ToolCallMetric] = field(default_factory=list)
    prompt_preview: Optional[str] = None  # First 100 chars of prompt
    response_preview: Optional[str] = None  # First 100 chars of response

    @property
    def total_tokens(self) -> int:
        """Total tokens for this interaction."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL output."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "prompt_preview": self.prompt_preview,
            "response_preview": self.response_preview,
        }


@dataclass
class SessionMetrics:
    """Aggregate metrics for an entire agent session."""

    session_id: str
    model: str
    start_time: datetime
    end_time: datetime
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    interaction_count: int
    tool_call_count: int
    tool_calls_blocked: int
    total_duration_ms: float
    interactions: list[InteractionMetrics]

    @property
    def total_tokens(self) -> int:
        """Total tokens for entire session."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_tokens_per_interaction(self) -> float:
        """Average tokens per interaction."""
        if self.interaction_count == 0:
            return 0.0
        return self.total_tokens / self.interaction_count

    @property
    def tokens_per_second(self) -> float:
        """Token velocity (tokens per second)."""
        if self.total_duration_ms == 0:
            return 0.0
        return self.total_tokens / (self.total_duration_ms / 1000)

    def to_dict(self) -> dict:
        """Convert to dictionary for summary output."""
        return {
            "session_id": self.session_id,
            "model": self.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "interaction_count": self.interaction_count,
            "tool_call_count": self.tool_call_count,
            "tool_calls_blocked": self.tool_calls_blocked,
            "total_duration_ms": self.total_duration_ms,
            "avg_tokens_per_interaction": self.avg_tokens_per_interaction,
            "tokens_per_second": self.tokens_per_second,
        }


class SessionContext:
    """Context manager for tracking a session's metrics.

    Usage:
        collector = MetricsCollector()
        session = collector.start_session(model_config)
        session.record_interaction(input_tokens=100, output_tokens=50, duration_ms=500)
        session.record_tool_call("Write", {"file_path": "test.py"}, duration_ms=10)
        summary = session.end()
    """

    def __init__(
        self,
        session_id: str,
        model_config: ModelConfig,
        collector: "MetricsCollector",
    ):
        self.session_id = session_id
        self.model_config = model_config
        self.collector = collector
        self.start_time = datetime.now(timezone.utc)
        self.interactions: list[InteractionMetrics] = []
        self._current_interaction: Optional[InteractionMetrics] = None
        self._ended = False

    def record_interaction(
        self,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        prompt_preview: Optional[str] = None,
        response_preview: Optional[str] = None,
    ) -> InteractionMetrics:
        """Record an interaction (prompt/response cycle).

        Args:
            input_tokens: Tokens in the prompt
            output_tokens: Tokens in the response
            duration_ms: Time taken for the interaction
            prompt_preview: Optional preview of the prompt
            response_preview: Optional preview of the response

        Returns:
            The recorded InteractionMetrics
        """
        interaction = InteractionMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            prompt_preview=prompt_preview[:100] if prompt_preview else None,
            response_preview=response_preview[:100] if response_preview else None,
        )
        self.interactions.append(interaction)
        self._current_interaction = interaction

        # Write event to JSONL
        self.collector._write_event(
            event_type="agent_interaction",
            session_id=self.session_id,
            data=interaction.to_dict(),
        )

        return interaction

    def record_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        duration_ms: float = 0.0,
        tool_output: Optional[str] = None,
        blocked: bool = False,
        block_reason: Optional[str] = None,
    ) -> ToolCallMetric:
        """Record a tool call.

        Args:
            tool_name: Name of the tool (e.g., "Write", "Bash", "Read")
            tool_input: Input parameters for the tool
            duration_ms: Time taken for the tool call
            tool_output: Optional output from the tool
            blocked: Whether the tool call was blocked by a hook
            block_reason: Reason for blocking if blocked

        Returns:
            The recorded ToolCallMetric
        """
        tool_metric = ToolCallMetric(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            duration_ms=duration_ms,
            blocked=blocked,
            block_reason=block_reason,
        )

        # Add to current interaction if one exists
        if self._current_interaction:
            self._current_interaction.tool_calls.append(tool_metric)

        # Write event to JSONL
        self.collector._write_event(
            event_type="tool_call",
            session_id=self.session_id,
            data=tool_metric.to_dict(),
        )

        return tool_metric

    def end(self) -> SessionMetrics:
        """End the session and return aggregate metrics.

        Returns:
            SessionMetrics with aggregate data
        """
        if self._ended:
            raise RuntimeError("Session already ended")

        self._ended = True
        end_time = datetime.now(timezone.utc)

        # Calculate aggregates
        total_input = sum(i.input_tokens for i in self.interactions)
        total_output = sum(i.output_tokens for i in self.interactions)
        total_duration = sum(i.duration_ms for i in self.interactions)
        tool_calls = sum(len(i.tool_calls) for i in self.interactions)
        blocked_calls = sum(sum(1 for tc in i.tool_calls if tc.blocked) for i in self.interactions)

        # Calculate cost
        cost = self.model_config.calculate_cost(total_input, total_output)

        metrics = SessionMetrics(
            session_id=self.session_id,
            model=self.model_config.api_name,
            start_time=self.start_time,
            end_time=end_time,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost_usd=cost,
            interaction_count=len(self.interactions),
            tool_call_count=tool_calls,
            tool_calls_blocked=blocked_calls,
            total_duration_ms=total_duration,
            interactions=self.interactions,
        )

        # Write session end event
        self.collector._write_event(
            event_type="agent_session_end",
            session_id=self.session_id,
            data=metrics.to_dict(),
        )

        return metrics


class MetricsCollector:
    """Collects and persists metrics to JSONL.

    Writes events to a JSONL file in the format compatible with agentic_analytics.

    Usage:
        collector = MetricsCollector(output_path=".agentic/analytics/events.jsonl")
        config = load_model_config("claude-sonnet-4-5-20250929")

        session = collector.start_session(model=config)
        session.record_interaction(input_tokens=100, output_tokens=50, duration_ms=500)
        session.record_tool_call("Write", {"file_path": "test.py"}, duration_ms=10)
        summary = session.end()
    """

    def __init__(
        self,
        output_path: str | Path = ".agentic/analytics/events.jsonl",
    ):
        self.output_path = Path(output_path)
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        """Ensure the output directory exists."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def start_session(self, model: ModelConfig) -> SessionContext:
        """Start a new metrics session.

        Args:
            model: Model configuration for cost calculation

        Returns:
            SessionContext for recording metrics
        """
        session_id = str(uuid.uuid4())

        # Write session start event
        self._write_event(
            event_type="agent_session_start",
            session_id=session_id,
            data={
                "model": model.api_name,
                "model_display_name": model.display_name,
                "provider": model.provider,
                "pricing": {
                    "input_per_1m_tokens": model.input_per_1m_tokens,
                    "output_per_1m_tokens": model.output_per_1m_tokens,
                },
            },
        )

        return SessionContext(
            session_id=session_id,
            model_config=model,
            collector=self,
        )

    def _write_event(
        self,
        event_type: str,
        session_id: str,
        data: dict[str, Any],
    ) -> None:
        """Write an event to the JSONL file.

        Args:
            event_type: Type of event (e.g., "agent_session_start", "tool_call")
            session_id: Session identifier
            data: Event-specific data
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "session_id": session_id,
            "data": data,
        }

        with open(self.output_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def read_events(self) -> list[dict]:
        """Read all events from the JSONL file.

        Returns:
            List of event dictionaries
        """
        if not self.output_path.exists():
            return []

        events = []
        with open(self.output_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def clear(self) -> None:
        """Clear all events from the output file."""
        if self.output_path.exists():
            self.output_path.unlink()
