"""NullObservability implementation for tests.

CRITICAL: This adapter throws TestOnlyAdapterError if AEF_ENVIRONMENT != 'test'.
This prevents accidental use in production/development where observations would be lost.

Usage:
    # In tests only
    os.environ["AEF_ENVIRONMENT"] = "test"
    observability = NullObservability()

    executor = WorkflowExecutor(observability=observability)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agentic_observability.exceptions import TestOnlyAdapterError
from agentic_observability.protocol import ObservationContext, ObservationType


@dataclass
class RecordedObservation:
    """A recorded observation for test assertions."""

    observation_type: ObservationType
    context: ObservationContext
    data: dict[str, Any]


class NullObservability:
    """Null implementation of ObservabilityPort for unit tests.

    CRITICAL: Throws TestOnlyAdapterError if AEF_ENVIRONMENT != 'test'.

    This implementation:
    - Records observations in memory for test assertions
    - Never writes to any external system
    - Must NEVER be used in production
    - Provides helpers for test assertions

    Usage:
        # Ensure test environment
        os.environ["AEF_ENVIRONMENT"] = "test"

        observability = NullObservability()
        executor = WorkflowExecutor(observability=observability)

        # Run test
        await executor.run(...)

        # Assert observations
        assert observability.count == 5
        assert observability.has_observation(ObservationType.TOKEN_USAGE)
        tool_ops = observability.get_observations(ObservationType.TOOL_COMPLETED)
    """

    def __init__(self) -> None:
        """Initialize null observability.

        Raises:
            TestOnlyAdapterError: If AEF_ENVIRONMENT is not 'test'
        """
        env = os.environ.get("AEF_ENVIRONMENT", "")
        if env != "test":
            raise TestOnlyAdapterError("NullObservability")

        self._observations: list[RecordedObservation] = []
        self._operation_ids: dict[str, dict[str, Any]] = {}

    async def record(
        self,
        observation_type: ObservationType,
        context: ObservationContext,
        data: dict[str, Any],
    ) -> None:
        """Record an observation to memory."""
        self._observations.append(
            RecordedObservation(
                observation_type=observation_type,
                context=context,
                data=data,
            )
        )

    async def record_tool_started(
        self,
        context: ObservationContext,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> str:
        """Record a tool started observation."""
        operation_id = str(uuid4())

        self._operation_ids[operation_id] = {
            "tool_name": tool_name,
            "context": context,
        }

        await self.record(
            ObservationType.TOOL_STARTED,
            context,
            {
                "operation_id": operation_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
            },
        )
        return operation_id

    async def record_tool_completed(
        self,
        context: ObservationContext,
        operation_id: str,
        tool_name: str,
        success: bool,
        duration_ms: int,
        output_preview: str | None = None,
    ) -> None:
        """Record a tool completed observation."""
        await self.record(
            ObservationType.TOOL_COMPLETED,
            context,
            {
                "operation_id": operation_id,
                "tool_name": tool_name,
                "success": success,
                "duration_ms": duration_ms,
                "output_preview": output_preview,
            },
        )

    async def record_token_usage(
        self,
        context: ObservationContext,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: str | None = None,
    ) -> None:
        """Record token usage observation."""
        await self.record(
            ObservationType.TOKEN_USAGE,
            context,
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "model": model,
            },
        )

    async def flush(self) -> None:
        """No-op for null implementation."""
        pass

    async def close(self) -> None:
        """No-op for null implementation."""
        pass

    # ─── Test Helpers ───────────────────────────────────────────────────

    @property
    def observations(self) -> list[RecordedObservation]:
        """Get all recorded observations."""
        return list(self._observations)

    @property
    def count(self) -> int:
        """Get number of recorded observations."""
        return len(self._observations)

    def has_observation(self, observation_type: ObservationType) -> bool:
        """Check if an observation of the given type was recorded."""
        return any(o.observation_type == observation_type for o in self._observations)

    def get_observations(self, observation_type: ObservationType) -> list[RecordedObservation]:
        """Get all observations of a specific type."""
        return [o for o in self._observations if o.observation_type == observation_type]

    def get_by_session(self, session_id: str) -> list[RecordedObservation]:
        """Get all observations for a specific session."""
        return [o for o in self._observations if o.context.session_id == session_id]

    def clear(self) -> None:
        """Clear all recorded observations (for test cleanup)."""
        self._observations.clear()
        self._operation_ids.clear()

    def assert_has_observation(
        self, observation_type: ObservationType, msg: str | None = None
    ) -> RecordedObservation:
        """Assert that at least one observation of this type exists.

        Returns the first matching observation.

        Raises:
            AssertionError: If no matching observation found
        """
        for obs in self._observations:
            if obs.observation_type == observation_type:
                return obs
        raise AssertionError(msg or f"Expected observation of type {observation_type}, found none")

    def assert_observation_count(
        self,
        observation_type: ObservationType,
        expected: int,
        msg: str | None = None,
    ) -> None:
        """Assert the count of observations of a specific type.

        Raises:
            AssertionError: If count doesn't match
        """
        actual = len(self.get_observations(observation_type))
        if actual != expected:
            raise AssertionError(
                msg
                or f"Expected {expected} observations of type {observation_type}, found {actual}"
            )
