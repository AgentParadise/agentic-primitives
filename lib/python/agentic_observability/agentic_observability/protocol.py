"""ObservabilityPort protocol definition.

This module defines the core ObservabilityPort protocol that all agent
executors must depend on. This is a Poka-Yoke pattern that makes it
impossible to run agents without observability configured.

Usage:
    from agentic_observability import ObservabilityPort

    class WorkflowExecutor:
        def __init__(self, observability: ObservabilityPort) -> None:
            # Observability is REQUIRED - no default None!
            self._observability = observability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


class ObservationType(str, Enum):
    """Types of observations that can be recorded.

    These align with the Claude SDK events and AEF domain events.
    Using str enum ensures consistent serialization.
    """

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    SESSION_ERROR = "session_error"
    SESSION_CANCELLED = "session_cancelled"

    # Execution lifecycle
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_ERROR = "execution_error"

    # Tool operations
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_ERROR = "tool_error"

    # Token usage
    TOKEN_USAGE = "token_usage"

    # Context management
    CONTEXT_COMPACTING = "context_compacting"

    # Sub-agent operations
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_STOPPED = "subagent_stopped"

    # Progress updates
    PROGRESS = "progress"


@dataclass(frozen=True)
class ObservationContext:
    """Context for an observation.

    Immutable dataclass that carries all the context needed to
    identify and correlate observations.
    """

    session_id: str
    execution_id: str | None = None
    workflow_id: str | None = None
    phase_id: str | None = None
    agent_id: str | None = None
    observation_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    def with_execution(self, execution_id: str) -> ObservationContext:
        """Create a new context with execution_id set."""
        return ObservationContext(
            session_id=self.session_id,
            execution_id=execution_id,
            workflow_id=self.workflow_id,
            phase_id=self.phase_id,
            agent_id=self.agent_id,
            observation_id=self.observation_id,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
        )


@runtime_checkable
class ObservabilityPort(Protocol):
    """Protocol for observability implementations.

    This is the core abstraction that all agent executors MUST depend on.
    By making this a required constructor argument (not optional), we
    enforce observability as a first-class requirement.

    Implementations:
        - TimescaleObservability: Production (writes to TimescaleDB)
        - NullObservability: Tests only (throws if not in test env)

    Why Protocol?
        - Enables dependency injection
        - Allows different backends (TimescaleDB, OpenTelemetry, etc.)
        - Makes testing straightforward with NullObservability
        - Type-safe at runtime (@runtime_checkable)
    """

    async def record(
        self,
        observation_type: ObservationType,
        context: ObservationContext,
        data: dict[str, Any],
    ) -> None:
        """Record an observation.

        This is the primary method for recording any type of observation.
        Implementations should be non-blocking and fail-safe.

        Args:
            observation_type: The type of observation to record
            context: Context identifying the session/execution
            data: Observation-specific data (tool name, tokens, etc.)

        Note:
            This method should NEVER raise exceptions that would
            interrupt agent execution. Log errors internally.
        """
        ...

    async def record_tool_started(
        self,
        context: ObservationContext,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> str:
        """Record a tool execution starting.

        Convenience method for tool_started observations.

        Args:
            context: Observation context
            tool_name: Name of the tool being executed
            tool_input: Input parameters to the tool

        Returns:
            Operation ID for correlating with tool_completed
        """
        ...

    async def record_tool_completed(
        self,
        context: ObservationContext,
        operation_id: str,
        tool_name: str,
        success: bool,
        duration_ms: int,
        output_preview: str | None = None,
    ) -> None:
        """Record a tool execution completing.

        Convenience method for tool_completed observations.

        Args:
            context: Observation context
            operation_id: ID from record_tool_started
            tool_name: Name of the tool that executed
            success: Whether execution succeeded
            duration_ms: Duration in milliseconds
            output_preview: Optional preview of output
        """
        ...

    async def record_token_usage(
        self,
        context: ObservationContext,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: str | None = None,
    ) -> None:
        """Record token usage.

        Convenience method for token_usage observations.

        Args:
            context: Observation context
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            cache_read_tokens: Tokens read from cache
            cache_write_tokens: Tokens written to cache
            model: Model identifier
        """
        ...

    async def flush(self) -> None:
        """Flush any buffered observations.

        Ensures all observations are persisted. Call this before
        session/execution ends to avoid data loss.
        """
        ...

    async def close(self) -> None:
        """Close the observability client.

        Release any resources (connections, buffers, etc.).
        """
        ...
