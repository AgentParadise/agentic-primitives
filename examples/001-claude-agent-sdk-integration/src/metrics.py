"""Metrics collection system for Claude Agent SDK integration.

Captures comprehensive metrics including:
- Token usage (input/output) per interaction
- Tool calls with timing
- Session aggregates with cost estimation
- JSONL output using agentic_analytics canonical events

Metrics Reference:
- Cognitive Efficiency: Committed Tokens / Total Tokens
- Cost Efficiency: Cost / Committed Tokens
- Token Velocity: Quality Tokens / Hour

This module uses the canonical event schemas from agentic_analytics:
- SessionStarted -> session.started
- TokensUsed -> tokens.used
- ToolCalled -> tool.called
- SessionEnded -> session.ended
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_analytics import (
    EventEmitter,
    SessionEnded,
    SessionStarted,
    TokensUsed,
    ToolCalled,
)

from src.models import ModelConfig


@dataclass
class ToolCallMetric:
    """Metrics for a single tool call.

    Note: This is a local convenience class that wraps the canonical
    ToolCalled event for building session summaries.
    """

    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str | None = None
    tool_use_id: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    blocked: bool = False
    block_reason: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for summary output."""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "tool_use_id": self.tool_use_id,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


@dataclass
class InteractionMetrics:
    """Metrics for a single agent interaction (prompt/response cycle).

    Note: This is a local convenience class that wraps the canonical
    TokensUsed event for building session summaries.
    """

    input_tokens: int
    output_tokens: int
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    tool_calls: list[ToolCallMetric] = field(default_factory=list)
    prompt_preview: str | None = None
    response_preview: str | None = None

    @property
    def total_tokens(self) -> int:
        """Total tokens for this interaction."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for summary output."""
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

    Emits canonical events from agentic_analytics while building
    local summary objects for the session.

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
        emitter: EventEmitter,
    ):
        self.session_id = session_id
        self.model_config = model_config
        self.emitter = emitter
        self.start_time = datetime.now(UTC)
        self.interactions: list[InteractionMetrics] = []
        self._current_interaction: InteractionMetrics | None = None
        self._interaction_index = 0
        self._ended = False

    def record_interaction(
        self,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        prompt_preview: str | None = None,
        response_preview: str | None = None,
    ) -> InteractionMetrics:
        """Record an interaction (prompt/response cycle).

        Emits a TokensUsed event to the analytics stream.

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

        # Emit canonical TokensUsed event
        self.emitter.emit(
            TokensUsed(
                session_id=self.session_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                prompt_preview=prompt_preview[:100] if prompt_preview else None,
                response_preview=response_preview[:100] if response_preview else None,
                interaction_index=self._interaction_index,
            )
        )
        self._interaction_index += 1

        return interaction

    def record_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        duration_ms: float = 0.0,
        tool_output: str | None = None,
        tool_use_id: str | None = None,
        blocked: bool = False,
        block_reason: str | None = None,
    ) -> ToolCallMetric:
        """Record a tool call.

        Emits a ToolCalled event to the analytics stream.

        Args:
            tool_name: Name of the tool (e.g., "Write", "Bash", "Read")
            tool_input: Input parameters for the tool
            duration_ms: Time taken for the tool call
            tool_output: Optional output from the tool
            tool_use_id: Unique ID for correlation (generates if not provided)
            blocked: Whether the tool call was blocked by a hook
            block_reason: Reason for blocking if blocked

        Returns:
            The recorded ToolCallMetric
        """
        # Generate tool_use_id if not provided
        tool_use_id = tool_use_id or f"toolu_{uuid.uuid4().hex[:12]}"

        tool_metric = ToolCallMetric(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            tool_use_id=tool_use_id,
            duration_ms=duration_ms,
            blocked=blocked,
            block_reason=block_reason,
        )

        # Add to current interaction if one exists
        if self._current_interaction:
            self._current_interaction.tool_calls.append(tool_metric)

        # Emit canonical ToolCalled event
        self.emitter.emit(
            ToolCalled(
                session_id=self.session_id,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
                tool_output=tool_output,
                duration_ms=duration_ms,
                blocked=blocked,
                block_reason=block_reason,
            )
        )

        return tool_metric

    def end(self) -> SessionMetrics:
        """End the session and return aggregate metrics.

        Emits a SessionEnded event to the analytics stream.

        Returns:
            SessionMetrics with aggregate data
        """
        if self._ended:
            raise RuntimeError("Session already ended")

        self._ended = True
        end_time = datetime.now(UTC)

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

        # Emit canonical SessionEnded event
        self.emitter.emit(
            SessionEnded(
                session_id=self.session_id,
                start_time=self.start_time,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
                total_cost_usd=cost,
                interaction_count=len(self.interactions),
                tool_call_count=tool_calls,
                tool_calls_blocked=blocked_calls,
                total_duration_ms=total_duration,
                model=self.model_config.api_name,
                exit_reason="completed",
            )
        )

        return metrics


class MetricsCollector:
    """Collects and persists metrics using agentic_analytics EventEmitter.

    Writes canonical events to a JSONL file compatible with the
    observability dashboard and analytics services.

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
        self.emitter = EventEmitter(output_path=self.output_path)

    def start_session(self, model: ModelConfig, session_id: str | None = None) -> SessionContext:
        """Start a new metrics session.

        Emits a SessionStarted event to the analytics stream.

        Args:
            model: Model configuration for cost calculation
            session_id: Optional session ID (generates UUID if not provided)

        Returns:
            SessionContext for recording metrics
        """
        session_id = session_id or str(uuid.uuid4())

        # Emit canonical SessionStarted event
        self.emitter.emit(
            SessionStarted(
                session_id=session_id,
                model=model.api_name,
                provider=model.provider,
                model_display_name=model.display_name,
                pricing={
                    "input_per_1m_tokens": model.input_per_1m_tokens,
                    "output_per_1m_tokens": model.output_per_1m_tokens,
                },
            )
        )

        return SessionContext(
            session_id=session_id,
            model_config=model,
            emitter=self.emitter,
        )

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
