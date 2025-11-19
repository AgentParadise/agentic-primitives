"""API publisher for HTTP POST delivery"""

import asyncio
import logging
from typing import Any

import httpx

from analytics.models.events import NormalizedEvent
from analytics.publishers.base import BasePublisher

logger = logging.getLogger(__name__)

# HTTP status code constants
HTTP_CLIENT_ERROR_MIN = 400
HTTP_CLIENT_ERROR_MAX = 500


class APIPublisher(BasePublisher):
    """Publisher that sends events to HTTP API endpoint

    Sends events as JSON via HTTP POST with retry logic and
    exponential backoff for transient failures.
    """

    def __init__(
        self, endpoint: str, timeout: int = 30, retry_attempts: int = 3
    ) -> None:
        """Initialize API publisher

        Args:
            endpoint: HTTP endpoint URL to POST events to
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for transient errors
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.client = httpx.AsyncClient(timeout=timeout)

    async def publish(self, event: NormalizedEvent) -> None:
        """Publish a single event to API endpoint

        Args:
            event: Normalized event to publish
        """
        # Serialize event to dict for JSON transmission
        event_data = event.model_dump(mode="json")

        await self._publish_with_retry(event_data, event)

    async def publish_batch(self, events: list[NormalizedEvent]) -> None:
        """Publish multiple events to API endpoint

        Args:
            events: List of normalized events to publish

        Note:
            Currently publishes events one-by-one. Could be optimized
            to send as batch if API supports it.
        """
        for event in events:
            await self.publish(event)

    async def _publish_with_retry(
        self, event_data: dict[str, Any], event: NormalizedEvent
    ) -> None:
        """Publish with retry logic and exponential backoff

        Args:
            event_data: Event data as dictionary
            event: Original event for logging context
        """
        last_error: Exception | None = None

        for attempt in range(self.retry_attempts + 1):
            try:
                response = await self.client.post(
                    self.endpoint,
                    json=event_data,
                    headers={"Content-Type": "application/json"},
                )

                # Raise for 4xx/5xx status codes
                response.raise_for_status()

                # Success!
                logger.debug(
                    f"Event published successfully to {self.endpoint}",
                    extra={
                        "event_type": event.event_type,
                        "session_id": event.session_id,
                        "status_code": response.status_code,
                    },
                )
                return

            except httpx.HTTPStatusError as e:
                # Don't retry on 4xx client errors (user error)
                if HTTP_CLIENT_ERROR_MIN <= e.response.status_code < HTTP_CLIENT_ERROR_MAX:
                    logger.warning(
                        f"Client error publishing event (no retry): {e}",
                        extra={
                            "event_type": event.event_type,
                            "session_id": event.session_id,
                            "status_code": e.response.status_code,
                            "endpoint": self.endpoint,
                        },
                    )
                    return

                # Retry on 5xx server errors
                last_error = e
                attempt_info = f"{attempt + 1}/{self.retry_attempts + 1}"
                logger.warning(
                    f"Server error publishing event (attempt {attempt_info}): {e}",
                    extra={
                        "event_type": event.event_type,
                        "session_id": event.session_id,
                        "status_code": e.response.status_code,
                        "endpoint": self.endpoint,
                    },
                )

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                # Retry on network/timeout errors
                last_error = e
                attempt_info = f"{attempt + 1}/{self.retry_attempts + 1}"
                logger.warning(
                    f"Network error publishing event (attempt {attempt_info}): {e}",
                    extra={
                        "event_type": event.event_type,
                        "session_id": event.session_id,
                        "endpoint": self.endpoint,
                        "error": str(e),
                    },
                )

            except Exception as e:
                # Catch-all for unexpected errors
                last_error = e
                logger.error(
                    f"Unexpected error publishing event: {e}",
                    extra={
                        "event_type": event.event_type,
                        "session_id": event.session_id,
                        "endpoint": self.endpoint,
                        "error": str(e),
                    },
                )
                return

            # Exponential backoff before retry (except on last attempt)
            if attempt < self.retry_attempts:
                delay = 2**attempt  # 1s, 2s, 4s, 8s...
                logger.debug(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)

        # All retries exhausted
        if last_error:
            logger.error(
                f"Failed to publish event after {self.retry_attempts + 1} attempts",
                extra={
                    "event_type": event.event_type,
                    "session_id": event.session_id,
                    "endpoint": self.endpoint,
                    "error": str(last_error),
                },
            )

    async def close(self) -> None:
        """Clean up HTTP client resources"""
        await self.client.aclose()

