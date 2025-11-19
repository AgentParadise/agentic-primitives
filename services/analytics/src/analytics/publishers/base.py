"""Base publisher interface for event delivery"""

from abc import ABC, abstractmethod

from analytics.models.events import NormalizedEvent


class BasePublisher(ABC):
    """Abstract base class for event publishers

    Publishers are responsible for delivering normalized events to
    various backends (files, APIs, databases, etc.). All publishers
    must be non-blocking and never raise exceptions, as analytics
    should not disrupt the main application.
    """

    @abstractmethod
    async def publish(self, event: NormalizedEvent) -> None:
        """Publish a single normalized event to the backend

        Args:
            event: Normalized event to publish

        Note:
            Implementations must never raise exceptions. Catch all
            errors internally and log them.
        """
        pass

    @abstractmethod
    async def publish_batch(self, events: list[NormalizedEvent]) -> None:
        """Publish multiple events (optional optimization)

        Args:
            events: List of normalized events to publish

        Note:
            Implementations may simply call publish() in a loop,
            or provide optimized batch delivery.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (file handles, HTTP clients, etc.)

        Should be called when the publisher is no longer needed.
        """
        pass

