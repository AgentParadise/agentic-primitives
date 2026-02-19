"""Retry and circuit-breaker utilities for agent workspace operations.

Transient failures are common when working with Docker containers, local
subprocesses, or remote execution environments.  This module provides
composable, framework-agnostic primitives for resilient retries:

* :func:`retry_async` – exponential/fixed back-off with a pluggable predicate.
* :class:`CircuitBreaker` – classic three-state circuit breaker.
* :func:`retry_with_circuit_breaker` – convenience composer.
* :class:`RetryPolicy` – factory for common configurations.

Examples
--------
Basic exponential back-off::

    from agentic_isolation.retry import retry_async, RetryPolicy

    result = await retry_async(
        lambda: workspace.execute("docker ps"),
        policy=RetryPolicy.exponential(max_attempts=4),
    )

Circuit breaker protecting a remote service::

    from agentic_isolation.retry import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=5, reset_timeout_s=30)
    result = await breaker.execute(lambda: workspace.execute("my-cmd"))

Composing both::

    from agentic_isolation.retry import retry_with_circuit_breaker, RetryPolicy

    breaker = CircuitBreaker(failure_threshold=3)
    policy  = RetryPolicy.exponential(max_attempts=3)
    result  = await retry_with_circuit_breaker(fn, policy, breaker)
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"All {attempts} retry attempt(s) exhausted. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is OPEN."""

    def __init__(self, reset_at: float) -> None:
        self.reset_at = reset_at
        import datetime

        reset_iso = datetime.datetime.fromtimestamp(reset_at).isoformat()
        super().__init__(
            f"Circuit breaker is OPEN. Requests rejected until {reset_iso}."
        )


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Immutable configuration for retry behaviour.

    Use the factory class-methods rather than instantiating directly:

    * :meth:`exponential` – exponential back-off (recommended for I/O).
    * :meth:`fixed` – constant delay between retries.
    * :meth:`none` – no retries; errors propagate immediately.
    """

    #: Maximum number of attempts *including* the first (must be ≥ 1).
    max_attempts: int = 3
    #: Base delay in seconds between retries.
    base_delay_s: float = 0.1
    #: Upper bound on computed delay.
    max_delay_s: float = 10.0
    #: Multiplier applied to base_delay_s on each successive attempt.
    backoff_factor: float = 2.0
    #: When True, add uniform random jitter ∈ [0, computed_delay] seconds.
    jitter: bool = True
    #: If provided, only errors for which this returns True are retried.
    #: Receives ``(error, attempt_number)``; defaults to retrying everything.
    is_retryable: Callable[[BaseException, int], bool] | None = None
    #: Optional hook called *before* sleeping; receives ``(error, attempt, delay_s)``.
    on_retry: Callable[[BaseException, int, float], None] | None = None

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def exponential(cls, **kwargs: Any) -> "RetryPolicy":
        """Exponential back-off with jitter (recommended for I/O operations)."""
        defaults: dict[str, Any] = {
            "max_attempts": 3,
            "base_delay_s": 0.1,
            "max_delay_s": 10.0,
            "backoff_factor": 2.0,
            "jitter": True,
        }
        defaults.update(kwargs)
        return cls(**defaults)

    @classmethod
    def fixed(cls, delay_s: float = 0.5, **kwargs: Any) -> "RetryPolicy":
        """Fixed delay between retries (no exponential growth)."""
        defaults: dict[str, Any] = {
            "max_attempts": 3,
            "base_delay_s": delay_s,
            "max_delay_s": delay_s,
            "backoff_factor": 1.0,
            "jitter": False,
        }
        defaults.update(kwargs)
        return cls(**defaults)

    @classmethod
    def none(cls) -> "RetryPolicy":
        """No retries – errors propagate after the very first attempt."""
        return cls(max_attempts=1, base_delay_s=0.0, max_delay_s=0.0, jitter=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def compute_delay(self, attempt: int) -> float:
        """Return the delay in seconds before attempt *attempt* (1-indexed)."""
        exp = min(self.base_delay_s * math.pow(self.backoff_factor, attempt - 1), self.max_delay_s)
        if not self.jitter:
            return exp
        return random.uniform(0.0, exp)  # noqa: S311 – not security-sensitive


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
) -> T:
    """Execute *fn* with automatic async retries according to *policy*.

    Parameters
    ----------
    fn:
        Zero-argument coroutine factory to execute (may be called multiple times).
    policy:
        Retry configuration.  Defaults to :meth:`RetryPolicy.exponential`.

    Returns
    -------
    T
        The result of the first successful call.

    Raises
    ------
    RetryExhaustedError
        When all attempts are exhausted.

    Examples
    --------
    >>> result = await retry_async(
    ...     lambda: workspace.execute("docker ps"),
    ...     policy=RetryPolicy.exponential(max_attempts=5),
    ... )
    """
    if policy is None:
        policy = RetryPolicy.exponential()

    is_retryable = policy.is_retryable or (lambda _err, _attempt: True)
    last_exc: BaseException = RuntimeError("retry_async called with max_attempts=0")

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            is_last = attempt == policy.max_attempts
            if is_last or not is_retryable(exc, attempt):
                break

            delay = policy.compute_delay(attempt)
            if policy.on_retry is not None:
                try:
                    policy.on_retry(exc, attempt, delay)
                except Exception:  # noqa: BLE001
                    pass
            logger.debug(
                "retry_async: attempt %d/%d failed (%s). Retrying in %.3fs.",
                attempt,
                policy.max_attempts,
                type(exc).__name__,
                delay,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    raise RetryExhaustedError(policy.max_attempts, last_exc)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    """Possible states of a :class:`CircuitBreaker`."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerStats:
    """Point-in-time snapshot of circuit breaker metrics."""

    state: CircuitState
    failures: int
    successes: int
    last_failure_at: float | None
    total_calls: int
    total_failures: int


class CircuitBreaker:
    """Three-state circuit breaker (CLOSED → OPEN → HALF_OPEN → CLOSED).

    A :class:`CircuitBreaker` wraps an async callable and prevents cascading
    failures when a downstream dependency is unavailable.

    States
    ------
    CLOSED
        Normal operation.  Failures are counted; once *failure_threshold* is
        reached the circuit trips to OPEN.
    OPEN
        All calls are rejected immediately with :exc:`CircuitOpenError`.
        After *reset_timeout_s* seconds the circuit transitions to HALF_OPEN.
    HALF_OPEN
        A single probe call is allowed through.  On success the circuit closes;
        on failure it re-opens.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive failures that trip the circuit.  Default: 5.
    reset_timeout_s:
        Seconds the circuit stays OPEN before moving to HALF_OPEN.  Default: 30.
    success_threshold:
        Successful probes in HALF_OPEN required to close.  Default: 1.
    is_failure:
        Predicate deciding whether an exception counts toward the failure
        counter.  By default every exception counts.
    on_state_change:
        Optional callback ``(from_state, to_state)`` invoked on transitions.

    Examples
    --------
    >>> breaker = CircuitBreaker(failure_threshold=3, reset_timeout_s=10)
    >>> try:
    ...     result = await breaker.execute(lambda: workspace.execute("cmd"))
    ... except CircuitOpenError:
    ...     # Use a fallback or propagate the error
    ...     ...
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        success_threshold: int = 1,
        is_failure: Callable[[BaseException], bool] | None = None,
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s
        self._success_threshold = success_threshold
        self._is_failure = is_failure or (lambda _: True)
        self._on_state_change = on_state_change

        self._state: CircuitState = CircuitState.CLOSED
        self._failures: int = 0
        self._successes: int = 0
        self._opened_at: float | None = None
        self._last_failure_at: float | None = None
        self._total_calls: int = 0
        self._total_failures: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit state (rechecks reset timeout on every access)."""
        self._check_reset()
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Snapshot of current circuit breaker metrics."""
        self._check_reset()
        return CircuitBreakerStats(
            state=self._state,
            failures=self._failures,
            successes=self._successes,
            last_failure_at=self._last_failure_at,
            total_calls=self._total_calls,
            total_failures=self._total_failures,
        )

    async def execute(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run *fn* through the circuit breaker.

        Raises
        ------
        CircuitOpenError
            When the circuit is OPEN and the call is rejected immediately.
        """
        self._check_reset()
        self._total_calls += 1

        if self._state is CircuitState.OPEN:
            assert self._opened_at is not None  # noqa: S101
            raise CircuitOpenError(reset_at=self._opened_at + self._reset_timeout_s)

        try:
            result = await fn()
            self._on_success()
            return result
        except Exception as exc:  # noqa: BLE001
            self._on_failure(exc)
            raise

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED (useful in tests)."""
        prev = self._state
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at = None
        self._last_failure_at = None
        if prev is not CircuitState.CLOSED:
            self._notify(prev, CircuitState.CLOSED)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_reset(self) -> None:
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._reset_timeout_s:
                self._transition(CircuitState.OPEN, CircuitState.HALF_OPEN)
                self._successes = 0

    def _on_success(self) -> None:
        self._successes += 1
        if self._state is CircuitState.HALF_OPEN and self._successes >= self._success_threshold:
            self._transition(CircuitState.HALF_OPEN, CircuitState.CLOSED)
            self._failures = 0
            self._successes = 0
            self._opened_at = None
        elif self._state is CircuitState.CLOSED:
            # Reset failure streak on success
            self._failures = 0

    def _on_failure(self, exc: BaseException) -> None:
        if not self._is_failure(exc):
            return

        self._total_failures += 1
        self._failures += 1
        self._last_failure_at = time.monotonic()

        if self._state is CircuitState.HALF_OPEN:
            self._transition(CircuitState.HALF_OPEN, CircuitState.OPEN)
            self._opened_at = time.monotonic()
            self._failures = 1
        elif self._state is CircuitState.CLOSED and self._failures >= self._failure_threshold:
            self._transition(CircuitState.CLOSED, CircuitState.OPEN)
            self._opened_at = time.monotonic()

    def _transition(self, from_state: CircuitState, to_state: CircuitState) -> None:
        self._state = to_state
        logger.info("CircuitBreaker: %s → %s", from_state.value, to_state.value)
        self._notify(from_state, to_state)

    def _notify(self, from_state: CircuitState, to_state: CircuitState) -> None:
        if self._on_state_change is not None:
            try:
                self._on_state_change(from_state, to_state)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Convenience composer
# ---------------------------------------------------------------------------


async def retry_with_circuit_breaker(
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    circuit_breaker: CircuitBreaker,
) -> T:
    """Execute *fn* protected by both retry and circuit breaker.

    The circuit breaker wraps the entire retry sequence.  A persistent outage
    trips the circuit after *failure_threshold* full retry sequences rather
    than individual attempts.

    Parameters
    ----------
    fn:
        Zero-argument coroutine factory.
    policy:
        Retry configuration.
    circuit_breaker:
        Pre-configured :class:`CircuitBreaker` instance (shared across calls).

    Returns
    -------
    T
        Result of the first successful call.

    Raises
    ------
    CircuitOpenError
        When the circuit is OPEN.
    RetryExhaustedError
        When all retry attempts within a single circuit-breaker call fail.

    Examples
    --------
    >>> breaker = CircuitBreaker(failure_threshold=3)
    >>> policy  = RetryPolicy.exponential(max_attempts=3)
    >>> result  = await retry_with_circuit_breaker(
    ...     lambda: workspace.execute("docker ps"),
    ...     policy,
    ...     breaker,
    ... )
    """
    return await circuit_breaker.execute(lambda: retry_async(fn, policy=policy))
