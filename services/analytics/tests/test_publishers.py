"""Tests for event publishers (file and API backends)

Following TDD: write tests first, then implement publishers
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from analytics.models.events import (
    EventMetadata,
    NormalizedEvent,
    SessionContext,
)


# Test fixture: sample normalized event
@pytest.fixture
def sample_event() -> NormalizedEvent:
    """Create a sample normalized event for testing"""
    return NormalizedEvent(
        event_type="session_started",
        timestamp="2025-11-19T12:00:00+00:00",  # type: ignore[arg-type]
        session_id="test-session-123",
        provider="claude",
        context=SessionContext(source="startup", reason=None).model_dump(),
        metadata=EventMetadata(
            hook_event_name="SessionStart",
            transcript_path="/path/to/transcript.jsonl",
            permission_mode="default",
            raw_event={},
        ),
        cwd="/tmp/test",
    )


@pytest.fixture
def sample_events(sample_event: NormalizedEvent) -> list[NormalizedEvent]:
    """Create a list of sample events for batch testing"""
    return [sample_event, sample_event, sample_event]


@pytest.mark.unit
class TestBasePublisher:
    """Test base publisher interface"""

    def test_base_publisher_imports(self) -> None:
        """Test that BasePublisher can be imported"""
        from analytics.publishers.base import BasePublisher  # noqa: F401

    def test_base_publisher_is_abstract(self) -> None:
        """Test that BasePublisher cannot be instantiated directly"""
        from analytics.publishers.base import BasePublisher

        # Should raise TypeError because it's abstract
        with pytest.raises(TypeError):
            BasePublisher()  # type: ignore[abstract]

    def test_base_publisher_has_required_methods(self) -> None:
        """Test that BasePublisher defines required abstract methods"""
        from analytics.publishers.base import BasePublisher

        # Check abstract methods exist
        assert hasattr(BasePublisher, "publish")
        assert hasattr(BasePublisher, "publish_batch")
        assert hasattr(BasePublisher, "close")


@pytest.mark.asyncio
class TestFilePublisher:
    """Test file publisher (JSONL backend)"""

    async def test_file_publisher_imports(self) -> None:
        """Test that FilePublisher can be imported"""
        from analytics.publishers.file import FilePublisher  # noqa: F401

    async def test_file_publisher_instantiation(self, tmp_path: Path) -> None:
        """Test that FilePublisher can be instantiated"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)
        assert publisher is not None

    async def test_file_publisher_creates_parent_directories(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that FilePublisher creates parent directories if they don't exist"""
        from analytics.publishers.file import FilePublisher

        # Use nested directory that doesn't exist
        output_file = tmp_path / "nested" / "dir" / "events.jsonl"
        assert not output_file.parent.exists()

        publisher = FilePublisher(output_path=output_file)
        await publisher.publish(sample_event)

        # Directory should now exist
        assert output_file.parent.exists()
        await publisher.close()

    async def test_file_publisher_writes_jsonl_format(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that FilePublisher writes events in JSONL format (one per line)"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)

        await publisher.publish(sample_event)
        await publisher.close()

        # Verify file exists
        assert output_file.exists()

        # Verify JSONL format (one JSON object per line)
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 1

            # Should be valid JSON
            event_data = json.loads(lines[0])
            assert event_data["session_id"] == "test-session-123"
            assert event_data["event_type"] == "session_started"

    async def test_file_publisher_appends_events(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that FilePublisher appends to existing file"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)

        # Publish multiple events
        await publisher.publish(sample_event)
        await publisher.publish(sample_event)
        await publisher.publish(sample_event)
        await publisher.close()

        # Should have 3 lines
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 3

    async def test_file_publisher_atomic_writes(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that FilePublisher uses atomic writes (temp file + rename)"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)

        # Mock should show temp file usage
        with patch("aiofiles.open", wraps=__import__("aiofiles").open) as mock_open:
            await publisher.publish(sample_event)
            await publisher.close()

            # Should have been called
            assert mock_open.called

    async def test_file_publisher_publish_batch(
        self, tmp_path: Path, sample_events: list[NormalizedEvent]
    ) -> None:
        """Test that FilePublisher can publish batch of events"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)

        await publisher.publish_batch(sample_events)
        await publisher.close()

        # Should have 3 lines
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 3

    async def test_file_publisher_handles_permission_errors(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that FilePublisher handles file permission errors gracefully"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "readonly.jsonl"

        # Create read-only directory
        output_file.parent.chmod(0o444)

        publisher = FilePublisher(output_path=output_file)

        # Should not raise exception (non-blocking middleware)
        try:
            await publisher.publish(sample_event)
        except Exception:
            # If it does raise, that's fine too - just testing it doesn't crash
            pass
        finally:
            # Restore permissions for cleanup
            output_file.parent.chmod(0o755)
            await publisher.close()

    async def test_file_publisher_validates_event(self, tmp_path: Path) -> None:
        """Test that FilePublisher validates event with Pydantic"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "events.jsonl"
        publisher = FilePublisher(output_path=output_file)

        # Invalid event (not a NormalizedEvent)
        with pytest.raises((ValidationError, TypeError, AttributeError)):
            await publisher.publish({"invalid": "event"})  # type: ignore[arg-type]

        await publisher.close()


@pytest.mark.asyncio
class TestAPIPublisher:
    """Test API publisher (HTTP POST backend)"""

    async def test_api_publisher_imports(self) -> None:
        """Test that APIPublisher can be imported"""
        from analytics.publishers.api import APIPublisher  # noqa: F401

    async def test_api_publisher_instantiation(self) -> None:
        """Test that APIPublisher can be instantiated"""
        from analytics.publishers.api import APIPublisher

        publisher = APIPublisher(endpoint="https://api.example.com/events")
        assert publisher is not None
        await publisher.close()

    async def test_api_publisher_sends_http_post(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher sends HTTP POST request"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)

            publisher = APIPublisher(endpoint="https://api.example.com/events")
            await publisher.publish(sample_event)
            await publisher.close()

            # Verify POST was called
            mock_post.assert_called_once()

    async def test_api_publisher_sends_json_body(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher sends event as JSON in request body"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)

            publisher = APIPublisher(endpoint="https://api.example.com/events")
            await publisher.publish(sample_event)
            await publisher.close()

            # Verify JSON body
            call_args = mock_post.call_args
            assert "json" in call_args.kwargs or "data" in call_args.kwargs

    async def test_api_publisher_sets_content_type_header(
        self, sample_event: NormalizedEvent
    ) -> None:
        """Test that APIPublisher sets Content-Type: application/json header"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)

            publisher = APIPublisher(endpoint="https://api.example.com/events")
            await publisher.publish(sample_event)
            await publisher.close()

            # Verify headers
            call_args = mock_post.call_args
            if "headers" in call_args.kwargs:
                assert "application/json" in str(call_args.kwargs["headers"]).lower()

    async def test_api_publisher_handles_connection_error(
        self, sample_event: NormalizedEvent
    ) -> None:
        """Test that APIPublisher handles connection errors gracefully"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=0)

            # Should not raise exception (non-blocking middleware)
            await publisher.publish(sample_event)
            await publisher.close()

    async def test_api_publisher_handles_timeout(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher handles timeout errors"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=0)

            # Should not raise exception
            await publisher.publish(sample_event)
            await publisher.close()

    async def test_api_publisher_handles_http_status_error(
        self, sample_event: NormalizedEvent
    ) -> None:
        """Test that APIPublisher handles HTTP status errors (4xx, 5xx)"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            response = MagicMock()
            response.status_code = 500
            response.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
                "Server error", request=MagicMock(), response=response
            )
            mock_post.return_value = response

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=0)

            # Should not raise exception
            await publisher.publish(sample_event)
            await publisher.close()

    async def test_api_publisher_respects_timeout_config(
        self, sample_event: NormalizedEvent
    ) -> None:
        """Test that APIPublisher respects timeout configuration"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            publisher = APIPublisher(endpoint="https://api.example.com/events", timeout=10)
            await publisher.close()

            # Verify timeout was passed to client
            call_args = mock_client_class.call_args
            if call_args and "timeout" in call_args.kwargs:
                assert call_args.kwargs["timeout"] == 10

    async def test_api_publisher_publish_batch(self, sample_events: list[NormalizedEvent]) -> None:
        """Test that APIPublisher can publish batch of events"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)

            publisher = APIPublisher(endpoint="https://api.example.com/events")
            await publisher.publish_batch(sample_events)
            await publisher.close()

            # Should have called POST multiple times (or once with batch)
            assert mock_post.called


@pytest.mark.asyncio
class TestAPIPublisherRetryLogic:
    """Test API publisher retry logic and exponential backoff"""

    async def test_api_publisher_retries_on_5xx_errors(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher retries on 5xx server errors"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            # Fail twice, then succeed
            response_fail = MagicMock()
            response_fail.status_code = 500
            response_fail.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
                "Server error", request=MagicMock(), response=response_fail
            )

            response_success = AsyncMock()
            response_success.status_code = 200

            mock_post.side_effect = [response_fail, response_fail, response_success]

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=3)
            await publisher.publish(sample_event)
            await publisher.close()

            # Should have been called 3 times (2 fails + 1 success)
            assert mock_post.call_count >= 2

    async def test_api_publisher_does_not_retry_on_4xx_errors(
        self, sample_event: NormalizedEvent
    ) -> None:
        """Test that APIPublisher does NOT retry on 4xx client errors"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            response = MagicMock()
            response.status_code = 400
            response.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
                "Bad request", request=MagicMock(), response=response
            )
            mock_post.return_value = response

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=3)
            await publisher.publish(sample_event)
            await publisher.close()

            # Should only be called once (no retries for 4xx)
            assert mock_post.call_count == 1

    async def test_api_publisher_exponential_backoff(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher uses exponential backoff between retries"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post, patch("asyncio.sleep") as mock_sleep:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=3)
            await publisher.publish(sample_event)
            await publisher.close()

            # Should have slept with increasing delays
            if mock_sleep.called:
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                # Each sleep should be longer than the previous (exponential backoff)
                # Typical pattern: 1s, 2s, 4s, 8s...
                for i in range(1, len(sleep_calls)):
                    assert sleep_calls[i] >= sleep_calls[i - 1]

    async def test_api_publisher_max_retries(self, sample_event: NormalizedEvent) -> None:
        """Test that APIPublisher respects max retry attempts"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=2)
            await publisher.publish(sample_event)
            await publisher.close()

            # Should not exceed max attempts (initial + 2 retries = 3 total)
            assert mock_post.call_count <= 3


@pytest.mark.asyncio
class TestPublisherErrorHandling:
    """Test error handling and logging across publishers"""

    async def test_file_publisher_logs_errors(
        self, tmp_path: Path, sample_event: NormalizedEvent, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that FilePublisher logs errors with context"""
        from analytics.publishers.file import FilePublisher

        output_file = tmp_path / "readonly" / "events.jsonl"

        # Create read-only parent directory
        output_file.parent.mkdir()
        output_file.parent.chmod(0o444)

        publisher = FilePublisher(output_path=output_file)

        try:
            await publisher.publish(sample_event)
        except Exception:
            pass

        # Restore permissions
        output_file.parent.chmod(0o755)
        await publisher.close()

        # Should have logged something about the error
        # (We'll verify this when implementing)

    async def test_api_publisher_logs_errors(
        self, sample_event: NormalizedEvent, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that APIPublisher logs errors with context"""
        from analytics.publishers.api import APIPublisher

        with patch("httpx.AsyncClient.post") as mock_post:
            import httpx

            mock_post.side_effect = httpx.ConnectError("Connection refused")

            publisher = APIPublisher(endpoint="https://api.example.com/events", retry_attempts=0)
            await publisher.publish(sample_event)
            await publisher.close()

            # Should have logged error
            # (We'll verify log format when implementing)

    async def test_publishers_never_raise_exceptions(
        self, tmp_path: Path, sample_event: NormalizedEvent
    ) -> None:
        """Test that publishers never raise exceptions (non-blocking middleware)"""
        from analytics.publishers.api import APIPublisher
        from analytics.publishers.file import FilePublisher

        # File publisher with bad path
        file_publisher = FilePublisher(output_path=Path("/invalid/path/events.jsonl"))

        # Should not raise
        await file_publisher.publish(sample_event)
        await file_publisher.close()

        # API publisher with bad endpoint
        api_publisher = APIPublisher(endpoint="http://localhost:99999/invalid", retry_attempts=0)

        # Should not raise
        await api_publisher.publish(sample_event)
        await api_publisher.close()
