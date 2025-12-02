"""Integration tests for HTTPBackend with retry logic."""

import pytest

from agentic_hooks.backends import HTTPBackend
from agentic_hooks.events import EventType, HookEvent

# Check if httpx is available
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


def make_event(session_id: str = "session-123") -> HookEvent:
    """Create a test event."""
    return HookEvent(
        event_type=EventType.SESSION_STARTED,
        session_id=session_id,
        data={"key": "value"},
    )


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestHTTPBackendConfig:
    """Tests for HTTPBackend configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        assert backend.base_url == "http://localhost:8080"
        assert backend.timeout == 5.0
        assert backend.max_retries == 3
        assert backend.retry_backoff_factor == 0.5
        assert backend.retry_max_delay == 30.0
        assert backend.retry_jitter == 0.1

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        backend = HTTPBackend(
            base_url="http://localhost:9090",
            timeout=10.0,
            max_retries=5,
            retry_backoff_factor=1.0,
            retry_max_delay=60.0,
            retry_jitter=0.2,
            headers={"X-Custom": "header"},
        )

        assert backend.base_url == "http://localhost:9090"
        assert backend.timeout == 10.0
        assert backend.max_retries == 5
        assert backend.retry_backoff_factor == 1.0
        assert backend.retry_max_delay == 60.0
        assert backend.retry_jitter == 0.2
        assert backend.headers == {"X-Custom": "header"}


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestHTTPBackendRetryLogic:
    """Tests for HTTPBackend retry logic."""

    def test_calculate_retry_delay_exponential(self) -> None:
        """Test exponential backoff calculation."""
        backend = HTTPBackend(
            base_url="http://localhost:8080",
            retry_backoff_factor=1.0,
            retry_jitter=0.0,  # No jitter for predictable test
        )

        # delay = factor * 2^attempt
        assert backend._calculate_retry_delay(0) == 1.0  # 1 * 2^0 = 1
        assert backend._calculate_retry_delay(1) == 2.0  # 1 * 2^1 = 2
        assert backend._calculate_retry_delay(2) == 4.0  # 1 * 2^2 = 4
        assert backend._calculate_retry_delay(3) == 8.0  # 1 * 2^3 = 8

    def test_calculate_retry_delay_with_backoff_factor(self) -> None:
        """Test backoff factor affects delay."""
        backend = HTTPBackend(
            base_url="http://localhost:8080",
            retry_backoff_factor=0.5,
            retry_jitter=0.0,
        )

        # delay = 0.5 * 2^attempt
        assert backend._calculate_retry_delay(0) == 0.5  # 0.5 * 2^0 = 0.5
        assert backend._calculate_retry_delay(1) == 1.0  # 0.5 * 2^1 = 1.0
        assert backend._calculate_retry_delay(2) == 2.0  # 0.5 * 2^2 = 2.0

    def test_calculate_retry_delay_capped(self) -> None:
        """Test delay is capped at max_delay."""
        backend = HTTPBackend(
            base_url="http://localhost:8080",
            retry_backoff_factor=1.0,
            retry_max_delay=5.0,
            retry_jitter=0.0,
        )

        # Without cap: 1 * 2^10 = 1024
        # With cap: 5.0
        assert backend._calculate_retry_delay(10) == 5.0

    def test_calculate_retry_delay_with_jitter(self) -> None:
        """Test jitter adds randomness to delay."""
        backend = HTTPBackend(
            base_url="http://localhost:8080",
            retry_backoff_factor=1.0,
            retry_jitter=0.5,  # ±50%
        )

        # Run multiple times to check jitter range
        delays = [backend._calculate_retry_delay(0) for _ in range(100)]

        # Base delay is 1.0, with ±50% jitter should be in range [0.5, 1.5]
        assert all(0.5 <= d <= 1.5 for d in delays)

        # Check there's actual variation (not all the same)
        assert len(set(delays)) > 1

    def test_is_retryable_error_connect_error(self) -> None:
        """Test connect errors are retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        error = httpx.ConnectError("Connection refused")
        assert backend._is_retryable_error(error) is True

    def test_is_retryable_error_timeout(self) -> None:
        """Test timeout errors are retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        error = httpx.TimeoutException("Request timed out")
        assert backend._is_retryable_error(error) is True

    def test_is_retryable_error_5xx(self) -> None:
        """Test 5xx errors are retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        request = httpx.Request("POST", "http://localhost:8080/events")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("Server error", request=request, response=response)

        assert backend._is_retryable_error(error) is True

    def test_is_retryable_error_429(self) -> None:
        """Test 429 rate limit errors are retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        request = httpx.Request("POST", "http://localhost:8080/events")
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError("Rate limited", request=request, response=response)

        assert backend._is_retryable_error(error) is True

    def test_is_retryable_error_4xx_not_retryable(self) -> None:
        """Test 4xx errors (except 429) are not retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        request = httpx.Request("POST", "http://localhost:8080/events")
        response = httpx.Response(400, request=request)
        error = httpx.HTTPStatusError("Bad request", request=request, response=response)

        assert backend._is_retryable_error(error) is False

    def test_is_retryable_error_other(self) -> None:
        """Test other errors are not retryable."""
        backend = HTTPBackend(base_url="http://localhost:8080")

        error = ValueError("Some other error")
        assert backend._is_retryable_error(error) is False


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestHTTPBackendWithMockTransport:
    """Tests for HTTPBackend with mock transport."""

    @pytest.mark.asyncio
    async def test_write_single_event(self) -> None:
        """Test writing a single event uses /events endpoint."""
        requests_received: list[httpx.Request] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            requests_received.append(request)
            return httpx.Response(202)

        backend = HTTPBackend(base_url="http://test:8080")

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        await backend.write([make_event()])

        assert len(requests_received) == 1
        assert requests_received[0].url.path == "/events"

        await backend.close()

    @pytest.mark.asyncio
    async def test_write_batch_events(self) -> None:
        """Test writing multiple events uses /events/batch endpoint."""
        requests_received: list[httpx.Request] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            requests_received.append(request)
            return httpx.Response(202)

        backend = HTTPBackend(base_url="http://test:8080")

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        events = [make_event(f"session-{i}") for i in range(5)]
        await backend.write(events)

        assert len(requests_received) == 1
        assert requests_received[0].url.path == "/events/batch"

        await backend.close()

    @pytest.mark.asyncio
    async def test_write_empty_list(self) -> None:
        """Test writing empty list doesn't make request."""
        requests_received: list[httpx.Request] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            requests_received.append(request)
            return httpx.Response(202)

        backend = HTTPBackend(base_url="http://test:8080")

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        await backend.write([])

        assert len(requests_received) == 0

        await backend.close()

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self) -> None:
        """Test retry on 5xx server error."""
        attempt_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return httpx.Response(500)
            return httpx.Response(202)

        backend = HTTPBackend(
            base_url="http://test:8080",
            max_retries=3,
            retry_backoff_factor=0.01,  # Fast for testing
        )

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        await backend.write([make_event()])

        # Should succeed on third attempt
        assert attempt_count == 3

        await backend.close()

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self) -> None:
        """Test error is raised when all retries exhausted."""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        backend = HTTPBackend(
            base_url="http://test:8080",
            max_retries=2,
            retry_backoff_factor=0.01,
        )

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        with pytest.raises(httpx.HTTPStatusError):
            await backend.write([make_event()])

        await backend.close()

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self) -> None:
        """Test no retry on 4xx client errors."""
        attempt_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            return httpx.Response(400)

        backend = HTTPBackend(
            base_url="http://test:8080",
            max_retries=3,
            retry_backoff_factor=0.01,
        )

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        with pytest.raises(httpx.HTTPStatusError):
            await backend.write([make_event()])

        # Should only attempt once (no retry on 4xx)
        assert attempt_count == 1

        await backend.close()

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self) -> None:
        """Test retry on 429 rate limit."""
        attempt_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                return httpx.Response(429)
            return httpx.Response(202)

        backend = HTTPBackend(
            base_url="http://test:8080",
            max_retries=3,
            retry_backoff_factor=0.01,
        )

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        await backend.write([make_event()])

        assert attempt_count == 2

        await backend.close()

    @pytest.mark.asyncio
    async def test_no_retry_when_disabled(self) -> None:
        """Test no retry when max_retries is 0."""
        attempt_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt_count
            attempt_count += 1
            return httpx.Response(500)

        backend = HTTPBackend(
            base_url="http://test:8080",
            max_retries=0,  # Disable retry
        )

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        with pytest.raises(httpx.HTTPStatusError):
            await backend.write([make_event()])

        assert attempt_count == 1

        await backend.close()


@pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")
class TestHTTPBackendConnectionPool:
    """Tests for HTTPBackend connection pooling."""

    @pytest.mark.asyncio
    async def test_client_reuses_connection(self) -> None:
        """Test client is reused across writes."""
        request_count = 0

        def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(202)

        backend = HTTPBackend(base_url="http://test:8080")

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        # Make multiple writes
        for _ in range(5):
            await backend.write([make_event()])

        assert request_count == 5

        # Client should still be the same
        assert backend._client is not None

        await backend.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self) -> None:
        """Test close clears the client."""

        def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(202)

        backend = HTTPBackend(base_url="http://test:8080")

        # Inject mock client
        backend._client = httpx.AsyncClient(
            transport=httpx.MockTransport(mock_handler),
            base_url="http://test:8080",
        )

        await backend.write([make_event()])
        assert backend._client is not None

        await backend.close()
        assert backend._client is None
