"""Backend adapters for event emission.

This module provides pluggable backends for writing hook events:
- JSONLBackend: Local file storage (JSONL format)
- HTTPBackend: Remote HTTP endpoint (requires httpx)
- NullBackend: No-op backend for testing

Example:
    from agentic_hooks.backends import JSONLBackend, HTTPBackend

    # Local development
    backend = JSONLBackend(output_path=".agentic/analytics/events.jsonl")
    await backend.write([event])

    # Production
    backend = HTTPBackend(base_url="http://localhost:8080")
    await backend.write([event])

    # Production with retry
    backend = HTTPBackend(
        base_url="http://localhost:8080",
        max_retries=3,
        retry_backoff_factor=0.5,
    )
    await backend.write([event])
"""

from __future__ import annotations

import asyncio
import json
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentic_hooks.events import HookEvent


class Backend(ABC):
    """Abstract base class for event backends.

    All backends must implement the async write() method
    for sending events to the storage layer.
    """

    @abstractmethod
    async def write(self, events: list[HookEvent]) -> None:
        """Write events to the backend.

        Args:
            events: List of events to write.

        Raises:
            Exception: If write fails (implementation-specific).
        """
        ...

    async def close(self) -> None:  # noqa: B027
        """Close the backend and release resources.

        Override this method if the backend needs cleanup.
        Default implementation is a no-op.
        """


@dataclass
class NullBackend(Backend):
    """No-op backend for testing.

    Events are accepted but not stored anywhere.
    Useful for testing and benchmarking.
    """

    events_received: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, events: list[HookEvent]) -> None:
        """Accept events without storing them.

        Args:
            events: List of events (ignored).
        """
        # Store for inspection in tests
        for event in events:
            self.events_received.append(event.to_dict())


@dataclass
class JSONLBackend(Backend):
    """Local file backend using JSONL format.

    Appends events to a JSON Lines file, one event per line.
    Creates parent directories if they don't exist.

    This backend is synchronous for simplicity but wrapped
    in async interface for consistency.

    Attributes:
        output_path: Path to the JSONL file.

    Example:
        backend = JSONLBackend(output_path=".agentic/analytics/events.jsonl")
        await backend.write([event])
    """

    output_path: Path | str = ".agentic/analytics/events.jsonl"

    def __post_init__(self) -> None:
        """Convert string path to Path object."""
        if isinstance(self.output_path, str):
            self.output_path = Path(self.output_path)

    async def write(self, events: list[HookEvent]) -> None:
        """Append events to JSONL file.

        Args:
            events: List of events to write.
        """
        if not events:
            return

        # Ensure we have a Path object
        path = Path(self.output_path) if isinstance(self.output_path, str) else self.output_path

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write events as JSONL
        with open(path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event.to_dict()) + "\n")


@dataclass
class HTTPBackend(Backend):
    """HTTP backend for remote event storage with retry logic.

    Sends events to a remote HTTP endpoint in batches.
    Requires the httpx optional dependency.

    Features:
        - Connection pooling (via httpx)
        - Configurable timeouts
        - Exponential backoff retry
        - Jitter to prevent thundering herd

    Attributes:
        base_url: Base URL of the hook backend service.
        timeout: Request timeout in seconds.
        headers: Additional HTTP headers.
        max_retries: Maximum number of retry attempts (0 = no retry).
        retry_backoff_factor: Base delay multiplier for exponential backoff.
        retry_max_delay: Maximum delay between retries in seconds.
        retry_jitter: Add random jitter to retry delays (0.0-1.0).

    Example:
        # Simple usage
        backend = HTTPBackend(base_url="http://localhost:8080")
        await backend.write([event])

        # With retry configuration
        backend = HTTPBackend(
            base_url="http://localhost:8080",
            timeout=10.0,
            max_retries=3,
            retry_backoff_factor=0.5,
        )
        await backend.write([event])
    """

    base_url: str
    timeout: float = 5.0
    headers: dict[str, str] = field(default_factory=dict)
    max_retries: int = 3
    retry_backoff_factor: float = 0.5
    retry_max_delay: float = 30.0
    retry_jitter: float = 0.1

    _client: Any = field(default=None, repr=False)

    async def _get_client(self) -> Any:
        """Get or create httpx async client with connection pooling."""
        if self._client is None:
            try:
                import httpx
            except ImportError as e:
                raise ImportError(
                    "HTTPBackend requires httpx. Install with: pip install agentic-hooks[http]"
                ) from e

            # Configure connection pool limits for high concurrency
            limits = httpx.Limits(
                max_keepalive_connections=100,
                max_connections=200,
                keepalive_expiry=30.0,
            )

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Content-Type": "application/json", **self.headers},
                limits=limits,
            )
        return self._client

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt with exponential backoff and jitter.

        Args:
            attempt: The retry attempt number (0-indexed).

        Returns:
            Delay in seconds before next retry.
        """
        # Exponential backoff: delay = factor * 2^attempt
        delay = self.retry_backoff_factor * (2**attempt)

        # Cap at max delay
        delay = min(delay, self.retry_max_delay)

        # Add jitter (±jitter% of delay)
        if self.retry_jitter > 0:
            jitter_range = delay * self.retry_jitter
            delay += random.uniform(-jitter_range, jitter_range)

        return float(max(0, delay))

    def _is_retryable_error(self, exception: Exception) -> bool:
        """Check if an exception is retryable.

        Args:
            exception: The exception to check.

        Returns:
            True if the error is retryable (transient).
        """
        try:
            import httpx

            # Retry on connection errors, timeouts, and 5xx responses
            if isinstance(exception, httpx.ConnectError | httpx.TimeoutException):
                return True

            if isinstance(exception, httpx.HTTPStatusError):
                # Retry on 5xx server errors and 429 rate limiting
                return exception.response.status_code >= 500 or (
                    exception.response.status_code == 429
                )

        except ImportError:
            pass

        return False

    async def write(self, events: list[HookEvent]) -> None:
        """Send events to HTTP endpoint with retry logic.

        Args:
            events: List of events to send.

        Raises:
            Exception: If all retry attempts fail.
        """
        if not events:
            return

        client = await self._get_client()

        payload = [event.to_dict() for event in events]

        # Determine endpoint based on batch size
        endpoint: str
        data: dict[str, Any] | list[dict[str, Any]]
        if len(payload) == 1:
            endpoint = "/events"
            data = payload[0]
        else:
            endpoint = "/events/batch"
            data = payload

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                response = await client.post(endpoint, json=data)
                response.raise_for_status()
                return  # Success!

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if attempt < self.max_retries and self._is_retryable_error(e):
                    delay = self._calculate_retry_delay(attempt)
                    await asyncio.sleep(delay)
                    continue

                # No more retries or non-retryable error
                raise

        # Should not reach here, but just in case
        if last_exception is not None:
            raise last_exception

    async def close(self) -> None:
        """Close the HTTP client and release connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
