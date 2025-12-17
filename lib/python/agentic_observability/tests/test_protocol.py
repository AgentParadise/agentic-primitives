"""Tests for the ObservabilityPort protocol."""

import os
from typing import Any

import pytest

from agentic_observability import (
    NullObservability,
    ObservabilityPort,
    ObservationContext,
    ObservationType,
)


@pytest.fixture(autouse=True)
def set_test_environment():
    """Ensure we're in test environment."""
    original = os.environ.get("AEF_ENVIRONMENT")
    os.environ["AEF_ENVIRONMENT"] = "test"
    yield
    if original is None:
        del os.environ["AEF_ENVIRONMENT"]
    else:
        os.environ["AEF_ENVIRONMENT"] = original


class TestObservationType:
    """Tests for ObservationType enum."""

    def test_types_are_strings(self):
        """ObservationType values should be strings for serialization."""
        assert isinstance(ObservationType.TOKEN_USAGE.value, str)
        assert ObservationType.TOKEN_USAGE.value == "token_usage"

    def test_all_types_defined(self):
        """Critical observation types should be defined."""
        expected_types = [
            "SESSION_STARTED",
            "SESSION_COMPLETED",
            "EXECUTION_STARTED",
            "EXECUTION_COMPLETED",
            "TOOL_STARTED",
            "TOOL_COMPLETED",
            "TOKEN_USAGE",
        ]
        for type_name in expected_types:
            assert hasattr(ObservationType, type_name), f"Missing type: {type_name}"


class TestObservationContext:
    """Tests for ObservationContext dataclass."""

    def test_minimal_context(self):
        """Context only requires session_id."""
        ctx = ObservationContext(session_id="session-123")
        assert ctx.session_id == "session-123"
        assert ctx.execution_id is None
        assert ctx.observation_id  # Auto-generated

    def test_full_context(self):
        """Context can include all fields."""
        ctx = ObservationContext(
            session_id="session-123",
            execution_id="exec-456",
            workflow_id="workflow-789",
            phase_id="phase-1",
            agent_id="agent-abc",
            correlation_id="corr-xyz",
        )
        assert ctx.session_id == "session-123"
        assert ctx.execution_id == "exec-456"
        assert ctx.workflow_id == "workflow-789"

    def test_immutable(self):
        """Context should be immutable."""
        ctx = ObservationContext(session_id="session-123")
        with pytest.raises(AttributeError):
            ctx.session_id = "changed"  # type: ignore

    def test_with_execution(self):
        """with_execution should return new context."""
        ctx = ObservationContext(session_id="session-123", workflow_id="workflow-789")
        new_ctx = ctx.with_execution("exec-456")

        # Original unchanged
        assert ctx.execution_id is None

        # New context has execution_id
        assert new_ctx.execution_id == "exec-456"
        assert new_ctx.session_id == "session-123"
        assert new_ctx.workflow_id == "workflow-789"


class TestObservabilityPortProtocol:
    """Tests for ObservabilityPort protocol conformance."""

    def test_null_observability_is_protocol_compliant(self):
        """NullObservability should implement ObservabilityPort."""
        observability = NullObservability()
        assert isinstance(observability, ObservabilityPort)

    def test_custom_implementation(self):
        """Custom implementations can satisfy the protocol."""

        class CustomObservability:
            """Custom implementation for testing."""

            async def record(
                self,
                observation_type: ObservationType,
                context: ObservationContext,
                data: dict[str, Any],
            ) -> None:
                pass

            async def record_tool_started(
                self,
                context: ObservationContext,
                tool_name: str,
                tool_input: dict[str, Any],
            ) -> str:
                return "op-123"

            async def record_tool_completed(
                self,
                context: ObservationContext,
                operation_id: str,
                tool_name: str,
                success: bool,
                duration_ms: int,
                output_preview: str | None = None,
            ) -> None:
                pass

            async def record_token_usage(
                self,
                context: ObservationContext,
                input_tokens: int,
                output_tokens: int,
                cache_read_tokens: int = 0,
                cache_write_tokens: int = 0,
                model: str | None = None,
            ) -> None:
                pass

            async def flush(self) -> None:
                pass

            async def close(self) -> None:
                pass

        custom = CustomObservability()
        assert isinstance(custom, ObservabilityPort)
