"""Event emitter for writing analytics events to JSONL.

This module provides a unified interface for emitting all event types
(SessionStarted, TokensUsed, ToolCalled, SessionEnded, HookDecision)
to the standard output file.

Usage:
    from agentic_analytics import EventEmitter, SessionStarted, ToolCalled

    emitter = EventEmitter()

    # Emit session start
    emitter.emit(SessionStarted(
        session_id="sess-123",
        model="claude-sonnet-4-5-20250929",
        provider="anthropic",
    ))

    # Emit tool call
    emitter.emit(ToolCalled(
        session_id="sess-123",
        tool_name="Write",
        tool_input={"file_path": "app.py"},
        tool_use_id="toolu_01ABC",
    ))

Session Context Manager:
    with emitter.session(model="claude-sonnet-4-5-20250929", provider="anthropic") as session:
        session.tokens_used(input_tokens=100, output_tokens=50)
        session.tool_called("Write", {"file_path": "app.py"})
"""

import json
import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_analytics.events import (
    AgentEvent,
    AuditContext,
    SessionEnded,
    SessionStarted,
    TokensUsed,
    ToolCalled,
)
from agentic_analytics.models import HookDecision


class EventEmitter:
    """Unified event emitter for analytics events.

    Writes events to JSONL file in a format compatible with the
    observability dashboard and analytics services.

    Attributes:
        output_path: Path to the JSONL output file
    """

    DEFAULT_PATH = Path(".agentic/analytics/events.jsonl")

    def __init__(
        self,
        output_path: Path | str | None = None,
    ) -> None:
        """Initialize the event emitter.

        Args:
            output_path: Path to JSONL file. Default: .agentic/analytics/events.jsonl
                         Can also be set via AGENTIC_EVENTS_PATH env var.
        """
        if output_path:
            self.output_path = Path(output_path)
        else:
            env_path = os.getenv("AGENTIC_EVENTS_PATH")
            self.output_path = Path(env_path) if env_path else self.DEFAULT_PATH

    def emit(self, event: AgentEvent | HookDecision) -> None:
        """Emit an event to the JSONL file.

        Fail-safe: errors are silently ignored to avoid blocking agent execution.

        Args:
            event: Any analytics event (SessionStarted, TokensUsed, ToolCalled,
                   SessionEnded, or HookDecision)
        """
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict - all events have to_dict()
            event_dict = event.to_dict()

            # HookDecision needs timestamp added (events.py events already have it)
            if isinstance(event, HookDecision):
                event_dict = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event_type": "hook_decision",
                    **event_dict,
                }

            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_dict) + "\n")
        except Exception:
            # Fail-safe: never block agent execution
            pass

    def emit_raw(self, event_type: str, session_id: str, data: dict[str, Any]) -> None:
        """Emit a raw event dictionary.

        Useful for custom event types not covered by the standard schemas.

        Args:
            event_type: Type of event (e.g., "custom.milestone")
            session_id: Session identifier
            data: Event-specific data
        """
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "session_id": session_id,
                "data": data,
            }

            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass

    @contextmanager
    def session(
        self,
        model: str,
        provider: str,
        session_id: str | None = None,
        model_display_name: str | None = None,
        pricing: dict[str, float] | None = None,
        audit: AuditContext | None = None,
    ) -> Generator["SessionContext", None, None]:
        """Context manager for tracking a complete session.

        Automatically emits SessionStarted on entry and SessionEnded on exit.

        Args:
            model: Model identifier
            provider: Provider name
            session_id: Optional session ID (generates UUID if not provided)
            model_display_name: Human-readable model name
            pricing: Token pricing info
            audit: Optional audit context

        Yields:
            SessionContext for recording events within the session

        Example:
            with emitter.session(model="claude-sonnet-4-5", provider="anthropic") as s:
                s.tokens_used(input_tokens=100, output_tokens=50)
                s.tool_called("Write", {"file_path": "app.py"})
        """
        ctx = SessionContext(
            emitter=self,
            model=model,
            provider=provider,
            session_id=session_id or str(uuid.uuid4()),
            model_display_name=model_display_name,
            pricing=pricing,
            audit=audit,
        )
        ctx._start()
        try:
            yield ctx
        finally:
            ctx._end()


class SessionContext:
    """Context for tracking events within a session.

    Provides convenience methods for emitting events and automatically
    tracks aggregates for the SessionEnded event.
    """

    def __init__(
        self,
        emitter: EventEmitter,
        model: str,
        provider: str,
        session_id: str,
        model_display_name: str | None = None,
        pricing: dict[str, float] | None = None,
        audit: AuditContext | None = None,
    ) -> None:
        self.emitter = emitter
        self.model = model
        self.provider = provider
        self.session_id = session_id
        self.model_display_name = model_display_name
        self.pricing = pricing
        self.audit = audit

        # Aggregates for SessionEnded
        self._start_time: datetime | None = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_duration_ms = 0.0
        self._interaction_count = 0
        self._tool_call_count = 0
        self._tool_calls_blocked = 0

    def _start(self) -> None:
        """Emit SessionStarted event."""
        self._start_time = datetime.now(UTC)
        self.emitter.emit(
            SessionStarted(
                session_id=self.session_id,
                model=self.model,
                provider=self.provider,
                timestamp=self._start_time,
                model_display_name=self.model_display_name,
                pricing=self.pricing,
                audit=self.audit,
            )
        )

    def _end(self, exit_reason: str = "completed") -> None:
        """Emit SessionEnded event with aggregates."""
        total_cost = 0.0
        if self.pricing:
            input_rate = self.pricing.get("input_per_1m_tokens", 0)
            output_rate = self.pricing.get("output_per_1m_tokens", 0)
            input_cost = (self._total_input_tokens / 1_000_000) * input_rate
            output_cost = (self._total_output_tokens / 1_000_000) * output_rate
            total_cost = input_cost + output_cost

        self.emitter.emit(
            SessionEnded(
                session_id=self.session_id,
                start_time=self._start_time,
                total_input_tokens=self._total_input_tokens,
                total_output_tokens=self._total_output_tokens,
                total_cost_usd=total_cost,
                interaction_count=self._interaction_count,
                tool_call_count=self._tool_call_count,
                tool_calls_blocked=self._tool_calls_blocked,
                total_duration_ms=self._total_duration_ms,
                model=self.model,
                exit_reason=exit_reason,
            )
        )

    def tokens_used(
        self,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float | None = None,
        prompt_preview: str | None = None,
        response_preview: str | None = None,
    ) -> TokensUsed:
        """Record token usage for an interaction.

        Args:
            input_tokens: Tokens in the prompt
            output_tokens: Tokens in the response
            duration_ms: Time taken for the interaction
            prompt_preview: First N chars of prompt
            response_preview: First N chars of response

        Returns:
            The emitted TokensUsed event
        """
        event = TokensUsed(
            session_id=self.session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            prompt_preview=prompt_preview[:100] if prompt_preview else None,
            response_preview=response_preview[:100] if response_preview else None,
            interaction_index=self._interaction_count,
        )
        self.emitter.emit(event)

        # Update aggregates
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        if duration_ms:
            self._total_duration_ms += duration_ms
        self._interaction_count += 1

        return event

    def tool_called(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str | None = None,
        tool_output: str | None = None,
        duration_ms: float | None = None,
        blocked: bool = False,
        block_reason: str | None = None,
    ) -> ToolCalled:
        """Record a tool call.

        Args:
            tool_name: Name of the tool
            tool_input: Input parameters
            tool_use_id: Correlation ID (generates if not provided)
            tool_output: Output from the tool
            duration_ms: Time taken for the call
            blocked: Whether blocked by a hook
            block_reason: Reason for blocking

        Returns:
            The emitted ToolCalled event
        """
        event = ToolCalled(
            session_id=self.session_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id or f"toolu_{uuid.uuid4().hex[:12]}",
            tool_output=tool_output,
            duration_ms=duration_ms,
            blocked=blocked,
            block_reason=block_reason,
        )
        self.emitter.emit(event)

        # Update aggregates
        self._tool_call_count += 1
        if blocked:
            self._tool_calls_blocked += 1

        return event


# Convenience functions
def emit(event: AgentEvent | HookDecision) -> None:
    """Emit an event using the default emitter.

    Args:
        event: Any analytics event
    """
    EventEmitter().emit(event)


def emit_raw(event_type: str, session_id: str, data: dict[str, Any]) -> None:
    """Emit a raw event using the default emitter.

    Args:
        event_type: Type of event
        session_id: Session identifier
        data: Event-specific data
    """
    EventEmitter().emit_raw(event_type, session_id, data)
