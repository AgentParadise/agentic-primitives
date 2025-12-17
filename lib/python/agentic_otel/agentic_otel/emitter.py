"""OTel emitter for hook scripts.

Provides a high-level interface for emitting spans and events
from Claude Code hook scripts (pre_tool_use, post_tool_use, etc.).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from agentic_otel.semantic import AgentSemanticConventions as Sem
from agentic_otel.setup import get_tracer, initialize_otel

if TYPE_CHECKING:
    from agentic_otel.config import OTelConfig


class HookOTelEmitter:
    """Emit OTel signals from hook scripts.

    Used inside .claude/hooks/*.py to emit spans and events
    for tool executions and security decisions.

    Example:
        >>> from agentic_otel import HookOTelEmitter, OTelConfig
        >>>
        >>> config = OTelConfig(endpoint="http://collector:4317")
        >>> emitter = HookOTelEmitter(config)
        >>>
        >>> with emitter.start_tool_span("Bash", "toolu_123", {"command": "ls"}) as span:
        ...     result = run_security_checks()
        ...     span.set_attribute("tool.success", result.safe)
    """

    def __init__(self, config: OTelConfig) -> None:
        """Initialize the emitter with OTel configuration.

        This also initializes the OTel SDK if not already done.

        Args:
            config: OTel configuration with endpoint and attributes.
        """
        self._config = config
        initialize_otel(config)
        self._tracer = get_tracer("agentic.hooks")
        self._logger = logging.getLogger("agentic.otel")

    @contextmanager
    def start_tool_span(
        self,
        tool_name: str,
        tool_use_id: str,
        tool_input: dict[str, Any] | None = None,
        max_input_length: int = 1000,
    ) -> Iterator[Span]:
        """Start a span for tool execution.

        Creates an OTel span that tracks the lifecycle of a tool call.
        Use as a context manager - the span is automatically ended.

        Args:
            tool_name: Name of the tool (e.g., "Bash", "Write").
            tool_use_id: Unique identifier for this tool invocation.
            tool_input: Tool input parameters (will be JSON-serialized).
            max_input_length: Maximum length of serialized input to store.

        Yields:
            The OTel Span object for adding additional attributes.

        Example:
            >>> with emitter.start_tool_span("Bash", "toolu_123", {"command": "ls"}) as span:
            ...     # Do work
            ...     span.set_attribute("custom.attr", "value")
        """
        # Truncate input for storage
        input_str = ""
        if tool_input:
            try:
                input_str = json.dumps(tool_input)[:max_input_length]
            except (TypeError, ValueError):
                input_str = str(tool_input)[:max_input_length]

        span = self._tracer.start_span(
            name=f"tool.{tool_name}",
            attributes={
                Sem.TOOL_NAME: tool_name,
                Sem.TOOL_USE_ID: tool_use_id,
                Sem.TOOL_INPUT: input_str,
            },
        )

        start_time = time.monotonic()

        try:
            with trace.use_span(span, end_on_exit=False):
                yield span
                # If we get here without exception, mark success
                span.set_status(Status(StatusCode.OK))
                span.set_attribute(Sem.TOOL_SUCCESS, True)
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.set_attribute(Sem.TOOL_SUCCESS, False)
            span.set_attribute(Sem.TOOL_ERROR, str(e))
            span.record_exception(e)
            raise
        finally:
            duration_ms = (time.monotonic() - start_time) * 1000
            span.set_attribute(Sem.TOOL_DURATION_MS, duration_ms)
            span.end()

    def emit_security_event(
        self,
        hook_type: str,
        decision: str,
        tool_name: str,
        tool_use_id: str,
        reason: str | None = None,
        validators: list[str] | None = None,
    ) -> None:
        """Emit a security decision as an OTel event.

        Records a security decision (allow/block/warn) as an OTel log event.
        These events are correlated with tool spans via tool_use_id.

        Args:
            hook_type: Type of hook (e.g., "pre_tool_use", "post_tool_use").
            decision: Security decision ("allow", "block", "warn").
            tool_name: Name of the tool being evaluated.
            tool_use_id: Unique identifier for the tool invocation.
            reason: Reason for block/warn decision.
            validators: List of validators that were run.

        Example:
            >>> emitter.emit_security_event(
            ...     hook_type="pre_tool_use",
            ...     decision="block",
            ...     tool_name="Bash",
            ...     tool_use_id="toolu_123",
            ...     reason="Dangerous command: rm -rf /",
            ...     validators=["bash_validator"],
            ... )
        """
        # Get current span if in context
        current_span = trace.get_current_span()

        # Build event attributes
        attributes: dict[str, Any] = {
            Sem.HOOK_TYPE: hook_type,
            Sem.HOOK_DECISION: decision,
            Sem.TOOL_NAME: tool_name,
            Sem.TOOL_USE_ID: tool_use_id,
        }

        if reason:
            attributes[Sem.HOOK_REASON] = reason
        if validators:
            attributes[Sem.HOOK_VALIDATORS] = ",".join(validators)

        # Add as span event if we have an active span
        if current_span.is_recording():
            current_span.add_event(
                name=Sem.EVENT_SECURITY_DECISION,
                attributes=attributes,
            )
        else:
            # Fall back to logging (will be picked up by OTel logging handler)
            self._logger.info(
                "Security decision: %s for %s",
                decision,
                tool_name,
                extra={"otel.event.name": Sem.EVENT_SECURITY_DECISION, **attributes},
            )

    def record_tool_output(
        self,
        span: Span,
        output: str,
        success: bool = True,
        max_output_length: int = 500,
    ) -> None:
        """Record tool output on a span.

        Call this to add the tool's output to the span before it ends.

        Args:
            span: The span from start_tool_span.
            output: Tool output (will be truncated).
            success: Whether the tool execution succeeded.
            max_output_length: Maximum length of output to store.
        """
        span.set_attribute(Sem.TOOL_OUTPUT_PREVIEW, output[:max_output_length])
        span.set_attribute(Sem.TOOL_SUCCESS, success)

        if success:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, "Tool execution failed"))
