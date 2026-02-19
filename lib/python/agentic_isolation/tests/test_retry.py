"""Tests for the retry and circuit breaker utilities.

Covers:
- RetryPolicy factory presets and delay computation
- retry_async: success, retry-until-success, exhaustion, predicate filtering
- CircuitBreaker: state machine, is_failure predicate, on_state_change callback
- retry_with_circuit_breaker: composition behaviour
- RetryExhaustedError and CircuitOpenError error helpers
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from agentic_isolation.retry import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RetryExhaustedError,
    RetryPolicy,
    retry_async,
    retry_with_circuit_breaker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TransientError(Exception):
    """Represents a transient (retryable) error."""


class FatalError(Exception):
    """Represents a non-retryable error."""


def make_fn(fail_count: int, result: object = "ok", error_type: type = TransientError):
    """Return an async callable that fails *fail_count* times then returns *result*."""
    calls = 0

    async def fn() -> object:
        nonlocal calls
        calls += 1
        if calls <= fail_count:
            raise error_type(f"Simulated failure #{calls}")
        return result

    return fn


def always_fail(error_type: type = TransientError):
    async def fn() -> object:
        raise error_type("always fails")

    return fn


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_exponential_defaults(self):
        p = RetryPolicy.exponential()
        assert p.max_attempts == 3
        assert p.backoff_factor == 2.0
        assert p.jitter is True

    def test_exponential_overrides(self):
        p = RetryPolicy.exponential(max_attempts=7, jitter=False)
        assert p.max_attempts == 7
        assert p.jitter is False
        assert p.backoff_factor == 2.0  # unchanged

    def test_fixed_constant_delay(self):
        p = RetryPolicy.fixed(delay_s=0.5)
        assert p.base_delay_s == 0.5
        assert p.max_delay_s == 0.5
        assert p.backoff_factor == 1.0
        assert p.jitter is False

    def test_none_single_attempt(self):
        p = RetryPolicy.none()
        assert p.max_attempts == 1
        assert p.base_delay_s == 0.0

    def test_compute_delay_no_jitter(self):
        p = RetryPolicy.fixed(delay_s=1.0)
        # All attempts should have the same delay
        for attempt in range(1, 6):
            assert p.compute_delay(attempt) == 1.0

    def test_compute_delay_exponential_no_jitter(self):
        p = RetryPolicy.exponential(base_delay_s=1.0, backoff_factor=2.0, jitter=False)
        assert p.compute_delay(1) == 1.0
        assert p.compute_delay(2) == 2.0
        assert p.compute_delay(3) == 4.0

    def test_compute_delay_respects_max(self):
        p = RetryPolicy.exponential(base_delay_s=1.0, max_delay_s=3.0, backoff_factor=2.0, jitter=False)
        assert p.compute_delay(5) == 3.0  # would be 16, capped at 3

    def test_compute_delay_jitter_within_bounds(self):
        p = RetryPolicy.exponential(base_delay_s=1.0, max_delay_s=10.0, backoff_factor=2.0, jitter=True)
        for _ in range(50):
            delay = p.compute_delay(1)
            assert 0.0 <= delay <= 1.0


# ---------------------------------------------------------------------------
# retry_async – success paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetryAsyncSuccess:
    async def test_returns_immediately_on_first_success(self):
        fn = AsyncMock(return_value="result")
        result = await retry_async(fn, policy=RetryPolicy.none())
        assert result == "result"
        fn.assert_called_once()

    async def test_retries_and_eventually_succeeds(self):
        fn = make_fn(fail_count=2, result="value")
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_async(fn, policy=RetryPolicy.fixed(delay_s=0.0, max_attempts=3))
        assert result == "value"

    async def test_uses_default_policy_when_none_provided(self):
        fn = AsyncMock(return_value=42)
        result = await retry_async(fn)
        assert result == 42


# ---------------------------------------------------------------------------
# retry_async – exhaustion paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetryAsyncExhausted:
    async def test_raises_retry_exhausted_after_max_attempts(self):
        fn = always_fail()
        policy = RetryPolicy.fixed(delay_s=0.0, max_attempts=3)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RetryExhaustedError) as exc_info:
                await retry_async(fn, policy=policy)
        assert exc_info.value.attempts == 3

    async def test_retry_exhausted_wraps_last_error(self):
        fn = always_fail(error_type=TransientError)
        policy = RetryPolicy.none()
        with pytest.raises(RetryExhaustedError) as exc_info:
            await retry_async(fn, policy=policy)
        assert isinstance(exc_info.value.last_error, TransientError)

    async def test_respects_is_retryable_false(self):
        fn = AsyncMock(side_effect=FatalError("fatal"))
        policy = RetryPolicy.exponential(
            max_attempts=5,
            is_retryable=lambda err, _: not isinstance(err, FatalError),
        )
        with pytest.raises(RetryExhaustedError):
            await retry_async(fn, policy=policy)
        # Only 1 call because is_retryable returned False immediately
        fn.assert_called_once()

    async def test_retries_only_retryable_errors(self):
        """Mix of transient and fatal: stop on first fatal."""
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TransientError("transient")
            raise FatalError("fatal")

        def is_retryable(err: BaseException, _attempt: int) -> bool:
            return isinstance(err, TransientError)

        policy = RetryPolicy.fixed(delay_s=0.0, max_attempts=5, is_retryable=is_retryable)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RetryExhaustedError) as exc_info:
                await retry_async(fn, policy=policy)
        # attempt 1 → TransientError (retried), attempt 2 → FatalError (not retried)
        assert call_count == 2
        assert isinstance(exc_info.value.last_error, FatalError)


# ---------------------------------------------------------------------------
# retry_async – on_retry callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetryAsyncOnRetry:
    async def test_on_retry_called_before_sleep(self):
        on_retry = MagicMock()
        fn = make_fn(fail_count=2, result="done")
        policy = RetryPolicy.fixed(delay_s=0.0, max_attempts=3, on_retry=on_retry)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await retry_async(fn, policy=policy)
        assert on_retry.call_count == 2
        # First call: attempt=1
        first_call_args = on_retry.call_args_list[0]
        assert isinstance(first_call_args[0][0], TransientError)
        assert first_call_args[0][1] == 1

    async def test_on_retry_exception_does_not_abort_retry(self):
        """on_retry raising should not prevent the retry loop from continuing."""

        def bad_on_retry(err, attempt, delay):
            raise RuntimeError("callback exploded")

        fn = make_fn(fail_count=1, result="ok")
        policy = RetryPolicy.fixed(delay_s=0.0, max_attempts=3, on_retry=bad_on_retry)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_async(fn, policy=policy)
        assert result == "ok"


# ---------------------------------------------------------------------------
# CircuitBreaker – state machine
# ---------------------------------------------------------------------------


class TestCircuitBreakerStateMachine:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        fn = make_fn(fail_count=2, result="ok")
        with pytest.raises(TransientError):
            await cb.execute(fn)
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_transitions_closed_to_open(self):
        cb = CircuitBreaker(failure_threshold=2)
        fn = always_fail()
        with pytest.raises(TransientError):
            await cb.execute(fn)
        assert cb.state is CircuitState.CLOSED
        with pytest.raises(TransientError):
            await cb.execute(fn)
        assert cb.state is CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_immediately_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        assert cb.state is CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await cb.execute(always_fail())

    @pytest.mark.asyncio
    async def test_transitions_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_s=0.05)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        assert cb.state is CircuitState.OPEN

        await asyncio.sleep(0.06)
        assert cb.state is CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_transitions_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_s=0.05)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        await asyncio.sleep(0.06)
        assert cb.state is CircuitState.HALF_OPEN

        result = await cb.execute(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_transitions_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout_s=0.05)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        await asyncio.sleep(0.06)
        assert cb.state is CircuitState.HALF_OPEN

        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        assert cb.state is CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_reset_returns_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        assert cb.state is CircuitState.OPEN
        cb.reset()
        assert cb.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# CircuitBreaker – is_failure predicate
# ---------------------------------------------------------------------------


class TestCircuitBreakerIsFailure:
    @pytest.mark.asyncio
    async def test_excluded_errors_do_not_count(self):
        """Errors excluded by is_failure should not trip the circuit."""
        cb = CircuitBreaker(
            failure_threshold=1,
            is_failure=lambda err: not isinstance(err, FatalError),
        )
        # FatalError is excluded – circuit should stay CLOSED
        with pytest.raises(FatalError):
            await cb.execute(always_fail(error_type=FatalError))
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_included_errors_count_toward_threshold(self):
        cb = CircuitBreaker(failure_threshold=1)
        with pytest.raises(TransientError):
            await cb.execute(always_fail(error_type=TransientError))
        assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# CircuitBreaker – on_state_change callback
# ---------------------------------------------------------------------------


class TestCircuitBreakerOnStateChange:
    @pytest.mark.asyncio
    async def test_callback_invoked_on_closed_to_open(self):
        on_change = MagicMock()
        cb = CircuitBreaker(failure_threshold=1, on_state_change=on_change)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        on_change.assert_called_once_with(CircuitState.CLOSED, CircuitState.OPEN)

    @pytest.mark.asyncio
    async def test_callback_on_reset(self):
        on_change = MagicMock()
        cb = CircuitBreaker(failure_threshold=1, on_state_change=on_change)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        cb.reset()
        assert on_change.call_args_list == [
            call(CircuitState.CLOSED, CircuitState.OPEN),
            call(CircuitState.OPEN, CircuitState.CLOSED),
        ]

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self):
        def bad_callback(f, t):
            raise RuntimeError("boom")

        cb = CircuitBreaker(failure_threshold=1, on_state_change=bad_callback)
        # Should not raise even though callback throws
        with pytest.raises(TransientError):
            await cb.execute(always_fail())
        assert cb.state is CircuitState.OPEN


# ---------------------------------------------------------------------------
# CircuitBreaker – stats
# ---------------------------------------------------------------------------


class TestCircuitBreakerStats:
    @pytest.mark.asyncio
    async def test_stats_reflect_calls(self):
        cb = CircuitBreaker(failure_threshold=5)
        success_fn = AsyncMock(return_value="ok")
        await cb.execute(success_fn)
        await cb.execute(success_fn)
        with pytest.raises(TransientError):
            await cb.execute(always_fail())

        stats = cb.stats
        assert stats.total_calls == 3
        assert stats.total_failures == 1
        assert stats.last_failure_at is not None
        assert stats.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# retry_with_circuit_breaker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRetryWithCircuitBreaker:
    async def test_succeeds_on_first_try(self):
        cb = CircuitBreaker(failure_threshold=5)
        fn = AsyncMock(return_value="result")
        result = await retry_with_circuit_breaker(fn, RetryPolicy.none(), cb)
        assert result == "result"

    async def test_propagates_circuit_open_error(self):
        cb = CircuitBreaker(failure_threshold=1)
        fn = always_fail()
        policy = RetryPolicy.none()
        # Trip the circuit
        with pytest.raises(TransientError):
            await retry_with_circuit_breaker(fn, policy, cb)
        assert cb.state is CircuitState.OPEN
        # Next call should raise CircuitOpenError
        with pytest.raises(CircuitOpenError):
            await retry_with_circuit_breaker(fn, policy, cb)

    async def test_retries_inside_circuit_boundary(self):
        cb = CircuitBreaker(failure_threshold=5)
        fn = make_fn(fail_count=2, result="done")
        policy = RetryPolicy.fixed(delay_s=0.0, max_attempts=3)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_with_circuit_breaker(fn, policy, cb)
        assert result == "done"
        # Circuit should still be CLOSED (fn eventually succeeded)
        assert cb.state is CircuitState.CLOSED
