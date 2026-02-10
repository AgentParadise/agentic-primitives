"""Event emitter for AI agent hooks.

Emit structured events to stdout as JSONL. Zero external dependencies.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from typing import IO, Any

from agentic_events.types import EventType, SecurityDecision


class EventEmitter:
    """Emit structured events to stdout as JSONL.

    This is the primary interface for hooks to emit observability events.
    Events are written as JSON lines to stdout, where they can be captured
    by the agent runner and stored for analysis.

    Zero external dependencies - uses only Python stdlib.

    Example:
        >>> emitter = EventEmitter(session_id="session-123", provider="claude")
        >>> emitter.tool_started("Bash", "toolu_abc", "git status")
        >>> # ... tool executes ...
        >>> emitter.tool_completed("Bash", "toolu_abc", success=True, duration_ms=150)
    """

    def __init__(
        self,
        session_id: str,
        provider: str = "claude",
        output: IO[str] | None = None,
    ) -> None:
        """Initialize the event emitter.

        Args:
            session_id: Unique identifier for the agent session.
            provider: Agent provider name (e.g., "claude", "openai").
            output: Output stream for events. Defaults to sys.stdout.
        """
        self.session_id = session_id
        self.provider = provider
        self._output = output or sys.stdout
        self._tool_start_times: dict[str, float] = {}

    def emit(
        self,
        event_type: EventType | str,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Emit an event to stdout as a JSON line.

        Args:
            event_type: The type of event (from EventType enum or string).
            context: Event-specific context data.
            **kwargs: Additional top-level fields to include.

        Returns:
            The emitted event dict (for testing/verification).
        """
        event = {
            "event_type": str(event_type),
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": self.session_id,
            "provider": self.provider,
            "context": context or {},
            **kwargs,
        }

        # Write as JSON line
        print(json.dumps(event, default=str), file=self._output, flush=True)

        return event

    # -------------------------------------------------------------------------
    # Session lifecycle events
    # -------------------------------------------------------------------------

    def session_started(self, source: str = "startup", **metadata: Any) -> dict[str, Any]:
        """Emit a session started event.

        Args:
            source: How the session started (startup, resume, clear, compact).
            **metadata: Additional metadata (e.g., transcript_path, permission_mode).
        """
        return self.emit(
            EventType.SESSION_STARTED,
            context={"source": source},
            metadata=metadata if metadata else None,
        )

    def session_completed(
        self,
        reason: str = "normal",
        duration_ms: int | None = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        """Emit a session completed event.

        Args:
            reason: Why the session ended (normal, error, timeout, cancelled).
            duration_ms: Total session duration in milliseconds.
            **metadata: Additional metadata.
        """
        context: dict[str, Any] = {"reason": reason}
        if duration_ms is not None:
            context["duration_ms"] = duration_ms
        return self.emit(
            EventType.SESSION_COMPLETED,
            context=context,
            metadata=metadata if metadata else None,
        )

    # -------------------------------------------------------------------------
    # Tool execution events
    # -------------------------------------------------------------------------

    def tool_started(
        self,
        tool_name: str,
        tool_use_id: str,
        input_preview: str = "",
        max_preview_length: int = 500,
    ) -> dict[str, Any]:
        """Emit a tool execution started event.

        Args:
            tool_name: Name of the tool (e.g., "Bash", "Write", "Read").
            tool_use_id: Unique identifier for this tool invocation.
            input_preview: Preview of tool input (truncated for storage).
            max_preview_length: Maximum length of input preview.
        """
        # Track start time for duration calculation
        self._tool_start_times[tool_use_id] = time.monotonic()

        return self.emit(
            EventType.TOOL_STARTED,
            context={
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "input_preview": input_preview[:max_preview_length],
            },
        )

    def tool_completed(
        self,
        tool_name: str,
        tool_use_id: str,
        success: bool,
        duration_ms: int | None = None,
        output_preview: str = "",
        error: str | None = None,
        max_preview_length: int = 500,
    ) -> dict[str, Any]:
        """Emit a tool execution completed event.

        Args:
            tool_name: Name of the tool.
            tool_use_id: Unique identifier for this tool invocation.
            success: Whether the tool execution succeeded.
            duration_ms: Execution duration. Auto-calculated if tool_started was called.
            output_preview: Preview of tool output (truncated for storage).
            error: Error message if the tool failed.
            max_preview_length: Maximum length of output preview.
        """
        # Calculate duration if not provided and we tracked start time
        if duration_ms is None and tool_use_id in self._tool_start_times:
            start_time = self._tool_start_times.pop(tool_use_id)
            duration_ms = int((time.monotonic() - start_time) * 1000)

        context: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "success": success,
        }

        if duration_ms is not None:
            context["duration_ms"] = duration_ms
        if output_preview:
            context["output_preview"] = output_preview[:max_preview_length]
        if error:
            context["error"] = error

        return self.emit(EventType.TOOL_COMPLETED, context=context)

    # -------------------------------------------------------------------------
    # Security events
    # -------------------------------------------------------------------------

    def security_decision(
        self,
        tool_name: str,
        decision: SecurityDecision | str,
        reason: str = "",
        validators: list[str] | None = None,
        tool_use_id: str | None = None,
    ) -> dict[str, Any]:
        """Emit a security decision event.

        Args:
            tool_name: Name of the tool being evaluated.
            decision: The security decision (allow, block, warn).
            reason: Reason for the decision (especially for block/warn).
            validators: List of validators that were run.
            tool_use_id: Optional tool use ID for correlation.
        """
        context: dict[str, Any] = {
            "tool_name": tool_name,
            "decision": str(decision),
        }

        if reason:
            context["reason"] = reason
        if validators:
            context["validators"] = validators
        if tool_use_id:
            context["tool_use_id"] = tool_use_id

        return self.emit(EventType.SECURITY_DECISION, context=context)

    # -------------------------------------------------------------------------
    # Agent control events
    # -------------------------------------------------------------------------

    def agent_stopped(self, reason: str = "normal", **metadata: Any) -> dict[str, Any]:
        """Emit an agent stopped event.

        Args:
            reason: Why the agent stopped (normal, error, timeout, user_cancelled).
            **metadata: Additional metadata.
        """
        return self.emit(
            EventType.AGENT_STOPPED,
            context={"reason": reason},
            metadata=metadata if metadata else None,
        )

    def subagent_stopped(
        self,
        subagent_id: str,
        reason: str = "normal",
        **metadata: Any,
    ) -> dict[str, Any]:
        """Emit a subagent stopped event.

        Args:
            subagent_id: Identifier of the subagent.
            reason: Why the subagent stopped.
            **metadata: Additional metadata.
        """
        return self.emit(
            EventType.SUBAGENT_STOPPED,
            context={"subagent_id": subagent_id, "reason": reason},
            metadata=metadata if metadata else None,
        )

    # -------------------------------------------------------------------------
    # System events
    # -------------------------------------------------------------------------

    def context_compacted(
        self,
        before_tokens: int,
        after_tokens: int,
        **metadata: Any,
    ) -> dict[str, Any]:
        """Emit a context compacted event.

        Args:
            before_tokens: Token count before compaction.
            after_tokens: Token count after compaction.
            **metadata: Additional metadata.
        """
        return self.emit(
            EventType.CONTEXT_COMPACTED,
            context={
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
                "reduction_percent": round((1 - after_tokens / before_tokens) * 100, 1)
                if before_tokens > 0
                else 0,
            },
            metadata=metadata if metadata else None,
        )

    def notification(self, message: str, level: str = "info") -> dict[str, Any]:
        """Emit a system notification event.

        Args:
            message: The notification message.
            level: Notification level (info, warning, error).
        """
        return self.emit(
            EventType.NOTIFICATION,
            context={"message": message, "level": level},
        )

    # -------------------------------------------------------------------------
    # User interaction events
    # -------------------------------------------------------------------------

    def prompt_submitted(
        self,
        prompt_preview: str = "",
        max_preview_length: int = 200,
    ) -> dict[str, Any]:
        """Emit a user prompt submitted event.

        Args:
            prompt_preview: Preview of the prompt (truncated for privacy).
            max_preview_length: Maximum length of preview.
        """
        return self.emit(
            EventType.PROMPT_SUBMITTED,
            context={"prompt_preview": prompt_preview[:max_preview_length]},
        )

    def permission_requested(
        self,
        tool_name: str,
        permission_type: str,
        **metadata: Any,
    ) -> dict[str, Any]:
        """Emit a permission requested event.

        Args:
            tool_name: Tool requesting permission.
            permission_type: Type of permission requested.
            **metadata: Additional metadata.
        """
        return self.emit(
            EventType.PERMISSION_REQUESTED,
            context={"tool_name": tool_name, "permission_type": permission_type},
            metadata=metadata if metadata else None,
        )
