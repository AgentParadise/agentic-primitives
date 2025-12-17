"""Tests for NullObservability implementation."""

import os

import pytest

from agentic_observability import (
    NullObservability,
    ObservationContext,
    ObservationType,
    TestOnlyAdapterError,
)


@pytest.fixture(autouse=True)
def set_test_environment():
    """Ensure we're in test environment for most tests."""
    original = os.environ.get("AEF_ENVIRONMENT")
    os.environ["AEF_ENVIRONMENT"] = "test"
    yield
    if original is None:
        os.environ.pop("AEF_ENVIRONMENT", None)
    else:
        os.environ["AEF_ENVIRONMENT"] = original


class TestNullObservabilitySafetyGuard:
    """Tests for the TestOnlyAdapterError safety guard."""

    def test_raises_in_development(self):
        """Should throw when AEF_ENVIRONMENT is 'development'."""
        os.environ["AEF_ENVIRONMENT"] = "development"
        with pytest.raises(TestOnlyAdapterError) as exc_info:
            NullObservability()
        assert "AEF_ENVIRONMENT='test'" in str(exc_info.value)
        assert "development" in str(exc_info.value)

    def test_raises_in_production(self):
        """Should throw when AEF_ENVIRONMENT is 'production'."""
        os.environ["AEF_ENVIRONMENT"] = "production"
        with pytest.raises(TestOnlyAdapterError) as exc_info:
            NullObservability()
        assert "production" in str(exc_info.value)

    def test_raises_when_not_set(self):
        """Should throw when AEF_ENVIRONMENT is not set."""
        os.environ.pop("AEF_ENVIRONMENT", None)
        with pytest.raises(TestOnlyAdapterError) as exc_info:
            NullObservability()
        assert "not set" in str(exc_info.value)

    def test_allows_test_environment(self):
        """Should allow instantiation in test environment."""
        os.environ["AEF_ENVIRONMENT"] = "test"
        observability = NullObservability()
        assert observability is not None


class TestNullObservabilityRecording:
    """Tests for observation recording."""

    @pytest.fixture
    def observability(self):
        """Create a NullObservability instance."""
        return NullObservability()

    @pytest.fixture
    def context(self):
        """Create a test context."""
        return ObservationContext(
            session_id="session-123",
            execution_id="exec-456",
        )

    @pytest.mark.asyncio
    async def test_record_generic(self, observability, context):
        """Can record a generic observation."""
        await observability.record(
            ObservationType.PROGRESS,
            context,
            {"message": "Processing..."},
        )
        assert observability.count == 1

    @pytest.mark.asyncio
    async def test_record_tool_started(self, observability, context):
        """Can record tool started observations."""
        op_id = await observability.record_tool_started(
            context,
            tool_name="Bash",
            tool_input={"command": "echo 'hello'"},
        )
        assert op_id is not None
        assert observability.has_observation(ObservationType.TOOL_STARTED)

    @pytest.mark.asyncio
    async def test_record_tool_completed(self, observability, context):
        """Can record tool completed observations."""
        await observability.record_tool_completed(
            context,
            operation_id="op-123",
            tool_name="Bash",
            success=True,
            duration_ms=150,
            output_preview="hello",
        )
        assert observability.has_observation(ObservationType.TOOL_COMPLETED)

    @pytest.mark.asyncio
    async def test_record_token_usage(self, observability, context):
        """Can record token usage observations."""
        await observability.record_token_usage(
            context,
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=100,
            model="claude-sonnet-4-20250514",
        )
        obs = observability.get_observations(ObservationType.TOKEN_USAGE)
        assert len(obs) == 1
        assert obs[0].data["input_tokens"] == 1000
        assert obs[0].data["output_tokens"] == 500


class TestNullObservabilityTestHelpers:
    """Tests for test helper methods."""

    @pytest.fixture
    def observability(self):
        """Create a NullObservability instance."""
        return NullObservability()

    @pytest.fixture
    def context(self):
        """Create a test context."""
        return ObservationContext(session_id="session-123")

    @pytest.mark.asyncio
    async def test_count(self, observability, context):
        """Count should track recorded observations."""
        assert observability.count == 0
        await observability.record(ObservationType.PROGRESS, context, {})
        assert observability.count == 1
        await observability.record(ObservationType.PROGRESS, context, {})
        assert observability.count == 2

    @pytest.mark.asyncio
    async def test_has_observation(self, observability, context):
        """has_observation should check for specific types."""
        assert not observability.has_observation(ObservationType.TOKEN_USAGE)
        await observability.record_token_usage(context, 100, 50)
        assert observability.has_observation(ObservationType.TOKEN_USAGE)
        assert not observability.has_observation(ObservationType.TOOL_STARTED)

    @pytest.mark.asyncio
    async def test_get_observations(self, observability, context):
        """get_observations should filter by type."""
        await observability.record(ObservationType.PROGRESS, context, {"step": 1})
        await observability.record_token_usage(context, 100, 50)
        await observability.record(ObservationType.PROGRESS, context, {"step": 2})

        progress = observability.get_observations(ObservationType.PROGRESS)
        assert len(progress) == 2
        assert progress[0].data["step"] == 1
        assert progress[1].data["step"] == 2

    @pytest.mark.asyncio
    async def test_get_by_session(self, observability):
        """get_by_session should filter by session_id."""
        ctx1 = ObservationContext(session_id="session-1")
        ctx2 = ObservationContext(session_id="session-2")

        await observability.record(ObservationType.PROGRESS, ctx1, {"msg": "a"})
        await observability.record(ObservationType.PROGRESS, ctx2, {"msg": "b"})
        await observability.record(ObservationType.PROGRESS, ctx1, {"msg": "c"})

        session1_obs = observability.get_by_session("session-1")
        assert len(session1_obs) == 2

        session2_obs = observability.get_by_session("session-2")
        assert len(session2_obs) == 1

    @pytest.mark.asyncio
    async def test_clear(self, observability, context):
        """clear should remove all observations."""
        await observability.record(ObservationType.PROGRESS, context, {})
        await observability.record(ObservationType.PROGRESS, context, {})
        assert observability.count == 2

        observability.clear()
        assert observability.count == 0

    @pytest.mark.asyncio
    async def test_assert_has_observation(self, observability, context):
        """assert_has_observation should return matching observation."""
        await observability.record_token_usage(context, 100, 50)

        obs = observability.assert_has_observation(ObservationType.TOKEN_USAGE)
        assert obs.data["input_tokens"] == 100

    @pytest.mark.asyncio
    async def test_assert_has_observation_fails(self, observability):
        """assert_has_observation should raise if not found."""
        with pytest.raises(AssertionError) as exc_info:
            observability.assert_has_observation(ObservationType.TOKEN_USAGE)
        assert "TOKEN_USAGE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_assert_observation_count(self, observability, context):
        """assert_observation_count should validate count."""
        await observability.record(ObservationType.PROGRESS, context, {})
        await observability.record(ObservationType.PROGRESS, context, {})

        observability.assert_observation_count(ObservationType.PROGRESS, 2)

    @pytest.mark.asyncio
    async def test_assert_observation_count_fails(self, observability, context):
        """assert_observation_count should raise on mismatch."""
        await observability.record(ObservationType.PROGRESS, context, {})

        with pytest.raises(AssertionError) as exc_info:
            observability.assert_observation_count(ObservationType.PROGRESS, 5)
        assert "Expected 5" in str(exc_info.value)
        assert "found 1" in str(exc_info.value)


class TestNullObservabilityFlushAndClose:
    """Tests for flush and close methods."""

    @pytest.mark.asyncio
    async def test_flush_is_noop(self):
        """flush should succeed without error."""
        observability = NullObservability()
        await observability.flush()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        """close should succeed without error."""
        observability = NullObservability()
        await observability.close()  # Should not raise
